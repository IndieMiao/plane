# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from uuid import uuid4

from django.db import transaction
from rest_framework import serializers

from plane.db.models import Project, ProjectMember, User, WorkspaceMember
from plane.utils.url import contains_url
from plane.utils.virtual_user_job_titles import resolve_job_titles


class VirtualUserJobTitleSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, trim_whitespace=True)


class WorkspaceMemberJobTitlesSerializer(serializers.Serializer):
    job_titles = serializers.ListField(
        child=serializers.CharField(max_length=255, trim_whitespace=True), max_length=100
    )

    @transaction.atomic
    def update(self, instance, validated_data):
        instance.job_titles = resolve_job_titles(
            instance.workspace, validated_data["job_titles"], self.context["request"].user
        )
        instance.save(update_fields=["job_titles", "updated_at", "updated_by"])
        return instance


class VirtualUserSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, trim_whitespace=True)
    job_title = serializers.CharField(
        max_length=255, trim_whitespace=True, required=False, allow_blank=True, default=""
    )
    job_titles = serializers.ListField(
        child=serializers.CharField(max_length=255, trim_whitespace=True), required=False, max_length=100
    )
    project_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=100)

    def validate_display_name(self, value):
        if contains_url(value):
            raise serializers.ValidationError("Display name cannot contain a URL.")
        return value

    def validate(self, attrs):
        if "job_titles" not in attrs:
            attrs["job_titles"] = [attrs["job_title"]] if attrs["job_title"] else []
        return attrs

    def validate_project_ids(self, value):
        project_ids = set(value)
        projects = list(
            Project.objects.filter(
                workspace=self.context["workspace"],
                pk__in=project_ids,
                project_projectmember__member=self.context["request"].user,
                project_projectmember__is_active=True,
                project_projectmember__deleted_at__isnull=True,
            )
        )
        if len(projects) != len(project_ids):
            raise serializers.ValidationError("Select projects in this workspace that you have joined.")
        self.projects = projects
        return value

    @transaction.atomic
    def create(self, validated_data):
        workspace = self.context["workspace"]
        actor = self.context["request"].user
        job_titles = resolve_job_titles(workspace, validated_data["job_titles"], actor)
        user_id = uuid4()
        user = User(
            id=user_id,
            username=f"virtual-{user_id.hex}",
            email=f"virtual-{user_id.hex}@users.invalid",
            display_name=validated_data["display_name"],
            first_name=validated_data["display_name"],
            is_virtual=True,
            job_title=job_titles[0] if job_titles else "",
            job_titles=job_titles,
            is_active=False,
            last_login_medium="",
        )
        user.set_unusable_password()
        user.save()
        WorkspaceMember.objects.create(
            workspace=workspace, member=user, role=15, created_by=actor, job_titles=job_titles
        )
        for project in self.projects:
            ProjectMember.objects.create(workspace=workspace, project=project, member=user, role=15, created_by=actor)
        return user
