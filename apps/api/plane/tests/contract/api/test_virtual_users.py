# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory

from plane.app.serializers.user import UserSerializer
from plane.app.serializers.virtual_user import VirtualUserSerializer
from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AuthenticationException
from plane.authentication.utils.login import user_login
from plane.db.models import (
    APIToken,
    Issue,
    IssueAssignee,
    Project,
    ProjectMember,
    ProjectUserProperty,
    User,
    UserNotificationPreference,
    Workspace,
    WorkspaceMember,
    WorkspaceJobTitle,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def local_services(settings, monkeypatch):
    settings.WEB_URL = "http://testserver"
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    monkeypatch.setattr("plane.middleware.logger.process_logs.delay", lambda *args, **kwargs: None)
    monkeypatch.setattr("plane.api.views.issue.issue_activity.delay", lambda *args, **kwargs: None)
    monkeypatch.setattr("plane.api.views.issue.model_activity.delay", lambda *args, **kwargs: None)


@pytest.fixture(params=["session", "api_key"])
def virtual_api(request, workspace):
    if request.param == "session":
        return request.getfixturevalue("session_client"), f"/api/workspaces/{workspace.slug}/virtual-users/"
    return request.getfixturevalue("api_key_client"), f"/api/v1/workspaces/{workspace.slug}/virtual-users/"


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Development", identifier="DEV", workspace=workspace)
    ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
    return project


def test_admin_creates_assignable_identity(virtual_api, workspace, project):
    client, url = virtual_api
    response = client.post(
        url, {"display_name": "  开发 Agent  ", "project_ids": [str(project.id), str(project.id)]}, format="json"
    )

    assert response.status_code == 201, response.data
    user = User.objects.get(pk=response.data["id"])
    assert response.data["is_virtual"] is True
    assert user.display_name == "开发 Agent"
    assert not user.is_active
    assert not user.has_usable_password()
    assert not user.is_bot
    assert not user.is_staff and not user.is_superuser
    assert WorkspaceMember.objects.filter(workspace=workspace, member=user, role=15, is_active=True).exists()
    assert ProjectMember.objects.filter(project=project, member=user, role=15, is_active=True).count() == 1
    assert ProjectUserProperty.objects.filter(project=project, user=user).exists()
    preferences = UserNotificationPreference.objects.get(user=user)
    assert not any(
        [
            preferences.property_change,
            preferences.state_change,
            preferences.comment,
            preferences.mention,
            preferences.issue_completed,
        ]
    )


def test_project_selection_is_optional_and_names_need_not_be_unique(virtual_api, workspace):
    client, url = virtual_api
    first = client.post(url, {"display_name": "Reviewer"}, format="json")
    second = client.post(url, {"display_name": "Reviewer"}, format="json")
    assert first.status_code == second.status_code == 201
    assert first.data["id"] != second.data["id"]
    assert not ProjectMember.objects.filter(member_id=first.data["id"]).exists()
    assert WorkspaceMember.objects.filter(workspace=workspace, member_id=first.data["id"]).exists()


@pytest.mark.parametrize("role", [5, 15])
def test_only_admin_can_create(virtual_api, workspace, create_user, role):
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=role)
    client, url = virtual_api
    response = client.post(url, {"display_name": "Unauthorized"}, format="json")
    assert response.status_code == 403
    assert not User.objects.filter(is_virtual=True).exists()


def test_inactive_admin_cannot_create(virtual_api, workspace, create_user):
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(is_active=False)
    client, url = virtual_api
    assert client.post(url, {"display_name": "Unauthorized"}, format="json").status_code == 403
    assert not User.objects.filter(is_virtual=True).exists()


def test_rejects_cross_workspace_projects_atomically(virtual_api, create_user, project):
    other_workspace = Workspace.objects.create(name="Other", slug="other", owner=create_user)
    other_project = Project.objects.create(name="Private", identifier="PRV", workspace=other_workspace)
    client, url = virtual_api
    response = client.post(
        url,
        {"display_name": "Agent", "project_ids": [str(project.id), str(other_project.id)]},
        format="json",
    )
    assert response.status_code == 400
    assert "project_ids" in response.data
    assert not User.objects.filter(is_virtual=True).exists()


def test_admin_cannot_inject_members_into_unjoined_project(virtual_api, workspace):
    project = Project.objects.create(name="Private", identifier="PRV", workspace=workspace, network=0)
    client, url = virtual_api
    response = client.post(url, {"display_name": "Agent", "project_ids": [str(project.id)]}, format="json")
    assert response.status_code == 400
    assert not User.objects.filter(is_virtual=True).exists()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": "  "},
        {"display_name": "x" * 256},
        {"display_name": "Agent", "project_ids": ["invalid"]},
        {"display_name": "Agent", "project_ids": [str(uuid4())]},
    ],
)
def test_invalid_creation_leaves_no_user(virtual_api, payload):
    client, url = virtual_api
    response = client.post(url, payload, format="json")
    assert response.status_code == 400, response.data
    assert not User.objects.filter(is_virtual=True).exists()


def test_untrusted_fields_cannot_create_login_or_privileged_user(virtual_api):
    client, url = virtual_api
    response = client.post(
        url,
        {
            "display_name": "Agent",
            "email": "real@example.com",
            "password": "secret-password",
            "is_active": True,
            "is_virtual": False,
            "is_superuser": True,
            "role": 20,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(pk=response.data["id"])
    assert user.email.endswith("@users.invalid")
    assert user.is_virtual and not user.is_active and not user.is_superuser
    assert not user.has_usable_password()
    assert user.member_workspace.get().role == 15


def test_list_is_scoped_and_hides_removed_identities(virtual_api, workspace, create_user):
    client, url = virtual_api
    created = client.post(url, {"display_name": "Visible"}, format="json")
    removed = client.post(url, {"display_name": "Removed"}, format="json")
    WorkspaceMember.objects.filter(workspace=workspace, member_id=removed.data["id"]).update(is_active=False)
    other = Workspace.objects.create(name="Other", slug="other", owner=create_user)
    outsider = User.objects.create(
        username="outsider", email="outsider@users.invalid", display_name="Outsider", is_virtual=True
    )
    WorkspaceMember.objects.create(workspace=other, member=outsider, role=15)
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)

    response = client.get(url)
    assert response.status_code == 200
    assert [row["id"] for row in response.data] == [created.data["id"]]


def test_creation_rolls_back_if_project_membership_fails(workspace, create_user, project):
    request = APIRequestFactory().post("/")
    request.user = create_user
    serializer = VirtualUserSerializer(
        data={
            "display_name": "Rollback",
            "project_ids": [str(project.id)],
            "job_titles": ["Rollback title", "Second title"],
        },
        context={"workspace": workspace, "request": request},
    )
    serializer.is_valid(raise_exception=True)
    with patch.object(ProjectMember.objects, "create", side_effect=RuntimeError("membership failure")):
        with pytest.raises(RuntimeError):
            serializer.save()
    assert not User.objects.filter(is_virtual=True).exists()
    assert WorkspaceMember.objects.filter(workspace=workspace).count() == 1
    assert not WorkspaceJobTitle.objects.filter(workspace=workspace).exists()


def test_virtual_user_is_listed_and_can_be_assigned(api_key_client, workspace, project):
    created = api_key_client.post(
        f"/api/v1/workspaces/{workspace.slug}/virtual-users/",
        {"display_name": "Development Agent", "project_ids": [str(project.id)]},
        format="json",
    )
    user_id = created.data["id"]
    members = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/members/")
    assert any(member["id"] == user_id and member["is_virtual"] for member in members.data)

    issue_url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
    response = api_key_client.post(issue_url, {"name": "Agent task", "assignees": [user_id]}, format="json")
    assert response.status_code == 201, response.data
    issue = Issue.objects.get(pk=response.data["id"])
    assert IssueAssignee.objects.filter(issue=issue, assignee_id=user_id).exists()
    assert str(issue.created_by_id) != user_id

    cleared = api_key_client.patch(f"{issue_url}{issue.id}/", {"assignees": []}, format="json")
    assert cleared.status_code == 200, cleared.data
    assert not IssueAssignee.objects.filter(issue=issue).exists()
    reassigned = api_key_client.patch(f"{issue_url}{issue.id}/", {"assignees": [user_id]}, format="json")
    assert reassigned.status_code == 200, reassigned.data
    assert IssueAssignee.objects.filter(issue=issue, assignee_id=user_id).exists()


def test_virtual_identity_cannot_log_in_or_authenticate_with_api_key(virtual_api):
    client, url = virtual_api
    created = client.post(url, {"display_name": "No login"}, format="json")
    user = User.objects.get(pk=created.data["id"])
    request = APIRequestFactory().get("/")
    with pytest.raises(AuthenticationException):
        user_login(request, user)
    adapter = Adapter(request=request, provider="email")
    with pytest.raises(AuthenticationException):
        adapter.save_user_data(user)
    user.refresh_from_db()
    assert not user.is_active

    token = APIToken.objects.create(user=user, label="Invalid virtual token", token="virtual-token")
    anonymous = APIClient()
    anonymous.credentials(HTTP_X_API_KEY=token.token)
    assert anonymous.get("/api/v1/users/me/").status_code in [401, 403]


def test_normal_user_cannot_turn_themselves_virtual(create_user):
    serializer = UserSerializer(
        create_user,
        data={"is_virtual": True, "job_title": "Unauthorized title", "job_titles": ["Unauthorized title"]},
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    create_user.refresh_from_db()
    assert not create_user.is_virtual
    assert create_user.job_title == ""
    assert create_user.job_titles == []


def test_default_job_titles(virtual_api):
    client, url = virtual_api
    response = client.get(url.replace("/virtual-users/", "/virtual-user-job-titles/"))
    assert response.status_code == 200, response.data
    assert response.data == [
        "高级UI设计师",
        "高级游戏策划",
        "高级项目经理",
        "高级游戏开发",
        "游戏主程",
        "架构师",
        "IT运维",
        "高级运营策划",
        "高级产品经理",
    ]


def test_custom_job_titles_persist_only_in_current_workspace(virtual_api, workspace, create_user):
    client, url = virtual_api
    url = url.replace("/virtual-users/", "/virtual-user-job-titles/")
    created = client.post(url, {"name": "  高级测试工程师  "}, format="json")
    assert created.status_code == 201, created.data
    assert created.data == {"name": "高级测试工程师"}
    assert "高级测试工程师" in client.get(url).data
    assert WorkspaceJobTitle.objects.filter(workspace=workspace, name="高级测试工程师").exists()
    other = Workspace.objects.create(name="Other titles", slug="other-titles", owner=create_user)
    WorkspaceMember.objects.create(workspace=other, member=create_user, role=20)
    assert "高级测试工程师" not in client.get(url.replace(workspace.slug, other.slug)).data


def test_job_title_duplicates_are_idempotent(virtual_api, workspace):
    client, url = virtual_api
    url = url.replace("/virtual-users/", "/virtual-user-job-titles/")
    assert client.post(url, {"name": "Technical Artist"}, format="json").status_code == 201
    repeated = client.post(url, {"name": " technical artist "}, format="json")
    assert repeated.status_code == 200
    assert repeated.data == {"name": "Technical Artist"}
    default = client.post(url, {"name": "it运维"}, format="json")
    assert default.status_code == 200
    assert default.data == {"name": "IT运维"}
    assert WorkspaceJobTitle.objects.filter(workspace=workspace).count() == 1


@pytest.mark.parametrize("name", ["", "  ", "x" * 256, None, {"name": "nested"}])
def test_invalid_job_titles_are_rejected(virtual_api, name):
    client, url = virtual_api
    response = client.post(url.replace("/virtual-users/", "/virtual-user-job-titles/"), {"name": name}, format="json")
    assert response.status_code == 400
    assert not WorkspaceJobTitle.objects.exists()


@pytest.mark.parametrize("role", [5, 15])
def test_only_admin_can_add_job_titles(virtual_api, workspace, create_user, role):
    client, url = virtual_api
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=role)
    url = url.replace("/virtual-users/", "/virtual-user-job-titles/")
    assert client.post(url, {"name": "Forbidden"}, format="json").status_code == 403
    assert client.get(url).status_code == (200 if role == 15 else 403)
    assert not WorkspaceJobTitle.objects.exists()


@pytest.mark.parametrize("job_title", ["架构师", "资深测试专家"])
def test_virtual_user_job_title_visible_in_members_and_api(virtual_api, workspace, create_user, job_title):
    client, url = virtual_api
    response = client.post(url, {"display_name": "Agent with role", "job_title": f"  {job_title}  "}, format="json")
    assert response.status_code == 201, response.data
    assert response.data["job_title"] == job_title
    assert response.data["job_titles"] == [job_title]
    user = User.objects.get(pk=response.data["id"])
    assert user.job_title == job_title
    assert user.member_workspace.get().role == 15
    assert client.get(url).data[0]["job_title"] == job_title
    assert job_title in client.get(url.replace("/virtual-users/", "/virtual-user-job-titles/")).data

    session = APIClient()
    session.force_authenticate(create_user)
    members = session.get(f"/api/workspaces/{workspace.slug}/members/")
    assert members.status_code == 200
    virtual = next(row["member"] for row in members.data if str(row["member"]["id"]) == str(user.id))
    assert virtual["job_title"] == job_title
    assert virtual["job_titles"] == [job_title]


def test_old_create_payload_keeps_job_title_optional(virtual_api):
    client, url = virtual_api
    response = client.post(url, {"display_name": "Legacy client"}, format="json")
    assert response.status_code == 201
    assert response.data["job_title"] == ""
    assert response.data["job_titles"] == []


def test_multiple_job_titles_saved_deduplicated_and_returned(virtual_api, workspace, create_user):
    client, url = virtual_api
    response = client.post(
        url,
        {"display_name": "Multi-role Agent", "job_titles": [" 架构师 ", "it运维", "IT运维", "技术美术", "架构师"]},
        format="json",
    )
    assert response.status_code == 201, response.data
    expected = ["架构师", "IT运维", "技术美术"]
    assert response.data["job_titles"] == expected
    assert response.data["job_title"] == expected[0]
    user = User.objects.get(pk=response.data["id"])
    assert user.job_titles == expected
    assert user.member_workspace.get().role == 15
    assert WorkspaceJobTitle.objects.filter(workspace=workspace, name="技术美术").count() == 1
    assert client.get(url).data[0]["job_titles"] == expected
    session = APIClient()
    session.force_authenticate(create_user)
    members = session.get(f"/api/workspaces/{workspace.slug}/members/")
    member = next(row["member"] for row in members.data if str(row["member"]["id"]) == str(user.id))
    assert member["job_titles"] == expected


def test_explicit_empty_job_titles_override_legacy_field(virtual_api):
    client, url = virtual_api
    response = client.post(
        url, {"display_name": "No roles", "job_title": "Ignore this legacy title", "job_titles": []}, format="json"
    )
    assert response.status_code == 201
    assert response.data["job_titles"] == []
    assert response.data["job_title"] == ""
    assert not WorkspaceJobTitle.objects.exists()


@pytest.mark.parametrize("titles", ["架构师", None, [""], ["  "], [None], [{}], ["x" * 256], ["Title"] * 101])
def test_invalid_job_title_arrays_are_rejected(virtual_api, titles):
    client, url = virtual_api
    response = client.post(url, {"display_name": "Bad roles", "job_titles": titles}, format="json")
    assert response.status_code == 400
    assert not User.objects.filter(is_virtual=True).exists()
    assert not WorkspaceJobTitle.objects.exists()


def test_single_title_written_by_old_container_remains_visible(virtual_api, workspace):
    user = User.objects.create(
        email="legacy-role@test.invalid",
        username="legacy-role",
        is_virtual=True,
        is_active=False,
        job_title="开发, 运维",
        job_titles=[],
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    client, url = virtual_api
    response = client.get(url)
    assert response.status_code == 200
    assert response.data[0]["job_titles"] == ["开发, 运维"]


def test_long_user_job_title_is_rejected(virtual_api):
    client, url = virtual_api
    response = client.post(url, {"display_name": "Agent", "job_title": "x" * 256}, format="json")
    assert response.status_code == 400
    assert not User.objects.filter(is_virtual=True).exists()
    assert not WorkspaceJobTitle.objects.exists()


def test_app_members_assignment_and_removal(session_client, workspace, project, monkeypatch):
    monkeypatch.setattr("plane.app.views.issue.base.issue_description_version_task.delay", lambda *args, **kwargs: None)
    monkeypatch.setattr("plane.db.mixins.soft_delete_related_objects.delay", lambda *args, **kwargs: None)
    base_url = f"/api/workspaces/{workspace.slug}"
    created = session_client.post(
        f"{base_url}/virtual-users/",
        {"display_name": "App Agent", "project_ids": [str(project.id)]},
        format="json",
    )
    assert created.status_code == 201, created.data
    user_id = created.data["id"]
    members = session_client.get(f"{base_url}/members/")
    assert members.status_code == 200, members.data
    assert any(row["member"]["id"] == user_id and row["member"]["is_virtual"] for row in members.data)
    project_members = session_client.get(f"{base_url}/projects/{project.id}/members/")
    assert project_members.status_code == 200, project_members.data
    assert any(str(row["member"]) == str(user_id) for row in project_members.data)

    response = session_client.post(
        f"{base_url}/projects/{project.id}/issues/",
        {"name": "Assigned from UI", "assignee_ids": [user_id]},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert IssueAssignee.objects.filter(issue_id=response.data["id"], assignee_id=user_id).exists()

    membership = WorkspaceMember.objects.get(workspace=workspace, member_id=user_id)
    removed = session_client.delete(f"{base_url}/members/{membership.id}/")
    assert removed.status_code == 204, removed.data
    assert not ProjectMember.objects.filter(project=project, member_id=user_id, is_active=True).exists()
    assert session_client.get(f"{base_url}/virtual-users/").data == []


def test_unauthenticated_creation_is_denied(workspace):
    client = APIClient()
    for prefix in ["/api", "/api/v1"]:
        response = client.post(
            f"{prefix}/workspaces/{workspace.slug}/virtual-users/", {"display_name": "Unauthorized"}, format="json"
        )
        assert response.status_code in [401, 403]
    assert not User.objects.filter(is_virtual=True).exists()


def _job_titles_url(virtual_url, user_id):
    return virtual_url.replace("virtual-users/", f"members/{user_id}/job-titles/")


@pytest.mark.parametrize("is_virtual", [True, False])
def test_admin_can_edit_and_clear_member_titles(virtual_api, workspace, is_virtual, create_user):
    client, url = virtual_api
    user = User.objects.create(
        username="editable",
        email="editable@test.invalid",
        is_virtual=is_virtual,
        job_title="旧岗位",
        job_titles=["旧岗位"],
    )
    membership = WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    edit_url = _job_titles_url(url, user.id)
    response = client.patch(edit_url, {"job_titles": [" 架构师 ", "IT运维", "it运维", "自定义岗位"]}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["job_titles"] == ["架构师", "IT运维", "自定义岗位"]
    assert response.data["job_title"] == "架构师"
    membership.refresh_from_db()
    assert membership.job_titles == response.data["job_titles"]
    assert membership.updated_by_id == create_user.id
    assert membership.role == 15
    user.refresh_from_db()
    assert user.job_titles == ["旧岗位"]
    assert WorkspaceJobTitle.objects.filter(workspace=workspace, name="自定义岗位").exists()
    response = client.patch(edit_url, {"job_titles": []}, format="json")
    assert response.status_code == 200
    assert response.data["job_titles"] == [] and response.data["job_title"] == ""
    session = APIClient()
    session.force_authenticate(create_user)
    members = session.get(f"/api/workspaces/{workspace.slug}/members/").data
    listed = next(row["member"] for row in members if str(row["member"]["id"]) == str(user.id))
    assert listed["job_titles"] == [] and listed["job_title"] == ""


def test_admin_can_edit_own_job_titles(virtual_api, create_user):
    client, url = virtual_api
    response = client.patch(_job_titles_url(url, create_user.id), {"job_titles": ["架构师"]}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["job_titles"] == ["架构师"]


def test_edit_is_scoped_to_workspace_and_visible_in_project_api(virtual_api, workspace, create_user, project):
    client, url = virtual_api
    created = client.post(
        url,
        {"display_name": "Scoped roles", "job_titles": ["游戏主程"], "project_ids": [str(project.id)]},
        format="json",
    )
    user = User.objects.get(id=created.data["id"])
    other = Workspace.objects.create(name="Other workspace", slug="other-jobs", owner=create_user)
    WorkspaceMember.objects.create(workspace=other, member=create_user, role=20)
    WorkspaceMember.objects.create(workspace=other, member=user, role=15)
    response = client.patch(_job_titles_url(url, user.id), {"job_titles": ["架构师", "本工作区自定义"]}, format="json")
    assert response.status_code == 200, response.data
    assert client.get(url).data[0]["job_titles"] == ["架构师", "本工作区自定义"]
    assert client.get(url.replace(workspace.slug, other.slug)).data[0]["job_titles"] == ["游戏主程"]
    assert not WorkspaceJobTitle.objects.filter(workspace=other, name="本工作区自定义").exists()
    token = APIToken.objects.create(user=create_user, label="Scoped test", token=f"scope-{uuid4()}")
    public = APIClient()
    public.credentials(HTTP_X_API_KEY=token.token)
    for path in [
        f"/api/v1/workspaces/{workspace.slug}/members/",
        f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/members/",
    ]:
        listed = public.get(path)
        assert listed.status_code == 200, listed.data
        member = next(row for row in listed.data if str(row["id"]) == str(user.id))
        assert member["job_titles"] == ["架构师", "本工作区自定义"]


@pytest.mark.parametrize("role", [5, 15])
def test_non_admin_cannot_edit_titles(virtual_api, workspace, create_user, role):
    client, url = virtual_api
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=role)
    response = client.patch(_job_titles_url(url, create_user.id), {"job_titles": ["Forbidden"]}, format="json")
    assert response.status_code == 403
    assert not WorkspaceJobTitle.objects.filter(name="Forbidden").exists()


@pytest.mark.parametrize("target_kind", ["outsider", "removed", "bot"])
def test_invalid_target_cannot_be_edited(virtual_api, workspace, target_kind):
    client, url = virtual_api
    user = User.objects.create(
        username="invalid-target", email="invalid-target@test.invalid", is_bot=target_kind == "bot"
    )
    if target_kind != "outsider":
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15, is_active=target_kind != "removed")
    response = client.patch(_job_titles_url(url, user.id), {"job_titles": ["Forbidden"]}, format="json")
    assert response.status_code == 404
    assert not WorkspaceJobTitle.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"job_title": "Wrong field"},
        {"job_titles": "string"},
        {"job_titles": [""]},
        {"job_titles": ["x" * 256]},
        {"job_titles": ["x"] * 101},
    ],
)
def test_invalid_edit_payload_preserves_previous_titles(virtual_api, create_user, workspace, payload):
    client, url = virtual_api
    membership = WorkspaceMember.objects.get(workspace=workspace, member=create_user)
    membership.job_titles = ["Existing"]
    membership.save()
    response = client.patch(_job_titles_url(url, create_user.id), payload, format="json")
    assert response.status_code == 400, response.data
    membership.refresh_from_db()
    assert membership.job_titles == ["Existing"]
    assert not WorkspaceJobTitle.objects.exists()


def test_edit_cannot_change_permissions_or_identity(virtual_api, create_user, workspace):
    client, url = virtual_api
    response = client.patch(
        _job_titles_url(url, create_user.id),
        {"job_titles": ["架构师"], "role": 5, "is_active": False, "is_virtual": True, "email": "changed@test.invalid"},
        format="json",
    )
    assert response.status_code == 200
    create_user.refresh_from_db()
    assert not create_user.is_virtual and create_user.email != "changed@test.invalid"
    assert WorkspaceMember.objects.get(workspace=workspace, member=create_user).role == 20


def test_title_save_is_atomic(virtual_api, create_user, workspace, monkeypatch):
    client, url = virtual_api

    def fail_save(*args, **kwargs):
        raise RuntimeError("Simulated membership save failure")

    monkeypatch.setattr(WorkspaceMember, "save", fail_save)
    response = client.patch(_job_titles_url(url, create_user.id), {"job_titles": ["Must roll back"]}, format="json")
    assert response.status_code == 500
    assert not WorkspaceJobTitle.objects.filter(name="Must roll back").exists()
    assert WorkspaceMember.objects.get(workspace=workspace, member=create_user).job_titles is None


def test_expanded_assignee_uses_workspace_titles(api_key_client, workspace, project):
    base = f"/api/v1/workspaces/{workspace.slug}"
    created = api_key_client.post(
        f"{base}/virtual-users/",
        {"display_name": "Edited assignee", "job_titles": ["旧岗位"], "project_ids": [str(project.id)]},
        format="json",
    )
    user_id = created.data["id"]
    issue = api_key_client.post(
        f"{base}/projects/{project.id}/work-items/", {"name": "Edited roles", "assignees": [user_id]}, format="json"
    )
    assert issue.status_code == 201, issue.data
    edit_url = f"{base}/members/{user_id}/job-titles/"
    for titles in [["架构师", "IT运维"], []]:
        assert api_key_client.patch(edit_url, {"job_titles": titles}, format="json").status_code == 200
        response = api_key_client.get(f"{base}/projects/{project.id}/work-items/{issue.data['id']}/?expand=assignees")
        assert response.status_code == 200, response.data
        assert response.data["assignees"][0]["job_titles"] == titles
        assert response.data["assignees"][0]["job_title"] == (titles[0] if titles else "")


def test_removed_admin_cannot_edit_titles(virtual_api, workspace, create_user):
    client, url = virtual_api
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(is_active=False)
    response = client.patch(_job_titles_url(url, create_user.id), {"job_titles": ["Forbidden"]}, format="json")
    assert response.status_code == 403
    assert not WorkspaceJobTitle.objects.exists()


def test_unauthenticated_edit_is_denied(workspace, create_user):
    client = APIClient()
    for prefix in ["/api", "/api/v1"]:
        response = client.patch(
            f"{prefix}/workspaces/{workspace.slug}/members/{create_user.id}/job-titles/",
            {"job_titles": ["Forbidden"]},
            format="json",
        )
        assert response.status_code in [401, 403]
    assert not WorkspaceJobTitle.objects.exists()
