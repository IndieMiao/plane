# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from plane.db.models import FileAsset, ProjectMember, User, Workspace, WorkspaceMember
from plane.tests.contract.api.test_virtual_users import local_services  # noqa: F401
from plane.tests.contract.api.test_virtual_users import project as project_fixture
from plane.tests.contract.api.test_virtual_users import virtual_api as virtual_api_fixture

project = project_fixture
virtual_api = virtual_api_fixture

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def avatar_file(format="PNG", size=(640, 480)):
    image = BytesIO()
    Image.new("RGB", size, "#234567").save(image, format=format)
    return SimpleUploadedFile("avatar.png", image.getvalue(), content_type="image/png")


@pytest.fixture
def storage(monkeypatch):
    storage = Mock()
    uploaded = []

    def upload(image, key, **kwargs):
        uploaded.append((key, image.read(), kwargs))
        return True

    storage.upload_file.side_effect = upload
    storage.uploaded = uploaded
    monkeypatch.setattr("plane.app.serializers.virtual_user.S3Storage", Mock(return_value=storage))
    return storage


@pytest.fixture
def profile(virtual_api, project):
    client, url = virtual_api
    response = client.post(
        url, {"display_name": "Agent", "job_titles": ["Artist"], "project_ids": [str(project.id)]}, format="json"
    )
    assert response.status_code == 201, response.data
    return User.objects.get(pk=response.data["id"])


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP", "GIF"])
def test_create_with_avatar_and_arrays(virtual_api, project, workspace, create_user, storage, format):
    client, url = virtual_api
    response = client.post(
        url,
        {
            "data": json.dumps(
                {"display_name": "Hero", "project_ids": [str(project.id)], "job_titles": ["Artist", "Designer"]}
            ),
            "avatar": avatar_file(format),
        },
        format="multipart",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(pk=response.data["id"])
    assert user.avatar_url == response.data["avatar_url"]
    assert user.avatar_asset.user_id == user.id and user.avatar_asset.workspace_id == workspace.id
    assert user.avatar_asset.created_by_id == create_user.id
    assert user.avatar_asset.is_uploaded and user.avatar_asset.entity_type == "USER_AVATAR"
    assert ProjectMember.objects.filter(project=project, member=user).exists()
    assert response.data["job_titles"] == ["Artist", "Designer"]
    assert not user.is_active and not user.has_usable_password()
    normalized = Image.open(BytesIO(storage.uploaded[0][1]))
    assert normalized.format == "PNG" and normalized.size == (512, 384)


def test_edit_name_avatar_and_workspace_jobs(virtual_api, profile, storage, workspace, create_user, project):
    client, url = virtual_api
    original_id, original_email, original_password = profile.id, profile.email, profile.password
    response = client.patch(
        f"{url}{profile.id}/",
        {
            "data": json.dumps({"display_name": "新名字", "job_titles": ["Developer", "Architect"]}),
            "avatar": avatar_file(),
        },
        format="multipart",
    )
    assert response.status_code == 200, response.data
    profile.refresh_from_db()
    assert profile.display_name == profile.first_name == "新名字" and profile.last_name == ""
    assert profile.id == original_id and profile.email == original_email and profile.password == original_password
    assert not profile.is_active and profile.is_virtual
    assert not profile.is_superuser and not profile.is_staff
    assert response.data["job_titles"] == ["Developer", "Architect"]
    assert WorkspaceMember.objects.get(workspace=workspace, member=profile).job_titles == ["Developer", "Architect"]
    assert ProjectMember.objects.filter(project=project, member=profile).count() == 1
    assert response.data["avatar_url"] == profile.avatar_asset.asset_url
    assert profile.avatar_asset.created_by_id == create_user.id


def test_name_only_preserves_avatar_and_jobs(virtual_api, profile, storage, workspace):
    client, url = virtual_api
    User.objects.filter(pk=profile.id).update(avatar="https://example.com/old.png")
    response = client.patch(f"{url}{profile.id}/", {"display_name": "Renamed"}, format="json")
    assert response.status_code == 200, response.data
    profile.refresh_from_db()
    assert profile.avatar == "https://example.com/old.png"
    assert response.data["job_titles"] == ["Artist"]
    assert WorkspaceMember.objects.get(workspace=workspace, member=profile).job_titles == ["Artist"]
    storage.upload_file.assert_not_called()


def test_replacing_and_removing_avatar_does_not_delete_previous_asset(virtual_api, profile, storage):
    client, url = virtual_api
    detail = f"{url}{profile.id}/"
    created = client.patch(detail, {"data": "{}", "avatar": avatar_file()}, format="multipart")
    assert created.status_code == 200, created.data
    profile.refresh_from_db()
    previous = profile.avatar_asset_id
    replaced = client.patch(detail, {"data": "{}", "avatar": avatar_file()}, format="multipart")
    assert replaced.status_code == 200, replaced.data
    profile.refresh_from_db()
    assert profile.avatar_asset_id != previous
    assert FileAsset.objects.filter(pk=previous).exists()
    removed = client.patch(detail, {"remove_avatar": True}, format="json")
    assert removed.status_code == 200, removed.data
    profile.refresh_from_db()
    assert profile.avatar_asset_id is None and profile.avatar == "" and profile.avatar_url is None
    assert FileAsset.objects.filter(pk=previous).exists()
    storage.delete_files.assert_not_called()


def test_clearing_jobs_in_multipart_preserves_other_workspaces(virtual_api, profile, workspace, create_user, storage):
    client, url = virtual_api
    other = Workspace.objects.create(name="Other", slug="other", owner=create_user)
    WorkspaceMember.objects.create(workspace=other, member=profile, job_titles=["Other role"])
    response = client.patch(
        f"{url}{profile.id}/", {"data": json.dumps({"job_titles": []}), "avatar": avatar_file()}, format="multipart"
    )
    assert response.status_code == 200, response.data
    assert response.data["job_titles"] == []
    assert WorkspaceMember.objects.get(workspace=workspace, member=profile).job_titles == []
    assert WorkspaceMember.objects.get(workspace=other, member=profile).job_titles == ["Other role"]


@pytest.mark.parametrize("role", [5, 15])
def test_non_admin_cannot_edit_even_as_project_admin(virtual_api, profile, workspace, create_user, storage, role):
    client, url = virtual_api
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=role)
    response = client.patch(
        f"{url}{profile.id}/",
        {"data": json.dumps({"display_name": "No access"}), "avatar": avatar_file()},
        format="multipart",
    )
    assert response.status_code == 403, response.data
    profile.refresh_from_db()
    assert profile.display_name == "Agent" and profile.avatar_asset_id is None
    storage.upload_file.assert_not_called()


@pytest.mark.parametrize("target", ["real", "other_workspace", "inactive", "removed", "unknown"])
def test_only_active_virtual_members_in_workspace_can_be_edited(
    virtual_api, profile, create_user, workspace, target, storage
):
    client, url = virtual_api
    user_id = profile.id
    if target == "real":
        user_id = create_user.id
    elif target == "unknown":
        user_id = uuid4()
    elif target == "inactive":
        WorkspaceMember.objects.filter(member=profile, workspace=workspace).update(is_active=False)
    else:
        WorkspaceMember.objects.filter(member=profile, workspace=workspace).delete()
        if target == "other_workspace":
            other = Workspace.objects.create(name="Other", slug="other", owner=create_user)
            WorkspaceMember.objects.create(workspace=other, member=profile)
    response = client.patch(f"{url}{user_id}/", {"display_name": "Forbidden"}, format="json")
    assert response.status_code == 404, response.data
    storage.upload_file.assert_not_called()


@pytest.mark.parametrize("invalid", ["text", "too_large", "dimensions", "svg"])
def test_invalid_images_rejected_before_creation(virtual_api, storage, invalid):
    client, url = virtual_api
    if invalid == "too_large":
        image = avatar_file()
        image = SimpleUploadedFile("huge.png", image.read() + b"x" * (5 * 1024 * 1024), "image/png")
    elif invalid == "dimensions":
        image = avatar_file(size=(4100, 4000))
    elif invalid == "svg":
        image = SimpleUploadedFile("avatar.svg", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "image/svg+xml")
    else:
        image = SimpleUploadedFile("avatar.png", b"not an image", "image/png")
    before = User.objects.count()
    response = client.post(url, {"data": json.dumps({"display_name": "Invalid"}), "avatar": image}, format="multipart")
    assert response.status_code == (413 if invalid == "too_large" else 400), response.content
    if invalid != "too_large":
        assert "avatar" in response.data
    assert User.objects.count() == before
    storage.upload_file.assert_not_called()


@pytest.mark.parametrize("editing", [False, True])
def test_storage_failure_rolls_back_profile_and_memberships(virtual_api, profile, workspace, storage, editing):
    client, url = virtual_api
    before = User.objects.count()
    storage.upload_file.side_effect = None
    storage.upload_file.return_value = False
    action = client.patch if editing else client.post
    response = action(
        f"{url}{profile.id}/" if editing else url,
        {"data": json.dumps({"display_name": "Rollback", "job_titles": ["Different role"]}), "avatar": avatar_file()},
        format="multipart",
    )
    assert response.status_code == 400, response.data
    assert User.objects.count() == before and FileAsset.objects.count() == 0
    profile.refresh_from_db()
    assert profile.display_name == "Agent"
    assert WorkspaceMember.objects.get(workspace=workspace, member=profile).job_titles == ["Artist"]
    storage.delete_files.assert_called_once()


@pytest.mark.parametrize("payload", ["not json", "[]", "null"])
def test_rejects_malformed_multipart(virtual_api, profile, storage, payload):
    client, url = virtual_api
    response = client.patch(f"{url}{profile.id}/", {"data": payload, "avatar": avatar_file()}, format="multipart")
    assert response.status_code == 400, response.data
    storage.upload_file.assert_not_called()


def test_profile_edit_cannot_change_login_permissions_or_project_memberships(
    virtual_api, profile, create_user, project, storage
):
    client, url = virtual_api
    response = client.patch(
        f"{url}{profile.id}/",
        {
            "display_name": "Renamed",
            "email": "other@example.com",
            "password": "unsafe",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "is_virtual": False,
            "avatar_asset_id": str(uuid4()),
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    profile.refresh_from_db()
    assert profile.email.endswith("@users.invalid") and not profile.has_usable_password()
    assert profile.is_virtual and not profile.is_active and not profile.is_staff and not profile.is_superuser
    assert profile.avatar_asset_id is None
    response = client.patch(f"{url}{profile.id}/", {"project_ids": []}, format="json")
    assert response.status_code == 400, response.data
    assert ProjectMember.objects.filter(project=project, member=profile).exists()


def test_upload_and_remove_cannot_be_combined(virtual_api, profile, storage):
    client, url = virtual_api
    response = client.patch(
        f"{url}{profile.id}/",
        {"data": json.dumps({"remove_avatar": True}), "avatar": avatar_file()},
        format="multipart",
    )
    assert response.status_code == 400, response.data
    storage.upload_file.assert_not_called()
