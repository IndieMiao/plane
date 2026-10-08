/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Dialog } from "@headlessui/react";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { ChevronDownIcon, ProjectIcon } from "@plane/propel/icons";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EModalWidth, Input, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
import { ProjectDropdown } from "@/components/dropdowns/project/dropdown";
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
import { WorkspaceService } from "@/services/workspace.service";
import { VirtualUserJobTitleSelect } from "./virtual-user-job-title-select";

const workspaceService = new WorkspaceService();
const translationPrefix = "workspace_settings.settings.members.virtual_user";

type Props = {
  workspaceSlug: string;
  onClose: () => void;
};

export const CreateVirtualUserModal = observer(function CreateVirtualUserModal({ workspaceSlug, onClose }: Props) {
  const { t } = useTranslation();
  const [displayName, setDisplayName] = useState("");
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [isJobTitleSaving, setIsJobTitleSaving] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    workspace: { fetchWorkspaceMembers },
    project: { fetchProjectMembers },
  } = useMember();
  const { getProjectById } = useProject();
  const projectLabel = projectIds.length
    ? projectIds.map((id) => getProjectById(id)?.name ?? t("loading")).join(", ")
    : t(`${translationPrefix}.select_projects`);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!displayName.trim() || isSubmitting || isJobTitleSaving) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await workspaceService.createVirtualUser(workspaceSlug, {
        display_name: displayName.trim(),
        project_ids: projectIds,
        job_titles: jobTitles,
      });
    } catch (err: unknown) {
      const details = err as
        | { display_name?: string[]; project_ids?: string[]; job_titles?: string[]; error?: string }
        | undefined;
      setError(
        details?.display_name?.[0] ??
          details?.project_ids?.[0] ??
          details?.job_titles?.[0] ??
          details?.error ??
          t(`${translationPrefix}.error`)
      );
      setIsSubmitting(false);
      return;
    }

    // A refresh failure must not encourage creating the same identity again.
    const refreshes = await Promise.allSettled([
      fetchWorkspaceMembers(workspaceSlug),
      ...projectIds.map((projectId) => fetchProjectMembers(workspaceSlug, projectId)),
    ]);
    setToast({
      type: TOAST_TYPE.SUCCESS,
      title: t(`${translationPrefix}.created`),
      message: refreshes.some((result) => result.status === "rejected")
        ? t(`${translationPrefix}.refresh_hint`)
        : t(`${translationPrefix}.success`),
    });
    onClose();
  };

  return (
    <ModalCore isOpen handleClose={() => !isSubmitting && !isJobTitleSaving && onClose()} width={EModalWidth.XL}>
      <form onSubmit={handleSubmit} className="space-y-5 p-6">
        <div className="space-y-2">
          <Dialog.Title as="h3" className="text-h3-medium">
            {t(`${translationPrefix}.create`)}
          </Dialog.Title>
          <Dialog.Description className="text-body-sm-regular text-secondary">
            {t(`${translationPrefix}.description`)}
          </Dialog.Description>
        </div>
        <div className="space-y-2">
          <label htmlFor="virtual-user-name" className="block text-body-sm-medium">
            {t(`${translationPrefix}.name`)}
          </label>
          <Input
            id="virtual-user-name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder={t(`${translationPrefix}.placeholder`)}
            maxLength={255}
            required
            disabled={isSubmitting}
            className="h-10 w-full"
          />
        </div>
        <div className="space-y-2">
          <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
            <div className="min-w-0 space-y-2">
              <p className="text-body-sm-medium">{t(`${translationPrefix}.projects`)}</p>
              <ProjectDropdown
                multiple
                value={projectIds}
                onChange={setProjectIds}
                disabled={isSubmitting}
                placeholder={t(`${translationPrefix}.select_projects`)}
                buttonVariant="border-with-text"
                className="h-10 w-full"
                buttonContainerClassName="h-10 w-full rounded-md focus-visible:ring-2 focus-visible:ring-accent-primary/20"
                button={
                  <span
                    className={cn(
                      "flex h-10 w-full min-w-0 items-center gap-2 rounded-md border border-subtle bg-surface-1 px-3 text-body-sm-regular transition-colors",
                      projectIds.length ? "text-primary" : "text-placeholder",
                      isSubmitting ? "opacity-50" : "hover:bg-layer-transparent-hover"
                    )}
                  >
                    <ProjectIcon className="size-4 shrink-0 text-tertiary" />
                    <span className="min-w-0 flex-1 truncate text-left" title={projectLabel}>
                      {projectLabel}
                    </span>
                    <ChevronDownIcon className="size-4 shrink-0 text-secondary" />
                  </span>
                }
              />
              <p className="text-body-xs-regular leading-5 text-tertiary">{t(`${translationPrefix}.projects_hint`)}</p>
            </div>
            <VirtualUserJobTitleSelect
              workspaceSlug={workspaceSlug}
              value={jobTitles}
              onChange={setJobTitles}
              onPendingChange={setIsJobTitleSaving}
              disabled={isSubmitting}
            />
          </div>
        </div>
        {error && (
          <p role="alert" className="text-body-sm-regular text-danger-primary">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 border-t border-subtle pt-4">
          <Button
            variant="secondary"
            size="lg"
            type="button"
            disabled={isSubmitting || isJobTitleSaving}
            onClick={onClose}
          >
            {t("cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="lg"
            loading={isSubmitting}
            disabled={!displayName.trim() || isSubmitting || isJobTitleSaving}
          >
            {t(`${translationPrefix}.create`)}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
});
