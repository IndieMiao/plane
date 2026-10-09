# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from html.parser import HTMLParser
from urllib.parse import urlsplit
from uuid import UUID

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from plane.db.models import FileAsset, Issue, ProjectMember, WorkspaceMember
from plane.settings.storage import S3Storage
from plane.utils.permissions.project import ProjectEntityPermission

from .base import BaseAPIView


class DescriptionImageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag in {"img", "image-component"}:
            attributes = dict(attrs)
            self.images.append({"src": attributes.get("src") or "", "alt": attributes.get("alt") or ""})


def image_asset_id(source, request, slug, project_id, issue_id):
    """Accept editor UUIDs and this task's same-origin asset routes, never arbitrary URLs."""
    source = source.strip()
    try:
        return UUID(source)
    except (ValueError, AttributeError):
        pass
    try:
        parsed = urlsplit(source)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return None
        if parsed.netloc and (parsed.netloc != request.get_host() or parsed.username or parsed.password):
            return None
        prefix = f"/api/assets/v2/workspaces/{slug}/projects/{project_id}/"
        if not parsed.path.startswith(prefix):
            return None
        suffix = parsed.path[len(prefix) :].strip("/")
        attachment_prefix = f"issues/{issue_id}/attachments/"
        if suffix.startswith(attachment_prefix):
            suffix = suffix[len(attachment_prefix) :]
        return UUID(suffix)
    except (ValueError, AttributeError):
        return None


class WorkItemDescriptionImagesEndpoint(BaseAPIView):
    """Read task-body images using API-key authentication and task-scoped authorization."""

    permission_classes = [ProjectEntityPermission]
    use_read_replica = True

    def get(self, request, slug, project_id, issue_id, image_index=None):
        if (
            not request.user.is_active
            or not WorkspaceMember.objects.filter(workspace__slug=slug, member=request.user, is_active=True).exists()
        ):
            raise PermissionDenied("An active workspace membership is required.")
        issue = get_object_or_404(
            Issue.issue_objects.select_related("project"), workspace__slug=slug, project_id=project_id, pk=issue_id
        )
        membership = ProjectMember.objects.get(project_id=project_id, member=request.user, is_active=True)
        if (
            membership.role == 5
            and not issue.project.guest_view_all_features
            and (issue.created_by_actor_id or issue.created_by_id) != request.user.id
        ):
            raise PermissionDenied("You are not allowed to view this work item.")

        parser = DescriptionImageParser()
        parser.feed(issue.description_html or "")
        references = [image_asset_id(item["src"], request, slug, project_id, issue_id) for item in parser.images]
        assets = FileAsset.objects.filter(
            id__in=[asset_id for asset_id in references if asset_id],
            workspace_id=issue.workspace_id,
            project_id=project_id,
            issue_id=issue_id,
            entity_type__in=[
                FileAsset.EntityTypeContext.ISSUE_DESCRIPTION,
                FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
            ],
            is_deleted=False,
            is_uploaded=True,
        ).in_bulk()
        images = []
        for index, (reference, asset_id) in enumerate(zip(parser.images, references), start=1):
            asset = assets.get(asset_id)
            attributes = asset.attributes if asset and isinstance(asset.attributes, dict) else {}
            images.append(
                {
                    "image_index": index,
                    "asset_id": str(asset.id) if asset else None,
                    "alt": reference["alt"],
                    "name": attributes.get("name") or f"Image {index}",
                    "content_type": attributes.get("type", ""),
                    "size": asset.size if asset else None,
                    "available": asset is not None,
                }
            )

        if image_index is None:
            return Response(images)
        if image_index < 1 or image_index > len(images) or not images[image_index - 1]["available"]:
            return Response({"error": "The description image is unavailable."}, status=status.HTTP_404_NOT_FOUND)
        image = images[image_index - 1]
        asset = assets[UUID(image["asset_id"])]
        storage = S3Storage(request=request)
        url = storage.generate_presigned_url(object_name=asset.asset.name, filename=image["name"])
        if not url:
            return Response({"error": "Unable to retrieve the image."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        response = Response({**image, "download_url": url, "expires_in": storage.signed_url_expiration})
        response["Cache-Control"] = "private, no-store"
        return response
