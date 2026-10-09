# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from crum import get_current_user
from django.conf import settings
from django.db import models


class VirtualUserAuditMixin(models.Model):
    """Keep the authenticated caller when a virtual user is the visible author."""

    created_by_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    updated_by_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        update_fields = kwargs.get("update_fields")
        if (
            not self._state.adding
            and user is not None
            and not user.is_anonymous
            and not kwargs.get("disable_auto_set_user", False)
            and (update_fields is None or "updated_by" in update_fields)
        ):
            # A subsequent ordinary edit is attributed directly to its caller.
            self.updated_by_actor_id = None
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"updated_by_actor"}
        return super().save(*args, **kwargs)
