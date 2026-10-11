// Plan 11.29 Task 3: offline fixtures for docs/work-status.html.
// Runs the page's exact inline script in a Node VM, with fake GitHub responses and a minimal fake DOM.
// No network, no packages:  node --test tools/testing/work_status_page.test.cjs
// WORK_STATUS_PAGE=<path> runs the same tests against another copy of the page.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {spawnSync} = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const PAGE = process.env.WORK_STATUS_PAGE || path.join(__dirname, "..", "..", "docs", "work-status.html");
const HTML = fs.readFileSync(PAGE, "utf8");

function block(id) {
  const match = new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)</script>`).exec(HTML);
  assert.ok(match, `page has no script block #${id}`);
  return match[1];
}

const VOCAB = JSON.parse(block("work-status-vocabulary"));
const REPO = VOCAB.repo;

function load(extra = {}) {
  const context = vm.createContext({URLSearchParams, console, ...extra});
  vm.runInContext(block("work-status-logic"), context, {filename: "work-status-logic.js"});
  assert.ok(context.WorkStatus, "the page script must export WorkStatus");
  return context.WorkStatus;
}

const WS = load();

// Values built inside the VM come from another realm; compare plain copies.
const plain = (value) => JSON.parse(JSON.stringify(value));

function issue(number, labels, extra = {}) {
  return {
    number,
    title: `Issue ${number}`,
    state: "open",
    state_reason: null,
    html_url: `https://github.com/${REPO}/issues/${number}`,
    parent_issue_url: null,
    labels: labels.map((name) => ({name})),
    ...extra,
  };
}

const FULL = ["status:open", "priority:medium", "difficulty:medium", "estimate:na", "handler:unassigned", "product:optimus", "kind:follow-up"];

function parentUrl(number) {
  return `https://api.github.com/repos/${REPO}/issues/${number}`;
}

function response(body, {status = 200, link = null, remaining = "59", raw = null} = {}) {
  const headers = new Map([["x-ratelimit-limit", "60"], ["x-ratelimit-remaining", remaining], ["x-ratelimit-reset", "1800000000"]]);
  if (link) headers.set("link", link);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {get: (name) => (headers.has(name.toLowerCase()) ? headers.get(name.toLowerCase()) : null)},
    json: async () => (raw !== null ? JSON.parse(raw) : body),
  };
}

function rowsByNumber(sections) {
  const out = new Map();
  for (const section of sections) for (const row of section.rows) out.set(row.number, {...row, section: section.title});
  return out;
}

// ---- fake DOM for the browser controller ----
function fakeDom() {
  const listeners = {};
  const el = (id) => ({id, value: "", textContent: "", innerHTML: "", href: "",
    addEventListener: (type, fn) => { listeners[`${id}:${type}`] = fn; }});
  const elements = {
    "work-status-vocabulary": {textContent: JSON.stringify(VOCAB)},
    state: {...el("state"), value: "open"},
    reload: el("reload"),
    out: el("out"),
    stamp: el("stamp"),
    live: el("live"),
  };
  const doc = {getElementById: (id) => elements[id]};
  return {doc, elements, fire: (id, type) => listeners[`${id}:${type}`]()};
}

function fakeWindow(fetchImpl, search = "") {
  return {location: {search}, URLSearchParams, fetch: fetchImpl};
}

test("test_closed_reason_mapping", () => {
  const closed = (reason) => WS.statusCell(issue(1, [], {state: "closed", state_reason: reason}), VOCAB);
  assert.deepEqual({...closed("completed")}, {text: "Done", bad: false});
  assert.deepEqual({...closed("not_planned")}, {text: "Not planned", bad: false});
  assert.deepEqual({...closed(null)}, {text: "Closed (reason unavailable)", bad: true});
  for (const reason of ["duplicate", "some_new_reason", "constructor", "toString", "__proto__", "hasOwnProperty"]) {
    assert.deepEqual({...closed(reason)}, {text: "Closed (reason unavailable)", bad: true}, reason);
  }
});

test("test_closed_with_status_label_is_invalid", () => {
  const cell = WS.statusCell(issue(1, ["status:open"], {state: "closed", state_reason: "completed"}), VOCAB);
  assert.equal(cell.bad, true);
  assert.match(cell.text, /conflict: closed but labelled status:open/);
});

test("test_missing_and_conflicting_dimensions", () => {
  assert.deepEqual({...WS.statusCell(issue(1, []), VOCAB)}, {text: "missing status", bad: true});
  assert.deepEqual({...WS.statusCell(issue(1, ["status:open", "status:blocked"]), VOCAB)}, {text: "conflict: open, blocked", bad: true});
  const priority = VOCAB.dimensions.priority;
  assert.deepEqual({...WS.metadataCell(issue(1, []), priority)}, {text: "missing", bad: true});
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:high", "priority:low"]), priority)}, {text: "conflict: high, low", bad: true});
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:medium"]), priority)}, {text: "Medium", bad: false});
  const estimate = VOCAB.dimensions.estimate;
  assert.deepEqual({...WS.metadataCell(issue(1, ["estimate:na"]), estimate)}, {text: "NA", bad: false});
  assert.deepEqual({...WS.metadataCell(issue(1, ["estimate:3d"]), estimate)}, {text: "3d", bad: false});
  // GitHub label names are case-insensitive: a case variant is the same dimension, and an unknown value of it.
  assert.deepEqual({...WS.metadataCell(issue(1, ["Priority:High"]), priority)}, {text: "unknown: High", bad: true});
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:medium", "Priority:High"]), priority)}, {text: "conflict: medium, High", bad: true});
  assert.deepEqual({...WS.statusCell(issue(1, ["Status:Open"]), VOCAB)}, {text: "unknown: Open", bad: true});
});

test("test_unknown_enum_and_unclassified_issue_visible", () => {
  assert.deepEqual({...WS.statusCell(issue(1, ["status:weird"]), VOCAB)}, {text: "unknown: weird", bad: true});
  assert.deepEqual({...WS.metadataCell(issue(1, ["handler:somebody"]), VOCAB.dimensions.owner)}, {text: "unknown: somebody", bad: true});
  for (const name of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
    assert.deepEqual({...WS.statusCell(issue(1, ["status:" + name]), VOCAB)}, {text: "unknown: " + name, bad: true}, name);
    for (const dimension of ["priority", "difficulty", "owner"]) {
      const spec = VOCAB.dimensions[dimension];
      assert.deepEqual({...WS.metadataCell(issue(1, [spec.label + ":" + name]), spec)}, {text: "unknown: " + name, bad: true}, dimension + ":" + name);
    }
    // the free-form estimate rule stands: any value is shown as written
    assert.deepEqual({...WS.metadataCell(issue(1, ["estimate:" + name]), VOCAB.dimensions.estimate)}, {text: name, bad: false});
    const odd = WS.buildRows([issue(2, [...FULL.slice(0, 5), "product:" + name, "kind:" + name])], VOCAB);
    assert.deepEqual(plain(odd.map((s) => s.title)), ["Untriaged issues"], name);
  }
  // each guard matters on its own: an inherited string entry, and an own entry that is not a display string
  const inherited = {label: "priority", values: Object.create({inherited: "Inherited"})};
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:inherited"]), inherited)}, {text: "unknown: inherited", bad: true});
  const numeric = {label: "priority", values: {weird: 5}};
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:weird"]), numeric)}, {text: "unknown: weird", bad: true});
  const sections = WS.buildRows([issue(1, FULL), issue(2, ["status:open"]), issue(3, [...FULL.slice(0, 5), "product:mars", "kind:plan"])], VOCAB);
  assert.deepEqual(plain(sections.map((s) => s.title)), ["Optimus", "Untriaged issues"]);
  const rows = rowsByNumber(sections);
  assert.equal(rows.get(2).section, "Untriaged issues");
  assert.equal(rows.get(3).section, "Untriaged issues");
  assert.equal(rows.size, 3, "every issue is visible");
});

test("test_issue_list_pagination", async () => {
  const urls = [];
  const pages = {
    first: response([issue(1, FULL), {...issue(9, FULL), pull_request: {}}], {link: `<https://api.github.com/p2>; rel="next", <https://api.github.com/p3>; rel="last"`}),
    "https://api.github.com/p2": response([issue(2, FULL), issue(1, FULL)], {link: `<https://api.github.com/p3>; rel="next"`}),
    "https://api.github.com/p3": response([issue(3, FULL)]),
  };
  const client = async (url) => { urls.push(url); return urls.length === 1 ? pages.first : pages[url]; };
  const view = await WS.loadView(client, VOCAB, "all", null);
  assert.equal(urls[0], `https://api.github.com/repos/${REPO}/issues?state=all&per_page=100`);
  assert.deepEqual(urls.slice(1), ["https://api.github.com/p2", "https://api.github.com/p3"]);
  assert.deepEqual(plain(view.issues.map((i) => i.number).sort()), [1, 2, 3], "pull requests dropped, duplicates removed");
  assert.equal(view.requests, 3);
  assert.equal(view.rate.remaining, "59");

  const labelled = [];
  await WS.loadView(async (url) => { labelled.push(url); return response([]); }, VOCAB, "open", {label: "shadow-pilot"});
  assert.equal(labelled[0], `https://api.github.com/repos/${REPO}/issues?state=open&per_page=100&labels=shadow-pilot`);

  const endless = async () => response([], {link: `<https://api.github.com/again>; rel="next"`});
  await assert.rejects(WS.loadView(endless, VOCAB, "open", null), /stopped after 50 pages/);
});

test("test_child_visible_without_selected_parent", () => {
  const rows = rowsByNumber(WS.buildRows([issue(7, FULL, {parent_issue_url: parentUrl(5)})], VOCAB));
  assert.equal(rows.get(7).depth, 0);
  assert.equal(rows.get(7).context, 5);
  assert.equal(rows.get(7).relationError, null);
  const html = WS.renderSections(WS.buildRows([issue(7, FULL, {parent_issue_url: parentUrl(5)})], VOCAB));
  assert.match(html, new RegExp(`\(under <a href="https://github.com/${REPO}/issues/5">#5</a>\)`), "the parent outside the view is a link");
});

test("test_multilevel_relations_render_once", () => {
  const feature = issue(10, [...FULL.slice(0, 6), "kind:feature"], {sub_issues_summary: {total: 1, completed: 0}});
  const plan = issue(20, [...FULL.slice(0, 6), "kind:plan"], {parent_issue_url: parentUrl(10)});
  const item = issue(30, FULL, {parent_issue_url: parentUrl(20)});
  const [section] = WS.buildRows([item, plan, feature], VOCAB);
  assert.deepEqual(plain(section.rows.map((r) => [r.number, r.depth])), [[10, 0], [20, 1], [30, 2]]);
  assert.deepEqual({...section.rows[0].progress}, {completed: 0, total: 1});

  const parent = issue(60, [...FULL.slice(0, 6), "kind:feature"]);
  const kids = [63, 61].map((n) => issue(n, FULL, {parent_issue_url: parentUrl(60)}));
  const planKid = issue(62, [...FULL.slice(0, 6), "kind:plan"], {parent_issue_url: parentUrl(60)});
  const ordered = WS.buildRows([...kids, planKid, parent], VOCAB)[0].rows.map((r) => r.number);
  assert.deepEqual(plain(ordered), [60, 62, 61, 63], "children in vocabulary kind order, then by number");

  const a = issue(41, FULL, {parent_issue_url: parentUrl(42)});
  const b = issue(42, FULL, {parent_issue_url: parentUrl(41)});
  const cyc = WS.buildRows([a, b], VOCAB)[0].rows;
  assert.deepEqual(plain(cyc.map((r) => r.number).sort()), [41, 42], "each issue of a cycle is still shown once");
  assert.ok(cyc.every((r) => r.relationError === "parent cycle"));

  const chain = Array.from({length: 13}, (_, i) => issue(101 + i, FULL, i ? {parent_issue_url: parentUrl(100 + i)} : {}));
  const deep = rowsByNumber(WS.buildRows(chain, VOCAB));
  assert.equal(deep.size, 13, "a chain deeper than the limit is still shown once per issue");
  assert.equal(deep.get(113).relationError, "parent chain deeper than 10 levels");
  assert.ok(![...deep.values()].some((r) => r.relationError === "parent cycle"), "depth is not reported as a cycle");

  const LIMIT = 5000;
  const long = Array.from({length: LIMIT}, (_, i) => issue(1000 + i, FULL, i ? {parent_issue_url: parentUrl(999 + i)} : {}));
  let built;
  assert.doesNotThrow(() => { built = WS.buildRows(long, VOCAB); });
  const numbers = built.flatMap((s) => s.rows.map((r) => r.number));
  assert.equal(numbers.length, LIMIT);
  assert.equal(new Set(numbers).size, LIMIT, "every issue of a full-population chain appears exactly once");
  assert.equal(rowsByNumber(built).get(1000 + LIMIT - 1).relationError, "parent chain deeper than 10 levels");
  assert.doesNotThrow(() => WS.renderSections(built));

  const foreign = issue(50, FULL, {parent_issue_url: "https://api.github.com/repos/someone/else/issues/1"});
  assert.equal(rowsByNumber(WS.buildRows([foreign], VOCAB)).get(50).relationError, "malformed parent link");
});

// A recursive walk needs a stack frame per level, so whether a 5,000-level chain fits depends on the host's stack.
// This runs the exact page logic in a child Node with a deliberately small stack: only a bounded-stack walk passes.
const SMALL_STACK_CHILD = `
  const {logic, vocab, labels, size} = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
  const context = require("node:vm").createContext({URLSearchParams});
  require("node:vm").runInContext(logic, context);
  const api = "https://api.github.com/repos/" + vocab.repo + "/issues/";
  const issue = (n, parent) => ({number: n, title: "t", state: "open", state_reason: null,
    html_url: "https://github.com/" + vocab.repo + "/issues/" + n, parent_issue_url: parent ? api + parent : null,
    labels: labels.map((name) => ({name}))});
  const chain = Array.from({length: size}, (_, i) => issue(1000 + i, i ? 999 + i : null));
  const sections = context.WorkStatus.buildRows(chain, vocab);
  context.WorkStatus.renderSections(sections);
  const rows = sections.flatMap((s) => s.rows);
  process.stdout.write(rows.length + " " + new Set(rows.map((r) => r.number)).size);
`;

test("test_hierarchy_walk_is_bounded_on_a_small_stack", () => {
  const input = JSON.stringify({logic: block("work-status-logic"), vocab: VOCAB, labels: FULL, size: 5000});
  const run = spawnSync(process.execPath, ["--stack-size=150", "-e", SMALL_STACK_CHILD], {input, encoding: "utf8"});
  assert.equal(run.status, 0, `the page logic failed on a small stack: ${run.stderr.split("\n").find((l) => /Error/.test(l))}`);
  assert.equal(run.stdout, "5000 5000", "every issue of the chain appears exactly once");
});

test("test_late_fetch_cannot_replace_newer_filter", async () => {
  let releaseFirst;
  const first = new Promise((resolve) => { releaseFirst = resolve; });
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    return calls === 1 ? first : response([issue(2, FULL, {title: "newer read"})]);
  };
  const {doc, elements, fire} = fakeDom();
  const ws = load();
  const firstRead = ws.boot(doc, fakeWindow(fetchImpl));
  elements.state.value = "closed";
  await fire("state", "change");
  assert.match(elements.out.innerHTML, /newer read/);
  releaseFirst(response([issue(1, FULL, {title: "stale read"})]));
  await firstRead;
  assert.match(elements.out.innerHTML, /newer read/);
  assert.doesNotMatch(elements.out.innerHTML, /stale read/);
});

test("test_failed_fetch_clears_rows", async () => {
  const replies = [response([issue(1, FULL, {title: "first"})]), response(null, {status: 500})];
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(async () => replies.shift()));
  assert.match(elements.out.innerHTML, /first/);
  await fire("reload", "click");
  assert.equal(elements.out.innerHTML, "");
  assert.match(elements.stamp.innerHTML, /Could not read GitHub: GitHub answered HTTP 500/);

  await assert.rejects(load().loadView(async () => response(null, {status: 403, remaining: "0"}), VOCAB, "open", null), /rate limit/);
  await assert.rejects(load().loadView(async () => response(null, {raw: "<html>"}), VOCAB, "open", null), /not JSON/);

  const empty = fakeDom();
  await load().boot(empty.doc, fakeWindow(async () => response([])));
  assert.match(empty.elements.out.innerHTML, /No issues in this view/);
  assert.match(empty.elements.stamp.textContent, /Live from GitHub/);
});

test("test_text_escaping_and_url_validation", () => {
  const hostile = issue(1, [...FULL.slice(1), "status:<img src=x onerror=alert(1)>"], {
    title: "<script>alert(1)</script>",
    html_url: "https://evil.example/phish",
  });
  const html = WS.renderSections(WS.buildRows([hostile], VOCAB));
  assert.doesNotMatch(html, /<script>|<img/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /evil\.example/);
  const good = WS.renderSections(WS.buildRows([issue(2, FULL)], VOCAB));
  assert.match(good, new RegExp(`href="https://github.com/${REPO}/issues/2"`));
});

test("test_only_get_requests_and_no_tokens", async () => {
  const calls = [];
  await WS.browserClient(async (url, options) => { calls.push({url, options}); return response([]); })("https://api.github.com/x");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.credentials, "omit");
  assert.ok(!Object.keys(calls[0].options.headers).some((h) => h.toLowerCase() === "authorization"));
  for (const forbidden of [/authorization/i, /\beval\s*\(/, /new Function/, /localStorage|sessionStorage|indexedDB/, /setInterval|setTimeout/, /method:\s*"(POST|PATCH|PUT|DELETE)"/]) {
    assert.doesNotMatch(block("work-status-logic"), forbidden);
  }
});
