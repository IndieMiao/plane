/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useState } from "react";
import { useDropzone } from "react-dropzone";
import { MAX_FILE_SIZE } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { UserCirclePropertyIcon } from "@plane/propel/icons";
import { cn, getFileURL } from "@plane/utils";

const prefix = "workspace_settings.settings.members.virtual_user";

type Props = {
  value: File | null;
  currentUrl?: string | null;
  removed: boolean;
  disabled: boolean;
  onChange: (file: File | null, removed: boolean) => void;
};

export function VirtualUserAvatarPicker({ value, currentUrl, removed, disabled, onChange }: Props) {
  const { t } = useTranslation();
  const inputId = useId();
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!value) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(value);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [value]);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    accept: { "image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"], "image/gif": [".gif"] },
    maxSize: MAX_FILE_SIZE,
    multiple: false,
    disabled,
    noClick: true,
    noKeyboard: true,
    onDropAccepted: (files) => {
      if (!files[0]) return;
      setError(null);
      onChange(files[0], false);
    },
    onDropRejected: () => setError(t(`${prefix}.avatar_invalid`)),
  });
  const src = preview ?? (!removed && currentUrl ? getFileURL(currentUrl) : null);

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-body-sm-medium">
        {t(`${prefix}.avatar`)}
      </label>
      <div
        {...getRootProps()}
        className={cn(
          "flex flex-wrap items-center gap-4 rounded-lg border border-dashed border-subtle p-3",
          isDragActive && "border-accent-strong bg-layer-transparent-hover"
        )}
      >
        <input {...getInputProps({ id: inputId, "aria-label": t(`${prefix}.upload_avatar`) })} />
        <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-full bg-layer-2">
          {src ? (
            <img src={src} alt={t(`${prefix}.avatar_preview`)} className="size-full object-cover" />
          ) : (
            <UserCirclePropertyIcon className="size-10 text-tertiary" aria-hidden="true" />
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" disabled={disabled} onClick={open}>
              {t(src ? `${prefix}.replace_avatar` : `${prefix}.upload_avatar`)}
            </Button>
            {src && (
              <Button
                type="button"
                variant="tertiary"
                size="sm"
                disabled={disabled}
                onClick={() => {
                  setError(null);
                  onChange(null, true);
                }}
              >
                {t(`${prefix}.remove_avatar`)}
              </Button>
            )}
          </div>
          <p className="text-body-xs-regular text-tertiary">{t(`${prefix}.avatar_hint`)}</p>
        </div>
      </div>
      {error && (
        <p role="alert" className="text-body-xs-regular text-danger-primary">
          {error}
        </p>
      )}
    </div>
  );
}
