# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import partial

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from plane.db.models import ProjectMember, WorkspaceMember


def validate_virtual_user(value, request, slug, project_id):
    """Resolve a project identity without changing the authenticated user."""
    if (
        not request.user.is_active
        or request.user.is_virtual
        or not WorkspaceMember.objects.filter(
            workspace__slug=slug, member=request.user, is_active=True, role__in=[15, 20]
        ).exists()
        or not ProjectMember.objects.filter(
            workspace__slug=slug, project_id=project_id, member=request.user, is_active=True, role__in=[15, 20]
        ).exists()
    ):
        raise PermissionDenied("Only active workspace and project members can act as a virtual user.")

    membership = (
        ProjectMember.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            project__archived_at__isnull=True,
            member_id=value,
            member__is_virtual=True,
            is_active=True,
            role__in=[15, 20],
        )
        .select_related("member")
        .first()
    )
    if (
        membership is None
        or not WorkspaceMember.objects.filter(
            workspace__slug=slug, member_id=value, is_active=True, role__in=[15, 20]
        ).exists()
    ):
        raise serializers.ValidationError("Choose a virtual user who is an active member of this project.")
    return membership.member


class VirtualUserAttributionSerializer(serializers.Serializer):
    virtual_user_id = serializers.UUIDField(required=False, write_only=True)

    def validate_virtual_user_id(self, value):
        return validate_virtual_user(value, **self.context)


class VirtualUserInputMixin(serializers.Serializer):
    """Document the request identity without passing it to model constructors."""

    virtual_user_id = serializers.UUIDField(required=False, write_only=True)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        values.pop("virtual_user_id", None)
        return values


def resolve_virtual_user(request, slug, project_id):
    serializer = VirtualUserAttributionSerializer(
        data=request.data, context={"request": request, "slug": slug, "project_id": project_id}
    )
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data.get("virtual_user_id")


def attribute_to_virtual_user(instance, virtual_user, caller, *, creating=False):
    """Apply visible authorship while retaining the real creator/editor for audit."""
    if virtual_user is None:
        return
    fields = {"updated_by_id": virtual_user.id, "updated_by_actor_id": caller.id}
    if creating:
        fields = {
            "created_by_id": virtual_user.id,
            "created_by_actor_id": caller.id,
            "updated_by_id": None,
            "updated_by_actor_id": None,
        }
    # Avoid BaseModel.save replacing the visible identity with the current user.
    type(instance).all_objects.filter(pk=instance.pk).update(**fields)
    for key, value in fields.items():
        setattr(instance, key, value)


def activity_actor(request, virtual_user):
    if virtual_user is None:
        return {"actor_id": str(request.user.id)}
    return {"actor_id": str(virtual_user.id), "actor_principal_id": str(request.user.id)}


def queue_attributed_activity(task, request, virtual_user, **kwargs):
    queue_task_after_commit(task, **kwargs, **activity_actor(request, virtual_user))


def queue_task_after_commit(task, *args, **kwargs):
    transaction.on_commit(partial(task.delay, *args, **kwargs))
