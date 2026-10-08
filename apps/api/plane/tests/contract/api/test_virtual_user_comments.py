# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import Issue, IssueComment, Project, ProjectMember, User, Workspace, WorkspaceMember

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def local_services(settings, monkeypatch):
    settings.WEB_URL = "http://testserver"
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    activity, webhook = Mock(), Mock()
    monkeypatch.setattr("plane.middleware.logger.process_logs.delay", Mock())
    monkeypatch.setattr("plane.db.mixins.soft_delete_related_objects.delay", Mock())
    monkeypatch.setattr("plane.api.views.issue.issue_activity.delay", activity)
    monkeypatch.setattr("plane.api.views.issue.model_activity.delay", webhook)
    return activity, webhook


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Development", identifier="DEV", workspace=workspace)
    ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
    return project


@pytest.fixture
def issue(workspace, project):
    return Issue.objects.create(name="Agent task", workspace=workspace, project=project)


@pytest.fixture
def virtual_user(api_key_client, workspace, project):
    response = api_key_client.post(
        f"/api/v1/workspaces/{workspace.slug}/virtual-users/",
        {"display_name": "开发 Agent", "project_ids": [str(project.id)]},
        format="json",
    )
    assert response.status_code == 201, response.data
    return User.objects.get(pk=response.json()["id"])


@pytest.fixture
def url(workspace, project, issue):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/comments/"


def _payload(user):
    return {"virtual_user_id": str(user.id), "comment_html": "<p>开发已完成，等待评审。</p>"}


@pytest.mark.parametrize("role", [15, 20])
def test_virtual_author_is_persisted_with_real_caller_audit(
    api_key_client, url, virtual_user, workspace, project, create_user, local_services, role
):
    WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=role)
    ProjectMember.objects.filter(project=project, member=create_user).update(role=role)
    response = api_key_client.post(
        url, {**_payload(virtual_user), "created_by": str(virtual_user.id), "actor": str(create_user.id)}, format="json"
    )

    assert response.status_code == 201, response.data
    comment = IssueComment.objects.get(pk=response.json()["id"])
    assert response.json()["actor"] == str(comment.actor_id) == str(virtual_user.id)
    assert response.json()["created_by"] == str(comment.created_by_id) == str(create_user.id)
    assert comment.comment_html == _payload(virtual_user)["comment_html"]
    assert comment.workspace_id == workspace.id and comment.project_id == project.id
    assert not virtual_user.is_active and not virtual_user.has_usable_password()
    activity, webhook = local_services
    activity.assert_called_once()
    assert activity.call_args.kwargs["actor_id"] == str(create_user.id)
    activity_payload = json.loads(activity.call_args.kwargs["requested_data"])
    assert activity_payload["id"] == str(comment.id)
    assert activity_payload["actor"] == str(virtual_user.id)
    assert activity_payload["created_by"] == str(create_user.id)
    assert webhook.call_args.kwargs["actor_id"] == create_user.id


def test_virtual_comment_can_be_read_by_api_and_existing_ui(
    api_key_client, url, virtual_user, workspace, project, issue, create_user
):
    created = api_key_client.post(url, _payload(virtual_user), format="json")
    assert created.status_code == 201, created.data
    comment_id = created.json()["id"]

    detail = api_key_client.get(f"{url}{comment_id}/")
    assert detail.status_code == 200
    assert detail.json()["actor"] == str(virtual_user.id)
    listed = api_key_client.get(url)
    assert listed.status_code == 200
    assert listed.json()["results"][0]["actor"] == str(virtual_user.id)

    ui_url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/comments/{comment_id}/"
    session_client = APIClient()
    session_client.force_authenticate(user=create_user)
    ui_comment = session_client.get(ui_url)
    assert ui_comment.status_code == 200, ui_comment.data
    assert ui_comment.json()["actor_detail"]["display_name"] == "开发 Agent"
    assert ui_comment.json()["actor_detail"]["is_virtual"] is True


def test_omitting_virtual_user_preserves_real_author(api_key_client, url, create_user, virtual_user):
    response = api_key_client.post(
        url,
        {"comment_html": "<p>Human comment</p>", "actor": str(virtual_user.id), "created_by": str(virtual_user.id)},
        format="json",
    )
    assert response.status_code == 201, response.data
    comment = IssueComment.objects.get(pk=response.json()["id"])
    assert comment.actor_id == comment.created_by_id == create_user.id
    assert response.json()["actor"] == str(create_user.id)


@pytest.mark.parametrize("identity", ["real_user", "missing", "invalid", "empty", "null"])
def test_rejects_invalid_or_real_identity(api_key_client, url, create_user, identity, local_services):
    identities = {
        "real_user": str(create_user.id),
        "missing": str(uuid4()),
        "invalid": "bad",
        "empty": "",
        "null": None,
    }
    response = api_key_client.post(
        url, {"virtual_user_id": identities[identity], "comment_html": "<p>Invalid author</p>"}, format="json"
    )
    assert response.status_code == 400, response.data
    assert "virtual_user_id" in response.data
    assert not IssueComment.objects.exists()
    for task in local_services:
        task.assert_not_called()


@pytest.mark.parametrize("membership_model", [WorkspaceMember, ProjectMember])
@pytest.mark.parametrize("restriction", ["inactive", "removed", "guest"])
def test_rejects_unavailable_virtual_membership(
    api_key_client, url, virtual_user, membership_model, restriction, local_services
):
    membership = membership_model.objects.filter(member=virtual_user)
    if restriction == "removed":
        membership.delete()
    else:
        membership.update(**({"is_active": False} if restriction == "inactive" else {"role": 5}))

    response = api_key_client.post(url, _payload(virtual_user), format="json")
    assert response.status_code == 400, response.data
    assert not IssueComment.objects.exists()
    for task in local_services:
        task.assert_not_called()


@pytest.mark.parametrize("membership_model", [WorkspaceMember, ProjectMember])
@pytest.mark.parametrize("restriction", ["inactive", "removed", "guest"])
def test_rejects_unprivileged_caller(
    api_key_client, url, virtual_user, create_user, membership_model, restriction, local_services
):
    membership = membership_model.objects.filter(member=create_user)
    if restriction == "removed":
        membership.delete()
    else:
        membership.update(**({"is_active": False} if restriction == "inactive" else {"role": 5}))

    response = api_key_client.post(url, _payload(virtual_user), format="json")
    assert response.status_code == 403, response.data
    assert not IssueComment.objects.exists()
    for task in local_services:
        task.assert_not_called()


def test_rejects_inactive_caller(api_key_client, url, virtual_user, create_user):
    User.objects.filter(pk=create_user.id).update(is_active=False)
    response = api_key_client.post(url, _payload(virtual_user), format="json")
    assert response.status_code == 403, response.data
    assert not IssueComment.objects.exists()


@pytest.mark.parametrize("other_workspace", [False, True])
def test_rejects_identity_from_another_project_or_workspace(
    api_key_client, url, virtual_user, workspace, create_user, other_workspace
):
    ProjectMember.objects.filter(member=virtual_user).delete()
    if other_workspace:
        WorkspaceMember.objects.filter(member=virtual_user).delete()
        workspace = Workspace.objects.create(name="Other", slug="other", owner=create_user)
        WorkspaceMember.objects.create(workspace=workspace, member=virtual_user, role=15)
    project = Project.objects.create(name="Other", identifier="OTHER", workspace=workspace)
    ProjectMember.objects.create(project=project, workspace=workspace, member=virtual_user, role=15)

    response = api_key_client.post(url, _payload(virtual_user), format="json")
    assert response.status_code == 400, response.data
    assert not IssueComment.objects.exists()


def test_issue_must_belong_to_target_project(api_key_client, url, virtual_user, workspace, issue):
    other_project = Project.objects.create(name="Other", identifier="OTHER", workspace=workspace)
    other_issue = Issue.objects.create(name="Private", workspace=workspace, project=other_project)
    response = api_key_client.post(
        url.replace(str(issue.id), str(other_issue.id)), _payload(virtual_user), format="json"
    )
    assert response.status_code == 404, response.data
    assert not IssueComment.objects.exists()


def test_cannot_comment_in_archived_project(api_key_client, url, virtual_user, project):
    Project.objects.filter(pk=project.id).update(archived_at=timezone.now())
    response = api_key_client.post(url, _payload(virtual_user), format="json")
    assert response.status_code == 404, response.data
    assert not IssueComment.objects.exists()


def test_cannot_change_virtual_author_on_edit(api_key_client, url, virtual_user, create_user):
    created = api_key_client.post(url, _payload(virtual_user), format="json")
    assert created.status_code == 201, created.data
    detail_url = f"{url}{created.json()['id']}/"
    changed_author = api_key_client.patch(detail_url, {"virtual_user_id": str(create_user.id)}, format="json")
    assert changed_author.status_code == 400, changed_author.data
    updated = api_key_client.patch(
        detail_url,
        {"comment_html": "<p>Updated</p>", "actor": str(create_user.id), "created_by": str(virtual_user.id)},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.json()["actor"] == str(virtual_user.id)
    assert updated.json()["created_by"] == str(create_user.id)
    assert updated.json()["comment_html"] == "<p>Updated</p>"
    assert api_key_client.delete(detail_url).status_code == 204
    assert not IssueComment.objects.filter(pk=created.json()["id"]).exists()


def test_external_id_deduplication_is_preserved(api_key_client, url, virtual_user):
    payload = {**_payload(virtual_user), "external_source": "agent", "external_id": "comment-1"}
    first = api_key_client.post(url, payload, format="json")
    second = api_key_client.post(url, payload, format="json")
    assert first.status_code == 201, first.data
    assert second.status_code == 409, second.data
    assert second.json()["id"] == first.json()["id"]
    assert IssueComment.objects.count() == 1


def test_anonymous_caller_cannot_use_virtual_identity(url, virtual_user):
    response = APIClient().post(url, _payload(virtual_user), format="json")
    assert response.status_code in [401, 403]
    assert not IssueComment.objects.exists()
