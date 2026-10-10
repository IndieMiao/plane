/* Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve: resolvePath } = require("node:path");
const { test, mock } = require("node:test");
const ts = require("typescript");
const mobx = require("mobx");
const lodash = require("lodash-es");
const noOp = () => Promise.resolve([]);
function Service() {
  return {};
}
function load(path, imports) {
  const result = {};
  const compiled = ts.transpileModule(readFileSync(resolvePath(__dirname, "..", path), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  });
  new Function("require", "exports", compiled.outputText)((name) => {
    assert.ok(name in imports, `Unexpected dependency: ${name}`);
    return imports[name];
  }, result);
  return result;
}
const common = {
  mobx,
  "mobx-utils": { computedFn: (fn) => fn },
  "lodash-es": lodash,
  "@plane/types": { EIssueServiceType: { ISSUES: "issues", EPICS: "epics" } },
};
const { IssueStore } = load("core/store/issue/issue-details/issue.store.ts", {
  ...common,
  "@/services/issue": { IssueService: Service, IssueArchiveService: Service, WorkspaceDraftService: Service },
});
function deferred() {
  let resolvePromise;
  let rejectPromise;
  const promise = new Promise((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}
function fixture() {
  const old = { id: "issue", project_id: "project", name: "Old", description_html: "<p>Old body</p>" };
  const fresh = {
    ...old,
    name: "New",
    description_html: "<p>New body</p>",
    issue_attachments: [],
    issue_link: [],
    issue_reactions: [],
  };
  const items = { issue: old };
  const root = {
    rootIssueStore: {
      issues: {
        getIssueById: (id) => items[id],
        addIssue: mock.fn((rows) =>
          rows.forEach((row) => {
            items[row.id] = { ...items[row.id], ...row };
          })
        ),
      },
      rootStore: { state: { fetchProjectStates: mock.fn(noOp) } },
    },
    addReactions: mock.fn(),
    addLinks: mock.fn(),
    addSubscription: mock.fn(),
    attachment: { replaceAttachments: mock.fn() },
    activity: { fetchActivities: mock.fn(noOp) },
    comment: { fetchComments: mock.fn(noOp) },
    subIssues: { fetchSubIssues: mock.fn(noOp) },
    relation: { fetchRelations: mock.fn(noOp) },
  };
  const store = new IssueStore(root, "issues");
  store.issueService = { retrieve: mock.fn(async () => fresh) };
  store.issueArchiveService = { retrieveArchivedIssue: mock.fn(async () => fresh) };
  return { store, root, items, fresh };
}

test("refresh updates only the selected work item and its detail collections", async () => {
  const { store, root, items } = fixture();
  await store.refreshIssue("ws", "project", "issue");
  assert.deepEqual(store.issueService.retrieve.mock.calls[0].arguments, [
    "ws",
    "project",
    "issue",
    { expand: "issue_reactions,issue_attachments,issue_link,parent" },
  ]);
  assert.equal(items.issue.description_html, "<p>New body</p>");
  assert.equal(items.issue.name, "New");
  assert.deepEqual(root.attachment.replaceAttachments.mock.calls[0].arguments, ["issue", []]);
  assert.deepEqual(root.comment.fetchComments.mock.calls[0].arguments, ["ws", "project", "issue", "mutate", true]);
  assert.deepEqual(root.activity.fetchActivities.mock.calls[0].arguments, ["ws", "project", "issue", "mutate", true]);
  assert.deepEqual(root.subIssues.fetchSubIssues.mock.calls[0].arguments, ["ws", "project", "issue", true]);
  assert.equal(root.rootIssueStore.rootStore.state.fetchProjectStates.mock.calls.length, 0);
  assert.equal(store.getDetailRefreshVersion("issue"), 1);
  assert.equal(store.getIsRefreshingIssue("issue"), false);
});

test("repeat clicks share the in-flight refresh instead of sending duplicate requests", async () => {
  const { store, fresh } = fixture();
  const pending = deferred();
  store.issueService.retrieve = mock.fn(() => pending.promise);
  const first = store.refreshIssue("ws", "project", "issue");
  assert.equal(store.getIsRefreshingIssue("issue"), true);
  await store.refreshIssue("ws", "project", "issue");
  assert.equal(store.issueService.retrieve.mock.calls.length, 1);
  pending.resolve(fresh);
  await first;
  assert.equal(store.getIsRefreshingIssue("issue"), false);
});

test("title and description saves independently block refresh", async () => {
  const { store } = fixture();
  store.setIsSavingIssueDetails("issue", "title", true);
  store.setIsSavingIssueDetails("issue", "description", true);
  store.setIsSavingIssueDetails("issue", "title", false);
  assert.equal(store.getIsSavingIssueDetails("issue"), true);
  await assert.rejects(store.refreshIssue("ws", "project", "issue"), /pending edits/);
  assert.equal(store.issueService.retrieve.mock.calls.length, 0);
  store.setIsSavingIssueDetails("issue", "description", false);
  await store.refreshIssue("ws", "project", "issue");
});

test("failed main requests keep the current details and allow retry", async () => {
  const { store, root, items } = fixture();
  store.issueService.retrieve = mock.fn(async () => {
    throw new Error("offline");
  });
  await assert.rejects(store.refreshIssue("ws", "project", "issue"), /offline/);
  assert.equal(items.issue.name, "Old");
  assert.equal(store.getDetailRefreshVersion("issue"), 0);
  assert.equal(store.getIsRefreshingIssue("issue"), false);
  assert.equal(root.comment.fetchComments.mock.calls.length, 0);
});

test("partial failures wait for all requested detail sections and then release loading state", async () => {
  const { store, root } = fixture();
  const pending = deferred();
  root.activity.fetchActivities = mock.fn(async () => {
    throw new Error("offline");
  });
  root.comment.fetchComments = mock.fn(() => pending.promise);
  const failure = assert.rejects(store.refreshIssue("ws", "project", "issue"), /Some work item details/);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(store.getIsRefreshingIssue("issue"), true);
  pending.resolve([]);
  await failure;
  assert.equal(store.getIsRefreshingIssue("issue"), false);
});

test("archived details refresh from the archive endpoint", async () => {
  const { store, items } = fixture();
  items.issue.archived_at = "2026-10-01";
  await store.refreshIssue("ws", "project", "issue");
  assert.equal(store.issueArchiveService.retrieveArchivedIssue.mock.calls.length, 1);
  assert.equal(store.issueService.retrieve.mock.calls.length, 0);
});

test("responses for a different card cannot overwrite the current details", async () => {
  const { store, items, fresh } = fixture();
  store.issueService.retrieve = mock.fn(async () => ({ ...fresh, id: "other" }));
  await assert.rejects(store.refreshIssue("ws", "project", "issue"), /not found/);
  assert.equal(items.issue.name, "Old");
});

const { IssueAttachmentStore } = load("core/store/issue/issue-details/attachment.store.ts", {
  ...common,
  uuid: { v4: () => "" },
  "@/services/issue": { IssueAttachmentService: Service },
});
test("attachment refresh removes deleted files, including when the server list becomes empty", () => {
  const store = new IssueAttachmentStore({ issueDetail: {} }, "issues");
  store.addAttachments("issue", [{ id: "old" }, { id: "kept", attributes: { name: "before.png" } }]);
  store.replaceAttachments("issue", [{ id: "kept", attributes: { name: "after.png" } }, { id: "new" }]);
  assert.deepEqual([...store.getAttachmentsByIssueId("issue")], ["kept", "new"]);
  assert.equal(store.getAttachmentById("old"), undefined);
  assert.equal(store.getAttachmentById("kept").attributes.name, "after.png");
  store.replaceAttachments("issue", []);
  assert.deepEqual([...store.getAttachmentsByIssueId("issue")], []);
});

const { IssueCommentStore } = load("core/store/issue/issue-details/comment.store.ts", {
  ...common,
  "@/services/issue": { IssueCommentService: Service },
});
function comments() {
  const store = new IssueCommentStore({ commentReaction: { applyCommentReactions: () => {} } }, "issues");
  store.comments.issue = ["old", "kept"];
  store.commentMap.old = { id: "old", created_at: "2026-10-01" };
  store.commentMap.kept = { id: "kept", created_at: "2026-10-02", comment_html: "Old" };
  return store;
}
test("full comment refresh fetches edits and deletions without a created_at filter", async () => {
  const store = comments();
  store.issueCommentService = {
    getIssueComments: mock.fn(async () => [{ id: "kept", comment_html: "Edited", created_at: "2026-10-02" }]),
  };
  await store.fetchComments("ws", "project", "issue", "mutate", true);
  assert.deepEqual(store.issueCommentService.getIssueComments.mock.calls[0].arguments, ["ws", "project", "issue", {}]);
  assert.deepEqual([...store.comments.issue], ["kept"]);
  assert.equal(store.commentMap.kept.comment_html, "Edited");
});
test("automatic comment fetches retain incremental behavior", async () => {
  const store = comments();
  store.issueCommentService = { getIssueComments: mock.fn(async () => []) };
  await store.fetchComments("ws", "project", "issue");
  assert.deepEqual(store.issueCommentService.getIssueComments.mock.calls[0].arguments[3], {
    created_at__gt: "2026-10-02",
  });
  assert.equal(store.comments.issue.length, 2);
});
test("a failed comment refresh retains content and clears its loader", async () => {
  const store = comments();
  store.issueCommentService = {
    getIssueComments: async () => {
      throw new Error("offline");
    },
  };
  await assert.rejects(store.fetchComments("ws", "project", "issue", "mutate", true), /offline/);
  assert.equal(store.comments.issue.length, 2);
  assert.equal(store.loader, undefined);
});

const { IssueActivityStore } = load("ce/store/issue/issue-details/activity.store.ts", {
  ...common,
  "@plane/constants": { EActivityFilterType: {} },
  "@/services/issue": { IssueActivityService: Service },
});
test("activity refresh replaces the server snapshot and clears removed records from the timeline", async () => {
  const store = new IssueActivityStore({}, "issues");
  store.activities.issue = ["old"];
  store.activityMap.old = { id: "old", created_at: "2026-10-01" };
  store.issueActivityService = { getIssueActivities: mock.fn(async () => []) };
  await store.fetchActivities("ws", "project", "issue", "mutate", true);
  assert.deepEqual(store.issueActivityService.getIssueActivities.mock.calls[0].arguments, [
    "ws",
    "project",
    "issue",
    {},
  ]);
  assert.deepEqual([...store.activities.issue], []);
});
