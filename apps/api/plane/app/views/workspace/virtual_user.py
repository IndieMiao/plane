# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import status
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema

from plane.app.serializers.virtual_user import (
    VirtualUserSerializer,
    VirtualUserJobTitleSerializer,
    WorkspaceMemberJobTitlesSerializer,
)
from plane.app.views.base import BaseAPIView
from plane.api.serializers.user import UserLiteSerializer
from plane.db.models import User, Workspace, WorkspaceMember
from plane.utils.permissions.workspace import WorkspaceVirtualUserPermission
from plane.utils.virtual_user_job_titles import (
    get_virtual_user_job_titles,
    get_or_create_virtual_user_job_title,
    with_workspace_job_titles,
)


class WorkspaceMemberJobTitlesViewMixin:
    permission_classes = [WorkspaceVirtualUserPermission]
    serializer_class = WorkspaceMemberJobTitlesSerializer

    @extend_schema(tags=["Members"], request=WorkspaceMemberJobTitlesSerializer, responses={200: UserLiteSerializer})
    @transaction.atomic
    def patch(self, request, slug, user_id):
        member = get_object_or_404(
            WorkspaceMember.objects.select_for_update(of=("self",)).select_related("workspace", "member"),
            workspace__slug=slug,
            member_id=user_id,
            is_active=True,
            member__is_bot=False,
        )
        serializer = WorkspaceMemberJobTitlesSerializer(member, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        member = serializer.save()
        member.member._workspace_job_titles = member.job_titles
        return Response(UserLiteSerializer(member.member).data)


class WorkspaceMemberJobTitlesEndpoint(WorkspaceMemberJobTitlesViewMixin, BaseAPIView):
    pass


class VirtualUserJobTitleViewMixin:
    permission_classes = [WorkspaceVirtualUserPermission]
    serializer_class = VirtualUserJobTitleSerializer

    @extend_schema(tags=["Members"], responses={200: {"type": "array", "items": {"type": "string"}}})
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        return Response(get_virtual_user_job_titles(workspace))

    @extend_schema(tags=["Members"], request=VirtualUserJobTitleSerializer, responses=VirtualUserJobTitleSerializer)
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = VirtualUserJobTitleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name, created = get_or_create_virtual_user_job_title(workspace, serializer.validated_data["name"], request.user)
        return Response({"name": name}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WorkspaceVirtualUserJobTitleEndpoint(VirtualUserJobTitleViewMixin, BaseAPIView):
    pass


class VirtualUserViewMixin:
    permission_classes = [WorkspaceVirtualUserPermission]
    serializer_class = VirtualUserSerializer

    @extend_schema(tags=["Members"], responses=UserLiteSerializer(many=True))
    def get(self, request, slug):
        users = (
            User.objects.filter(
                is_virtual=True,
                member_workspace__workspace__slug=slug,
                member_workspace__is_active=True,
                member_workspace__deleted_at__isnull=True,
            )
            .select_related("avatar_asset")
            .order_by("display_name", "id")
        )
        return Response(UserLiteSerializer(with_workspace_job_titles(users, workspace__slug=slug), many=True).data)

    @extend_schema(tags=["Members"], request=VirtualUserSerializer, responses={201: UserLiteSerializer})
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = VirtualUserSerializer(data=request.data, context={"workspace": workspace, "request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserLiteSerializer(user).data, status=status.HTTP_201_CREATED)


class WorkspaceVirtualUserEndpoint(VirtualUserViewMixin, BaseAPIView):
    pass
