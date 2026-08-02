# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import APIToken, Page, Project, ProjectMember, ProjectPage, User, WorkspaceMember


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Pages API Project",
        identifier="PAGES",
        workspace=workspace,
        created_by=create_user,
        page_view=True,
    )
    ProjectMember.objects.create(
        workspace=workspace,
        project=project,
        member=create_user,
        role=20,
        is_active=True,
    )
    return project


@pytest.fixture
def other_project_member_client(db, workspace, project):
    user = User.objects.create(
        email="pages-member@plane.so",
        username="pages-member",
        first_name="Pages",
        last_name="Member",
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15, is_active=True)
    ProjectMember.objects.create(
        workspace=workspace,
        project=project,
        member=user,
        role=15,
        is_active=True,
    )
    token = APIToken.objects.create(
        user=user,
        label="Pages member token",
        token="pages-member-api-token",
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


def _list_url(slug, project_id):
    return f"/api/v1/workspaces/{slug}/projects/{project_id}/pages/"


def _detail_url(slug, project_id, page_id):
    return f"{_list_url(slug, project_id)}{page_id}/"


@pytest.mark.contract
class TestProjectPageAPI:
    @pytest.mark.django_db
    def test_api_key_can_create_page(self, api_key_client, workspace, project, create_user):
        response = api_key_client.post(
            _list_url(workspace.slug, project.id),
            {
                "name": "Architecture",
                "description_html": "<h1>Architecture</h1><p>Community edition page.</p>",
                "access": Page.PRIVATE_ACCESS,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        page = Page.objects.get(pk=response.data["id"])
        assert page.name == "Architecture"
        assert page.owned_by == create_user
        assert page.workspace == workspace
        assert ProjectPage.objects.filter(page=page, project=project, workspace=workspace).exists()
        assert response.data["projects"] == [str(project.id)]
        assert response.data["description_html"] == "<h1>Architecture</h1><p>Community edition page.</p>"

    @pytest.mark.django_db
    def test_create_page_requires_name(self, api_key_client, workspace, project):
        response = api_key_client.post(
            _list_url(workspace.slug, project.id),
            {"description_html": "<p>Missing title</p>"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data

    @pytest.mark.django_db
    def test_create_page_sanitizes_html(self, api_key_client, workspace, project):
        response = api_key_client.post(
            _list_url(workspace.slug, project.id),
            {
                "name": "Safe page",
                "description_html": '<p onclick="alert(1)">Safe</p><script>alert(1)</script>',
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert "<script" not in response.data["description_html"]
        assert "onclick" not in response.data["description_html"]

    @pytest.mark.django_db
    def test_list_and_retrieve_created_page(self, api_key_client, workspace, project, create_user):
        page = Page.objects.create(
            name="Runbook",
            description_html="<p>Deploy safely.</p>",
            workspace=workspace,
            owned_by=create_user,
            created_by=create_user,
        )
        ProjectPage.objects.create(
            workspace=workspace,
            project=project,
            page=page,
            created_by=create_user,
        )

        list_response = api_key_client.get(_list_url(workspace.slug, project.id))
        detail_response = api_key_client.get(_detail_url(workspace.slug, project.id, page.id))

        assert list_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in list_response.data["results"]] == [page.id]
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data["id"] == page.id
        assert detail_response.data["description_html"] == "<p>Deploy safely.</p>"

    @pytest.mark.django_db
    def test_retrieve_rejects_page_from_another_project(self, api_key_client, workspace, project, create_user):
        other_project = Project.objects.create(
            name="Other Project",
            identifier="OTHER",
            workspace=workspace,
            created_by=create_user,
        )
        page = Page.objects.create(
            name="Other page",
            workspace=workspace,
            owned_by=create_user,
            created_by=create_user,
        )
        ProjectPage.objects.create(
            workspace=workspace,
            project=other_project,
            page=page,
            created_by=create_user,
        )

        response = api_key_client.get(_detail_url(workspace.slug, project.id, page.id))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_retrieve_unknown_page_returns_404(self, api_key_client, workspace, project):
        response = api_key_client.get(_detail_url(workspace.slug, project.id, uuid4()))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_private_page_is_hidden_from_other_project_members(
        self,
        other_project_member_client,
        workspace,
        project,
        create_user,
    ):
        page = Page.objects.create(
            name="Private runbook",
            workspace=workspace,
            owned_by=create_user,
            created_by=create_user,
            access=Page.PRIVATE_ACCESS,
        )
        ProjectPage.objects.create(
            workspace=workspace,
            project=project,
            page=page,
            created_by=create_user,
        )

        list_response = other_project_member_client.get(_list_url(workspace.slug, project.id))
        detail_response = other_project_member_client.get(_detail_url(workspace.slug, project.id, page.id))

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["results"] == []
        assert detail_response.status_code == status.HTTP_404_NOT_FOUND
