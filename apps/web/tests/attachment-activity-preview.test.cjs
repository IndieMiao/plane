/* Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");

function loadSource(path, imports) {
  const source = readFileSync(resolve(__dirname, "..", path), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  });
  const exports = {};
  new Function("require", "exports", compiled.outputText)((name) => {
    assert.ok(name in imports, `Unexpected dependency: ${name}`);
    return imports[name];
  }, exports);
  return exports;
}
const imageHelpers = loadSource("core/components/issues/attachment/attachment-image.ts", {});
const markdownHelpers = loadSource("core/components/issues/attachment/attachment-markdown.ts", {});
const attachment = {
  id: "image-1",
  attributes: { name: "screen.png", type: "image/png", size: 1024 },
  asset_url: "/original.png",
  thumbnail_url: "/thumbnail.webp",
};
const activity = {
  id: "activity-1",
  verb: "created",
  new_identifier: attachment.id,
  new_value: "untrusted-storage-key",
};

function renderActivity({ item = attachment, record = activity } = {}) {
  let stateIndex = 0;
  const state = [];
  const imports = {
    react: {
      useState: (initial) => {
        const index = stateIndex++;
        if (!(index in state)) state[index] = initial;
        return [
          state[index],
          (value) => {
            state[index] = value;
          },
        ];
      },
    },
    "react/jsx-runtime": {
      jsx: (type, props) => ({ type, props }),
      jsxs: (type, props) => ({ type, props }),
      Fragment: "fragment",
    },
    "mobx-react": { observer: (fn) => fn },
    "lucide-react": { ImageOff: "ImageOff", Paperclip: "Paperclip" },
    "@plane/i18n": { useTranslation: () => ({ t: (key, values) => (values?.name ? `${key}: ${values.name}` : key) }) },
    "@plane/ui": { ImagePreview: "ImagePreview" },
    "@plane/utils": { getFileURL: (value) => value, getFileExtension: (name) => name.split(".").at(-1) },
    "@/components/icons": { getFileIcon: (extension, size) => ({ type: "FileIcon", props: { extension, size } }) },
    "@/components/issues/attachment/attachment-image": imageHelpers,
    "@/components/issues/attachment/attachment-markdown": markdownHelpers,
    "@/components/issues/attachment/attachment-markdown-preview": { AttachmentMarkdownPreview: "MarkdownPreview" },
    "@/hooks/store/use-issue-detail": {
      useIssueDetail: () => ({
        activity: { getActivityById: () => record },
        attachment: { getAttachmentById: (id) => (item?.id === id ? item : undefined) },
      }),
    },
    "./helpers/activity-block": { IssueActivityBlockComponent: "ActivityBlock" },
    "./helpers/issue-link": { IssueLink: "IssueLink" },
  };
  const { IssueAttachmentActivity } = loadSource(
    "core/components/issues/issue-detail/issue-activity/activity/actions/attachment.tsx",
    imports
  );
  function render() {
    stateIndex = 0;
    const tree = IssueAttachmentActivity({ activityId: record?.id, showIssue: false });
    const elements = [];
    function visit(node) {
      if (Array.isArray(node)) return node.forEach(visit);
      if (!node || typeof node !== "object") return;
      elements.push(node);
      visit(node.props?.children);
      visit(node.props?.trailingContent);
    }
    visit(tree);
    return elements;
  }
  return { render };
}

test("an attachment activity loads only its associated cached thumbnail", () => {
  const elements = renderActivity().render();
  assert.equal(elements.filter((node) => node.type === "ImagePreview").length, 0);
  const images = elements.filter((node) => node.type === "img");
  assert.equal(images.length, 1);
  assert.equal(images[0].props.src, attachment.thumbnail_url);
  assert.equal(images[0].props.loading, "lazy");
  assert.equal(images[0].props.decoding, "async");
  assert.equal(images[0].props.width, 32);
  assert.equal(images[0].props.height, 32);
});

test("clicking the thumbnail opens the original and closing removes the viewer", () => {
  const ui = renderActivity();
  ui.render()
    .find((node) => node.type === "button")
    .props.onClick();
  const viewer = ui.render().find((node) => node.type === "ImagePreview");
  assert.deepEqual(viewer.props.images, [
    { id: attachment.id, src: attachment.asset_url, name: attachment.attributes.name },
  ]);
  viewer.props.onClose();
  assert.equal(ui.render().filter((node) => node.type === "ImagePreview").length, 0);
});

test("non-image attachments render a file type icon without an image or preview action", () => {
  const elements = renderActivity({
    item: { ...attachment, attributes: { name: "bundle.zip", type: "application/zip" } },
  }).render();
  assert.equal(elements.filter((node) => ["img", "button", "ImagePreview"].includes(node.type)).length, 0);
  assert.equal(elements.find((node) => node.type === "FileIcon").props.extension, "zip");
});

test("generic MIME images are recognized by their filenames", () => {
  const elements = renderActivity({
    item: { ...attachment, attributes: { name: "SCREEN.PNG", type: "application/octet-stream" } },
  }).render();
  assert.equal(elements.filter((node) => node.type === "img").length, 1);
});

test("Markdown activity icons open document preview", () => {
  const item = { ...attachment, attributes: { name: "review.md", type: "text/plain" } };
  const ui = renderActivity({ item });
  ui.render()
    .find((node) => node.type === "button")
    .props.onClick();
  const viewer = ui.render().find((node) => node.type === "MarkdownPreview");
  assert.equal(viewer.props.attachment, item);
  viewer.props.onClose();
  assert.equal(ui.render().filter((node) => node.type === "MarkdownPreview").length, 0);
});

test("failed thumbnails keep manual original preview available without automatic fallback", () => {
  const ui = renderActivity();
  ui.render()
    .find((node) => node.type === "img")
    .props.onError();
  const elements = ui.render();
  assert.equal(elements.filter((node) => ["img", "ImagePreview"].includes(node.type)).length, 0);
  assert.equal(elements.filter((node) => node.type === "ImageOff").length, 1);
  elements.find((node) => node.type === "button").props.onClick();
  assert.equal(ui.render().find((node) => node.type === "ImagePreview").props.images[0].src, attachment.asset_url);
});

for (const [name, options] of [
  ["deleted attachment", { record: { ...activity, verb: "deleted" } }],
  ["missing attachment", { item: null }],
  ["missing activity identifier", { record: { ...activity, new_identifier: undefined } }],
  ["unrelated attachment", { item: { ...attachment, id: "different" } }],
]) {
  test(`${name} preserves the activity without requesting media`, () => {
    const elements = renderActivity(options).render();
    assert.equal(elements.filter((node) => node.type === "ActivityBlock").length, 1);
    assert.equal(elements.filter((node) => ["img", "button", "ImagePreview"].includes(node.type)).length, 0);
  });
}
