# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db.models import OuterRef, Subquery

from plane.db.models import WorkspaceJobTitle, WorkspaceMember


DEFAULT_VIRTUAL_USER_JOB_TITLES = (
    "高级UI设计师",
    "高级游戏策划",
    "高级项目经理",
    "高级游戏开发",
    "游戏主程",
    "架构师",
    "IT运维",
    "高级运营策划",
    "高级产品经理",
)


def get_virtual_user_job_titles(workspace):
    names = list(DEFAULT_VIRTUAL_USER_JOB_TITLES)
    seen = {name.casefold() for name in names}
    for name in WorkspaceJobTitle.objects.filter(workspace=workspace).values_list("name", flat=True):
        if name.casefold() not in seen:
            names.append(name)
            seen.add(name.casefold())
    return names


def get_or_create_virtual_user_job_title(workspace, name, actor):
    """Store reusable names within the workspace, canonicalizing duplicates."""
    for default in DEFAULT_VIRTUAL_USER_JOB_TITLES:
        if name.casefold() == default.casefold():
            return default, False
    title, created = WorkspaceJobTitle.objects.get_or_create(
        workspace=workspace,
        name__iexact=name,
        defaults={"name": name, "created_by": actor},
    )
    return title.name, created


def resolve_job_titles(workspace, names, actor):
    titles = []
    seen = set()
    for name in names:
        if name.casefold() in seen:
            continue
        name, _ = get_or_create_virtual_user_job_title(workspace, name, actor)
        if name.casefold() not in seen:
            titles.append(name)
            seen.add(name.casefold())
    return titles


def with_workspace_job_titles(users, **workspace_filter):
    titles = WorkspaceMember.objects.filter(member_id=OuterRef("pk"), **workspace_filter).values("job_titles")[:1]
    return users.annotate(_workspace_job_titles=Subquery(titles))
