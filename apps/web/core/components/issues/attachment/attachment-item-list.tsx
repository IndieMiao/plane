/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import type { FileRejection } from "react-dropzone";
import { useDropzone } from "react-dropzone";
import { UploadCloud } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssueServiceType } from "@plane/types";
import { ImagePreview } from "@plane/ui";
import { cn, getFileURL } from "@plane/utils";
import { isAttachmentImage } from "./attachment-image";
import { EIssueServiceType } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// plane web hooks
import { useFileSize } from "@/plane-web/hooks/use-file-size";
// types
import type { TAttachmentHelpers } from "../issue-detail-widgets/attachments/helper";
// components
import { IssueAttachmentsListItem } from "./attachment-list-item";
import { IssueAttachmentsUploadItem } from "./attachment-list-upload-item";
// types
import { IssueAttachmentDeleteModal } from "./delete-attachment-modal";

type TIssueAttachmentItemList = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  attachmentHelpers: TAttachmentHelpers;
  disabled?: boolean;
  issueServiceType?: TIssueServiceType;
};

export const IssueAttachmentItemList = observer(function IssueAttachmentItemList(props: TIssueAttachmentItemList) {
  const {
    workspaceSlug,
    projectId,
    issueId,
    attachmentHelpers,
    disabled,
    issueServiceType = EIssueServiceType.ISSUES,
  } = props;
  const { t } = useTranslation();
  // states
  const [isUploading, setIsUploading] = useState(false);
  const [filter, setFilter] = useState<"all" | "images" | "files">("all");
  const [previewId, setPreviewId] = useState<string | null>(null);
  useEffect(() => {
    setFilter("all");
    setPreviewId(null);
  }, [issueId]);
  // store hooks
  const {
    attachment: { getAttachmentsByIssueId, getAttachmentById },
    attachmentDeleteModalId,
    toggleDeleteAttachmentModal,
    fetchActivities,
  } = useIssueDetail(issueServiceType);
  const { operations: attachmentOperations, snapshot: attachmentSnapshot } = attachmentHelpers;
  const { create: createAttachment } = attachmentOperations;
  const { uploadStatus } = attachmentSnapshot;
  // file size
  const { maxFileSize } = useFileSize();
  // derived values
  const issueAttachments = getAttachmentsByIssueId(issueId) ?? [];
  const attachments = issueAttachments.map(getAttachmentById).filter((item) => item !== undefined);
  const images = attachments.filter(isAttachmentImage);
  const files = attachments.filter((item) => !isAttachmentImage(item));
  const previewImages = images.map((item) => ({
    id: item.id,
    src: getFileURL(item.asset_url) ?? "",
    name: item.attributes.name,
  }));

  // handlers
  const handleFetchPropertyActivities = useCallback(() => {
    fetchActivities(workspaceSlug, projectId, issueId);
  }, [fetchActivities, workspaceSlug, projectId, issueId]);

  const onDrop = useCallback(
    async (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      if (rejectedFiles.length > 0) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: t("toast.error"),
          message: `${rejectedFiles.map(({ file }) => file.name).join(", ")}: ${t("attachment.file_size_limit", { size: maxFileSize / 1024 / 1024 })}`,
        });
      }

      if (acceptedFiles.length === 0 || !workspaceSlug) return;

      setIsUploading(true);
      const results = await Promise.allSettled(acceptedFiles.map((file) => createAttachment(file)));
      if (results.some((result) => result.status === "rejected")) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: t("toast.error"),
          message: t("attachment.error"),
        });
      }
      handleFetchPropertyActivities();
      setIsUploading(false);
    },
    [createAttachment, maxFileSize, workspaceSlug, handleFetchPropertyActivities, t]
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    maxSize: maxFileSize,
    multiple: true,
    noClick: true,
    noKeyboard: true,
    disabled: isUploading || disabled,
  });

  return (
    <div className="@container space-y-3 py-3">
      {previewId && previewImages.some((image) => image.id === previewId) && (
        <ImagePreview
          key={previewId}
          images={previewImages}
          initialId={previewId}
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
      {attachmentDeleteModalId && issueAttachments.includes(attachmentDeleteModalId) && (
        <IssueAttachmentDeleteModal
          isOpen
          onClose={() => toggleDeleteAttachmentModal(null)}
          attachmentOperations={attachmentOperations}
          attachmentId={attachmentDeleteModalId}
          issueServiceType={issueServiceType}
        />
      )}
      {attachments.length > 0 && (
        <div role="group" aria-label={t("attachment.filter")} className="flex flex-wrap gap-1">
          {(
            [
              ["all", attachments.length],
              ["images", images.length],
              ["files", files.length],
            ] as const
          ).map(([key, count]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              aria-pressed={filter === key}
              className={cn(
                "focus-visible:outline-accent-primary rounded-md px-3 py-1.5 text-12 focus-visible:outline-2",
                filter === key ? "bg-layer-2 font-medium text-primary" : "text-tertiary hover:bg-layer-1"
              )}
            >
              {t(`attachment.${key}`)} <span className="ml-1 tabular-nums">{count}</span>
            </button>
          ))}
        </div>
      )}
      {uploadStatus?.map((status) => (
        <IssueAttachmentsUploadItem key={status.id} uploadStatus={status} />
      ))}
      <div {...getRootProps()} className="relative min-h-12 space-y-3">
        <input {...getInputProps()} />
        {isDragActive && (
          <div className="absolute inset-0 z-30 flex min-h-32 items-center justify-center rounded-lg border border-dashed border-accent-strong bg-surface-2/90">
            <UploadCloud className="mr-2 size-6" />
            <span>{t("attachment.drag_and_drop")}</span>
          </div>
        )}
        {filter !== "files" && images.length > 0 && (
          <div className="grid grid-cols-1 gap-3 @min-[400px]:grid-cols-2 @min-[680px]:grid-cols-3 @min-[950px]:grid-cols-4">
            {images.map((image) => (
              <IssueAttachmentsListItem
                key={image.id}
                attachmentId={image.id}
                disabled={disabled}
                issueServiceType={issueServiceType}
                onPreview={setPreviewId}
              />
            ))}
          </div>
        )}
        {filter !== "images" && files.length > 0 && (
          <div className="space-y-2">
            {files.map((file) => (
              <IssueAttachmentsListItem
                key={file.id}
                attachmentId={file.id}
                disabled={disabled}
                issueServiceType={issueServiceType}
                onPreview={setPreviewId}
              />
            ))}
          </div>
        )}
        {attachments.length === 0 && (
          <div className="rounded-lg border border-dashed border-subtle p-6 text-center text-13 text-tertiary">
            <p>{t("attachment.empty")}</p>
            {!disabled && (
              <button
                type="button"
                onClick={open}
                disabled={isUploading}
                className="mt-3 rounded-md border border-subtle px-3 py-2 text-primary hover:bg-layer-1"
              >
                {t("common.attach")}
              </button>
            )}
          </div>
        )}
        {((filter === "images" && images.length === 0) || (filter === "files" && files.length === 0)) && (
          <p className="py-5 text-center text-13 text-tertiary">{t("attachment.no_matching_files")}</p>
        )}
      </div>
    </div>
  );
});
