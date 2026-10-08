/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIssueAttachment } from "@plane/types";

export function isAttachmentImage(attachment: TIssueAttachment): boolean {
  return (
    !!attachment.attributes.type?.toLowerCase().startsWith("image/") ||
    /\.(png|jpe?g|gif|webp|avif|bmp|ico|svg)$/i.test(attachment.attributes.name)
  );
}
