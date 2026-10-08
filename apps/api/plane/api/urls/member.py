# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path
from plane.api.views.virtual_user import (
    WorkspaceVirtualUserAPIEndpoint,
    WorkspaceVirtualUserJobTitleAPIEndpoint,
    WorkspaceMemberJobTitlesAPIEndpoint,
    WorkspaceVirtualUserDetailAPIEndpoint,
)

from plane.api.views import (
    ProjectMemberListCreateAPIEndpoint,
    ProjectMemberDetailAPIEndpoint,
    WorkspaceMemberAPIEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/virtual-users/<uuid:user_id>/",
        WorkspaceVirtualUserDetailAPIEndpoint.as_view(http_method_names=["patch", "options"]),
        name="workspace-virtual-user-detail-api",
    ),
    path(
        "workspaces/<str:slug>/members/<uuid:user_id>/job-titles/",
        WorkspaceMemberJobTitlesAPIEndpoint.as_view(http_method_names=["patch", "options"]),
        name="workspace-member-job-titles-api",
    ),
    path(
        "workspaces/<str:slug>/virtual-user-job-titles/",
        WorkspaceVirtualUserJobTitleAPIEndpoint.as_view(),
        name="workspace-virtual-user-job-titles-api",
    ),
    path(
        "workspaces/<str:slug>/virtual-users/",
        WorkspaceVirtualUserAPIEndpoint.as_view(),
        name="workspace-virtual-users-api",
    ),
    # Project members
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/members/",
        ProjectMemberListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="project-members",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/members/<uuid:pk>/",
        ProjectMemberDetailAPIEndpoint.as_view(http_method_names=["patch", "delete", "get"]),
        name="project-member",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/project-members/",
        ProjectMemberListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="project-members",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/project-members/<uuid:pk>/",
        ProjectMemberDetailAPIEndpoint.as_view(http_method_names=["patch", "delete", "get"]),
        name="project-member",
    ),
    path(
        "workspaces/<str:slug>/members/",
        WorkspaceMemberAPIEndpoint.as_view(http_method_names=["get"]),
        name="workspace-members",
    ),
]
