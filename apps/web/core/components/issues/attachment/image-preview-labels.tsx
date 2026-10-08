/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import { ImagePreviewLabelsContext } from "@plane/ui";

export const WorkItemImagePreviewLabels = observer(function WorkItemImagePreviewLabels({
  children,
}: {
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const labels = useMemo(
    () => ({
      close: t("attachment.close_preview"),
      previous: t("attachment.previous_image"),
      next: t("attachment.next_image"),
      zoomIn: t("attachment.zoom_in"),
      zoomOut: t("attachment.zoom_out"),
      reset: t("attachment.fit_image"),
      download: t("attachment.download"),
      error: t("attachment.preview_error"),
    }),
    [t]
  );
  return <ImagePreviewLabelsContext.Provider value={labels}>{children}</ImagePreviewLabelsContext.Provider>;
});
