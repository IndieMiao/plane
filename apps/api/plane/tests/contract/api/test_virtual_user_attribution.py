# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import (
    Estimate,
    EstimatePoint,
    FileAsset,
    Issue,
    IssueActivity,
    IssueLink,
    Label,
    Page,
    Project,
    ProjectMember,
    State,
    User,
)
from plane.db.models import WorkspaceMember

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def local_services(settings, monkeypatch):
    settings.WEB_URL = "http://testserver"
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    activity = Mock()
    for path in [
        "plane.middleware.logger.process_logs.delay",
        "plane.db.mixins.soft_delete_related_objects.delay",
        "plane.api.views.issue.model_activity.delay",
        "plane.api.views.issue.crawl_work_item_link_title.delay",
        "plane.api.views.issue.get_asset_object_metadata.delay",
        "plane.api.views.page.page_transaction.delay",
        "plane.app.views.issue.base.recent_visited_task.delay",
        "plane.bgtasks.issue_activities_task.notifications.delay",
    ]:
        monkeypatch.setattr(path, Mock())
    monkeypatch.setattr("plane.api.views.issue.issue_activity.delay", activity)
    monkeypatch.setattr("plane.bgtasks.issue_activities_task.redis_instance", Mock())
    storage = Mock()
    storage.generate_presigned_post.return_value = {"url": "https://uploads.example.com", "fields": {}}
    monkeypatch.setattr("plane.api.views.issue.S3Storage", Mock(return_value=storage))
    return activity


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Agents", identifier="AGT", workspace=workspace)
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20)
    State.objects.create(project=project, workspace=workspace, name="Backlog", group="backlog", default=True)
    return project


@pytest.fixture
def virtual_user(api_key_client, workspace, project):
    response = api_key_client.post(
        f"/api/v1/workspaces/{workspace.slug}/virtual-users/",
        {"display_name": "研发 Agent", "project_ids": [str(project.id)]},
        format="json",
    )
    assert response.status_code == 201, response.data
    return User.objects.get(pk=response.data["id"])


@pytest.fixture
def call(api_key_client, django_capture_on_commit_callbacks):
    def invoke(method, url, data=None):
        with django_capture_on_commit_callbacks(execute=True):
            response = getattr(api_key_client, method)(url, data or {}, format="json")
        return response

    return invoke


@pytest.fixture
def urls(workspace, project):
    root = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}"
    return {"issues": f"{root}/work-items/", "pages": f"{root}/pages/"}


@pytest.fixture
def issue(call, urls):
    response = call("post", urls["issues"], {"name": "Human task"})
    assert response.status_code == 201, response.data
    return Issue.objects.get(pk=response.data["id"])


@pytest.mark.parametrize("subtask", [False, True])
def test_created_card_author_profile_and_real_creator_permissions(
    call, api_key_client, urls, issue, virtual_user, workspace, project, create_user, local_services, subtask
):
    WorkspaceMember.objects.filter(member=create_user).update(role=15)
    ProjectMember.objects.filter(member=create_user).update(role=15)
    payload = {"name": "Agent-created task", "virtual_user_id": str(virtual_user.id)}
    if subtask:
        payload["parent"] = str(issue.id)
    response = call("post", urls["issues"], payload)
    assert response.status_code == 201, response.data
    created = Issue.objects.get(pk=response.data["id"])
    assert response.json()["created_by"] == str(virtual_user.id)
    assert response.json()["created_by_actor"] == str(create_user.id)
    assert created.created_by_id == virtual_user.id
    assert created.created_by_actor_id == create_user.id
    assert created.parent_id == (issue.id if subtask else None)
    activity = local_services.call_args.kwargs
    assert activity["actor_id"] == str(virtual_user.id)
    assert activity["actor_principal_id"] == str(create_user.id)
    issue_activity.run(**activity)
    saved_activity = IssueActivity.objects.get(issue=created, verb="created")
    assert saved_activity.actor_id == virtual_user.id and saved_activity.created_by_id == create_user.id

    session = APIClient()
    session.force_authenticate(user=create_user)
    profile = session.get(
        f"/api/workspaces/{workspace.slug}/user-issues/{virtual_user.id}/",
        {"created_by": str(virtual_user.id), "sub_issue": "true"},
    )
    assert profile.status_code == 200, profile.data
    assert str(created.id) in json.dumps(profile.data, default=str)
    detail = session.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{created.id}/")
    assert detail.status_code == 200, detail.data
    assert detail.json()["created_by_actor"] == str(create_user.id)
    # Creating as an identity must not take the actual member's creator permissions away.
    deleted = api_key_client.delete(f"{urls['issues']}{created.id}/")
    assert deleted.status_code == 204, deleted.data


@pytest.mark.parametrize("kind", ["name", "description", "priority", "state", "dates", "assignees", "labels"])
def test_card_updates_attribute_activity_and_preserve_creation(
    call, urls, issue, virtual_user, create_user, project, workspace, local_services, kind
):
    state = State.objects.create(project=project, workspace=workspace, name="Doing", group="started")
    label = Label.objects.create(project=project, workspace=workspace, name="Review", color="#112233")
    changes = {
        "name": {"name": "Agent title"},
        "description": {"description_html": "<p>Implementation complete</p>"},
        "priority": {"priority": "high"},
        "state": {"state": str(state.id)},
        "dates": {"start_date": "2026-10-08", "target_date": "2026-10-20"},
        "assignees": {"assignees": [str(virtual_user.id)]},
        "labels": {"labels": [str(label.id)]},
    }[kind]
    response = call("patch", f"{urls['issues']}{issue.id}/", {**changes, "virtual_user_id": str(virtual_user.id)})
    assert response.status_code == 200, response.data
    issue.refresh_from_db()
    assert issue.created_by_id == create_user.id
    assert issue.updated_by_id == virtual_user.id and issue.updated_by_actor_id == create_user.id
    assert response.json()["updated_by"] == str(virtual_user.id)
    activity = local_services.call_args.kwargs
    issue_activity.run(**activity)
    entries = IssueActivity.objects.filter(issue=issue, actor=virtual_user)
    assert entries.exists(), activity
    assert all(entry.created_by_id == create_user.id for entry in entries)


def test_subsequent_human_edit_clears_only_latest_delegation(call, urls, issue, virtual_user, create_user):
    url = f"{urls['issues']}{issue.id}/"
    assert call("patch", url, {"name": "Agent edit", "virtual_user_id": str(virtual_user.id)}).status_code == 200
    updated = call("patch", url, {"name": "Human edit", "created_by_actor": str(virtual_user.id)})
    assert updated.status_code == 200, updated.data
    issue.refresh_from_db()
    assert issue.updated_by_id == create_user.id and issue.updated_by_actor_id is None
    assert issue.created_by_id == create_user.id and issue.created_by_actor_id is None


def test_link_create_edit_delete_author_and_activity(call, urls, issue, virtual_user, create_user, local_services):
    url = f"{urls['issues']}{issue.id}/links/"
    identity = {"virtual_user_id": str(virtual_user.id)}
    created = call("post", url, {**identity, "url": "https://example.com/spec"})
    assert created.status_code == 201, created.data
    link = IssueLink.objects.get(pk=created.data["id"])
    assert link.created_by_id == virtual_user.id and link.created_by_actor_id == create_user.id
    detail = f"{url}{link.id}/"
    updated = call("patch", detail, {**identity, "url": "https://example.com/review"})
    assert updated.status_code == 200, updated.data
    link.refresh_from_db()
    assert link.updated_by_id == virtual_user.id and link.updated_by_actor_id == create_user.id
    deleted = call("delete", detail, identity)
    assert deleted.status_code == 204, deleted.data
    assert local_services.call_args.kwargs["actor_id"] == str(virtual_user.id)
    assert local_services.call_args.kwargs["actor_principal_id"] == str(create_user.id)
    assert not IssueLink.objects.filter(pk=link.id).exists()
    for event in local_services.call_args_list:
        if event.kwargs["type"].startswith("link."):
            issue_activity.run(**event.kwargs)
    events = IssueActivity.objects.filter(issue=issue, actor=virtual_user)
    assert events.count() == 3
    assert all(event.created_by_id == create_user.id for event in events)


@pytest.mark.parametrize("repeat_identity", [False, True])
def test_attachment_upload_preserves_author_and_delete_audit(
    call, urls, issue, virtual_user, create_user, local_services, repeat_identity
):
    url = f"{urls['issues']}{issue.id}/attachments/"
    identity = {"virtual_user_id": str(virtual_user.id)}
    created = call("post", url, {**identity, "name": "report.txt", "type": "text/plain", "size": 10})
    assert created.status_code == 200, created.data
    asset = FileAsset.objects.get(pk=created.data["asset_id"])
    detail = f"{url}{asset.id}/"
    confirmed = call("patch", detail, {"is_uploaded": True, **(identity if repeat_identity else {})})
    assert confirmed.status_code == 204, confirmed.data
    asset.refresh_from_db()
    assert asset.is_uploaded
    assert asset.created_by_id == virtual_user.id and asset.created_by_actor_id == create_user.id
    assert local_services.call_args.kwargs["actor_id"] == str(virtual_user.id)
    deleted = call("delete", detail, identity)
    assert deleted.status_code == 204, deleted.data
    asset = FileAsset.all_objects.get(pk=asset.id)
    assert asset.is_deleted and asset.updated_by_id == virtual_user.id
    assert asset.updated_by_actor_id == create_user.id
    assert local_services.call_args.kwargs["actor_principal_id"] == str(create_user.id)
    for event in local_services.call_args_list:
        if event.kwargs["type"].startswith("attachment."):
            issue_activity.run(**event.kwargs)
    events = IssueActivity.objects.filter(issue=issue, actor=virtual_user)
    assert events.count() == 2
    assert all(event.created_by_id == create_user.id for event in events)


def test_attachment_cannot_be_confirmed_or_deleted_through_another_card(call, urls, issue, virtual_user, project):
    other = Issue.objects.create(project=project, name="Other")
    created = call(
        "post",
        f"{urls['issues']}{issue.id}/attachments/",
        {"name": "report.txt", "type": "text/plain", "size": 10, "virtual_user_id": str(virtual_user.id)},
    )
    assert created.status_code == 200, created.data
    wrong_url = f"{urls['issues']}{other.id}/attachments/{created.data['asset_id']}/"
    for method in ["patch", "delete"]:
        assert call(method, wrong_url, {"virtual_user_id": str(virtual_user.id)}).status_code == 404


def test_page_author_editor_and_private_ownership(call, urls, virtual_user, create_user):
    created = call(
        "post",
        urls["pages"],
        {"name": "Design", "description_html": "<p>Plan</p>", "access": 1, "virtual_user_id": str(virtual_user.id)},
    )
    assert created.status_code == 201, created.data
    page = Page.objects.get(pk=created.data["id"])
    assert page.created_by_id == virtual_user.id and page.created_by_actor_id == create_user.id
    assert page.owned_by_id == create_user.id
    detail = f"{urls['pages']}{page.id}/"
    assert call("get", detail).status_code == 200
    updated = call(
        "patch",
        detail,
        {"name": "Final design", "description_html": "<p>Approved</p>", "virtual_user_id": str(virtual_user.id)},
    )
    assert updated.status_code == 200, updated.data
    page.refresh_from_db()
    assert page.updated_by_id == virtual_user.id and page.updated_by_actor_id == create_user.id
    assert page.created_by_id == virtual_user.id and page.owned_by_id == create_user.id


@pytest.mark.parametrize("resource", ["issues", "pages", "links", "attachments"])
@pytest.mark.parametrize("invalid", ["real", "missing", "null", "malformed", "other_project", "guest"])
def test_rejects_invalid_identity_without_side_effects(
    call, urls, issue, project, virtual_user, create_user, local_services, resource, invalid
):
    identity = {"real": str(create_user.id), "missing": str(uuid4()), "null": None, "malformed": "bad"}.get(
        invalid, str(virtual_user.id)
    )
    if invalid == "other_project":
        ProjectMember.objects.filter(project=project, member=virtual_user).delete()
    if invalid == "guest":
        ProjectMember.objects.filter(project=project, member=virtual_user).update(role=5)
    url = urls.get(resource) or f"{urls['issues']}{issue.id}/{resource}/"
    payload = {"name": "Invalid", "url": "https://example.com", "type": "text/plain", "size": 10}
    before = [m.objects.count() for m in [Issue, Page, IssueLink, FileAsset]]
    local_services.reset_mock()
    response = call("post", url, {**payload, "virtual_user_id": identity})
    assert response.status_code == 400, response.data
    assert "virtual_user_id" in response.data
    assert before == [m.objects.count() for m in [Issue, Page, IssueLink, FileAsset]]
    local_services.assert_not_called()


@pytest.mark.parametrize("resource", ["issues", "pages", "links", "attachments"])
def test_guest_caller_cannot_delegate(call, urls, issue, virtual_user, create_user, resource):
    WorkspaceMember.objects.filter(member=create_user).update(role=5)
    ProjectMember.objects.filter(member=create_user).update(role=5)
    url = urls.get(resource) or f"{urls['issues']}{issue.id}/{resource}/"
    response = call(
        "post",
        url,
        {
            "name": "Invalid",
            "url": "https://example.com",
            "type": "text/plain",
            "size": 10,
            "virtual_user_id": str(virtual_user.id),
        },
    )
    assert response.status_code == 403, response.data


def test_estimate_add_and_remove_are_attributed(call, urls, issue, virtual_user, project, workspace, local_services):
    estimate = Estimate.objects.create(project=project, workspace=workspace, name="Points", type="points")
    point = EstimatePoint.objects.create(project=project, workspace=workspace, estimate=estimate, value="3")
    for value in [str(point.id), None]:
        response = call(
            "patch", f"{urls['issues']}{issue.id}/", {"estimate_point": value, "virtual_user_id": str(virtual_user.id)}
        )
        assert response.status_code == 200, response.data
        issue_activity.run(**local_services.call_args.kwargs)
    events = IssueActivity.objects.filter(issue=issue, actor=virtual_user, field="estimate_points")
    assert set(events.values_list("verb", flat=True)) == {"updated", "removed"}


def test_metadata_crawler_keeps_virtual_editor(call, urls, issue, virtual_user, create_user, monkeypatch):
    from plane.bgtasks.work_item_link_task import crawl_work_item_link_title

    root = f"{urls['issues']}{issue.id}/links/"
    response = call("post", root, {"url": "https://example.com", "virtual_user_id": str(virtual_user.id)})
    link_id = response.data["id"]
    assert (
        call(
            "patch", f"{root}{link_id}/", {"url": "https://example.com/edited", "virtual_user_id": str(virtual_user.id)}
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        "plane.bgtasks.work_item_link_task.crawl_work_item_link_title_and_favicon", lambda url: {"title": "Spec"}
    )
    crawl_work_item_link_title.run(str(link_id), "https://example.com/edited")
    link = IssueLink.objects.get(pk=link_id)
    assert link.updated_by_id == virtual_user.id and link.updated_by_actor_id == create_user.id
    assert link.metadata["title"] == "Spec"


def test_attribution_failure_rolls_back_creation_and_queued_tasks(
    call, urls, virtual_user, monkeypatch, local_services
):
    def fail(*args, **kwargs):
        raise RuntimeError("Cannot store audit identity")

    monkeypatch.setattr("plane.api.views.issue.attribute_to_virtual_user", fail)
    response = call("post", urls["issues"], {"name": "Rollback", "virtual_user_id": str(virtual_user.id)})
    assert response.status_code == 500, response.data
    assert not Issue.objects.filter(name="Rollback").exists()
    local_services.assert_not_called()


def test_identity_and_audit_fields_cannot_rewrite_card_creator(call, urls, virtual_user, create_user):
    created = call(
        "post",
        urls["issues"],
        {
            "name": "Protected attribution",
            "virtual_user_id": str(virtual_user.id),
            "created_by": str(create_user.id),
            "created_by_actor": str(virtual_user.id),
        },
    )
    assert created.status_code == 201, created.data
    updated = call(
        "patch",
        f"{urls['issues']}{created.data['id']}/",
        {
            "name": "Keep author",
            "created_by": str(create_user.id),
            "created_by_actor": str(virtual_user.id),
            "updated_by_actor": str(virtual_user.id),
            "virtual_user_id": str(virtual_user.id),
        },
    )
    assert updated.status_code == 200, updated.data
    card = Issue.objects.get(pk=created.data["id"])
    assert card.created_by_id == virtual_user.id and card.created_by_actor_id == create_user.id
    assert card.updated_by_actor_id == create_user.id
