/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIssueAttachment } from "@plane/types";

export const MAX_MARKDOWN_PREVIEW_BYTES = 1024 * 1024;

export function isAttachmentMarkdown(attachment: TIssueAttachment): boolean {
  const mimeType = attachment.attributes.type?.split(";")[0].trim().toLowerCase();
  return (
    /\.(md|markdown)$/i.test(attachment.attributes.name) ||
    mimeType === "text/markdown" ||
    mimeType === "text/x-markdown"
  );
}

export class MarkdownPreviewError extends Error {
  constructor(public readonly reason: "too_large" | "invalid_content") {
    super(reason);
    this.name = "MarkdownPreviewError";
  }
}

export async function fetchAttachmentMarkdown(url: string, signal: AbortSignal): Promise<string> {
  const response = await fetch(url, { credentials: "include", signal });
  if (!response.ok) throw new Error(`Attachment request failed: ${response.status}`);
  if (response.headers.get("Content-Type")?.toLowerCase().includes("text/html")) {
    await response.body?.cancel();
    throw new MarkdownPreviewError("invalid_content");
  }
  if (Number(response.headers.get("Content-Length")) > MAX_MARKDOWN_PREVIEW_BYTES) {
    await response.body?.cancel();
    throw new MarkdownPreviewError("too_large");
  }
  if (!response.body) return "";

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      // Consume the stream sequentially so oversized downloads can be stopped immediately.
      // eslint-disable-next-line no-await-in-loop
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_MARKDOWN_PREVIEW_BYTES) {
        // eslint-disable-next-line no-await-in-loop
        await reader.cancel();
        throw new MarkdownPreviewError("too_large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    const encoding =
      bytes[0] === 0xff && bytes[1] === 0xfe
        ? "utf-16le"
        : bytes[0] === 0xfe && bytes[1] === 0xff
          ? "utf-16be"
          : "utf-8";
    const text = new TextDecoder(encoding, { fatal: true }).decode(bytes);
    if (text.includes("\0")) throw new MarkdownPreviewError("invalid_content");
    return text;
  } catch {
    throw new MarkdownPreviewError("invalid_content");
  }
}
