# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from io import BytesIO
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image

from plane.app.serializers.issue import IssueAttachmentLiteSerializer, IssueAttachmentSerializer
from plane.db.models import FileAsset, Issue, Project, ProjectMember

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def local_services(settings, monkeypatch):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    monkeypatch.setattr("plane.middleware.logger.process_logs.delay", Mock())
    monkeypatch.setattr(default_storage, "url", lambda name: name)
    source = BytesIO()
    Image.new("RGB", (2400, 1600), "coral").save(source, format="PNG")
    storage = Mock()
    storage.return_value.aws_storage_bucket_name = "test-bucket"
    storage.return_value.s3_client.get_object.side_effect = lambda **kwargs: {
        "Body": BytesIO(source.getvalue()),
        "ContentLength": len(source.getvalue()),
    }
    monkeypatch.setattr("plane.utils.attachment_thumbnail.S3Storage", storage)
    return storage


@pytest.fixture
def asset(workspace, create_user):
    project = Project.objects.create(name="Thumbnails", identifier="THUMB", workspace=workspace)
    ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
    issue = Issue.objects.create(name="Many images", workspace=workspace, project=project)
    return FileAsset.objects.create(
        workspace=workspace,
        project=project,
        issue=issue,
        entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
        asset=f"{workspace.id}/image.png",
        attributes={"name": "image.png", "type": "image/png", "size": 20000},
        size=20000,
        is_uploaded=True,
        created_by=create_user,
    )


def test_returns_real_thumbnail_and_reuses_cache(session_client, asset, local_services):
    response = session_client.get(asset.thumbnail_url)
    assert response.status_code == 200
    assert response["Content-Type"] == "image/webp"
    assert response["Cache-Control"] == "private, max-age=300"
    assert "Cookie" in response["Vary"]
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == (640, 427)
    assert session_client.get(asset.thumbnail_url).content == response.content
    assert session_client.get(asset.thumbnail_url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code == 304
    local_services.return_value.s3_client.get_object.assert_called_once_with(Bucket="test-bucket", Key=asset.asset.name)
    local_services.return_value.upload_file.assert_not_called()


def test_source_version_changes_invalidate_cache(session_client, asset, local_services):
    assert session_client.get(asset.thumbnail_url).status_code == 200
    FileAsset.objects.filter(pk=asset.pk).update(storage_metadata={"ETag": "new-source-version"})
    assert session_client.get(asset.thumbnail_url).status_code == 200
    assert local_services.return_value.s3_client.get_object.call_count == 2


@pytest.mark.parametrize("serializer_class", [IssueAttachmentLiteSerializer, IssueAttachmentSerializer])
def test_serializers_expose_upload_time_and_thumbnail_without_reading_storage(asset, local_services, serializer_class):
    data = serializer_class(asset).data
    assert data["created_at"]
    assert data["thumbnail_url"] == asset.asset_url + "?thumbnail=1"
    local_services.assert_not_called()


def test_original_download_still_redirects_to_unmodified_source(session_client, asset, monkeypatch, local_services):
    signer = Mock()
    signer.return_value.generate_presigned_url.return_value = "https://storage.example.com/original.png"
    monkeypatch.setattr("plane.app.views.issue.attachment.S3Storage", signer)
    response = session_client.get(asset.asset_url)
    assert response.status_code == 302
    assert response["Location"] == "https://storage.example.com/original.png"
    signer.return_value.generate_presigned_url.assert_called_once_with(
        object_name=asset.asset.name, disposition="attachment", filename="image.png"
    )
    local_services.assert_not_called()


@pytest.mark.parametrize(
    "restriction", ["other_issue", "other_project", "deleted", "soft_deleted", "description", "unuploaded"]
)
def test_unavailable_assets_are_not_thumbnailed(session_client, asset, local_services, restriction):
    url = asset.thumbnail_url
    changes = {
        "deleted": {"is_deleted": True},
        "soft_deleted": {"deleted_at": timezone.now()},
        "description": {"entity_type": FileAsset.EntityTypeContext.ISSUE_DESCRIPTION},
        "unuploaded": {"is_uploaded": False},
    }.get(restriction, {})
    if restriction == "other_issue":
        changes["issue"] = Issue.objects.create(name="Other", workspace=asset.workspace, project=asset.project)
    if restriction == "other_project":
        changes["project"] = Project.objects.create(name="Other", identifier="OTHER", workspace=asset.workspace)
    FileAsset.objects.filter(pk=asset.pk).update(**changes)
    assert session_client.get(url).status_code == (400 if restriction == "unuploaded" else 404)
    local_services.assert_not_called()


def test_cached_thumbnail_still_requires_active_membership(session_client, api_client, asset, local_services):
    assert session_client.get(asset.thumbnail_url).status_code == 200
    ProjectMember.objects.filter(project=asset.project).update(is_active=False)
    assert session_client.get(asset.thumbnail_url).status_code == 403
    api_client.force_authenticate(user=None)
    assert api_client.get(asset.thumbnail_url).status_code in (401, 403)
    assert local_services.return_value.s3_client.get_object.call_count == 1


def test_invalid_image_never_redirects_to_original_and_is_negatively_cached(session_client, asset, local_services):
    body = BytesIO(b"not an image")
    local_services.return_value.s3_client.get_object.side_effect = None
    local_services.return_value.s3_client.get_object.return_value = {"Body": body}
    for _ in range(2):
        response = session_client.get(asset.thumbnail_url)
        assert response.status_code == 415
        assert "Location" not in response
    assert body.closed
    assert local_services.return_value.s3_client.get_object.call_count == 1


def test_storage_outage_can_recover_without_caching_failure(session_client, asset, local_services):
    get_object = local_services.return_value.s3_client.get_object
    original = get_object.side_effect
    get_object.side_effect = OSError("Storage unavailable")
    assert session_client.get(asset.thumbnail_url).status_code == 503
    get_object.side_effect = original
    assert session_client.get(asset.thumbnail_url).status_code == 200


def test_large_storage_object_is_not_downloaded(session_client, asset, local_services):
    body = Mock()
    local_services.return_value.s3_client.get_object.side_effect = None
    local_services.return_value.s3_client.get_object.return_value = {"Body": body, "ContentLength": 100 * 1024 * 1024}
    assert session_client.get(asset.thumbnail_url).status_code == 415
    body.read.assert_not_called()
    body.close.assert_called_once()
