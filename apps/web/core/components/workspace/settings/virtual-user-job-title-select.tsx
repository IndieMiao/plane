/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import useSWR from "swr";
import { Combobox } from "@headlessui/react";
import { useTranslation } from "@plane/i18n";
import { CheckIcon, ChevronDownIcon, PlusIcon } from "@plane/propel/icons";
import { cn } from "@plane/utils";
import { WorkspaceService } from "@/services/workspace.service";
import { VirtualUserJobTitleTags } from "./virtual-user-job-title-tags";

const workspaceService = new WorkspaceService();
const prefix = "workspace_settings.settings.members.virtual_user";

type Props = {
  workspaceSlug: string;
  value: string[];
  onChange: (value: string[]) => void;
  onPendingChange: (pending: boolean) => void;
  disabled?: boolean;
};

export function VirtualUserJobTitleSelect({ workspaceSlug, value, onChange, onPendingChange, disabled }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const {
    data: jobTitles,
    error: loadError,
    mutate,
  } = useSWR(["virtual-user-job-titles", workspaceSlug], () =>
    workspaceService.fetchVirtualUserJobTitles(workspaceSlug)
  );
  const name = query.trim();
  const availableTitles = [...new Set([...(jobTitles ?? []), ...value])];
  const options = availableTitles.filter((title) => title.toLocaleLowerCase().includes(name.toLocaleLowerCase()));
  const canCreate = !!name && !availableTitles.some((title) => title.toLocaleLowerCase() === name.toLocaleLowerCase());

  const handleSelect = async (selected: string[]) => {
    if (isSaving || disabled) return;
    setSaveError(null);
    const addedName = selected.find((title) => !availableTitles.includes(title));
    if (!addedName) {
      onChange(selected);
      setQuery("");
      return;
    }
    setIsSaving(true);
    onPendingChange(true);
    try {
      const created = await workspaceService.createVirtualUserJobTitle(workspaceSlug, addedName);
      await mutate((current) => [...new Set([...(current ?? []), created.name])], { revalidate: false });
      onChange([...new Set(selected.map((title) => (title === addedName ? created.name : title)))]);
      setQuery("");
    } catch (err: unknown) {
      const details = err as { name?: string[]; error?: string } | undefined;
      setSaveError(details?.name?.[0] ?? details?.error ?? t(`${prefix}.job_title_error`));
    } finally {
      setIsSaving(false);
      onPendingChange(false);
    }
  };

  return (
    <div className="min-w-0 space-y-2">
      <Combobox
        as="div"
        multiple
        className="space-y-2"
        value={value}
        onChange={handleSelect}
        disabled={disabled || isSaving || !jobTitles}
      >
        <Combobox.Label className="block text-body-sm-medium">{t(`${prefix}.job_title`)}</Combobox.Label>
        <div className="relative">
          <div className="flex min-h-10 items-start rounded-md border border-subtle bg-surface-1 focus-within:border-accent-strong">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 px-2 py-1.5">
              <VirtualUserJobTitleTags
                values={value}
                onRemove={(title) => {
                  onChange(value.filter((selected) => selected !== title));
                  inputRef.current?.focus();
                }}
                disabled={disabled || isSaving}
                className="contents"
              />
              <Combobox.Input
                ref={inputRef}
                className="h-6 min-w-20 flex-1 bg-transparent px-1 text-body-sm-regular outline-none placeholder:text-placeholder disabled:opacity-50"
                displayValue={() => ""}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                maxLength={255}
                placeholder={t(
                  isSaving ? "loading" : value.length ? `${prefix}.add_more_job_titles` : `${prefix}.select_job_title`
                )}
                autoComplete="off"
              />
            </div>
            <Combobox.Button
              className="flex h-10 shrink-0 items-center px-3 text-secondary"
              aria-label={t(`${prefix}.select_job_title`)}
            >
              <ChevronDownIcon className="size-4" />
            </Combobox.Button>
          </div>
          <Combobox.Options className="absolute z-40 mt-1 max-h-60 w-full overflow-auto rounded-md border border-subtle bg-surface-1 p-1 shadow-raised-200">
            {options.map((title) => (
              <Combobox.Option
                key={title}
                value={title}
                className={({ active }) =>
                  cn(
                    "flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-body-sm-regular",
                    active && "bg-layer-transparent-hover"
                  )
                }
              >
                {({ selected }) => (
                  <>
                    <span
                      className={cn(
                        "grid size-4 shrink-0 place-items-center rounded border",
                        selected ? "border-accent-strong bg-accent-primary text-on-color" : "border-strong"
                      )}
                    >
                      {selected && <CheckIcon className="size-3" aria-hidden="true" />}
                    </span>
                    <span className="flex-1 truncate">{title}</span>
                  </>
                )}
              </Combobox.Option>
            ))}
            {canCreate && (
              <Combobox.Option
                value={name}
                className={({ active }) =>
                  cn(
                    "flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-body-sm-regular text-accent-primary",
                    active && "bg-layer-transparent-hover"
                  )
                }
              >
                <PlusIcon className="size-4 shrink-0" />
                <span className="truncate">
                  {t(`${prefix}.add_job_title`)} “{name}”
                </span>
              </Combobox.Option>
            )}
          </Combobox.Options>
        </div>
      </Combobox>
      <p className="text-body-xs-regular leading-5 text-tertiary">{t(`${prefix}.job_title_hint`)}</p>
      {saveError && (
        <p role="alert" className="text-body-xs-regular text-danger-primary">
          {saveError}
        </p>
      )}
      {loadError && (
        <p role="alert" className="text-body-xs-regular text-danger-primary">
          {t(`${prefix}.job_titles_load_error`)}{" "}
          <button type="button" className="underline" onClick={() => void mutate().catch(() => undefined)}>
            {t(`${prefix}.retry`)}
          </button>
        </p>
      )}
    </div>
  );
}
