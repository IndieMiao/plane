/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Download, ImageOff } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { TrashIcon } from "@plane/propel/icons";
import type { TIssueServiceType } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
import { CustomMenu } from "@plane/ui";
import { cn, convertBytesToSize, getFileExtension, getFileURL, renderFormattedDate } from "@plane/utils";
import { ButtonAvatars } from "@/components/dropdowns/member/avatar";
import { getFileIcon } from "@/components/icons";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useMember } from "@/hooks/store/use-member";
import { isAttachmentImage } from "./attachment-image";

type Props = {
  attachmentId: string;
  disabled?: boolean;
  issueServiceType?: TIssueServiceType;
  onPreview: (id: string) => void;
};

export const IssueAttachmentsListItem = observer(function IssueAttachmentsListItem({
  attachmentId,
  disabled,
  issueServiceType = EIssueServiceType.ISSUES,
  onPreview,
}: Props) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);
  const { getUserDetails } = useMember();
  const {
    attachment: { getAttachmentById },
    toggleDeleteAttachmentModal,
  } = useIssueDetail(issueServiceType);
  const attachment = getAttachmentById(attachmentId);
  if (!attachment) return null;
  const name = attachment.attributes.name;
  const url = getFileURL(attachment.asset_url);
  const thumbnailUrl = attachment.thumbnail_url ? getFileURL(attachment.thumbnail_url) : undefined;
  const isImage = isAttachmentImage(attachment);
  const uploader = getUserDetails(attachment.created_by)?.display_name;
  const uploadedAt = renderFormattedDate(new Date(attachment.created_at), "yyyy-MM-dd HH:mm");
  const uploadTime = uploadedAt ? (
    <time
      dateTime={attachment.created_at}
      title={t("attachment.uploaded_at", { date: uploadedAt })}
      className="block text-11 text-tertiary tabular-nums"
    >
      {t("attachment.uploaded_at", { date: uploadedAt })}
    </time>
  ) : null;
  const actions = (
    <div className="flex shrink-0 items-center gap-1">
      <a
        href={url}
        download={name}
        target="_blank"
        rel="noopener noreferrer"
        title={t("attachment.download")}
        aria-label={t("attachment.download_named", { name })}
        className="focus-visible:outline-accent-primary grid size-8 place-items-center rounded text-secondary hover:bg-layer-2 focus-visible:outline-2"
      >
        <Download className="size-4" />
      </a>
      {!disabled && (
        <CustomMenu ellipsis closeOnSelect placement="bottom-end" ariaLabel={t("attachment.actions_named", { name })}>
          <CustomMenu.MenuItem onClick={() => toggleDeleteAttachmentModal(attachmentId)}>
            <div className="flex items-center gap-2">
              <TrashIcon className="size-3.5" />
              <span>{t("common.actions.delete")}</span>
            </div>
          </CustomMenu.MenuItem>
        </CustomMenu>
      )}
    </div>
  );

  return (
    <div
      data-attachment-id={attachmentId}
      className={cn(
        "group min-w-0 rounded-lg border border-subtle bg-surface-1",
        isImage ? "overflow-hidden" : "flex items-center gap-3 px-3 py-2"
      )}
    >
      {isImage ? (
        <>
          <button
            type="button"
            disabled={!url}
            onClick={() => onPreview(attachmentId)}
            aria-label={t("attachment.preview_named", { name })}
            className="focus-visible:outline-accent-primary block w-full cursor-zoom-in text-left focus-visible:outline-2"
          >
            <span className="flex aspect-[4/3] w-full items-center justify-center overflow-hidden border-b border-subtle bg-layer-1">
              {failed || !thumbnailUrl ? (
                <ImageOff className="size-8 text-tertiary" />
              ) : (
                <img
                  src={thumbnailUrl}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="size-full object-contain p-2"
                  onError={() => setFailed(true)}
                />
              )}
            </span>
            <span className="block px-3 pt-3">
              <span className="line-clamp-2 text-13 font-medium break-all text-primary" title={name}>
                {name}
              </span>
            </span>
          </button>
          <div className="px-3 pt-1">{uploadTime}</div>
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <span className="text-12 text-tertiary">{convertBytesToSize(attachment.attributes.size)}</span>
            <div className="flex items-center gap-1">
              {attachment.created_by && (
                <span title={uploader}>
                  <ButtonAvatars showTooltip userIds={attachment.created_by} />
                </span>
              )}
              {actions}
            </div>
          </div>
        </>
      ) : (
        <>
          <span className="shrink-0">{getFileIcon(getFileExtension(name), 24)}</span>
          <a
            href={url}
            download={name}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-visible:outline-accent-primary min-w-0 flex-1 rounded focus-visible:outline-2"
          >
            <span className="block truncate text-13 font-medium text-primary" title={name}>
              {name}
            </span>
            <span className="text-12 text-tertiary">{convertBytesToSize(attachment.attributes.size)}</span>
            {uploadTime}
          </a>
          {attachment.created_by && (
            <span title={uploader}>
              <ButtonAvatars showTooltip userIds={attachment.created_by} />
            </span>
          )}
          {actions}
        </>
      )}
    </div>
  );
});
