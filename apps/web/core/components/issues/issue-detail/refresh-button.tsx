/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { IconButton } from "@plane/propel/icon-button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { usePlatformOS } from "@/hooks/use-platform-os";

type Props = { workspaceSlug: string; projectId: string; issueId: string };

export const IssueDetailRefreshButton = observer(function IssueDetailRefreshButton({
  workspaceSlug,
  projectId,
  issueId,
}: Props) {
  const { t } = useTranslation();
  const { isMobile } = usePlatformOS();
  const { issue, attachment } = useIssueDetail();
  const refreshing = issue.getIsRefreshingIssue(issueId);
  const saving =
    issue.getIsSavingIssueDetails(issueId) || !!attachment.getAttachmentsUploadStatusByIssueId(issueId)?.length;
  const label = t(
    refreshing ? "issue.refreshing_details" : saving ? "issue.refresh_wait_for_save" : "issue.refresh_details"
  );

  const handleRefresh = async () => {
    if (refreshing || saving) return;
    const positions = Array.from(document.querySelectorAll<HTMLElement>("[data-work-item-scroll]"))
      .filter(
        (element) => element.closest("[data-work-item-detail-id]")?.getAttribute("data-work-item-detail-id") === issueId
      )
      .map((element) => ({ element, top: element.scrollTop, left: element.scrollLeft }));
    try {
      await issue.refreshIssue(workspaceSlug, projectId, issueId);
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: t("toast.error"), message: t("issue.refresh_failed") });
    } finally {
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          for (const { element, top, left } of positions) {
            if (
              element.isConnected &&
              element.closest("[data-work-item-detail-id]")?.getAttribute("data-work-item-detail-id") === issueId
            ) {
              element.scrollTop = top;
              element.scrollLeft = left;
            }
          }
        })
      );
    }
  };

  return (
    <Tooltip tooltipContent={label} isMobile={isMobile}>
      <span className="inline-flex">
        <IconButton
          type="button"
          variant="secondary"
          size="lg"
          icon={RefreshCw}
          iconClassName={refreshing ? "animate-spin" : ""}
          disabled={refreshing || saving}
          aria-label={label}
          aria-busy={refreshing}
          onClick={handleRefresh}
        />
      </span>
    </Tooltip>
  );
});
