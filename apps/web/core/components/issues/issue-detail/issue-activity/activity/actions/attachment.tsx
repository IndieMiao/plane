/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { ImageOff, Paperclip } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { ImagePreview } from "@plane/ui";
import { getFileExtension, getFileURL } from "@plane/utils";
import { getFileIcon } from "@/components/icons";
import { isAttachmentImage } from "@/components/issues/attachment/attachment-image";
import { isAttachmentMarkdown } from "@/components/issues/attachment/attachment-markdown";
import { AttachmentMarkdownPreview } from "@/components/issues/attachment/attachment-markdown-preview";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent } from "./helpers/activity-block";
import { IssueLink } from "./helpers/issue-link";

type TIssueAttachmentActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssueAttachmentActivity = observer(function IssueAttachmentActivity(props: TIssueAttachmentActivity) {
  const { activityId, showIssue = true, ends } = props;
  const { t } = useTranslation();
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [failedThumbnail, setFailedThumbnail] = useState<string | undefined>();
  // hooks
  const {
    activity: { getActivityById },
    attachment: { getAttachmentById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);
  const attachment =
    activity?.verb === "created" && activity.new_identifier ? getAttachmentById(activity.new_identifier) : undefined;
  const name = attachment?.attributes.name ?? "";
  const isImage = attachment ? isAttachmentImage(attachment) : false;
  const isMarkdown = attachment ? !isImage && isAttachmentMarkdown(attachment) : false;
  const url = attachment ? getFileURL(attachment.asset_url) : undefined;
  const thumbnailUrl = attachment?.thumbnail_url ? getFileURL(attachment.thumbnail_url) : undefined;
  const preview = attachment ? (
    isImage ? (
      <button
        type="button"
        data-activity-attachment-preview={attachment.id}
        onClick={() => setPreviewId(attachment.id)}
        disabled={!url}
        title={name}
        aria-label={t("attachment.preview_named", { name })}
        className="focus-visible:outline-accent-primary grid size-8 shrink-0 cursor-zoom-in place-items-center overflow-hidden rounded border border-subtle bg-layer-1 align-middle focus-visible:outline-2"
      >
        {thumbnailUrl && failedThumbnail !== thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            width={32}
            height={32}
            alt=""
            loading="lazy"
            decoding="async"
            className="size-full object-cover"
            onError={() => setFailedThumbnail(thumbnailUrl)}
          />
        ) : (
          <ImageOff className="size-4 text-tertiary" aria-hidden="true" />
        )}
      </button>
    ) : isMarkdown ? (
      <button
        type="button"
        data-activity-attachment-file={attachment.id}
        disabled={!url}
        onClick={() => setPreviewId(attachment.id)}
        title={name}
        aria-label={t("attachment.preview_named", { name })}
        className="focus-visible:outline-accent-primary grid size-8 shrink-0 cursor-pointer place-items-center rounded text-secondary hover:bg-layer-2 focus-visible:outline-2"
      >
        {getFileIcon(getFileExtension(name), 20)}
      </button>
    ) : (
      <span
        data-activity-attachment-file={attachment.id}
        title={name}
        role="img"
        aria-label={name}
        className="grid size-8 shrink-0 place-items-center text-secondary"
      >
        {getFileIcon(getFileExtension(name), 20)}
      </span>
    )
  ) : undefined;

  if (!activity) return <></>;
  return (
    <>
      {attachment && isMarkdown && previewId === attachment.id && (
        <AttachmentMarkdownPreview key={attachment.id} attachment={attachment} onClose={() => setPreviewId(null)} />
      )}
      {attachment && isImage && url && previewId === attachment.id && (
        <ImagePreview
          images={[{ id: attachment.id, src: url, name }]}
          initialId={attachment.id}
          onClose={() => setPreviewId(null)}
          labels={{
            close: t("attachment.close_preview"),
            previous: t("attachment.previous_image"),
            next: t("attachment.next_image"),
            zoomIn: t("attachment.zoom_in"),
            zoomOut: t("attachment.zoom_out"),
            reset: t("attachment.fit_image"),
            download: t("attachment.download"),
            error: t("attachment.preview_error"),
          }}
        />
      )}
      <IssueActivityBlockComponent
        icon={<Paperclip size={14} className="text-secondary" aria-hidden="true" />}
        activityId={activityId}
        ends={ends}
        trailingContent={preview}
      >
        <>
          {activity.verb === "created" ? `uploaded a new attachment` : `removed an attachment`}
          {showIssue && (activity.verb === "created" ? ` to ` : ` from `)}
          {showIssue && <IssueLink activityId={activityId} />}.
        </>
      </IssueActivityBlockComponent>
    </>
  );
});
