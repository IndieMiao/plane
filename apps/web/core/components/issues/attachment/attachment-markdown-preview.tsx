/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Dialog } from "@headlessui/react";
import { Download, FileText, LoaderCircle, X } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import type { TIssueAttachment } from "@plane/types";
import { convertBytesToSize, getFileURL } from "@plane/utils";
import { fetchAttachmentMarkdown, MarkdownPreviewError, MAX_MARKDOWN_PREVIEW_BYTES } from "./attachment-markdown";

const AttachmentMarkdownContent = lazy(() => import("./attachment-markdown-content"));
type LoadState =
  | { status: "loading" }
  | { status: "ready"; content: string }
  | { status: "error"; reason: "too_large" | "invalid_content" | "request" };

export function AttachmentMarkdownPreview({
  attachment,
  onClose,
}: {
  attachment: TIssueAttachment;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  const url = getFileURL(attachment.asset_url);
  const name = attachment.attributes.name;
  const size = attachment.attributes.size;

  useEffect(() => {
    if (!url || size > MAX_MARKDOWN_PREVIEW_BYTES) {
      setState({ status: "error", reason: !url ? "request" : "too_large" });
      return;
    }
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 30_000);
    setState({ status: "loading" });
    fetchAttachmentMarkdown(url, controller.signal)
      .then((content) => {
        if (active) setState({ status: "ready", content });
        return content;
      })
      .catch((error: unknown) => {
        if (active)
          setState({ status: "error", reason: error instanceof MarkdownPreviewError ? error.reason : "request" });
      })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [url, size, attempt]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [onClose]);

  const loading = (
    <div role="status" className="flex justify-center gap-2 py-16 text-secondary">
      <LoaderCircle className="size-5 animate-spin" />
      {t("loading")}
    </div>
  );
  const buttonClass =
    "focus-visible:outline-accent-primary grid size-9 shrink-0 place-items-center rounded-md text-secondary hover:bg-layer-2 focus-visible:outline-2";
  return (
    <Dialog
      open
      onClose={onClose}
      initialFocus={closeRef}
      className="work-item-markdown-preview fixed inset-0 z-[100]"
      data-prevent-outside-click
    >
      <div className="fixed inset-0 bg-black/60" aria-hidden="true" />
      <div className="fixed inset-0 p-2 sm:p-6">
        <Dialog.Panel className="shadow-xl mx-auto flex h-full min-h-0 w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-subtle bg-surface-1">
          <header className="flex shrink-0 items-center gap-3 border-b border-subtle px-4 py-3 sm:px-6">
            <FileText className="size-5 shrink-0 text-secondary" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-14 font-medium text-primary" title={name}>
                {name}
              </Dialog.Title>
              <p className="mt-0.5 text-12 text-tertiary">
                {t("attachment.markdown_preview")} · {convertBytesToSize(size)}
              </p>
            </div>
            <a
              href={url}
              download={name}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonClass}
              aria-label={t("attachment.download_named", { name })}
              title={t("attachment.download")}
            >
              <Download className="size-4" />
            </a>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className={buttonClass}
              aria-label={t("close")}
              title={t("close")}
            >
              <X className="size-5" />
            </button>
          </header>
          <div className="vertical-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <article className="mx-auto w-full max-w-[800px] px-5 py-8 sm:px-10 sm:py-12">
              {state.status === "loading" && loading}
              {state.status === "error" && (
                <div role="alert" className="space-y-4 py-12 text-center text-14 text-secondary">
                  <p>
                    {t(
                      state.reason === "too_large"
                        ? "attachment.markdown_too_large"
                        : state.reason === "invalid_content"
                          ? "attachment.markdown_invalid"
                          : "attachment.markdown_error"
                    )}
                  </p>
                  {state.reason === "request" && (
                    <button
                      type="button"
                      onClick={() => setAttempt((value) => value + 1)}
                      className="rounded-md border border-subtle px-3 py-2 hover:bg-layer-1"
                    >
                      {t("attachment.retry_preview")}
                    </button>
                  )}
                </div>
              )}
              {state.status === "ready" &&
                (state.content.trim() ? (
                  <Suspense fallback={loading}>
                    <AttachmentMarkdownContent content={state.content} />
                  </Suspense>
                ) : (
                  <p className="py-12 text-center text-14 text-tertiary">{t("attachment.markdown_empty")}</p>
                ))}
            </article>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
