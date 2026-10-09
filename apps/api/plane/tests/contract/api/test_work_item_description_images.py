# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import FileAsset, Issue, Project, ProjectMember, Workspace, WorkspaceMember

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def local_services(settings, monkeypatch):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    monkeypatch.setattr("plane.middleware.logger.process_logs.delay", Mock())
    monkeypatch.setattr("plane.db.mixins.soft_delete_related_objects.delay", Mock())
    storage = Mock()
    storage.return_value.signed_url_expiration = 3600
    storage.return_value.generate_presigned_url.return_value = "https://storage.example.com/image?signature=test"
    monkeypatch.setattr("plane.api.views.work_item_images.S3Storage", storage)
    return storage


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(
        name="Images", identifier="IMG", workspace=workspace, guest_view_all_features=False
    )
    ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
    return project


@pytest.fixture
def issue(workspace, project):
    return Issue.objects.create(name="Body images", workspace=workspace, project=project)


@pytest.fixture
def asset(workspace, project, issue):
    asset = FileAsset.objects.create(
        workspace=workspace,
        project=project,
        issue=issue,
        entity_type=FileAsset.EntityTypeContext.ISSUE_DESCRIPTION,
        asset=f"{workspace.id}/{uuid4()}.png",
        size=100,
        attributes={"name": "screen.png", "type": "image/png", "size": 100},
        is_uploaded=True,
    )
    Issue.objects.filter(pk=issue.id).update(description_html=f'<image-component src="{asset.id}"></image-component>')
    return asset


@pytest.fixture
def url(workspace, project, issue):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/description-images/"


def test_list_and_sign_editor_image_without_browser_session(api_key_client, url, asset, local_services):
    listing = api_key_client.get(url)
    assert listing.status_code == 200, listing.data
    assert listing.data == [
        {
            "image_index": 1,
            "asset_id": str(asset.id),
            "alt": "",
            "name": "screen.png",
            "content_type": "image/png",
            "size": 100.0,
            "available": True,
        }
    ]
    local_services.assert_not_called()
    signed = api_key_client.get(url + "1/")
    assert signed.status_code == 200, signed.data
    assert signed.data["download_url"] == "https://storage.example.com/image?signature=test"
    assert signed.data["expires_in"] == 3600
    assert signed["Cache-Control"] == "private, no-store"
    assert set(local_services.call_args.kwargs) == {"request"}
    local_services.return_value.generate_presigned_url.assert_called_once_with(
        object_name=asset.asset.name, filename="screen.png"
    )


@pytest.mark.parametrize("source_format", ["relative", "absolute", "attachment", "upper_uuid"])
def test_supported_image_references_keep_document_order(
    api_key_client, url, asset, issue, workspace, project, source_format
):
    prefix = f"/api/assets/v2/workspaces/{workspace.slug}/projects/{project.id}/"
    source = {
        "relative": prefix + f"{asset.id}/",
        "absolute": "http://testserver" + prefix + f"{asset.id}/?cache=1",
        "attachment": prefix + f"issues/{issue.id}/attachments/{asset.id}/",
        "upper_uuid": str(asset.id).upper(),
    }[source_format]
    Issue.objects.filter(pk=issue.id).update(
        description_html=(
            f'<img src="{source}" alt="First &amp; second"/><image-component src="{asset.id}"></image-component>'
        )
    )
    response = api_key_client.get(url)
    assert response.status_code == 200, response.data
    assert [i["image_index"] for i in response.data] == [1, 2]
    assert all(i["asset_id"] == str(asset.id) for i in response.data)
    assert response.data[0]["alt"] == "First & second"


def test_empty_body_has_no_images(api_key_client, url, local_services):
    response = api_key_client.get(url)
    assert response.status_code == 200 and response.data == []
    assert api_key_client.get(url + "1/").status_code == 404
    local_services.assert_not_called()


@pytest.mark.parametrize(
    "source",
    [
        "https://evil.example/{path}",
        "data:image/png;base64,AAAA",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "{foreign_path}",
        "",
        "not-a-uuid",
    ],
)
def test_unsupported_sources_are_not_signed(
    api_key_client, url, asset, issue, workspace, project, local_services, source
):
    source = source.format(
        path=f"api/assets/v2/workspaces/{workspace.slug}/projects/{project.id}/{asset.id}/",
        foreign_path=f"/api/assets/v2/workspaces/other/projects/{project.id}/{asset.id}/",
    )
    Issue.objects.filter(pk=issue.id).update(description_html=f'<img src="{source}">')
    listing = api_key_client.get(url)
    assert listing.status_code == 200 and listing.data[0]["available"] is False
    assert listing.data[0]["asset_id"] is None
    assert api_key_client.get(url + "1/").status_code == 404
    local_services.assert_not_called()


@pytest.mark.parametrize(
    "restriction",
    [
        "unuploaded",
        "deleted",
        "soft_deleted",
        "other_issue",
        "other_project",
        "other_workspace",
        "comment",
        "page",
        "avatar",
    ],
)
def test_unavailable_or_out_of_scope_assets_cannot_be_read(
    api_key_client, url, asset, issue, workspace, project, create_user, local_services, restriction
):
    changes = {
        "unuploaded": {"is_uploaded": False},
        "deleted": {"is_deleted": True},
        "soft_deleted": {"deleted_at": timezone.now()},
        "comment": {"entity_type": FileAsset.EntityTypeContext.COMMENT_DESCRIPTION},
        "page": {"entity_type": FileAsset.EntityTypeContext.PAGE_DESCRIPTION},
        "avatar": {"entity_type": FileAsset.EntityTypeContext.USER_AVATAR},
    }.get(restriction, {})
    if restriction == "other_issue":
        changes["issue"] = Issue.objects.create(name="Other", project=project, workspace=workspace)
    if restriction == "other_project":
        changes["project"] = Project.objects.create(name="Other", identifier="OTHER", workspace=workspace)
    if restriction == "other_workspace":
        changes["workspace"] = Workspace.objects.create(name="Other", slug="other", owner=create_user)
    FileAsset.objects.filter(pk=asset.id).update(**changes)
    listing = api_key_client.get(url)
    assert listing.status_code == 200 and not listing.data[0]["available"]
    assert api_key_client.get(url + "1/").status_code == 404
    local_services.assert_not_called()


@pytest.mark.parametrize("model", [WorkspaceMember, ProjectMember])
@pytest.mark.parametrize("method", ["deactivate", "remove"])
def test_removed_members_cannot_read_images(api_key_client, url, asset, create_user, local_services, model, method):
    members = model.objects.filter(member=create_user)
    if method == "remove":
        members.delete()
    else:
        members.update(is_active=False)
    assert api_key_client.get(url).status_code == 403
    assert api_key_client.get(url + "1/").status_code == 403
    local_services.assert_not_called()


def test_anonymous_browser_stays_unauthorized(url, asset, local_services):
    assert APIClient().get(url + "1/").status_code == 401
    local_services.assert_not_called()


def test_task_must_belong_to_route_project(api_key_client, url, asset, issue, workspace, project, local_services):
    other = Project.objects.create(name="Other", identifier="OTHER", workspace=workspace)
    Issue.objects.filter(pk=issue.id).update(project=other)
    assert api_key_client.get(url).status_code == 404
    local_services.assert_not_called()


@pytest.mark.parametrize("guest_can_read", [False, True])
def test_guest_visibility_is_preserved(api_key_client, url, asset, project, create_user, guest_can_read):
    ProjectMember.objects.filter(project=project, member=create_user).update(role=5)
    Project.objects.filter(pk=project.id).update(guest_view_all_features=guest_can_read)
    assert api_key_client.get(url + "1/").status_code == (200 if guest_can_read else 403)


def test_guest_real_creator_can_read_its_virtual_authored_task(api_key_client, url, asset, issue, project, create_user):
    ProjectMember.objects.filter(project=project, member=create_user).update(role=5)
    Issue.objects.filter(pk=issue.id).update(created_by_actor=create_user)
    assert api_key_client.get(url + "1/").status_code == 200


@pytest.mark.parametrize("index", [0, 2, 999])
def test_invalid_index_does_not_sign(api_key_client, url, asset, local_services, index):
    assert api_key_client.get(url + f"{index}/").status_code == 404
    local_services.assert_not_called()


def test_storage_signing_failure_is_explicit(api_key_client, url, asset, local_services):
    local_services.return_value.generate_presigned_url.return_value = None
    assert api_key_client.get(url + "1/").status_code == 503
