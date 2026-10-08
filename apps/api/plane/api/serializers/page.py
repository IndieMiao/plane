# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

from plane.db.models import Page
from plane.utils.content_validator import validate_html_content
from plane.utils.virtual_user_attribution import VirtualUserInputMixin

from .base import BaseSerializer


class PageSerializer(VirtualUserInputMixin, BaseSerializer):
    """External API representation used by the Plane Pages SDK resource."""

    name = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    description_html = serializers.CharField(required=False, allow_blank=True, default="<p></p>")
    projects = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "virtual_user_id",
            "created_by_actor",
            "updated_by_actor",
            "id",
            "created_at",
            "updated_at",
            "name",
            "description_html",
            "description_stripped",
            "owned_by",
            "access",
            "color",
            "is_locked",
            "archived_at",
            "view_props",
            "logo_props",
            "external_id",
            "external_source",
            "workspace",
            "projects",
            "created_by",
            "updated_by",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "description_stripped",
            "owned_by",
            "workspace",
            "projects",
            "created_by",
            "updated_by",
        ]

    def get_projects(self, instance):
        """Do not leak project IDs that are outside the endpoint's project scope."""
        project_id = self.context.get("project_id")
        if project_id:
            return [str(project_id)]
        return [str(project_id) for project_id in instance.projects.values_list("id", flat=True)]

    def validate_description_html(self, value):
        is_valid, error_message, sanitized_html = validate_html_content(value)
        if not is_valid:
            raise serializers.ValidationError(error_message)
        return sanitized_html if sanitized_html is not None else value
