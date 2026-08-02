# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import partial

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import PageSerializer
from plane.app.permissions import ProjectEntityPermission
from plane.bgtasks.page_transaction_task import page_transaction
from plane.db.models import Page, Project, ProjectPage

from .base import BaseAPIView


class ProjectPageListCreateAPIEndpoint(BaseAPIView):
    """List and create project Pages through API-key authentication."""

    serializer_class = PageSerializer
    model = Page
    permission_classes = [ProjectEntityPermission]

    def get_queryset(self):
        return (
            Page.objects.filter(
                workspace__slug=self.workspace_slug,
                project_pages__project_id=self.project_id,
                project_pages__deleted_at__isnull=True,
            )
            .filter(Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=self.request.user))
            .select_related("workspace", "owned_by", "created_by", "updated_by")
            .order_by("-created_at")
            .distinct()
        )

    def get(self, request, slug, project_id):
        return self.paginate(
            request=request,
            queryset=self.get_queryset(),
            on_results=lambda pages: (
                PageSerializer(
                    pages,
                    many=True,
                    fields=self.fields,
                    expand=self.expand,
                    context={"project_id": project_id},
                ).data
            ),
        )

    def post(self, request, slug, project_id):
        project = get_object_or_404(Project, pk=project_id, workspace__slug=slug)
        serializer = PageSerializer(data=request.data, context={"project_id": project_id})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            page = serializer.save(
                workspace=project.workspace,
                owned_by=request.user,
                created_by=request.user,
            )
            ProjectPage.objects.create(
                workspace=project.workspace,
                project=project,
                page=page,
                created_by=request.user,
            )
            transaction.on_commit(
                partial(
                    page_transaction.delay,
                    new_description_html=page.description_html,
                    old_description_html=None,
                    page_id=str(page.id),
                ),
                robust=True,
            )

        return Response(
            PageSerializer(page, context={"project_id": project_id}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectPageDetailAPIEndpoint(BaseAPIView):
    """Retrieve a project Page through API-key authentication."""

    serializer_class = PageSerializer
    model = Page
    permission_classes = [ProjectEntityPermission]
    use_read_replica = True

    def get_queryset(self):
        return (
            Page.objects.filter(
                workspace__slug=self.workspace_slug,
                project_pages__project_id=self.project_id,
                project_pages__deleted_at__isnull=True,
            )
            .filter(Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=self.request.user))
            .select_related("workspace", "owned_by", "created_by", "updated_by")
            .distinct()
        )

    def get(self, request, slug, project_id, page_id):
        page = get_object_or_404(self.get_queryset(), pk=page_id)
        return Response(
            PageSerializer(
                page,
                fields=self.fields,
                expand=self.expand,
                context={"project_id": project_id},
            ).data,
            status=status.HTTP_200_OK,
        )
