# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.app.views.workspace.virtual_user import (
    VirtualUserViewMixin,
    VirtualUserJobTitleViewMixin,
    WorkspaceMemberJobTitlesViewMixin,
)
from .base import BaseAPIView


class WorkspaceVirtualUserAPIEndpoint(VirtualUserViewMixin, BaseAPIView):
    """List assignment identities, or create one as a workspace administrator."""


class WorkspaceVirtualUserJobTitleAPIEndpoint(VirtualUserJobTitleViewMixin, BaseAPIView):
    """List job titles or add a reusable name as a workspace administrator."""


class WorkspaceMemberJobTitlesAPIEndpoint(WorkspaceMemberJobTitlesViewMixin, BaseAPIView):
    """Allow workspace administrators to replace a member's workspace job titles."""
