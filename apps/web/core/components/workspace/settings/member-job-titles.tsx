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
import { EditIcon } from "@plane/propel/icons";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EModalWidth, ModalCore } from "@plane/ui";
import { useMember } from "@/hooks/store/use-member";
import { VirtualUserJobTitleSelect } from "./virtual-user-job-title-select";
import { VirtualUserJobTitleTags } from "./virtual-user-job-title-tags";

const prefix = "workspace_settings.settings.members.virtual_user";

type Member = { id: string; display_name?: string; job_title?: string; job_titles?: string[] };
type Props = { workspaceSlug: string; member: Member; canEdit: boolean; isSuspended: boolean };

function EditMemberJobTitlesModal({
  workspaceSlug,
  member,
  titles,
  onClose,
}: {
  workspaceSlug: string;
  member: Member;
  titles: string[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const {
    workspace: { updateMemberJobTitles },
  } = useMember();
  const [selected, setSelected] = useState(titles);
  const [isSaving, setIsSaving] = useState(false);
  const [isAddingTitle, setIsAddingTitle] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isBusy = isSaving || isAddingTitle;
  const hasChanges = JSON.stringify(selected) !== JSON.stringify(titles);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isBusy || !hasChanges) return;
    setIsSaving(true);
    setError(null);
    try {
      await updateMemberJobTitles(workspaceSlug, member.id, selected);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t(`${prefix}.updated`) });
      onClose();
    } catch (err: unknown) {
      const details = err as { error?: string; detail?: string } | undefined;
      setError(details?.error ?? details?.detail ?? t(`${prefix}.update_error`));
      setIsSaving(false);
    }
  };

  return (
    <ModalCore isOpen width={EModalWidth.LG} handleClose={() => !isBusy && onClose()}>
      <form onSubmit={handleSubmit} className="space-y-5 p-6">
        <div className="space-y-2">
          <Dialog.Title as="h3" className="text-h3-medium">
            {t(`${prefix}.edit`)}
          </Dialog.Title>
          <Dialog.Description className="text-body-sm-regular text-secondary">
            {member.display_name} · {t(`${prefix}.edit_description`)}
          </Dialog.Description>
        </div>
        <VirtualUserJobTitleSelect
          workspaceSlug={workspaceSlug}
          value={selected}
          onChange={setSelected}
          onPendingChange={setIsAddingTitle}
          disabled={isSaving}
        />
        {error && (
          <p role="alert" className="text-body-sm-regular text-danger-primary">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 border-t border-subtle pt-4">
          <Button type="button" variant="secondary" size="lg" disabled={isBusy} onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button type="submit" variant="primary" size="lg" loading={isSaving} disabled={isBusy || !hasChanges}>
            {t("save")}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
}

export const MemberJobTitles = observer(function MemberJobTitles({
  workspaceSlug,
  member,
  canEdit,
  isSuspended,
}: Props) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const titles = member.job_titles ?? (member.job_title ? [member.job_title] : []);
  return (
    <>
      <div className={`flex max-w-72 min-w-36 items-center gap-2 py-1 ${isSuspended ? "opacity-50" : ""}`}>
        <div className="min-w-0 flex-1">{titles.length ? <VirtualUserJobTitleTags values={titles} /> : "—"}</div>
        {canEdit && !isSuspended && (
          <button
            type="button"
            title={t(`${prefix}.edit`)}
            aria-label={`${t(`${prefix}.edit`)} ${member.display_name ?? ""}`}
            className="focus-visible:outline-accent-primary grid size-7 shrink-0 place-items-center rounded text-tertiary hover:bg-layer-transparent-hover hover:text-primary focus-visible:outline-2"
            onClick={() => setIsEditing(true)}
          >
            <EditIcon className="size-3.5" aria-hidden="true" />
          </button>
        )}
      </div>
      {isEditing && canEdit && !isSuspended && (
        <EditMemberJobTitlesModal
          workspaceSlug={workspaceSlug}
          member={member}
          titles={titles}
          onClose={() => setIsEditing(false)}
        />
      )}
    </>
  );
});
