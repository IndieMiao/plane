/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import Link from "next/link";
import { Controller, useForm } from "react-hook-form";

import { Disclosure } from "@headlessui/react";
// plane imports
import { ROLE, EUserPermissions, EUserPermissionsLevel, MEMBER_TRACKER_ELEMENTS } from "@plane/constants";
import { EditIcon, TrashIcon, SuspendedUserIcon } from "@plane/propel/icons";
import { Pill, EPillVariant, EPillSize } from "@plane/propel/pill";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IUser, IWorkspaceMember } from "@plane/types";
// plane ui
import { CustomSelect, PopoverMenu } from "@plane/ui";
// helpers
import { getFileURL } from "@plane/utils";
// hooks
import { VirtualUserModal } from "./create-virtual-user-modal";
import { useMember } from "@/hooks/store/use-member";
import { useUser, useUserPermissions } from "@/hooks/store/user";

export interface RowData {
  member: IWorkspaceMember;
  role: EUserPermissions;
  is_active: boolean;
}

type NameProps = {
  rowData: RowData;
  workspaceSlug: string;
  isAdmin: boolean;
  currentUser: IUser | undefined;
  setRemoveMemberModal: (rowData: RowData) => void;
};

type AccountTypeProps = {
  rowData: RowData;
  workspaceSlug: string;
};

export function NameColumn(props: NameProps) {
  const { rowData, workspaceSlug, isAdmin, currentUser, setRemoveMemberModal } = props;
  const { t } = useTranslation();
  // derived values
  const { avatar_url, display_name, email, first_name, id, last_name } = rowData.member;
  const isSuspended = rowData.is_active === false;
  const [isEditing, setIsEditing] = useState(false);

  return (
    <>
      <Disclosure>
        {() => (
          <div className="group relative">
            <div className="flex w-72 items-center justify-between gap-x-4 gap-y-2">
              <div className="flex flex-1 items-center gap-x-2 gap-y-2">
                {isSuspended ? (
                  <div className="rounded-full bg-layer-1">
                    <SuspendedUserIcon className="size-6 text-placeholder" />
                  </div>
                ) : avatar_url && avatar_url.trim() !== "" ? (
                  <Link href={`/${workspaceSlug}/profile/${id}`}>
                    <span className="relative flex size-6 items-center justify-center rounded-full text-on-color capitalize">
                      <img
                        src={getFileURL(avatar_url)}
                        className="absolute top-0 left-0 h-full w-full rounded-full object-cover"
                        alt={display_name || email}
                      />
                    </span>
                  </Link>
                ) : (
                  <Link href={`/${workspaceSlug}/profile/${id}`}>
                    <span className="relative flex size-6 items-center justify-center rounded-full bg-layer-3 text-11 text-tertiary capitalize">
                      {(email ?? display_name ?? "?")[0]}
                    </span>
                  </Link>
                )}
                <span className={isSuspended ? "text-placeholder" : ""}>
                  {first_name} {last_name}
                </span>
                {rowData.member.is_virtual && (
                  <Pill variant={EPillVariant.DEFAULT} size={EPillSize.XS}>
                    {t("workspace_settings.settings.members.virtual_user.label")}
                  </Pill>
                )}
              </div>

              {!isSuspended && (isAdmin || id === currentUser?.id) && (
                <PopoverMenu
                  data={isAdmin && rowData.member.is_virtual ? ["edit", "remove"] : ["remove"]}
                  keyExtractor={(item) => item}
                  popoverClassName="!w-auto shrink-0 justify-end"
                  buttonClassName="outline-none	origin-center rotate-90 size-8 aspect-square flex-shrink-0 grid place-items-center opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                  render={(item) =>
                    item === "edit" ? (
                      <button
                        type="button"
                        className="flex w-full items-center gap-x-3 rounded px-1 py-1.5 text-left hover:bg-layer-transparent-hover"
                        onClick={() => setIsEditing(true)}
                      >
                        <EditIcon className="size-3.5" />{" "}
                        {t("workspace_settings.settings.members.virtual_user.edit_profile")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="flex w-full cursor-pointer items-center gap-x-3 rounded px-1 py-1.5 text-left hover:bg-layer-transparent-hover"
                        onClick={() => setRemoveMemberModal(rowData)}
                        data-ph-element={MEMBER_TRACKER_ELEMENTS.WORKSPACE_MEMBER_TABLE_CONTEXT_MENU}
                      >
                        <TrashIcon className="size-3.5 align-middle" /> {id === currentUser?.id ? "Leave " : "Remove "}
                      </button>
                    )
                  }
                />
              )}
            </div>
          </div>
        )}
      </Disclosure>
      {isEditing && isAdmin && !isSuspended && rowData.member.is_virtual && (
        <VirtualUserModal workspaceSlug={workspaceSlug} member={rowData.member} onClose={() => setIsEditing(false)} />
      )}
    </>
  );
}

export const AccountTypeColumn = observer(function AccountTypeColumn(props: AccountTypeProps) {
  const { rowData, workspaceSlug } = props;
  // form info
  const {
    control,
    formState: { errors },
  } = useForm();
  // store hooks
  const { allowPermissions } = useUserPermissions();

  const {
    workspace: { updateMember },
  } = useMember();
  const { data: currentUser } = useUser();

  // derived values
  const isCurrentUser = currentUser?.id === rowData.member.id;
  const isAdminRole = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const isRoleNonEditable = isCurrentUser || !isAdminRole;
  const isSuspended = rowData.is_active === false;

  return (
    <>
      {isSuspended ? (
        <div className="flex w-32">
          <Pill variant={EPillVariant.DEFAULT} size={EPillSize.SM} className="border-none">
            Suspended
          </Pill>
        </div>
      ) : isRoleNonEditable ? (
        <div className="flex w-32">
          <span>{ROLE[rowData.role]}</span>
        </div>
      ) : (
        <Controller
          name="role"
          control={control}
          rules={{ required: "Role is required." }}
          render={({ field: { value } }) => (
            <CustomSelect
              value={value as EUserPermissions}
              onChange={async (value: EUserPermissions) => {
                if (!workspaceSlug) return;
                try {
                  await updateMember(workspaceSlug.toString(), rowData.member.id, {
                    role: value as unknown as EUserPermissions,
                  });
                } catch (err: unknown) {
                  const error = err as { error?: string | string[] };
                  const errorString = Array.isArray(error?.error) ? error.error[0] : error?.error;

                  setToast({
                    type: TOAST_TYPE.ERROR,
                    title: "Error!",
                    message: errorString ?? "An error occurred while updating member role. Please try again.",
                  });
                }
              }}
              label={
                <div className="flex">
                  <span>{ROLE[rowData.role]}</span>
                </div>
              }
              buttonClassName={`!px-0 !justify-start hover:bg-surface-1 ${errors.role ? "border-danger-strong" : "border-none"}`}
              className="w-32 rounded-md p-0"
              input
            >
              {Object.keys(ROLE).map((item) => (
                <CustomSelect.Option key={item} value={item as unknown as EUserPermissions}>
                  {ROLE[item as unknown as keyof typeof ROLE]}
                </CustomSelect.Option>
              ))}
            </CustomSelect>
          )}
        />
      )}
    </>
  );
});
