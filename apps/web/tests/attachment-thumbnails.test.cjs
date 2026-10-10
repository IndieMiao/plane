/* Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test, mock } = require("node:test");
const ts = require("typescript");

process.env.TZ = "Asia/Shanghai";
const dateUtils = {};
const dateSource = readFileSync(resolve(__dirname, "../../../packages/utils/src/datetime.ts"), "utf8");
const dateCompiled = ts.transpileModule(dateSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
new Function("require", "exports", dateCompiled.outputText)(require, dateUtils);
const markdownUtils = {};
const markdownSource = readFileSync(
  resolve(__dirname, "../core/components/issues/attachment/attachment-markdown.ts"),
  "utf8"
);
new Function(
  "require",
  "exports",
  ts.transpileModule(markdownSource, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
)(require, markdownUtils);

const attachment = {
  id: "image",
  attributes: { name: "screen.png", type: "image/png", size: 1024 },
  asset_url: "/original.png",
  thumbnail_url: "/thumbnail.webp",
  created_at: "2026-10-09T12:34:00Z",
  updated_at: "2026-10-10T18:00:00Z",
  created_by: "uploader",
};

function renderItem(item = attachment, failed = false) {
  const onPreview = mock.fn();
  const formatDate = mock.fn(dateUtils.renderFormattedDate);
  const imports = {
    react: { useState: () => [failed, () => {}] },
    "react/jsx-runtime": {
      jsx: (type, props) => ({ type, props }),
      jsxs: (type, props) => ({ type, props }),
      Fragment: "fragment",
    },
    "mobx-react": { observer: (fn) => fn },
    "lucide-react": { Download: "Download", ImageOff: "ImageOff" },
    "@plane/i18n": { useTranslation: () => ({ t: (key, values) => (values?.date ? `Uploaded ${values.date}` : key) }) },
    "@plane/propel/icons": { TrashIcon: "TrashIcon" },
    "@plane/types": { EIssueServiceType: { ISSUES: "issues" } },
    "@plane/ui": { CustomMenu: Object.assign(() => null, { MenuItem: "MenuItem" }) },
    "@plane/utils": {
      cn: (...values) => values.join(" "),
      convertBytesToSize: () => "1 KB",
      getFileExtension: () => "png",
      getFileURL: (value) => value,
      renderFormattedDate: formatDate,
    },
    "@/components/dropdowns/member/avatar": { ButtonAvatars: "ButtonAvatars" },
    "@/components/icons": { getFileIcon: () => "file" },
    "@/hooks/store/use-issue-detail": {
      useIssueDetail: () => ({ attachment: { getAttachmentById: () => item }, toggleDeleteAttachmentModal: () => {} }),
    },
    "@/hooks/store/use-member": { useMember: () => ({ getUserDetails: () => ({ display_name: "Uploader" }) }) },
    "./attachment-image": { isAttachmentImage: (candidate) => candidate.attributes.type.startsWith("image/") },
    "./attachment-markdown": markdownUtils,
  };
  const source = readFileSync(
    resolve(__dirname, "../core/components/issues/attachment/attachment-list-item.tsx"),
    "utf8"
  );
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  });
  const exports = {};
  new Function("require", "exports", compiled.outputText)((name) => {
    assert.ok(name in imports, `Unexpected dependency: ${name}`);
    return imports[name];
  }, exports);
  const tree = exports.IssueAttachmentsListItem({ attachmentId: item.id, onPreview });
  const elements = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== "object") return;
    elements.push(node);
    visit(node.props?.children);
  }
  visit(tree);
  return { elements, onPreview, formatDate };
}

test("the gallery only loads the thumbnail, and downloads retain the original", () => {
  const { elements, onPreview } = renderItem();
  const images = elements.filter((node) => node.type === "img");
  assert.equal(images.length, 1);
  assert.equal(images[0].props.src, attachment.thumbnail_url);
  assert.equal(images[0].props.loading, "lazy");
  assert.equal(images[0].props.decoding, "async");
  assert.equal(elements.find((node) => node.type === "a").props.href, attachment.asset_url);
  elements.find((node) => node.type === "button").props.onClick();
  assert.deepEqual(onPreview.mock.calls[0].arguments, [attachment.id]);
});

for (const [name, item, failed] of [
  ["missing thumbnail", { ...attachment, thumbnail_url: undefined }, false],
  ["failed thumbnail", attachment, true],
]) {
  test(`${name} never triggers an automatic original-image download`, () => {
    const { elements, onPreview } = renderItem(item, failed);
    assert.equal(elements.filter((node) => node.type === "img").length, 0);
    elements.find((node) => node.type === "button").props.onClick();
    assert.equal(onPreview.mock.calls.length, 1);
  });
}

test("image upload time is visible once and uses created_at, not updated_at", () => {
  const { elements, formatDate } = renderItem();
  const times = elements.filter((node) => node.type === "time");
  assert.equal(times.length, 1);
  assert.equal(times[0].props.dateTime, attachment.created_at);
  assert.equal(times[0].props.children, "Uploaded 2026-10-09 20:34");
  assert.deepEqual(formatDate.mock.calls[0].arguments, [new Date(attachment.created_at), "yyyy-MM-dd HH:mm"]);
});

test("upload timestamp is converted to the local date even across midnight", () => {
  const { elements } = renderItem({ ...attachment, created_at: "2026-10-09T20:34:00Z" });
  assert.equal(elements.find((node) => node.type === "time").props.children, "Uploaded 2026-10-10 04:34");
});

test("an older cached attachment without created_at does not display a false upload time", () => {
  const { elements } = renderItem({ ...attachment, created_at: undefined });
  assert.equal(elements.filter((node) => node.type === "time").length, 0);
});

test("file rows also display upload time without requesting thumbnails", () => {
  const { elements } = renderItem({ ...attachment, attributes: { ...attachment.attributes, type: "application/pdf" } });
  assert.equal(elements.filter((node) => node.type === "img").length, 0);
  assert.equal(elements.filter((node) => node.type === "time").length, 1);
});

test("Markdown filenames open preview while the separate download link retains the original", () => {
  const file = { ...attachment, attributes: { ...attachment.attributes, name: "review.MD", type: "text/plain" } };
  const { elements, onPreview } = renderItem(file);
  const button = elements.find((node) => node.type === "button");
  assert.ok(button);
  button.props.onClick();
  assert.deepEqual(onPreview.mock.calls[0].arguments, [file.id]);
  const downloads = elements.filter((node) => node.type === "a");
  assert.equal(downloads.length, 1);
  assert.equal(downloads[0].props.href, file.asset_url);
});
