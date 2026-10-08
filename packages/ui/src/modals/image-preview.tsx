/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Dialog } from "@headlessui/react";
import { ChevronLeft, ChevronRight, Download, ImageOff, Minus, Plus, RotateCcw, X } from "lucide-react";

export type TImagePreviewItem = { id: string; src: string; name: string; downloadSrc?: string };
export type TImagePreviewLabels = {
  close: string;
  previous: string;
  next: string;
  zoomIn: string;
  zoomOut: string;
  reset: string;
  download: string;
  error: string;
};
const defaultLabels: TImagePreviewLabels = {
  close: "Close image preview",
  previous: "Previous image",
  next: "Next image",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  reset: "Fit to screen",
  download: "Download image",
  error: "This image could not be loaded.",
};
export const ImagePreviewLabelsContext = createContext<TImagePreviewLabels | null>(null);

type Props = { images: TImagePreviewItem[]; initialId: string; onClose: () => void; labels?: TImagePreviewLabels };

export function ImagePreview({ images, initialId, onClose, labels: customLabels }: Props) {
  const contextLabels = useContext(ImagePreviewLabelsContext);
  const labels = customLabels ?? contextLabels ?? defaultLabels;
  const [selectedId, setSelectedId] = useState(initialId);
  const index = Math.max(
    0,
    images.findIndex((image) => image.id === selectedId)
  );
  const image = images[index];
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const reset = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    drag.current = null;
  };
  const navigate = (direction: number) => {
    const next = images[index + direction];
    if (!next) return;
    setSelectedId(next.id);
    reset();
    setFailed(false);
    setLoading(true);
  };
  const changeZoom = (amount: number) => {
    setZoom((value) => Math.min(4, Math.max(0.5, value + amount)));
    setOffset({ x: 0, y: 0 });
  };
  // Capture Escape before the surrounding work-item peek handles it.
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (!["Escape", "ArrowLeft", "ArrowRight", "+", "=", "-", "0"].includes(event.key)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") navigate(-1);
      if (event.key === "ArrowRight") navigate(1);
      if (event.key === "+" || event.key === "=") changeZoom(0.25);
      if (event.key === "-") changeZoom(-0.25);
      if (event.key === "0") reset();
    };
    window.addEventListener("keydown", keydown, true);
    return () => window.removeEventListener("keydown", keydown, true);
  });

  if (!image) return null;
  const buttonClass =
    "grid size-10 shrink-0 place-items-center rounded-md text-white/80 hover:bg-white/15 hover:text-white focus-visible:outline-2 focus-visible:outline-white disabled:opacity-30";
  return (
    <Dialog
      open
      onClose={onClose}
      initialFocus={closeRef}
      className="work-item-image-preview fixed inset-0 z-[100]"
      data-prevent-outside-click
    >
      <div className="fixed inset-0 bg-black/95" aria-hidden="true" />
      <div className="fixed inset-0 p-3 sm:p-5">
        <Dialog.Panel className="flex h-full min-h-0 w-full flex-col text-white">
          <div className="flex shrink-0 items-center gap-2 pb-3">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-14 font-medium" title={image.name}>
                {image.name}
              </Dialog.Title>
              <p className="mt-1 text-12 text-white/60">
                {index + 1} / {images.length}
              </p>
            </div>
            <a
              href={image.downloadSrc ?? image.src}
              download={image.name}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonClass}
              aria-label={labels.download}
              title={labels.download}
            >
              <Download className="size-5" />
            </a>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className={buttonClass}
              aria-label={labels.close}
              title={labels.close}
            >
              <X className="size-5" />
            </button>
          </div>
          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
            {images.length > 1 && (
              <button
                type="button"
                className={`${buttonClass} absolute left-0 z-10 bg-black/60`}
                disabled={index === 0}
                onClick={() => navigate(-1)}
                aria-label={labels.previous}
              >
                <ChevronLeft className="size-6" />
              </button>
            )}
            <div
              role="presentation"
              className="flex size-full touch-none items-center justify-center overflow-hidden"
              style={{ cursor: zoom > 1 ? "grab" : "default" }}
              onPointerDown={(event) => {
                if (zoom <= 1 || event.button !== 0) return;
                event.currentTarget.setPointerCapture(event.pointerId);
                drag.current = { x: event.clientX, y: event.clientY, left: offset.x, top: offset.y };
              }}
              onPointerMove={(event) => {
                if (drag.current)
                  setOffset({
                    x: drag.current.left + event.clientX - drag.current.x,
                    y: drag.current.top + event.clientY - drag.current.y,
                  });
              }}
              onPointerUp={() => {
                drag.current = null;
              }}
              onPointerCancel={() => {
                drag.current = null;
              }}
            >
              {failed ? (
                <div role="alert" className="flex flex-col items-center gap-3 text-white/70">
                  <ImageOff className="size-9" />
                  <p>{labels.error}</p>
                </div>
              ) : (
                <img
                  key={image.id}
                  src={image.src}
                  alt={image.name}
                  draggable={false}
                  className="max-h-full max-w-full object-contain select-none"
                  style={{
                    transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
                    opacity: loading ? 0 : 1,
                  }}
                  onLoad={() => setLoading(false)}
                  onError={() => {
                    setFailed(true);
                    setLoading(false);
                  }}
                />
              )}
              {loading && !failed && (
                <span
                  className="absolute size-7 animate-spin rounded-full border-2 border-white/30 border-t-white"
                  role="status"
                  aria-label={image.name}
                />
              )}
            </div>
            {images.length > 1 && (
              <button
                type="button"
                className={`${buttonClass} absolute right-0 z-10 bg-black/60`}
                disabled={index === images.length - 1}
                onClick={() => navigate(1)}
                aria-label={labels.next}
              >
                <ChevronRight className="size-6" />
              </button>
            )}
          </div>
          <div className="mt-3 flex shrink-0 items-center justify-center gap-2">
            <button
              type="button"
              className={buttonClass}
              disabled={zoom <= 0.5 || failed}
              onClick={() => changeZoom(-0.25)}
              aria-label={labels.zoomOut}
            >
              <Minus className="size-5" />
            </button>
            <span className="w-12 text-center text-13" aria-live="polite">
              {Math.round(zoom * 100)}%
            </span>
            <button
              type="button"
              className={buttonClass}
              disabled={zoom >= 4 || failed}
              onClick={() => changeZoom(0.25)}
              aria-label={labels.zoomIn}
            >
              <Plus className="size-5" />
            </button>
            <button
              type="button"
              className={buttonClass}
              onClick={reset}
              aria-label={labels.reset}
              title={labels.reset}
            >
              <RotateCcw className="size-4" />
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
