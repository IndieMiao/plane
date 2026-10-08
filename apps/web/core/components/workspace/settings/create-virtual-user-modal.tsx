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
import { VirtualUserAvatarPicker } from "./virtual-user-avatar-picker";

const workspaceService = new WorkspaceService();
const translationPrefix = "workspace_settings.settings.members.virtual_user";

type Props = {
  workspaceSlug: string;
  onClose: () => void;
  member?: { id: string; display_name?: string; avatar_url?: string | null; job_title?: string; job_titles?: string[] };
};

export const VirtualUserModal = observer(function VirtualUserModal({ workspaceSlug, onClose, member }: Props) {
  const { t } = useTranslation();
  const [displayName, setDisplayName] = useState(member?.display_name ?? "");
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [jobTitles, setJobTitles] = useState<string[]>(
    member?.job_titles ?? (member?.job_title ? [member.job_title] : [])
  );
  const [avatar, setAvatar] = useState<File | null>(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [isJobTitleSaving, setIsJobTitleSaving] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    workspace: { fetchWorkspaceMembers, updateVirtualUser },
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
      if (member) {
        await updateVirtualUser(
          workspaceSlug,
          member.id,
          {
            display_name: displayName.trim(),
            job_titles: jobTitles,
            remove_avatar: removeAvatar,
          },
          avatar
        );
      } else {
        await workspaceService.createVirtualUser(
          workspaceSlug,
          {
            display_name: displayName.trim(),
            project_ids: projectIds,
            job_titles: jobTitles,
          },
          avatar
        );
      }
    } catch (err: unknown) {
      const details = err as Record<string, string | string[]> | undefined;
      const detail =
        details?.avatar ??
        details?.display_name ??
        details?.project_ids ??
        details?.job_titles ??
        details?.error ??
        details?.detail;
      setError(
        (Array.isArray(detail) ? detail[0] : detail) ??
          t(member ? `${translationPrefix}.profile_update_error` : `${translationPrefix}.error`)
      );
      setIsSubmitting(false);
      return;
    }

    if (member) {
      setToast({ type: TOAST_TYPE.SUCCESS, title: t(`${translationPrefix}.profile_updated`) });
      onClose();
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
            {t(member ? `${translationPrefix}.edit_profile` : `${translationPrefix}.create`)}
          </Dialog.Title>
          <Dialog.Description className="text-body-sm-regular text-secondary">
            {t(member ? `${translationPrefix}.edit_profile_description` : `${translationPrefix}.description`)}
          </Dialog.Description>
        </div>
        <VirtualUserAvatarPicker
          value={avatar}
          currentUrl={member?.avatar_url}
          removed={removeAvatar}
          disabled={isSubmitting}
          onChange={(file, removed) => {
            setAvatar(file);
            setRemoveAvatar(removed);
          }}
        />
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
          <div className={cn("grid grid-cols-1 items-start gap-4", !member && "sm:grid-cols-2")}>
            {!member && (
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
                <p className="text-body-xs-regular leading-5 text-tertiary">
                  {t(`${translationPrefix}.projects_hint`)}
                </p>
              </div>
            )}
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
            {t(member ? "save" : `${translationPrefix}.create`)}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
});

export const CreateVirtualUserModal = VirtualUserModal;
