/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { CloseIcon } from "@plane/propel/icons";
import { EPillSize, EPillVariant, Pill } from "@plane/propel/pill";
import { cn } from "@plane/utils";

type Props = {
  values: string[];
  onRemove?: (name: string) => void;
  disabled?: boolean;
  className?: string;
};

export function VirtualUserJobTitleTags({ values, onRemove, disabled, className }: Props) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex min-w-0 flex-wrap gap-1.5", className)}>
      {values.map((title) => (
        <Pill key={title} variant={EPillVariant.PRIMARY} size={EPillSize.SM} className="max-w-full gap-1" title={title}>
          <span className="min-w-0 truncate">{title}</span>
          {onRemove && (
            <button
              type="button"
              disabled={disabled}
              aria-label={`${t("workspace_settings.settings.members.virtual_user.remove_job_title")} ${title}`}
              className="focus-visible:outline-accent-primary grid size-4 shrink-0 place-items-center rounded-full hover:bg-accent-primary/10 focus-visible:outline-2 disabled:opacity-50"
              onMouseDown={(event) => event.preventDefault()}
              onClick={(event) => {
                event.stopPropagation();
                onRemove(title);
              }}
            >
              <CloseIcon className="size-3" aria-hidden="true" />
            </button>
          )}
        </Pill>
      ))}
    </div>
  );
}
