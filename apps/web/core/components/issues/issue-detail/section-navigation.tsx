/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { RefObject } from "react";
import { observer } from "mobx-react";
import { MessageSquarePlus } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";

type Section = "details" | "attachments" | "properties" | "activity";
type Props = {
  issueId: string;
  scopeRef: RefObject<HTMLDivElement>;
  onPropertiesNavigate?: () => void;
  canComment: boolean;
};

export const WorkItemSectionNavigation = observer(function WorkItemSectionNavigation({
  issueId,
  scopeRef,
  onPropertiesNavigate,
  canComment,
}: Props) {
  const { t } = useTranslation();
  const [active, setActive] = useState<Section>("details");
  const {
    issue: { getIssueById },
    attachment: { getAttachmentsCountByIssueId },
    openWidgets,
    setOpenWidgets,
  } = useIssueDetail();
  const { getProjectIdentifierById } = useProject();
  const issue = getIssueById(issueId);
  const count = getAttachmentsCountByIssueId(issueId);
  const identifier = getProjectIdentifierById(issue?.project_id);

  useEffect(() => {
    const scope = scopeRef.current;
    if (!scope) return;
    const scroller = scope.querySelector<HTMLElement>("[data-work-item-scroll]");
    if (!scroller) return;
    scroller.scrollTop = 0;
    setActive("details");
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        let current: Section = "details";
        const top = scroller.getBoundingClientRect().top + 64;
        for (const element of scroller.querySelectorAll<HTMLElement>("[data-work-item-section]")) {
          if (element.closest("[data-work-item-scroll]") !== scroller || !element.getClientRects().length) continue;
          if (element.getBoundingClientRect().top <= top) current = element.dataset.workItemSection as Section;
        }
        if (scroller.scrollTop > 0 && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2)
          current = "activity";
        setActive(current);
      });
    };
    scroller.addEventListener("scroll", update, { passive: true });
    const resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(scroller);
    if (scroller.firstElementChild) resizeObserver.observe(scroller.firstElementChild);
    return () => {
      scroller.removeEventListener("scroll", update);
      resizeObserver.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [issueId, scopeRef]);

  const navigate = (section: Section, comment = false) => {
    if (section === "attachments" && !openWidgets.includes("attachments"))
      setOpenWidgets([...openWidgets, "attachments"]);
    if (section === "properties") onPropertiesNavigate?.();
    requestAnimationFrame(() => {
      const scope = scopeRef.current;
      if (!scope) return;
      const selector = comment ? "[data-work-item-comment]" : `[data-work-item-section="${section}"]`;
      const target = Array.from(scope.querySelectorAll<HTMLElement>(selector)).find((element) => {
        const rect = element.getBoundingClientRect();
        return element.getClientRects().length > 0 && rect.right > 0 && rect.left < window.innerWidth;
      });
      if (!target) return;
      const scroller = target.closest<HTMLElement>("[data-work-item-scroll]");
      if (scroller)
        scroller.scrollTo({
          top:
            section === "details"
              ? 0
              : scroller.scrollTop + target.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 12,
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        });
      setActive(section);
      const focusTarget = comment ? target.querySelector<HTMLElement>('[contenteditable="true"]') : target;
      if (focusTarget) {
        if (!comment) focusTarget.tabIndex = -1;
        focusTarget.focus({ preventScroll: true });
      }
    });
  };

  return (
    <div className="shrink-0 border-b border-subtle bg-surface-1 px-4 pt-2 sm:px-6" data-work-item-navigation>
      <div className="mb-1 flex min-w-0 items-center gap-2 text-12">
        <span className="shrink-0 text-tertiary">
          {identifier}-{issue?.sequence_id}
        </span>
        <span className="truncate text-secondary" title={issue?.name}>
          {issue?.name}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <nav aria-label={t("issue.detail_navigation.label")} className="flex min-w-0 gap-1 overflow-x-auto">
          {(["details", "attachments", "properties", "activity"] as const).map((section) => (
            <button
              type="button"
              key={section}
              onClick={() => navigate(section)}
              aria-current={active === section ? "location" : undefined}
              className={cn(
                "focus-visible:outline-accent-primary shrink-0 border-b-2 px-3 py-2.5 text-13 focus-visible:outline-2",
                active === section
                  ? "border-accent-strong font-medium text-accent-primary"
                  : "border-transparent text-secondary hover:text-primary"
              )}
            >
              {t(`issue.detail_navigation.${section}`)}
              {section === "attachments" && <span className="ml-1.5 text-11 text-tertiary tabular-nums">{count}</span>}
            </button>
          ))}
        </nav>
        {canComment && (
          <button
            type="button"
            onClick={() => navigate("activity", true)}
            title={t("issue.detail_navigation.write_comment")}
            aria-label={t("issue.detail_navigation.write_comment")}
            className="focus-visible:outline-accent-primary flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-12 text-secondary hover:bg-layer-1 focus-visible:outline-2"
          >
            <MessageSquarePlus className="size-4" />
            <span className="hidden sm:inline">{t("issue.detail_navigation.write_comment")}</span>
          </button>
        )}
      </div>
    </div>
  );
});
