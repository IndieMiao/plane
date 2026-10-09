/* Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test, mock } = require("node:test");
const ts = require("typescript");
const noOp = () => Promise.resolve();
function ServiceStub() {
  return {};
}

function loadSource(path, imports) {
  const source = readFileSync(resolve(__dirname, "..", path), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      esModuleInterop: true,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const exports = {};
  new Function("require", "exports", compiled.outputText)((name) => {
    assert.ok(name in imports, `Unexpected dependency: ${name}`);
    return imports[name];
  }, exports);
  return exports;
}

const route = { workspaceSlug: "zili", projectId: "project", issueId: "issue" };
const issue = { id: "issue", project_id: "project", description_html: "<p>Saved description</p>" };

function renderPeek({ cached = issue, peek = route, fetchError, operationError, isValidating = true } = {}) {
  let swr;
  const fetchIssue = mock.fn(async () => issue);
  const store = { peekIssue: peek, issue: { fetchIssue, getIssueById: () => cached } };
  const imports = {
    react: { useState: () => [operationError, () => {}], useMemo: (fn) => fn(), useCallback: (fn) => fn },
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), Fragment: "fragment" },
    "mobx-react": { observer: (fn) => fn },
    "next/navigation": { usePathname: () => "/zili/projects/project/issues" },
    swr: (key, fetcher, options) => {
      swr = { key, fetcher, options };
      return { error: fetchError, isLoading: true, isValidating };
    },
    "@plane/constants": { EUserPermissions: {}, EUserPermissionsLevel: {} },
    "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
    "@plane/propel/toast": {},
    "@plane/types": { EIssueServiceType: {}, EIssuesStoreType: {} },
    "@/hooks/store/use-issue-detail": { useIssueDetail: () => store },
    "@/hooks/store/use-issues": { useIssues: () => ({ issues: {} }) },
    "@/hooks/store/user": { useUserPermissions: () => ({ allowPermissions: () => true }) },
    "@/hooks/use-issue-layout-store": { useIssueStoreType: () => "project" },
    "@/plane-web/hooks/use-issue-properties": { useWorkItemProperties: () => {} },
    "./view": { IssueView: "IssueView" },
  };
  const { IssuePeekOverview } = loadSource("core/components/issues/peek-overview/root.tsx", imports);
  return {
    view: IssuePeekOverview({}),
    get swr() {
      return swr;
    },
    fetchIssue,
    store,
  };
}

test("detail requests return data for SWR caching", async () => {
  const rendered = renderPeek();
  assert.equal(await rendered.swr.fetcher(rendered.swr.key), issue);
  assert.deepEqual(rendered.fetchIssue.mock.calls[0].arguments, ["zili", "project", "issue"]);
});

test("reopening a fetched card keeps its content visible during background refresh", () => {
  const rendered = renderPeek();
  assert.equal(rendered.view.props.isLoading, false);
  assert.equal(rendered.swr.options.revalidateOnMount, true);
});

for (const description_html of ["", null]) {
  test(`a fetched empty description (${JSON.stringify(description_html)}) is ready`, () => {
    assert.equal(renderPeek({ cached: { ...issue, description_html } }).view.props.isLoading, false);
  });
}

test("a board card without a description does not mount the editable details prematurely", () => {
  assert.equal(renderPeek({ cached: { id: "issue", project_id: "project" } }).view.props.isLoading, true);
});

test("cached details from another project are not reused", () => {
  assert.equal(renderPeek({ cached: { ...issue, project_id: "other" } }).view.props.isLoading, true);
});

test("closed peeks do not start a request", () => {
  assert.equal(renderPeek({ peek: null }).swr.key, null);
});

test("cached content stays read-only until the refresh finishes", () => {
  assert.equal(renderPeek().view.props.disabled, true);
  assert.equal(renderPeek({ isValidating: false }).view.props.disabled, false);
});

test("a request remains bound to its key when the selection changes", async () => {
  const rendered = renderPeek();
  const { key, fetcher } = rendered.swr;
  rendered.store.peekIssue = { ...route, issueId: "other" };
  await fetcher(key);
  assert.deepEqual(rendered.fetchIssue.mock.calls[0].arguments, ["zili", "project", "issue"]);
});

test("request errors are shown for the current card", () => {
  assert.equal(renderPeek({ fetchError: new Error("Unavailable") }).view.props.isError, true);
});

test("an operation error on the previous card does not hide the current card", () => {
  assert.equal(renderPeek({ operationError: "previous" }).view.props.isError, false);
});

test("one detail response is stored once and retains the real creator for permissions", async () => {
  const addIssue = mock.fn();
  const root = {
    rootIssueStore: { issues: { addIssue }, rootStore: { state: { fetchProjectStates: noOp } } },
    addSubscription: noOp,
    activity: { fetchActivities: noOp },
    comment: { fetchComments: noOp },
    subIssues: { fetchSubIssues: noOp },
    relation: { fetchRelations: noOp },
  };
  const { IssueStore } = loadSource("core/store/issue/issue-details/issue.store.ts", {
    mobx: { makeObservable: () => {}, observable: {} },
    "mobx-utils": { computedFn: (fn) => fn },
    "@plane/types": { EIssueServiceType: {} },
    "@/services/issue": {
      IssueService: ServiceStub,
      IssueArchiveService: ServiceStub,
      WorkspaceDraftService: ServiceStub,
    },
  });
  const store = new IssueStore(root, "issues");
  const attributedIssue = { ...issue, created_by: "virtual", created_by_actor: "real" };
  store.issueService = { retrieve: async () => attributedIssue };
  assert.equal(await store.fetchIssue("zili", "project", "issue"), attributedIssue);
  assert.equal(addIssue.mock.callCount(), 1);
  assert.equal(addIssue.mock.calls[0].arguments[0][0].created_by_actor, "real");
});
