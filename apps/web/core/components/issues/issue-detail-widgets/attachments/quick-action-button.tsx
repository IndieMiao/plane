/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useCallback, useState } from "react";
import { observer } from "mobx-react";
import type { FileRejection } from "react-dropzone";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "@plane/i18n";
import { PlusIcon } from "@plane/propel/icons";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssueServiceType } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// plane web hooks
import { useFileSize } from "@/plane-web/hooks/use-file-size";
// local imports
import { useAttachmentOperations } from "./helper";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  customButton?: React.ReactNode;
  disabled?: boolean;
  issueServiceType: TIssueServiceType;
};

export const IssueAttachmentActionButton = observer(function IssueAttachmentActionButton(props: Props) {
  const { workspaceSlug, projectId, issueId, customButton, disabled = false, issueServiceType } = props;
  const { t } = useTranslation();
  // state
  const [isLoading, setIsLoading] = useState(false);
  // store hooks
  const { setLastWidgetAction, fetchActivities } = useIssueDetail(issueServiceType);
  // file size
  const { maxFileSize } = useFileSize();
  // operations
  const { operations: attachmentOperations } = useAttachmentOperations(
    workspaceSlug,
    projectId,
    issueId,
    issueServiceType
  );
  // handlers
  const handleFetchPropertyActivities = useCallback(() => {
    fetchActivities(workspaceSlug, projectId, issueId);
  }, [fetchActivities, workspaceSlug, projectId, issueId]);

  const onDrop = useCallback(
    async (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      if (rejectedFiles.length > 0) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: "Error!",
          message: `${rejectedFiles.map(({ file }) => file.name).join(", ")}: file must be of ${maxFileSize / 1024 / 1024}MB or less in size.`,
        });
      }

      if (acceptedFiles.length === 0 || !workspaceSlug) return;

      setIsLoading(true);
      const results = await Promise.allSettled(acceptedFiles.map((file) => attachmentOperations.create(file)));
      if (results.some((result) => result.status === "rejected")) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: "Error!",
          message: "Some files could not be attached. Try uploading them again.",
        });
      }
      handleFetchPropertyActivities();
      setLastWidgetAction("attachments");
      setIsLoading(false);
    },
    [attachmentOperations, maxFileSize, workspaceSlug, handleFetchPropertyActivities, setLastWidgetAction]
  );

  const { getRootProps, getInputProps } = useDropzone({
    onDrop,
    maxSize: maxFileSize,
    multiple: true,
    disabled: isLoading || disabled,
  });

  return (
    <div
      role="presentation"
      onClick={(e) => {
        // TODO: Remove extra div and move event propagation to button
        e.stopPropagation();
      }}
    >
      <button {...getRootProps()} type="button" disabled={disabled || isLoading} aria-label={t("attachment.upload")}>
        <input {...getInputProps()} />
        {customButton ? customButton : <PlusIcon className="h-4 w-4" />}
      </button>
    </div>
  );
});
