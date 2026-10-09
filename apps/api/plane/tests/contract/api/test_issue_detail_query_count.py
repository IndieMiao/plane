# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.files.storage import default_storage

from plane.app.serializers.issue import IssueDetailSerializer
from plane.db.models import FileAsset, Issue, Project

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("attachment_count", [0, 1, 25])
def test_attachment_expansion_uses_one_query_regardless_of_attachment_count(
    workspace, create_user, django_assert_num_queries, monkeypatch, attachment_count
):
    project = Project.objects.create(name="Performance", identifier="PERF", workspace=workspace)
    issue = Issue.objects.create(name="Attachments", workspace=workspace, project=project)
    FileAsset.objects.bulk_create(
        [
            FileAsset(
                workspace=workspace,
                project=project,
                issue=issue,
                entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
                asset=f"{workspace.id}/{index}.png",
                attributes={"name": f"{index}.png", "size": 100},
                is_uploaded=True,
                created_by=create_user,
            )
            for index in range(attachment_count)
        ]
    )
    monkeypatch.setattr(default_storage, "url", lambda name: f"https://storage.example.com/{name}")
    serializer = IssueDetailSerializer(issue, expand=["issue_attachments"])
    with django_assert_num_queries(1):
        data = serializer.data
    assert len(data["issue_attachments"]) == attachment_count
    for attachment in data["issue_attachments"]:
        assert attachment["asset_url"].startswith(
            f"/api/assets/v2/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/attachments/"
        )
