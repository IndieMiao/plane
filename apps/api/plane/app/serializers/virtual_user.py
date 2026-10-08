# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from io import BytesIO
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps
from rest_framework import serializers

from plane.db.models import FileAsset, Project, ProjectMember, User, WorkspaceMember
from plane.settings.storage import S3Storage
from plane.utils.exception_logger import log_exception
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
    avatar = serializers.ImageField(required=False, write_only=True)
    remove_avatar = serializers.BooleanField(required=False, default=False)

    def validate_avatar(self, value):
        if value.size > min(settings.FILE_SIZE_LIMIT, 5 * 1024 * 1024):
            raise serializers.ValidationError("The avatar must be no larger than 5 MB.")
        image = value.image
        if image.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
            raise serializers.ValidationError("Use a PNG, JPEG, WebP or GIF image.")
        if image.width * image.height > 16_000_000:
            raise serializers.ValidationError("The avatar must contain no more than 16 million pixels.")
        value.seek(0)
        try:
            with Image.open(value) as decoded:
                normalized = ImageOps.exif_transpose(decoded).convert("RGBA")
                normalized.thumbnail((512, 512), Image.Resampling.LANCZOS)
                output = BytesIO()
                normalized.save(output, format="PNG")
        except (OSError, ValueError) as exc:
            raise serializers.ValidationError("The image could not be read.") from exc
        return ContentFile(output.getvalue(), name="avatar.png")

    def validate_display_name(self, value):
        if contains_url(value):
            raise serializers.ValidationError("Display name cannot contain a URL.")
        return value

    def validate(self, attrs):
        if "job_titles" not in attrs and (self.instance is None or "job_title" in attrs):
            attrs["job_titles"] = [attrs["job_title"]] if attrs.get("job_title") else []
        if attrs.get("avatar") and attrs.get("remove_avatar"):
            raise serializers.ValidationError({"avatar": "Choose an image or remove the avatar, not both."})
        if self.instance is not None and "project_ids" in attrs:
            raise serializers.ValidationError({"project_ids": "Manage project membership in project settings."})
        return attrs

    def save(self, **kwargs):
        self.uploaded_avatar_key = None
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except Exception:
            if self.uploaded_avatar_key:
                try:
                    S3Storage().delete_files([self.uploaded_avatar_key])
                except Exception as cleanup_error:
                    log_exception(cleanup_error)
            raise

    def save_avatar(self, user, image):
        if image is None:
            return
        actor = self.context["request"].user
        storage = S3Storage()
        key = f"virtual-user-avatars/{user.id}/{uuid4().hex}.png"
        self.uploaded_avatar_key = key
        if not storage.upload_file(image, key, content_type="image/png", extra_args={}):
            raise serializers.ValidationError({"avatar": "Unable to upload the avatar. Please try again."})
        asset = FileAsset(
            user=user,
            workspace=self.context["workspace"],
            created_by=actor,
            entity_type=FileAsset.EntityTypeContext.USER_AVATAR,
            attributes={"name": "avatar.png", "type": "image/png", "size": image.size},
            asset=key,
            size=image.size,
            is_uploaded=True,
        )
        asset.save(disable_auto_set_user=True)
        user.avatar_asset = asset
        user.avatar = ""
        user.save(update_fields=["avatar_asset", "avatar", "updated_at"])

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
        self.save_avatar(user, validated_data.get("avatar"))
        return user

    def update(self, instance, validated_data):
        fields = []
        if "display_name" in validated_data:
            instance.display_name = validated_data["display_name"]
            instance.first_name = validated_data["display_name"]
            instance.last_name = ""
            fields += ["display_name", "first_name", "last_name"]
        if validated_data.get("remove_avatar"):
            instance.avatar_asset = None
            instance.avatar = ""
            fields += ["avatar_asset", "avatar"]
        if fields:
            instance.save(update_fields=[*fields, "updated_at"])
        if "job_titles" in validated_data:
            membership = self.context["membership"]
            membership.job_titles = resolve_job_titles(
                membership.workspace, validated_data["job_titles"], self.context["request"].user
            )
            membership.save(update_fields=["job_titles", "updated_at", "updated_by"])
        self.save_avatar(instance, validated_data.get("avatar"))
        instance._workspace_job_titles = self.context["membership"].job_titles
        return instance
