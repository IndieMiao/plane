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
from plane.db.models import Page, Project, ProjectMember, ProjectPage, UserFavorite, UserRecentVisit

from .base import BaseAPIView
from plane.utils.virtual_user_attribution import resolve_virtual_user, attribute_to_virtual_user


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

    @transaction.atomic
    def post(self, request, slug, project_id):
        virtual_user = resolve_virtual_user(request, slug, project_id)
        project = get_object_or_404(Project, pk=project_id, workspace__slug=slug)
        serializer = PageSerializer(data=request.data, context={"project_id": project_id})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            page = serializer.save(
                workspace=project.workspace,
                owned_by=request.user,
                created_by=request.user,
            )
            attribute_to_virtual_user(page, virtual_user, request.user, creating=True)
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
    """Retrieve, update, and delete a project Page through API-key authentication."""

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

    @transaction.atomic
    def patch(self, request, slug, project_id, page_id):
        """Partially update a Page; changing ``name`` renames it."""
        virtual_user = resolve_virtual_user(request, slug, project_id)
        if virtual_user is not None and "archived_at" in request.data:
            return Response({"virtual_user_id": ["Virtual attribution is not enabled for archiving."]}, status=400)
        page = get_object_or_404(self.get_queryset(), pk=page_id)

        is_unlock_request = (set(request.data) - {"virtual_user_id"}) == {"is_locked"} and request.data.get(
            "is_locked"
        ) is False
        if page.is_locked and not is_unlock_request:
            return Response({"error": "Page is locked"}, status=status.HTTP_400_BAD_REQUEST)

        if page.access != request.data.get("access", page.access) and page.owned_by_id != request.user.id:
            return Response(
                {"error": "Access cannot be updated since this page is owned by someone else"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PageSerializer(
            page,
            data=request.data,
            partial=True,
            context={"project_id": project_id},
        )
        serializer.is_valid(raise_exception=True)

        old_description_html = page.description_html
        with transaction.atomic():
            page = serializer.save(updated_by=request.user)
            attribute_to_virtual_user(page, virtual_user, request.user)

            if "description_html" in request.data and page.description_html != old_description_html:
                transaction.on_commit(
                    partial(
                        page_transaction.delay,
                        new_description_html=page.description_html,
                        old_description_html=old_description_html,
                        page_id=str(page.id),
                    ),
                    robust=True,
                )

        return Response(
            PageSerializer(page, context={"project_id": project_id}).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, slug, project_id, page_id):
        """Delete an archived Page owned by the caller or managed by a project admin."""
        page = get_object_or_404(
            Page.objects.filter(
                workspace__slug=slug,
                project_pages__project_id=project_id,
                project_pages__deleted_at__isnull=True,
            ).distinct(),
            pk=page_id,
        )

        if page.archived_at is None:
            return Response(
                {"error": "The page should be archived before deleting"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_project_admin = ProjectMember.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            member=request.user,
            role=20,
            is_active=True,
        ).exists()
        if page.owned_by_id != request.user.id and not is_project_admin:
            return Response(
                {"error": "Only admin or owner can delete the page"},
                status=status.HTTP_403_FORBIDDEN,
            )

        Page.objects.filter(
            parent_id=page_id,
            workspace__slug=slug,
            project_pages__project_id=project_id,
            project_pages__deleted_at__isnull=True,
        ).update(parent=None)
        page.delete()

        UserFavorite.objects.filter(
            project_id=project_id,
            workspace__slug=slug,
            entity_identifier=page_id,
            entity_type="page",
        ).delete()
        UserRecentVisit.objects.filter(
            project_id=project_id,
            workspace__slug=slug,
            entity_identifier=page_id,
            entity_name="page",
        ).delete(soft=False)

        return Response(status=status.HTTP_204_NO_CONTENT)
