/* Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

function loadSource(path) {
  const source = readFileSync(resolve(__dirname, "../core/components/issues/attachment", path), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  });
  const exports = {};
  new Function("require", "exports", compiled.outputText)(require, exports);
  return exports;
}
const { isAttachmentMarkdown, fetchAttachmentMarkdown, MAX_MARKDOWN_PREVIEW_BYTES } =
  loadSource("attachment-markdown.ts");
const MarkdownContent = loadSource("attachment-markdown-content.tsx").default;
const renderMarkdown = (content) => renderToStaticMarkup(React.createElement(MarkdownContent, { content }));

for (const [name, type, expected] of [
  ["review.md", "application/octet-stream", true],
  ["REVIEW.MARKDOWN", "text/plain", true],
  ["notes.txt", "text/markdown; charset=utf-8", true],
  ["report.txt", "text/plain", false],
  ["archive.md.zip", "application/zip", false],
]) {
  test(`detects Markdown by filename or MIME: ${name}`, () => {
    assert.equal(isAttachmentMarkdown({ attributes: { name, type } }), expected);
  });
}

test("renders document structure, GFM tables, task lists, and code as semantic elements", () => {
  const html = renderMarkdown(
    "# 报告\n\n## 结论\n\n**完成**，包含 *说明*。\n\n- 项目一\n- 项目二\n\n1. 第一步\n2. 第二步\n\n- [x] 已完成\n- [ ] 待处理\n\n| 项目 | 状态 |\n| --- | --- |\n| UI | 完成 |\n\n> 引用说明\n\n```js\nconst ready = true;\n```\n\n`inline`"
  );
  for (const tag of ["h1", "h2", "strong", "em", "ul", "ol", "table", "thead", "td", "blockquote", "pre", "code"]) {
    assert.match(html, new RegExp(`<${tag}[ >]`));
  }
  assert.match(html, /type="checkbox"/);
  assert.match(html, /checked=""/);
  assert.match(html, /language-js/);
  assert.doesNotMatch(html, /\| 项目 \|/);
});

test("embedded HTML and unsafe link or image protocols do not become executable markup", () => {
  const html = renderMarkdown(
    '<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[bad](javascript:alert)\n\n![bad](data:image/svg+xml;base64,PHN2Zz4=)\n\n[good](https://example.com)'
  );
  assert.doesNotMatch(html, /<script|onerror=|href="javascript:|src="data:/);
  assert.match(html, /href="https:\/\/example.com"/);
  assert.match(html, /rel="noopener noreferrer"/);
});

test("code blocks retain literal HTML as escaped code", () => {
  const html = renderMarkdown('```html\n<script>alert("example")</script>\n```');
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script/);
});

test("loads UTF-8 text across chunks and includes session credentials", async (context) => {
  const bytes = new TextEncoder().encode("\ufeff# 中文文档\n\n预览内容");
  const signal = new AbortController().signal;
  context.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/attachment/");
    assert.equal(options.credentials, "include");
    assert.equal(options.signal, signal);
    return new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(bytes.slice(0, 7));
          controller.enqueue(bytes.slice(7));
          controller.close();
        },
      })
    );
  });
  assert.equal(await fetchAttachmentMarkdown("/attachment/", signal), "# 中文文档\n\n预览内容");
});

test("supports a UTF-16 document with a byte-order mark", async (context) => {
  const bytes = Buffer.from("\ufeff# 中文", "utf16le");
  context.mock.method(globalThis, "fetch", async () => new Response(bytes));
  assert.equal(await fetchAttachmentMarkdown("/attachment/", new AbortController().signal), "# 中文");
});

test("rejects authentication failures and HTML login responses", async (context) => {
  context.mock.method(globalThis, "fetch", async () => new Response("Denied", { status: 403 }));
  await assert.rejects(fetchAttachmentMarkdown("/attachment/", new AbortController().signal), /403/);
  globalThis.fetch = async () => new Response("<html>Login</html>", { headers: { "Content-Type": "text/html" } });
  await assert.rejects(fetchAttachmentMarkdown("/attachment/", new AbortController().signal), {
    reason: "invalid_content",
  });
});

test("oversized response headers cancel the download", async (context) => {
  let cancelled = false;
  context.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(
        new ReadableStream({
          cancel() {
            cancelled = true;
          },
        }),
        { headers: { "Content-Length": String(MAX_MARKDOWN_PREVIEW_BYTES + 1) } }
      )
  );
  await assert.rejects(fetchAttachmentMarkdown("/attachment/", new AbortController().signal), { reason: "too_large" });
  assert.equal(cancelled, true);
});

test("streamed content is bounded even without Content-Length", async (context) => {
  let cancelled = false;
  context.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(new Uint8Array(MAX_MARKDOWN_PREVIEW_BYTES));
            controller.enqueue(new Uint8Array(1));
          },
          cancel() {
            cancelled = true;
          },
        })
      )
  );
  await assert.rejects(fetchAttachmentMarkdown("/attachment/", new AbortController().signal), { reason: "too_large" });
  assert.equal(cancelled, true);
});

test("invalid binary contents are not displayed as a text document", async (context) => {
  context.mock.method(globalThis, "fetch", async () => new Response(new Uint8Array([0xff, 0xff, 0])));
  await assert.rejects(fetchAttachmentMarkdown("/attachment/", new AbortController().signal), {
    reason: "invalid_content",
  });
});

test("closing the preview can abort an in-flight request", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    (_url, { signal }) =>
      new Promise((_resolve, reject) =>
        signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })
      )
  );
  const controller = new AbortController();
  const pending = fetchAttachmentMarkdown("/attachment/", controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});
