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
const withKind = (kind) => [...FULL.slice(0, 6), `kind:${kind}`];
const withLabels = (replace) => FULL.map((label) => replace[label.split(":")[0]] || label);

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

function allRows(model) {
  return [...model.tables.flatMap((table) => table.rows), ...model.untriaged];
}

function rowsByNumber(model) {
  return new Map(allRows(model).map((row) => [row.number, row]));
}

const tableOf = (model, key) => model.tables.find((table) => table.key === key);
const numbersOf = (rows) => plain(rows.map((row) => row.number));

// ---- fake DOM for the browser controller ----
function fakeDom() {
  const listeners = {};
  const focused = [];
  const el = (id) => ({id, value: "", textContent: "", innerHTML: "", href: "",
    addEventListener: (type, fn) => { listeners[`${id}:${type}`] = fn; }});
  const elements = {
    "work-status-vocabulary": {textContent: JSON.stringify(VOCAB)},
    state: {...el("state"), value: "open"},
    product: {...el("product"), value: ""},
    clear: el("clear"),
    reload: el("reload"),
    out: el("out"),
    stamp: el("stamp"),
    announce: el("announce"),
    live: el("live"),
  };
  const dynamic = (id) => ({id, value: "", focus: () => focused.push(id), setSelectionRange: () => {}});
  const doc = {getElementById: (id) => elements[id] || (/^flt-/.test(id) ? dynamic(id) : undefined)};
  return {doc, elements, focused, fire: (id, type, event) => listeners[`${id}:${type}`](event)};
}

function fakeWindow(fetchImpl, search = "") {
  const listeners = {};
  return {location: {search}, URLSearchParams, fetch: fetchImpl, listeners, addEventListener: (type, fn) => { listeners[type] = fn; }};
}

// A change in the header of one table: the control names its table (data-table) and carries a per-table id.
const filterEvent = (key, value, table = "follow-ups") => ({target: {dataset: {filter: key, table}, value, id: `flt-${table}-${key}`}});

// ---- cells: status and metadata dimensions ----
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

test("test_unknown_enum_values_are_visible_never_guessed", () => {
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
    const odd = WS.buildModel([issue(2, [...FULL.slice(0, 5), "product:" + name, "kind:" + name])], VOCAB, {});
    assert.deepEqual(numbersOf(odd.untriaged), [2], name);
  }
  // each guard matters on its own: an inherited string entry, and an own entry that is not a display string
  const inherited = {label: "priority", values: Object.create({inherited: "Inherited"})};
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:inherited"]), inherited)}, {text: "unknown: inherited", bad: true});
  const numeric = {label: "priority", values: {weird: 5}};
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:weird"]), numeric)}, {text: "unknown: weird", bad: true});
});

// ---- the model: one flat table per kind group ----
test("test_every_kind_belongs_to_exactly_one_table", () => {
  const listed = VOCAB.tables.flatMap((table) => table.kinds);
  assert.deepEqual([...listed].sort(), Object.keys(VOCAB.kinds).sort(), "every kind has a table");
  assert.equal(new Set(listed).size, listed.length, "no kind is in two tables");
  assert.equal(new Set(VOCAB.tables.map((table) => table.key)).size, VOCAB.tables.length, "table keys are unique");
  assert.ok(VOCAB.tables.every((table) => table.key && table.title));
  assert.deepEqual(VOCAB.tables.map((table) => table.key), ["features", "plans", "follow-ups", "hardening", "obligations"]);
});

test("test_issues_group_into_one_flat_table_per_kind_in_number_order", () => {
  const issues = [
    issue(9, withKind("follow-up")), issue(3, withKind("feature")), issue(7, withKind("follow-up")), issue(5, withKind("track")),
    issue(6, withKind("candidate")), issue(4, withKind("obligation")), issue(2, withKind("plan")), issue(8, withKind("item")),
  ];
  const model = WS.buildModel(issues, VOCAB, {});
  assert.deepEqual(plain(model.tables.map((table) => table.key)), VOCAB.tables.map((table) => table.key));
  assert.deepEqual(numbersOf(tableOf(model, "features").rows), [3]);
  assert.deepEqual(numbersOf(tableOf(model, "plans").rows), [2]);
  assert.deepEqual(numbersOf(tableOf(model, "follow-ups").rows), [7, 9]);
  assert.deepEqual(numbersOf(tableOf(model, "hardening").rows), [5, 8, 6], "a multi-kind table lists its kinds in the table's order, then by number");
  assert.deepEqual(numbersOf(tableOf(model, "obligations").rows), [4]);
  assert.deepEqual(plain(tableOf(model, "hardening").rows.map((row) => row.kind)), ["Track", "Item", "Candidate"]);
  assert.equal(tableOf(model, "hardening").multiKind, true, "a table that holds several kinds shows a Kind column");
  assert.equal(tableOf(model, "features").multiKind, false);
  assert.ok(allRows(model).every((row) => row.depth === undefined), "rows are flat: nothing is nested");
  assert.deepEqual(plain(model.untriaged), []);
});

test("test_collapsed_flags_come_from_the_vocabulary", () => {
  const model = WS.buildModel([issue(1, FULL)], VOCAB, {});
  assert.equal(tableOf(model, "hardening").collapsed, true);
  assert.equal(tableOf(model, "obligations").collapsed, true);
  assert.equal(tableOf(model, "features").collapsed, false);
});

const MIXED_PRODUCTS = () => [
  issue(1, FULL, {title: "optimus one"}), issue(2, ["status:open"], {title: "no labels"}),
  issue(3, [...FULL.slice(0, 5), "product:mars", "kind:plan"], {title: "unknown product"}),
  issue(4, [...FULL.slice(0, 5), "product:evidence-a2a", "kind:follow-up"], {title: "evidence one"}),
];

test("test_unlabelled_or_unknown_issues_are_untriaged_and_every_issue_is_visible", () => {
  const model = WS.buildModel(MIXED_PRODUCTS(), VOCAB, {});
  assert.deepEqual(numbersOf(model.untriaged), [2, 3]);
  assert.equal(allRows(model).length, 4, "every issue is visible");
});

test("test_product_is_a_column_a_row_names_and_a_filter_that_never_hides_untriaged_issues", () => {
  const model = WS.buildModel(MIXED_PRODUCTS(), VOCAB, {});
  const rows = tableOf(model, "follow-ups").rows;
  assert.deepEqual(plain(rows.map((row) => [row.number, row.product, row.productKey])), [[1, "Optimus", "optimus"], [4, "Evidence/A2A", "evidence-a2a"]]);
  const run = (product) => numbersOf(WS.filterRows(rows, {...WS.emptyFilters(), product}, false));
  assert.deepEqual(run("optimus"), [1]);
  assert.deepEqual(run("evidence-a2a"), [4]);
  assert.deepEqual(run(""), [1, 4]);
  assert.deepEqual(plain(WS.filterOptions(rows, VOCAB).product), [{value: "optimus", label: "Optimus"}, {value: "evidence-a2a", label: "Evidence/A2A"}]);
  const html = WS.renderPage(model, uiWith("follow-ups", {product: "evidence-a2a"}));
  assert.match(html, /<tr><td class="c-title"><a [^>]*>#4<\/a> — <bdi>evidence one<\/bdi><\/td><td>Evidence\/A2A<\/td>/, "each row names its product beside its title");
  assert.doesNotMatch(html, /optimus one/);
  assert.match(html, /no labels/, "an untriaged issue is a data fault and stays visible");
  assert.match(html, /unknown product/);
  const untriaged = html.split('id="sec-untriaged"')[1];
  assert.match(untriaged, /<td class="bad">missing<\/td>/, "a missing product is red in the Product column");
  assert.match(untriaged, /<td class="bad">unknown: mars<\/td>/);
});

test("test_belongs_to_names_the_parent_instead_of_nesting", () => {
  const parent = issue(10, withKind("feature"), {title: "P11-FEAT-X: Zed session resume"});
  const child = issue(20, withKind("plan"), {parent_issue_url: parentUrl(10)});
  const absent = issue(30, FULL, {parent_issue_url: parentUrl(99)});
  const foreign = issue(40, FULL, {parent_issue_url: "https://api.github.com/repos/someone/else/issues/1"});
  const rows = rowsByNumber(WS.buildModel([parent, child, absent, foreign], VOCAB, {}));
  assert.deepEqual(plain(rows.get(20).parent), {number: 10, title: "Zed session resume", url: `https://github.com/${REPO}/issues/10`});
  assert.deepEqual(plain(rows.get(30).parent), {number: 99, title: null, url: `https://github.com/${REPO}/issues/99`}, "a parent outside the view is still a link");
  assert.equal(rows.get(10).parent, null);
  assert.equal(rows.get(40).parent, null);
  assert.equal(rows.get(40).relationError, "malformed parent link");
  assert.equal(rows.get(20).relationError, null);
  const evidenceChild = issue(21, [...FULL.slice(0, 5), "product:evidence-a2a", "kind:plan"], {parent_issue_url: parentUrl(10)});
  const html = WS.renderPage(WS.buildModel([parent, evidenceChild], VOCAB, {}), uiWith("plans", {}, {product: "evidence-a2a"}));
  assert.match(html, /<bdi>Zed session resume<\/bdi>/, "the parent is named even when the product filter hides the parent's own row");
});

test("test_a_parent_cycle_is_flagged_on_every_issue_on_or_under_it_and_a_chain_is_not", () => {
  const issues = [
    issue(41, FULL, {parent_issue_url: parentUrl(42)}), issue(42, FULL, {parent_issue_url: parentUrl(41)}),
    issue(43, FULL, {parent_issue_url: parentUrl(41)}), // hangs under the cycle
    issue(44, FULL, {parent_issue_url: parentUrl(44)}), // its own parent
    issue(45, FULL, {parent_issue_url: parentUrl(46)}), issue(46, FULL), // an ordinary parent and child
    issue(47, FULL, {parent_issue_url: parentUrl(999)}), // a parent outside the read ends the walk
  ];
  const model = WS.buildModel(issues, VOCAB, {});
  const rows = rowsByNumber(model);
  for (const number of [41, 42, 43, 44]) assert.equal(rows.get(number).relationError, "parent cycle", `#${number}`);
  for (const number of [45, 46, 47]) assert.equal(rows.get(number).relationError, null, `#${number}`);
  assert.equal(allRows(model).length, 7, "every issue is still one row");
  assert.equal(model.summary.attention, 4);
  assert.deepEqual(plain(rows.get(41).parent), {number: 42, title: "Issue 42", url: `https://github.com/${REPO}/issues/42`}, "the parent link stays");
  const html = WS.renderPage(model, ui());
  assert.equal((html.match(/<span class="bad">parent cycle<\/span>/g) || []).length, 4, "the warning is drawn beside the parent link");
  const chain = Array.from({length: 13}, (_, i) => issue(101 + i, FULL, i ? {parent_issue_url: parentUrl(100 + i)} : {}));
  assert.ok(allRows(WS.buildModel(chain, VOCAB, {})).every((row) => row.relationError === null), "depth alone is not a fault in a flat table");
});

test("test_progress_and_closed_rows", () => {
  const feature = issue(10, withKind("feature"), {sub_issues_summary: {total: 3, completed: 1}});
  const done = issue(11, [], {state: "closed", state_reason: "completed"});
  const rows = rowsByNumber(WS.buildModel([feature, issue(12, FULL), done], VOCAB, {}));
  assert.deepEqual(plain(rows.get(10).progress), {completed: 1, total: 3});
  assert.equal(rows.get(12).progress, null);
  assert.equal(rows.get(11).closed, true);
  assert.equal(rows.get(12).closed, false);
  assert.equal(rows.get(11).cells.status.text, "Done");
});

// ---- summary tiles ----
test("test_summary_counts_the_view", () => {
  const issues = [
    issue(1, withLabels({status: "status:blocked", priority: "priority:high"})),
    issue(2, withLabels({status: "status:partially-implemented"})),
    issue(3, FULL),
    issue(4, withLabels({priority: "priority:high"})),
    issue(5, withLabels({estimate: "estimate:na"}).filter((label) => !label.startsWith("priority:"))),
    issue(6, ["status:open"]),
  ];
  const {summary} = WS.buildModel(issues, VOCAB, {});
  assert.deepEqual(plain(summary), {total: 6, blocked: 1, high: 2, partial: 1, followUps: 5, attention: 2});
});

// ---- filters ----
function filterFixture() {
  const issues = [
    issue(11, withLabels({status: "status:blocked", priority: "priority:high"}), {title: "Zed refusal rendering"}),
    issue(12, FULL, {title: "Gateway flake", parent_issue_url: parentUrl(20)}),
    issue(13, withLabels({status: "status:promoted", handler: "handler:codex"}), {title: "Zed resume probe", parent_issue_url: parentUrl(20)}),
    issue(14, withLabels({priority: "priority:low", estimate: "estimate:3d"}), {title: "Naming alignment"}),
    issue(20, withKind("feature"), {title: "F: Parent feature"}),
  ];
  return tableOf(WS.buildModel(issues, VOCAB, {}), "follow-ups").rows;
}

test("test_filter_rows_matches_search_text_case_insensitively_by_number_or_title", () => {
  const rows = filterFixture();
  const run = (text) => numbersOf(WS.filterRows(rows, {...WS.emptyFilters(), text}, false));
  assert.deepEqual(run(""), [11, 12, 13, 14]);
  assert.deepEqual(run("ZED"), [11, 13]);
  assert.deepEqual(run("#12"), [12]);
  assert.deepEqual(run("  flake "), [12]);
  assert.deepEqual(run("nothing"), []);
});

test("test_filter_rows_dropdowns_match_the_displayed_cell_and_combine", () => {
  const rows = filterFixture();
  const run = (patch) => numbersOf(WS.filterRows(rows, {...WS.emptyFilters(), ...patch}, false));
  assert.deepEqual(run({status: "Blocked"}), [11]);
  assert.deepEqual(run({priority: "Medium"}), [12, 13]);
  assert.deepEqual(run({estimate: "3d"}), [14]);
  assert.deepEqual(run({owner: "Codex"}), [13]);
  assert.deepEqual(run({difficulty: "Medium"}), [11, 12, 13, 14]);
  assert.deepEqual(run({priority: "Medium", text: "zed"}), [13], "filters combine with AND");
  assert.deepEqual(run({status: "Blocked", priority: "Low"}), []);
});

test("test_filter_rows_belongs_to_and_kind", () => {
  const rows = filterFixture();
  const run = (patch, hasKind) => numbersOf(WS.filterRows(rows, {...WS.emptyFilters(), ...patch}, hasKind));
  assert.deepEqual(run({belongs: "20"}, false), [12, 13]);
  assert.deepEqual(run({belongs: "none"}, false), [11, 14]);
  assert.deepEqual(run({kind: "Track"}, false), [11, 12, 13, 14], "a kind filter is ignored by a table with no Kind column");
  assert.deepEqual(run({kind: "Track"}, true), [], "and applied by a table that has one");
  assert.deepEqual(run({kind: "Follow-up"}, true), [11, 12, 13, 14]);
});

test("test_filter_options_list_only_values_present_in_vocabulary_order", () => {
  const rows = filterFixture();
  const options = WS.filterOptions(rows, VOCAB);
  const values = (list) => plain(list.map((option) => option.value));
  assert.deepEqual(values(options.status), ["Open", "Promoted", "Blocked"]);
  assert.deepEqual(values(options.priority), ["High", "Medium", "Low"]);
  assert.deepEqual(values(options.difficulty), ["Medium"]);
  assert.deepEqual(values(options.owner), ["Codex", "Unassigned"]);
  assert.deepEqual(values(options.estimate), ["NA", "3d"]);
  assert.deepEqual(values(options.belongs), ["20", "none"]);
  assert.equal(options.belongs[0].label, "#20 Parent feature");
  const unknown = filterFixture().concat(tableOf(WS.buildModel([issue(99, withLabels({priority: "priority:weird"}))], VOCAB, {}), "follow-ups").rows);
  assert.equal(plain(WS.filterOptions(unknown, VOCAB).priority.at(-1).value), "unknown: weird", "a bad value is listed last so it can be found");
});

// ---- rendering ----
const ui = (patch = {}) => ({...WS.initialUi(VOCAB, "open"), ...patch});
// A page state with header filters set in one table and, optionally, page-wide choices (the toolbar Product and the tiles).
const uiWith = (tableKey, patch, page = {}) => {
  const state = ui();
  state.filters[tableKey] = {...WS.emptyFilters(), ...patch};
  state.page = {...WS.emptyFilters(), ...page};
  return state;
};

test("test_render_page_gives_every_header_its_full_text_and_a_filter", () => {
  const model = WS.buildModel([issue(1, FULL), issue(2, withKind("track")), issue(3, withKind("feature"))], VOCAB, {});
  const open = WS.initialUi(VOCAB, "open");
  open.collapsed.hardening = false;
  const html = WS.renderPage(model, open);
  for (const label of ["Issue / Title", "Product", "Belongs to", "Status", "Priority", "Difficulty", "Estimate", "Owner", "Kind"]) {
    assert.ok(html.includes(`<span class="hl">${label}</span>`), `header ${label}`);
  }
  assert.equal((html.match(/<th scope="col"/g) || []).length, (html.match(/data-filter="/g) || []).length, "every header carries one filter");
  assert.equal((html.match(/data-filter="kind"/g) || []).length, 1, "only the multi-kind table has a Kind column");
  assert.match(html, /<th scope="col" class="c-title" aria-label="Issue \/ Title"><span class="hl">Issue \/ Title<\/span><input type="search" data-filter="text"/);
  assert.match(html, /<th scope="col" class="c-estimate" aria-label="Estimate" title="Planned Estimate">/);
});

test("test_the_page_style_never_clips_text_or_forces_a_narrow_table", () => {
  const style = /<style>([\s\S]*?)<\/style>/.exec(HTML)[1].replace(/\.sr-only\s*\{[^}]*\}/, ""); // the visually hidden live region is the one thing meant to be invisible
  assert.doesNotMatch(style, /text-overflow/);
  assert.doesNotMatch(style, /overflow:\s*hidden/);
  assert.doesNotMatch(style, /table-layout:\s*fixed/);
  assert.doesNotMatch(style, /width:\s*1000px/);
  assert.match(style, /th,\s*td\s*\{[^}]*white-space:\s*nowrap/, "a header or value cell never wraps to a clipped width");
});

test("test_render_page_collapsed_tables_show_only_their_header_and_count", () => {
  const model = WS.buildModel([issue(1, FULL, {title: "visible follow-up"}), issue(2, withKind("track"), {title: "hidden track"})], VOCAB, {});
  const html = WS.renderPage(model, WS.initialUi(VOCAB, "open"));
  assert.match(html, /data-toggle="hardening" aria-expanded="false"/);
  assert.match(html, /data-toggle="follow-ups" aria-expanded="true"/);
  assert.match(html, /visible follow-up/);
  assert.doesNotMatch(html, /hidden track/);
  assert.match(html, /<span class="count">1 open<\/span>/);
  const open = WS.initialUi(VOCAB, "open");
  open.collapsed.hardening = false;
  assert.match(WS.renderPage(model, open), /hidden track/);
});

test("test_render_page_reflects_filter_state_and_counts", () => {
  const model = WS.buildModel([
    issue(1, withLabels({status: "status:blocked"}), {title: "blocked one"}), issue(2, FULL, {title: "plain two"}),
  ], VOCAB, {});
  const html = WS.renderPage(model, uiWith("follow-ups", {status: "Blocked", text: "one"}));
  assert.match(html, /<option value="Blocked" selected>Blocked<\/option>/);
  assert.match(html, /<option value="">All<\/option>/);
  assert.match(html, /data-filter="text" data-table="follow-ups" id="flt-follow-ups-text" [^>]*value="one"/);
  assert.match(html, /<span class="count">1 of 2 open<\/span>/);
  assert.match(html, /blocked one/);
  assert.doesNotMatch(html, /plain two/);
  const none = WS.renderPage(model, uiWith("follow-ups", {text: "zzz"}));
  assert.match(none, /No matching issues/);
  // a filter value no row carries any more stays selectable so the state is visible
  const stale = WS.renderPage(model, uiWith("follow-ups", {owner: "Codex"}));
  assert.match(stale, /<option value="Codex" selected>Codex<\/option>/);
});

test("test_render_page_rows_carry_belongs_to_status_chip_progress_and_closed_style", () => {
  const parent = issue(10, withKind("feature"), {title: "FEAT: Parent name", sub_issues_summary: {total: 2, completed: 1}});
  const child = issue(20, withLabels({status: "status:blocked"}), {title: "Child plan", parent_issue_url: parentUrl(10)});
  const done = issue(30, [], {title: "Finished thing", state: "closed", state_reason: "completed"});
  const html = WS.renderPage(WS.buildModel([parent, child, done], VOCAB, {}), ui({state: "all"}));
  assert.match(html, /1\/2 sub-issues done/);
  assert.match(html, new RegExp(`<a href="https://github.com/${REPO}/issues/10">#10</a> <bdi>Parent name</bdi>`));
  assert.match(html, /<span class="chip tone-danger">Blocked<\/span>/);
  assert.match(html, /<tr class="closed">/);
  assert.match(html, /<span class="chip tone-success">Done<\/span>/);
  assert.match(html, /<span class="count">1 issue<\/span>/);
});

test("test_render_page_untriaged_rows_are_never_filtered_or_collapsed", () => {
  const model = WS.buildModel([issue(1, FULL), issue(2, ["status:open"], {title: "no kind yet"})], VOCAB, {});
  const html = WS.renderPage(model, uiWith("follow-ups", {text: "zzz"}, {status: "Blocked"}));
  assert.match(html, /no kind yet/);
  assert.match(html, /id="sec-untriaged"/);
  assert.doesNotMatch(html.split('id="sec-untriaged"')[1], /data-filter=/, "the untriaged table has no filter row");
});

test("test_render_page_tiles_filter_only_where_a_column_filter_exists", () => {
  const model = WS.buildModel([issue(1, withLabels({status: "status:blocked"})), issue(2, FULL)], VOCAB, {});
  const html = WS.renderPage(model, ui());
  assert.match(html, /<button type="button" class="tile" data-tile-column="status" data-tile-value="Blocked" aria-pressed="false"><b>1<\/b><span>Blocked<\/span><\/button>/);
  assert.match(html, /<div class="tile"><b>2<\/b><span>Open<\/span><\/div>/);
  const pressed = WS.renderPage(model, uiWith("follow-ups", {}, {status: "Blocked"}));
  assert.match(pressed, /data-tile-value="Blocked" aria-pressed="true"/);
  const tableChoice = WS.renderPage(model, uiWith("follow-ups", {status: "Blocked"}));
  assert.match(tableChoice, /data-tile-value="Blocked" aria-pressed="false"/, "a status chosen inside a table is not the tile's page-wide choice");
  assert.match(html, /data-tile-column="priority" data-tile-value="High"/);
  assert.match(html, /data-tile-column="status" data-tile-value="Partially implemented"/);
});

test("test_empty_model_says_so", () => {
  assert.match(WS.renderPage(WS.buildModel([], VOCAB, {}), ui()), /No issues in this view/);
});

test("test_status_tones_only_name_known_statuses", () => {
  for (const key of Object.keys(WS.STATUS_TONES)) assert.ok(Object.hasOwn(VOCAB.statuses, key), key);
  assert.equal(WS.STATUS_TONES.blocked, "danger");
});

// ---- loading ----
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

// A recursive walk needs a stack frame per level, so a deep parent chain must never cost stack. Flat tables have no walk,
// and this keeps it that way: the exact page logic, in a child Node with a deliberately small stack.
const SMALL_STACK_CHILD = `
  const {logic, vocab, labels, size} = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
  const context = require("node:vm").createContext({URLSearchParams});
  require("node:vm").runInContext(logic, context);
  const api = "https://api.github.com/repos/" + vocab.repo + "/issues/";
  const issue = (n, parent) => ({number: n, title: "t", state: "open", state_reason: null,
    html_url: "https://github.com/" + vocab.repo + "/issues/" + n, parent_issue_url: parent ? api + parent : null,
    labels: labels.map((name) => ({name}))});
  const chain = Array.from({length: size}, (_, i) => issue(1000 + i, i ? 999 + i : null));
  const model = context.WorkStatus.buildModel(chain, vocab, {});
  const ui = context.WorkStatus.initialUi(vocab, "open");
  context.WorkStatus.renderPage(model, ui);
  const rows = model.tables.flatMap((t) => t.rows).concat(model.untriaged);
  process.stdout.write(rows.length + " " + new Set(rows.map((r) => r.number)).size + " " + rows.filter((r) => r.relationError !== null).length);
`;

test("test_a_large_chain_of_parents_renders_every_issue_once_on_a_small_stack", () => {
  const input = JSON.stringify({logic: block("work-status-logic"), vocab: VOCAB, labels: FULL, size: 5000});
  const run = spawnSync(process.execPath, ["--stack-size=150", "-e", SMALL_STACK_CHILD], {input, encoding: "utf8"});
  assert.equal(run.status, 0, `the page logic failed on a small stack: ${run.stderr.split("\n").find((l) => /Error/.test(l))}`);
  assert.equal(run.stdout, "5000 5000 0", "every issue of the chain appears exactly once, and a long chain is not mistaken for a cycle");
});

// ---- browser controller ----
function populatedFetch() {
  const issues = [
    issue(1, withLabels({status: "status:blocked", priority: "priority:high"}), {title: "blocked high"}),
    issue(2, FULL, {title: "plain follow-up"}),
    issue(3, withKind("track"), {title: "a hardening track"}),
    issue(4, [...FULL.slice(0, 5), "product:evidence-a2a", "kind:follow-up"], {title: "evidence thing"}),
  ];
  return async () => response(issues);
}

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

test("test_changing_a_column_filter_redraws_the_tables_and_keeps_the_typing_focus", async () => {
  const {doc, elements, focused, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  assert.match(elements.out.innerHTML, /plain follow-up/);
  fire("out", "change", filterEvent("status", "Blocked"));
  assert.match(elements.out.innerHTML, /blocked high/);
  assert.doesNotMatch(elements.out.innerHTML, /plain follow-up/);
  assert.match(elements.out.innerHTML, /<span class="count">1 of 3 open<\/span>/);
  assert.deepEqual(focused.slice(-1), ["flt-follow-ups-status"], "focus returns to the control that changed");
  fire("out", "input", filterEvent("text", "blocked"));
  assert.match(elements.out.innerHTML, /data-filter="text" data-table="follow-ups" id="flt-follow-ups-text" [^>]*value="blocked"/);
  assert.deepEqual(focused.slice(-1), ["flt-follow-ups-text"]);
  const before = elements.out.innerHTML;
  fire("out", "input", filterEvent("text", "blocked"));
  assert.equal(elements.out.innerHTML, before, "an unchanged value does not redraw");
  fire("out", "change", {target: {dataset: {filter: "constructor"}, value: "x", id: "flt-x"}});
  fire("out", "change", {target: {dataset: {}, value: "x", id: "flt-y"}});
  assert.equal(elements.out.innerHTML, before, "an unknown control is ignored");
});

test("test_clear_filters_and_the_product_filter", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  assert.match(elements.product.innerHTML, /<option value="">All products<\/option><option value="optimus">Optimus<\/option><option value="evidence-a2a">Evidence\/A2A<\/option>/);
  assert.equal(elements.clear.textContent, "Clear filters");
  fire("out", "change", filterEvent("priority", "High"));
  assert.equal(elements.clear.textContent, "Clear filters (1)");
  elements.product.value = "evidence-a2a";
  fire("product", "change");
  assert.match(elements.out.innerHTML, /<span class="count">0 of 3 open<\/span>/, "the toolbar Product choice is a page-wide filter that combines with the table's own Priority choice");
  assert.doesNotMatch(elements.out.innerHTML, /<option value="evidence-a2a" selected>/, "and it is not shown as a choice made inside a table header");
  assert.equal(elements.clear.textContent, "Clear filters (2)");
  fire("out", "change", filterEvent("product", "optimus"));
  assert.equal(elements.product.value, "evidence-a2a", "a Product choice made in a table header does not change the toolbar");
  assert.equal(elements.clear.textContent, "Clear filters (3)");
  elements.product.value = "";
  fire("product", "change");
  assert.match(elements.out.innerHTML, /blocked high/, "Priority High and the table's own Product Optimus together keep the one row that has both");
  assert.doesNotMatch(elements.out.innerHTML, /plain follow-up|evidence thing/);
  assert.equal(elements.clear.textContent, "Clear filters (2)");
  fire("clear", "click");
  assert.equal(elements.clear.textContent, "Clear filters");
  assert.equal(elements.product.value, "", "Clear filters also clears the Product choice");
  assert.match(elements.out.innerHTML, /evidence thing/);
  assert.match(elements.out.innerHTML, /plain follow-up/);
});

// ---- a filter chosen in one table's header belongs to that table ----
// Two features, two follow-ups and a plan: three tables that each carry a Status column.
function threeTableFetch() {
  const as = (status, kind) => [...withLabels({status}).slice(0, 6), `kind:${kind}`];
  const issues = [
    issue(10, as("status:open", "feature"), {title: "feature plain"}),
    issue(11, as("status:partially-implemented", "feature"), {title: "feature partial"}),
    issue(20, as("status:blocked", "follow-up"), {title: "followup blocked"}),
    issue(21, as("status:open", "follow-up"), {title: "followup plain"}),
    issue(22, as("status:active", "plan"), {title: "plan active"}),
  ];
  return async () => response(issues);
}

const section = (html, key) => html.split(`id="sec-${key}"`)[1].split("</section>")[0];
const countOf = (html, key) => /<span class="count">([^<]*)<\/span>/.exec(section(html, key))[1];

test("test_a_status_chosen_in_one_table_filters_that_table_only", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(threeTableFetch()));
  fire("out", "change", filterEvent("status", "Partially implemented", "features"));
  const html = elements.out.innerHTML;
  assert.equal(countOf(html, "features"), "1 of 2 open");
  assert.match(section(html, "features"), /<option value="Partially implemented" selected>/);
  assert.match(section(html, "features"), /feature partial/);
  assert.doesNotMatch(section(html, "features"), /feature plain/);
  for (const [key, count, rows] of [["follow-ups", "2 open", /followup blocked[\s\S]*followup plain/], ["plans", "1 open", /plan active/]]) {
    assert.equal(countOf(html, key), count, `${key} is not filtered`);
    assert.match(section(html, key), rows, `${key} keeps all its rows`);
    assert.doesNotMatch(section(html, key), /<option [^>]*selected/, `${key} does not show the Features choice`);
  }
  assert.equal(elements.announce.textContent, "4 of 5 issues match");
  fire("out", "change", filterEvent("status", "Blocked", "follow-ups"));
  const both = elements.out.innerHTML;
  assert.equal(countOf(both, "follow-ups"), "1 of 2 open");
  assert.doesNotMatch(section(both, "follow-ups"), /followup plain/);
  assert.equal(countOf(both, "features"), "1 of 2 open", "the earlier Features choice is untouched by the Follow-ups one");
  assert.match(section(both, "features"), /<option value="Partially implemented" selected>/);
  assert.equal(countOf(both, "plans"), "1 open");
  assert.equal(elements.clear.textContent, "Clear filters (2)", "each table's choice is counted");
});

test("test_search_text_typed_in_one_table_searches_that_table_only", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(threeTableFetch()));
  fire("out", "input", filterEvent("text", "partial", "features"));
  const html = elements.out.innerHTML;
  assert.equal(countOf(html, "features"), "1 of 2 open");
  assert.match(section(html, "features"), /data-filter="text" data-table="features" id="flt-features-text" [^>]*value="partial"/);
  assert.equal(countOf(html, "follow-ups"), "2 open");
  assert.match(section(html, "follow-ups"), /data-filter="text" data-table="follow-ups" id="flt-follow-ups-text" [^>]*value=""/);
});

test("test_every_filter_control_names_the_table_it_belongs_to", () => {
  const model = WS.buildModel([issue(1, FULL), issue(2, withKind("feature")), issue(3, withKind("track"))], VOCAB, {});
  const open = WS.initialUi(VOCAB, "open");
  open.collapsed.hardening = false;
  const html = WS.renderPage(model, open);
  for (const table of ["follow-ups", "features", "hardening"]) {
    const controls = [...section(html, table).matchAll(/<(?:select|input) [^>]*data-filter="[^"]+"[^>]*>/g)].map((m) => m[0]);
    assert.ok(controls.length >= 8, `${table} has its filter row`);
    for (const control of controls) assert.match(control, new RegExp(`data-table="${table}"`), control);
  }
});

test("test_a_header_product_filter_is_that_tables_alone_but_the_toolbar_product_and_the_tiles_stay_page_wide", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(threeTableFetch()));
  fire("out", "change", filterEvent("product", "evidence-a2a", "features"));
  assert.equal(elements.product.value, "", "the toolbar does not follow a table's own Product choice");
  assert.equal(countOf(elements.out.innerHTML, "features"), "0 of 2 open");
  assert.equal(countOf(elements.out.innerHTML, "follow-ups"), "2 open");
  fire("clear", "click");
  elements.product.value = "evidence-a2a";
  fire("product", "change");
  for (const [key, count] of [["features", "0 of 2 open"], ["follow-ups", "0 of 2 open"], ["plans", "0 of 1 open"]]) {
    assert.equal(countOf(elements.out.innerHTML, key), count, `the toolbar Product choice reaches ${key}`);
    assert.doesNotMatch(section(elements.out.innerHTML, key), /<option [^>]*selected/, `and is not shown as a choice made inside ${key}`);
  }
  fire("clear", "click");
  fire("out", "click", {target: {dataset: {tileColumn: "status", tileValue: "Blocked"}}});
  assert.equal(countOf(elements.out.innerHTML, "follow-ups"), "1 of 2 open", "a tile is a page-wide filter");
  assert.equal(countOf(elements.out.innerHTML, "features"), "0 of 2 open");
  assert.match(elements.out.innerHTML, /data-tile-value="Blocked" aria-pressed="true"/);
  assert.doesNotMatch(section(elements.out.innerHTML, "follow-ups"), /<option [^>]*selected/, "and does not pose as a choice made in a table");
});

test("test_clear_filters_resets_every_table_and_the_page_wide_choices", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(threeTableFetch()));
  fire("out", "change", filterEvent("status", "Partially implemented", "features"));
  fire("out", "input", filterEvent("text", "plain", "follow-ups"));
  fire("out", "click", {target: {dataset: {tileColumn: "status", tileValue: "Blocked"}}});
  assert.equal(elements.clear.textContent, "Clear filters (3)");
  fire("clear", "click");
  assert.equal(elements.clear.textContent, "Clear filters");
  for (const [key, count] of [["features", "2 open"], ["follow-ups", "2 open"], ["plans", "1 open"]]) assert.equal(countOf(elements.out.innerHTML, key), count);
  assert.doesNotMatch(elements.out.innerHTML, /<option [^>]*selected|aria-pressed="true"|value="plain"/);
});

test("test_table_filters_survive_a_reload_each_in_its_own_table", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(threeTableFetch()));
  fire("out", "change", filterEvent("status", "Partially implemented", "features"));
  await fire("reload", "click");
  assert.equal(countOf(elements.out.innerHTML, "features"), "1 of 2 open");
  assert.equal(countOf(elements.out.innerHTML, "follow-ups"), "2 open");
});

test("test_a_filter_event_from_a_table_that_does_not_exist_is_ignored", async () => {
  const {doc, elements, focused, fire} = fakeDom();
  await load().boot(doc, fakeWindow(threeTableFetch()));
  const before = elements.out.innerHTML;
  const drawn = focused.length;
  for (const table of ["nope", "constructor", "__proto__", "hasOwnProperty", undefined]) {
    fire("out", "change", {target: {dataset: {filter: "status", table}, value: "Blocked", id: "flt-x-status"}});
  }
  assert.equal(elements.out.innerHTML, before);
  assert.equal(focused.length, drawn);
  assert.equal(elements.clear.textContent, "Clear filters");
});

// ---- tables wider than the page scroll inside their own section ----
test("test_a_table_wider_than_its_section_gets_a_scroll_wrapper_and_stops_being_sticky", async () => {
  const box = (scrollWidth, clientWidth) => {
    const classes = new Set();
    return {scrollWidth, clientWidth, classes, classList: {add: (name) => classes.add(name), remove: (name) => classes.delete(name)}};
  };
  const wide = box(1444, 1217);
  const fits = box(1215, 1217);
  const {doc, elements} = fakeDom();
  elements.out.querySelectorAll = (selector) => (selector === ".scroll" ? [wide, fits] : []);
  const win = fakeWindow(populatedFetch());
  await load().boot(doc, win);
  assert.ok(wide.classes.has("scrolls"), "the table that does not fit scrolls inside its section");
  assert.ok(!fits.classes.has("scrolls"), "a table that fits is left alone");
  fits.scrollWidth = 1300;
  wide.scrollWidth = 1100;
  win.listeners.resize();
  assert.ok(fits.classes.has("scrolls") && !wide.classes.has("scrolls"), "the check is repeated when the window is resized");
});

test("test_a_table_scrolls_only_when_it_is_wider_than_its_section_by_more_than_a_pixel_of_rounding", async () => {
  const box = (scrollWidth) => {
    const classes = new Set();
    return {scrollWidth, clientWidth: 1217, classes, classList: {add: (name) => classes.add(name), remove: (name) => classes.delete(name)}};
  };
  const exact = box(1217);
  const rounded = box(1218);
  const wider = box(1219);
  const {doc, elements} = fakeDom();
  elements.out.querySelectorAll = () => [exact, rounded, wider];
  await load().boot(doc, fakeWindow(populatedFetch()));
  assert.ok(!exact.classes.has("scrolls"), "a table that exactly fits keeps its sticky header");
  assert.ok(!rounded.classes.has("scrolls"), "one pixel of sub-pixel rounding is not overflow");
  assert.ok(wider.classes.has("scrolls"), "two pixels is");
});

test("test_clear_resets_the_toolbar_product_even_when_nothing_could_be_read", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(async () => response(null, {status: 500})));
  elements.product.value = "optimus";
  fire("product", "change");
  assert.equal(elements.clear.textContent, "Clear filters (1)");
  fire("clear", "click");
  assert.equal(elements.product.value, "", "the toolbar must not keep showing a product filter that Clear removed");
  assert.equal(elements.clear.textContent, "Clear filters");
});

test("test_the_scroll_fallback_overrides_the_sticky_header", () => {
  const scroll = cssRules().find((rule) => rule.selector === ".scroll.scrolls");
  assert.ok(scroll && /overflow-x:\s*auto/.test(scroll.body));
  const head = cssRules().find((rule) => rule.selector === ".scroll.scrolls thead th");
  assert.ok(head && /position:\s*static/.test(head.body), "a scrolling table cannot also stick: the wider rule must win");
});

test("test_tiles_toggle_a_column_filter_and_headers_toggle_collapse", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  fire("out", "click", {target: {dataset: {tileColumn: "status", tileValue: "Blocked"}}});
  assert.doesNotMatch(elements.out.innerHTML, /plain follow-up/);
  assert.match(elements.out.innerHTML, /data-tile-value="Blocked" aria-pressed="true"/);
  fire("out", "click", {target: {dataset: {tileColumn: "status", tileValue: "Blocked"}}});
  assert.match(elements.out.innerHTML, /plain follow-up/, "a second click clears the filter");
  assert.doesNotMatch(elements.out.innerHTML, /a hardening track/);
  fire("out", "click", {target: {dataset: {toggle: "hardening"}}});
  assert.match(elements.out.innerHTML, /a hardening track/);
  fire("out", "click", {target: {closest: () => ({dataset: {toggle: "hardening"}}), dataset: {}}});
  assert.doesNotMatch(elements.out.innerHTML, /a hardening track/, "the nearest control is used when a child element is clicked");
  fire("out", "click", {target: {dataset: {toggle: "no-such-table"}}});
  fire("out", "click", {target: null});
});

test("test_filters_and_collapse_survive_a_reload", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  fire("out", "change", filterEvent("status", "Blocked"));
  fire("out", "click", {target: {dataset: {toggle: "hardening"}}});
  await fire("reload", "click");
  assert.doesNotMatch(elements.out.innerHTML, /plain follow-up/);
  assert.match(elements.out.innerHTML, /blocked high/);
  assert.match(elements.out.innerHTML, /<span class="count">1 of 3 open<\/span>/);
  assert.match(elements.out.innerHTML, /data-toggle="hardening" aria-expanded="true"/);
});

// ---- defects found by the independent review of this page ----
test("test_attention_counts_an_untriaged_row_whose_only_fault_is_its_product_or_kind_label", () => {
  const issues = [
    issue(1, [...FULL.slice(0, 5), "product:mars", "kind:follow-up"]),
    issue(2, FULL.slice(0, 6).concat([])),
    issue(3, [...FULL.slice(0, 5), "kind:plan"]),
    issue(4, FULL),
  ];
  const model = WS.buildModel(issues, VOCAB, {});
  assert.deepEqual(numbersOf(model.untriaged), [1, 2, 3]);
  assert.equal(model.summary.attention, 3);
  const html = WS.renderPage(model, ui());
  assert.match(html, /<div class="tile warn"><b>3<\/b><span>Need attention<\/span><\/div>/);
});

test("test_an_empty_label_value_is_a_red_fault_not_a_blank_cell", () => {
  assert.deepEqual({...WS.metadataCell(issue(1, ["estimate:"]), VOCAB.dimensions.estimate)}, {text: "empty value", bad: true});
  assert.deepEqual({...WS.metadataCell(issue(1, ["priority:"]), VOCAB.dimensions.priority)}, {text: "empty value", bad: true});
  const rows = tableOf(WS.buildModel([issue(1, FULL), issue(2, withLabels({estimate: "estimate:"}))], VOCAB, {}), "follow-ups").rows;
  assert.equal(WS.filterOptions(rows, VOCAB).estimate.some((option) => option.value === ""), false, "no option can collide with All");
});

test("test_no_parent_means_no_parent_link_at_all", () => {
  const model = WS.buildModel([
    issue(6, FULL, {parent_issue_url: "https://api.github.com/repos/someone/else/issues/1"}), issue(7, FULL),
  ], VOCAB, {});
  const rows = tableOf(model, "follow-ups").rows;
  assert.deepEqual(numbersOf(WS.filterRows(rows, {...WS.emptyFilters(), belongs: "none"}, false)), [7], "a malformed link is a fault, not an absent parent");
  const onlyMalformed = tableOf(WS.buildModel([issue(6, FULL, {parent_issue_url: "https://api.github.com/repos/someone/else/issues/1"})], VOCAB, {}), "follow-ups").rows;
  assert.equal(WS.filterOptions(onlyMalformed, VOCAB).belongs.length, 0, "no No-parent choice when every row has a malformed link");
});

test("test_the_kind_dropdown_lists_kinds_in_the_order_the_table_groups_its_rows", () => {
  const model = WS.buildModel([issue(1, withKind("track")), issue(2, withKind("item")), issue(3, withKind("candidate"))], VOCAB, {});
  const hardening = tableOf(model, "hardening");
  assert.deepEqual(plain(hardening.rows.map((row) => row.kind)), ["Track", "Item", "Candidate"]);
  const open = WS.initialUi(VOCAB, "open");
  open.collapsed.hardening = false;
  const html = WS.renderPage(model, open);
  assert.match(html, /<select data-filter="kind"[^>]*><option value="">All<\/option><option value="Track">Track<\/option><option value="Item">Item<\/option><option value="Candidate">Candidate<\/option><\/select>/);
});

test("test_a_long_belongs_to_label_is_cut_on_a_character_boundary", () => {
  const parent = issue(77, withKind("feature"), {title: "ID: " + "😀".repeat(80)});
  const child = issue(78, FULL, {parent_issue_url: parentUrl(77)});
  const rows = tableOf(WS.buildModel([parent, child], VOCAB, {}), "follow-ups").rows;
  const label = WS.filterOptions(rows, VOCAB).belongs[0].label;
  assert.doesNotMatch(label, /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/, "no lone surrogate");
  assert.ok(label.endsWith("…"));
  assert.ok(Array.from(label).length <= 60);
});

test("test_issue_titles_are_bidi_isolated_so_they_cannot_reorder_the_text_around_them", () => {
  const spoof = "Spoofed ‮esrever siht";
  const parent = issue(10, withKind("feature"), {title: "FEAT: " + spoof});
  const child = issue(11, FULL, {title: spoof, parent_issue_url: parentUrl(10)});
  const html = WS.renderPage(WS.buildModel([parent, child, issue(12, [], {title: spoof})], VOCAB, {}), ui());
  assert.equal(html.split(`<bdi>${spoof}</bdi>`).length - 1, 3, "the issue title in each row and the parent title are isolated");
  assert.match(html, /<\/bdi> <span class="bad">product missing; kind missing<\/span>/, "the fault text sits outside the isolated title");
});

test("test_a_blank_search_is_not_an_active_filter_and_clear_resets_the_label_after_a_failed_read", async () => {
  const {doc, elements, fire} = fakeDom();
  const replies = [response([issue(1, FULL, {title: "one"})]), response(null, {status: 500})];
  await load().boot(doc, fakeWindow(async () => replies.shift()));
  fire("out", "input", filterEvent("text", "   "));
  assert.equal(elements.clear.textContent, "Clear filters", "whitespace filters nothing, so it is not counted");
  fire("out", "change", filterEvent("priority", "Medium"));
  assert.equal(elements.clear.textContent, "Clear filters (1)");
  await fire("reload", "click");
  assert.equal(elements.out.innerHTML, "");
  fire("clear", "click");
  assert.equal(elements.clear.textContent, "Clear filters", "the label follows the filters even when nothing is drawn");
});


// ---- accessibility and layout defects found by the independent review ----
const STYLE = /<style>([\s\S]*?)<\/style>/.exec(HTML)[1];
const cssRules = () => Array.from(STYLE.matchAll(/([^{}]+)\{([^}]*)\}/g), (m) => ({selector: m[1].trim(), body: m[2]}));

test("test_filter_dropdowns_size_to_their_widest_option_so_the_chosen_value_is_never_cut", () => {
  const rules = cssRules().filter((rule) => rule.selector === "th select");
  assert.ok(rules.length > 0);
  for (const rule of rules) {
    assert.doesNotMatch(rule.body, /(^|;)\s*width:\s*100%/, "a percentage width lets the column squeeze the select to its label");
  }
  assert.ok(rules.some((rule) => /(^|;)\s*width:\s*auto/.test(rule.body)), "a select is as wide as its widest option");
  const belongs = cssRules().find((rule) => rule.selector === "th.c-belongs select");
  assert.ok(belongs && /min-width:\s*\d/.test(belongs.body), "the long parent list still keeps All readable");
});

test("test_the_sticky_header_only_applies_where_the_tables_fit_and_never_hides_a_focused_row", () => {
  const sticky = /@media \(min-width: (\d+)px\) \{([^}]*\{[^}]*\}[^}]*)\}/.exec(STYLE);
  const scroll = /@media \(max-width: (\d+)px\) \{ \.scroll \{ overflow-x: auto; \} \}/.exec(STYLE);
  assert.ok(sticky && scroll);
  assert.match(sticky[2], /position:\s*sticky/);
  assert.equal(Number(sticky[1]), Number(scroll[1]) + 1, "exactly one of sticky headers and a scroll wrapper is on at any width");
  assert.match(sticky[2], /scroll-padding-top:\s*\d/, "keyboard focus scrolls clear of the sticky header");
});

test("test_wide_values_wrap_instead_of_widening_the_table_and_long_parent_titles_break", () => {
  const wrapped = cssRules().find((rule) => rule.selector === "td.bad, td.c-estimate");
  assert.ok(wrapped && /white-space:\s*normal/.test(wrapped.body) && /max-width:\s*\d/.test(wrapped.body));
  const belongs = cssRules().find((rule) => rule.selector === "th.c-belongs, td.c-belongs");
  assert.ok(belongs && /overflow-wrap:\s*anywhere/.test(belongs.body));
});

test("test_every_cell_class_the_style_sheet_targets_is_one_the_renderer_emits", () => {
  // A rule for a class that no cell carries does nothing: the Estimate wrapping rule was exactly that.
  const targeted = new Set();
  for (const rule of cssRules()) for (const m of rule.selector.matchAll(/\b(td|th)\.([a-z][\w-]*)/g)) targeted.add(`${m[1]}.${m[2]}`);
  assert.ok(targeted.size >= 7);
  const model = WS.buildModel([
    issue(1, withLabels({priority: "priority:high", estimate: "estimate:about two weeks of focused work"}), {parent_issue_url: parentUrl(2), title: "high"}),
    issue(2, withLabels({priority: "priority:low"}), {title: "low"}),
    issue(3, withLabels({priority: "priority:high"}).filter((label) => !label.startsWith("estimate:")), {title: "bad estimate"}),
    issue(4, withKind("track"), {state: "closed", state_reason: "completed", title: "closed"}),
  ], VOCAB, {});
  const html = WS.renderPage(model, ui());
  const emitted = new Set(Array.from(html.matchAll(/<(td|th)[^>]*class="([^"]+)"/g), (m) => m[2].split(" ").map((name) => `${m[1]}.${name}`)).flat());
  for (const name of targeted) assert.ok(emitted.has(name), `the style sheet targets ${name} but no such cell is rendered`);
});

test("test_a_long_estimate_wraps_in_a_bounded_cell_and_cannot_widen_its_dropdown", () => {
  const long = "about two weeks of focused work incl review";
  const html = WS.renderPage(WS.buildModel([issue(1, withLabels({estimate: "estimate:" + long}))], VOCAB, {}), ui());
  assert.ok(html.includes(`<td class="c-estimate">${long}</td>`), "the free-form Estimate cell carries the class the wrapping rule targets");
  const bound = (rule) => Number(/max-width:\s*([\d.]+)rem/.exec(rule.body)[1]);
  const cell = cssRules().find((rule) => rule.selector === "td.bad, td.c-estimate");
  const dropdown = cssRules().find((rule) => rule.selector === "th select" && /max-width:\s*[\d.]+rem/.test(rule.body));
  assert.ok(cell && dropdown, "both are bounded in rem: a percentage cannot bound a control the column is sized by");
  assert.equal(bound(dropdown), bound(cell), "the dropdown and the cell bound the column to the same width");
  assert.ok(bound(cell) <= 10, "narrow enough that every table still fits at the width where headers stick");
});

test("test_a_pressed_tile_has_a_cue_that_does_not_depend_on_color", () => {
  const pressed = cssRules().find((rule) => rule.selector === 'button.tile[aria-pressed="true"]');
  assert.ok(pressed && /outline:\s*\d+px solid/.test(pressed.body), "an outline survives forced-colors mode");
});

test("test_loading_state_is_a_live_region_and_filter_results_are_announced", async () => {
  assert.match(HTML, /<p class="note" id="stamp" role="status" aria-live="polite">/);
  assert.match(HTML, /<p class="sr-only" id="announce" role="status" aria-live="polite"><\/p>/);
  assert.ok(cssRules().some((rule) => rule.selector === ".sr-only" && /clip|clip-path/.test(rule.body)));
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  assert.equal(elements.announce.textContent, "4 issues");
  fire("out", "click", {target: {dataset: {tileColumn: "status", tileValue: "Blocked"}}});
  assert.equal(elements.announce.textContent, "1 of 4 issues match", "collapsed tables count too: the header shows how many match");
  fire("clear", "click");
  assert.equal(elements.announce.textContent, "4 issues");
  fire("out", "change", filterEvent("status", "Blocked"));
  assert.equal(elements.announce.textContent, "2 of 4 issues match", "a choice in one table narrows that table only");
  fire("clear", "click");
  assert.equal(elements.announce.textContent, "4 issues");
});

test("test_tables_and_headers_have_unique_accessible_names", () => {
  const model = WS.buildModel([issue(1, FULL), issue(2, withKind("feature")), issue(3, ["status:open"])], VOCAB, {});
  const html = WS.renderPage(model, ui());
  assert.match(html, /<table aria-label="Follow-ups and defects">/);
  assert.match(html, /<table aria-label="Features">/);
  assert.match(html, /<table aria-label="Untriaged issues">/);
  assert.match(html, /<th scope="col" class="c-priority" aria-label="Priority"><span class="hl">Priority<\/span><select data-filter="priority" data-table="follow-ups" id="flt-follow-ups-priority" aria-label="Filter Priority in Follow-ups and defects">/);
  assert.match(html, /aria-label="Search Issue \/ Title in Features"/);
  const labels = html.match(/aria-label="(?:Filter|Search) [^"]*"/g);
  assert.equal(new Set(labels).size, labels.length, "no two controls on the page share a name");
});

test("test_typing_waits_for_an_ime_composition_to_end", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  const before = elements.out.innerHTML;
  fire("out", "input", {isComposing: true, target: {dataset: {filter: "text", table: "follow-ups"}, value: "ni", id: "flt-follow-ups-text"}});
  assert.equal(elements.out.innerHTML, before, "a redraw mid-composition would destroy the composition");
  fire("out", "compositionend", {target: {dataset: {filter: "text", table: "follow-ups"}, value: "nihao", id: "flt-follow-ups-text"}});
  assert.match(elements.out.innerHTML, /data-filter="text" data-table="follow-ups" id="flt-follow-ups-text" [^>]*value="nihao"/);
});

// ---- behaviour pinned by mutation testing: each test below fails when a deliberate fault is put into the page ----
const withoutStatus = FULL.filter((label) => !label.startsWith("status:"));

test("test_closed_rows_get_a_chip_tone_from_their_close_reason", () => {
  const model = WS.buildModel([issue(1, withoutStatus, {state: "closed", state_reason: "not_planned"}),
    issue(2, withoutStatus, {state: "closed", state_reason: "completed"})], VOCAB, {});
  const rows = rowsByNumber(model);
  assert.equal(rows.get(1).tone, "neutral");
  assert.equal(rows.get(2).tone, "success");
  const html = WS.renderPage(model, ui({state: "closed"}));
  assert.match(html, /<span class="chip tone-neutral">Not planned<\/span>/);
  assert.match(html, /<span class="chip tone-success">Done<\/span>/);
});

test("test_every_vocabulary_status_has_the_tone_the_table_names_or_neutral", () => {
  for (const key of Object.keys(VOCAB.statuses)) {
    const model = WS.buildModel([issue(1, withLabels({status: "status:" + key}))], VOCAB, {});
    const expected = Object.hasOwn(WS.STATUS_TONES, key) ? WS.STATUS_TONES[key] : "neutral";
    assert.equal(allRows(model)[0].tone, expected, key);
    assert.ok(WS.renderPage(model, ui()).includes(`<span class="chip tone-${expected}">${VOCAB.statuses[key]}</span>`), key);
  }
});

test("test_a_tile_count_equals_the_rows_its_filter_keeps", () => {
  const model = WS.buildModel([
    issue(1, withLabels({status: "status:blocked"}), {state: "closed", state_reason: "completed"}),
    issue(2, withLabels({status: "status:partially-implemented"}), {state: "closed", state_reason: "completed"}),
    issue(3, withLabels({status: "status:blocked"})),
  ], VOCAB, {});
  const rows = allRows(model);
  for (const tile of model.tiles.filter((t) => t.column !== undefined)) {
    assert.equal(tile.count, rows.filter((row) => row.cells[tile.column].text === tile.value).length, `${tile.id} tile`);
  }
  assert.equal(model.summary.blocked, 1, "a closed issue is not blocked, whatever label it still carries");
  assert.equal(model.summary.partial, 0);
});

test("test_an_issue_without_sub_issues_shows_no_progress", () => {
  // GitHub sends {total: 0, completed: 0, percent_completed: 0} for an issue that has no sub-issues.
  const model = WS.buildModel([issue(1, FULL, {sub_issues_summary: {total: 0, completed: 0, percent_completed: 0}})], VOCAB, {});
  assert.equal(rowsByNumber(model).get(1).progress, null);
  assert.doesNotMatch(WS.renderPage(model, ui()), /sub-issues done/);
});

test("test_only_the_priority_cell_carries_a_level_class_and_a_bad_one_is_red_instead", () => {
  const model = WS.buildModel([
    issue(1, withLabels({priority: "priority:high"})), issue(2, FULL), issue(3, withLabels({priority: "priority:low"})),
    issue(4, withLabels({priority: "priority:weird"})),
  ], VOCAB, {});
  const html = WS.renderPage(model, ui());
  assert.match(html, /<td class="pri-high">High<\/td>/);
  assert.match(html, /<td class="pri-low">Low<\/td>/);
  assert.match(html, /<td class="pri-medium">Medium<\/td>/);
  assert.match(html, /<td class="bad">unknown: weird<\/td>/);
  assert.equal((html.match(/class="pri-/g) || []).length, 3);
});

test("test_a_malformed_parent_link_needs_attention", () => {
  const model = WS.buildModel([issue(1, FULL, {parent_issue_url: "https://api.github.com/repos/someone/else/issues/1"}), issue(2, FULL)], VOCAB, {});
  assert.equal(rowsByNumber(model).get(1).relationError, "malformed parent link");
  assert.equal(model.summary.attention, 1);
  assert.match(WS.renderPage(model, ui()), /<div class="tile warn"><b>1<\/b><span>Need attention<\/span><\/div>/);
});

test("test_the_attention_tile_is_not_flagged_when_nothing_needs_attention", () => {
  const html = WS.renderPage(WS.buildModel([issue(1, FULL), issue(2, withKind("track"))], VOCAB, {}), ui());
  assert.match(html, /<div class="tile"><b>0<\/b><span>Need attention<\/span><\/div>/);
  assert.doesNotMatch(html, /tile warn/);
});

test("test_a_vocabulary_without_a_high_priority_has_no_high_priority_tile", () => {
  const noHigh = JSON.parse(JSON.stringify(VOCAB));
  delete noHigh.dimensions.priority.values.high;
  const model = WS.buildModel([issue(1, FULL)], noHigh, {});
  assert.deepEqual(plain(model.tiles.map((tile) => tile.id)), ["total", "blocked", "partial", "followUps", "attention"]);
  assert.doesNotMatch(WS.renderPage(model, WS.initialUi(noHigh, "open")), /data-tile-column="priority"/);
  const noPriority = JSON.parse(JSON.stringify(VOCAB));
  delete noPriority.dimensions.priority;
  assert.equal(WS.buildModel([issue(1, FULL)], noPriority, {}).tiles.some((tile) => tile.id === "high"), false);
});

test("test_the_difficulty_dropdown_filters_rows", () => {
  const rows = tableOf(WS.buildModel([
    issue(1, withLabels({difficulty: "difficulty:low"})), issue(2, FULL), issue(3, withLabels({difficulty: "difficulty:high"})),
  ], VOCAB, {}), "follow-ups").rows;
  const run = (difficulty) => numbersOf(WS.filterRows(rows, {...WS.emptyFilters(), difficulty}, false));
  assert.deepEqual(run("Low"), [1]);
  assert.deepEqual(run("Medium"), [2]);
  assert.deepEqual(run("High"), [3]);
});

test("test_every_filter_control_the_page_draws_is_a_filter_the_controller_keeps", async () => {
  const model = WS.buildModel([issue(1, FULL), issue(2, withKind("track"))], VOCAB, {});
  const open = WS.initialUi(VOCAB, "open");
  open.collapsed.hardening = false;
  const drawn = new Set(Array.from(WS.renderPage(model, open).matchAll(/data-filter="([^"]+)"/g), (m) => m[1]));
  assert.equal(drawn.size, 9);
  for (const key of drawn) assert.ok(Object.hasOwn(WS.emptyFilters(), key), `${key} must be a key of the filter state`);
  const {doc, elements, fire} = fakeDom();
  const issues = [issue(1, withLabels({handler: "handler:codex"}), {title: "codex one"}), issue(2, FULL, {title: "unassigned two"})];
  await load().boot(doc, fakeWindow(async () => response(issues)));
  fire("out", "change", filterEvent("owner", "Codex"));
  assert.match(elements.out.innerHTML, /codex one/);
  assert.doesNotMatch(elements.out.innerHTML, /unassigned two/);
  assert.equal(elements.clear.textContent, "Clear filters (1)");
});

test("test_values_the_vocabulary_does_not_know_are_listed_alphabetically_after_the_known_ones", () => {
  const rows = tableOf(WS.buildModel([
    issue(1, withLabels({estimate: "estimate:3d"})), issue(2, withLabels({estimate: "estimate:1d"})),
    issue(3, withLabels({estimate: "estimate:2d"})), issue(4, FULL),
  ], VOCAB, {}), "follow-ups").rows;
  assert.deepEqual(plain(WS.filterOptions(rows, VOCAB).estimate.map((option) => option.value)), ["NA", "1d", "2d", "3d"]);
});

test("test_belongs_to_choices_are_in_numeric_order", () => {
  const rows = tableOf(WS.buildModel([
    issue(100, withKind("feature")), issue(9, withKind("feature")), issue(10, withKind("feature")),
    issue(201, FULL, {parent_issue_url: parentUrl(100)}), issue(202, FULL, {parent_issue_url: parentUrl(9)}),
    issue(203, FULL, {parent_issue_url: parentUrl(10)}),
  ], VOCAB, {}), "follow-ups").rows;
  assert.deepEqual(plain(WS.filterOptions(rows, VOCAB).belongs.map((option) => option.value)), ["9", "10", "100"]);
});

test("test_the_status_dropdown_lists_close_reasons_before_faulty_values", () => {
  const rows = tableOf(WS.buildModel([
    issue(1, FULL), issue(2, withoutStatus, {state: "closed", state_reason: "completed"}),
    issue(3, withoutStatus, {state: "closed", state_reason: "not_planned"}), issue(4, withoutStatus, {state: "closed", state_reason: null}),
  ], VOCAB, {}), "follow-ups").rows;
  assert.deepEqual(plain(WS.filterOptions(rows, VOCAB).status.map((option) => option.value)),
    ["Open", "Done", "Not planned", "Closed (reason unavailable)"]);
});

test("test_a_belongs_to_label_of_exactly_the_limit_is_not_cut", () => {
  const label = (title) => {
    const rows = tableOf(WS.buildModel([issue(77, withKind("feature"), {title: "ID: " + title}), issue(78, FULL, {parent_issue_url: parentUrl(77)})], VOCAB, {}), "follow-ups").rows;
    return WS.filterOptions(rows, VOCAB).belongs[0].label;
  };
  const exact = "x".repeat(56); // "#77 " is 4 characters, so this label is exactly 60
  assert.equal(label(exact), "#77 " + exact);
  const over = label("x".repeat(57)); // 61 characters: cut to 59 and an ellipsis
  assert.equal(over, "#77 " + "x".repeat(55) + "…");
  assert.equal(Array.from(over).length, 60);
});

test("test_a_parent_title_loses_only_an_identifier_prefix", () => {
  const parentTitleOf = (title) => {
    const model = WS.buildModel([issue(10, withKind("feature"), {title}), issue(20, FULL, {parent_issue_url: parentUrl(10)})], VOCAB, {});
    return rowsByNumber(model).get(20).parent.title;
  };
  assert.equal(parentTitleOf("P11-FEAT-X: Zed resume"), "Zed resume");
  assert.equal(parentTitleOf(": leading colon"), ": leading colon");
  assert.equal(parentTitleOf("Fix the build: part two"), "Fix the build: part two", "prose before a colon is not an identifier");
  assert.equal(parentTitleOf("no colon here"), "no colon here");
});

test("test_the_page_cap_is_exactly_fifty_requests", async () => {
  let calls = 0;
  const endless = async () => { calls += 1; return response([], {link: `<https://api.github.com/again>; rel="next"`}); };
  await assert.rejects(WS.loadView(endless, VOCAB, "open", null), /stopped after 50 pages/);
  assert.equal(calls, 50, "the 51st request is never made");
  let n = 0;
  const fifty = async () => { n += 1; return response([issue(n, FULL)], n < 50 ? {link: `<https://api.github.com/p${n + 1}>; rel="next"`} : {}); };
  const view = await WS.loadView(fifty, VOCAB, "open", null);
  assert.equal(view.requests, 50, "a list that ends on page 50 is read in full");
  assert.equal(view.issues.length, 50);
});

test("test_a_label_is_url_encoded_and_an_unknown_state_is_refused_before_any_request", async () => {
  const urls = [];
  await WS.loadView(async (url) => { urls.push(url); return response([]); }, VOCAB, "open", {label: "needs review&x=1"});
  assert.equal(urls[0], `https://api.github.com/repos/${REPO}/issues?state=open&per_page=100&labels=needs%20review%26x%3D1`);
  let called = false;
  await assert.rejects(WS.loadView(async () => { called = true; return response([]); }, VOCAB, "bogus", null), /unknown state filter bogus/);
  assert.equal(called, false);
});

test("test_http_429_with_no_quota_left_is_a_rate_limit_but_other_failures_are_not", async () => {
  await assert.rejects(WS.loadView(async () => response(null, {status: 429, remaining: "0"}), VOCAB, "open", null), /rate limit/);
  await assert.rejects(WS.loadView(async () => response(null, {status: 403, remaining: "0"}), VOCAB, "open", null), /rate limit/);
  await assert.rejects(WS.loadView(async () => response(null, {status: 403, remaining: "59"}), VOCAB, "open", null), /GitHub answered HTTP 403/);
  await assert.rejects(WS.loadView(async () => response(null, {status: 429, remaining: "59"}), VOCAB, "open", null), /GitHub answered HTTP 429/);
});

test("test_columns_come_in_the_documented_order", () => {
  const model = WS.buildModel([issue(1, FULL), issue(2, withKind("track"))], VOCAB, {});
  const open = WS.initialUi(VOCAB, "open");
  open.collapsed.hardening = false;
  const heads = WS.renderPage(model, open).split("<thead>").slice(1)
    .map((part) => [...part.split("</thead>")[0].matchAll(/<th scope="col" class="c-(\w+)"/g)].map((m) => m[1]));
  assert.deepEqual(heads, [
    ["title", "product", "belongs", "status", "priority", "difficulty", "estimate", "owner"],
    ["title", "kind", "product", "belongs", "status", "priority", "difficulty", "estimate", "owner"],
  ]);
});

test("test_a_late_failed_read_cannot_clear_a_newer_view", async () => {
  let rejectFirst;
  const first = new Promise((_, reject) => { rejectFirst = reject; });
  let calls = 0;
  const fetchImpl = async () => { calls += 1; return calls === 1 ? first : response([issue(2, FULL, {title: "newer read"})]); };
  const {doc, elements, fire} = fakeDom();
  const firstRead = load().boot(doc, fakeWindow(fetchImpl));
  elements.state.value = "closed";
  await fire("state", "change");
  assert.match(elements.out.innerHTML, /newer read/);
  rejectFirst(new Error("late network failure"));
  await firstRead;
  assert.match(elements.out.innerHTML, /newer read/);
  assert.doesNotMatch(elements.stamp.innerHTML, /late network failure/);
});

test("test_the_total_tile_and_the_count_word_follow_the_state_that_was_read", () => {
  const closed = (number) => issue(number, withoutStatus, {state: "closed", state_reason: "completed"});
  const closedHtml = WS.renderPage(WS.buildModel([closed(1), closed(2)], VOCAB, {}), ui({state: "closed"}));
  assert.match(closedHtml, /<span class="count">2 closed<\/span>/);
  assert.match(closedHtml, /<div class="tile"><b>2<\/b><span>Closed<\/span><\/div>/);
  const all = WS.renderPage(WS.buildModel([issue(1, FULL), issue(2, FULL)], VOCAB, {}), ui({state: "all"}));
  assert.match(all, /<div class="tile"><b>2<\/b><span>Issues<\/span><\/div>/);
  assert.match(all, /<span class="count">2 issues<\/span>/);
});

test("test_the_caret_is_restored_where_the_user_was_typing", async () => {
  const {doc, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  const carets = [];
  const byId = doc.getElementById;
  doc.getElementById = (id) => (/^flt-/.test(id) ? {id, focus() {}, setSelectionRange: (a, b) => carets.push([a, b])} : byId(id));
  fire("out", "input", {target: {dataset: {filter: "text", table: "follow-ups"}, value: "blocked", id: "flt-follow-ups-text", selectionStart: 3}});
  assert.deepEqual(carets, [[3, 3]]);
  fire("out", "change", filterEvent("status", "Blocked"));
  assert.deepEqual(carets, [[3, 3]], "a select has no caret to restore");
});

test("test_a_row_whose_url_is_not_the_issue_page_has_no_link", () => {
  const html = WS.renderPage(WS.buildModel([issue(1, FULL, {html_url: "https://evil.example/phish"})], VOCAB, {}), ui());
  assert.match(html, /<td class="c-title">#1 — <bdi>Issue 1<\/bdi>/);
  assert.doesNotMatch(html, /href="null"/);
});

test("test_a_single_product_fault_is_explained_in_the_row", () => {
  const html = WS.renderPage(WS.buildModel([issue(1, [...FULL.slice(0, 5), "product:mars", "kind:follow-up"])], VOCAB, {}), ui());
  assert.match(html, /<\/bdi> <span class="bad">product unknown: mars<\/span>/);
});

test("test_an_unrecognised_kind_label_is_escaped_and_shown_in_the_untriaged_kind_cell", () => {
  const hostile = WS.renderPage(WS.buildModel([issue(1, [...FULL.slice(0, 6), "kind:<img src=x onerror=alert(1)>"])], VOCAB, {}), ui());
  assert.doesNotMatch(hostile, /<img/);
  assert.match(hostile, /<td>&lt;img src=x onerror=alert\(1\)&gt;<\/td>/);
  const part = WS.renderPage(WS.buildModel([issue(2, [...FULL.slice(0, 6), "kind:mars"])], VOCAB, {}), ui()).split('id="sec-untriaged"')[1];
  assert.match(part, /<th scope="col" class="c-kind">Kind<\/th>/);
  assert.match(part, /<td>mars<\/td>/);
});

test("test_a_parent_outside_the_view_is_a_bare_link", () => {
  const html = WS.renderPage(WS.buildModel([issue(30, FULL, {parent_issue_url: parentUrl(99)})], VOCAB, {}), ui());
  assert.match(html, new RegExp(`<td class="c-belongs"><a href="https://github.com/${REPO}/issues/99">#99</a></td>`));
  assert.doesNotMatch(html, /<bdi>null<\/bdi>/);
});

test("test_a_missing_value_cell_carries_the_bad_class", () => {
  const noPriority = WS.renderPage(WS.buildModel([issue(1, FULL.filter((label) => !label.startsWith("priority:")))], VOCAB, {}), ui());
  assert.match(noPriority, /<td class="bad">missing<\/td>/);
  const noStatus = WS.renderPage(WS.buildModel([issue(1, withoutStatus)], VOCAB, {}), ui());
  assert.match(noStatus, /<td class="bad">missing status<\/td>/);
});

test("test_open_on_github_mirrors_the_read", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  const href = (query) => `https://github.com/${REPO}/issues?q=${encodeURIComponent(query)}`;
  assert.equal(elements.live.href, href("is:issue is:open"));
  elements.state.value = "closed";
  await fire("state", "change");
  assert.equal(elements.live.href, href("is:issue is:closed"));
  elements.state.value = "all";
  await fire("state", "change");
  assert.equal(elements.live.href, href("is:issue"));
});

test("test_the_chevron_shows_collapsed_or_expanded_and_empty_kind_groups_are_not_drawn", () => {
  const html = WS.renderPage(WS.buildModel([issue(1, FULL), issue(2, withKind("track"))], VOCAB, {}), ui());
  assert.match(html, /<span class="chev" aria-hidden="true">▸<\/span>Hardening work/);
  assert.match(html, /<span class="chev" aria-hidden="true">▾<\/span>Follow-ups and defects/);
  const lone = WS.renderPage(WS.buildModel([issue(1, FULL)], VOCAB, {}), ui());
  assert.equal((lone.match(/<section class="sec"/g) || []).length, 1);
  for (const key of ["features", "plans", "hardening", "obligations"]) assert.doesNotMatch(lone, new RegExp(`data-toggle="${key}"`));
});

test("test_the_kind_filter_does_not_hide_rows_of_tables_without_a_kind_column", () => {
  const model = WS.buildModel([issue(1, FULL, {title: "plain follow-up"}), issue(2, withKind("track"), {title: "a hardening track"})], VOCAB, {});
  const open = uiWith("follow-ups", {kind: "Track"});
  open.collapsed.hardening = false;
  const html = WS.renderPage(model, open);
  assert.match(html, /plain follow-up/);
  assert.match(html, /a hardening track/);
});

test("test_a_filtered_column_still_offers_every_value_of_the_table", () => {
  const model = WS.buildModel([issue(1, withLabels({status: "status:blocked"})), issue(2, FULL)], VOCAB, {});
  const html = WS.renderPage(model, uiWith("follow-ups", {status: "Blocked"}));
  assert.match(html, /<select data-filter="status"[^>]*><option value="">All<\/option><option value="Open">Open<\/option><option value="Blocked" selected>Blocked<\/option><\/select>/);
});

test("test_an_unchanged_value_does_not_redraw_or_refocus_and_an_unknown_control_is_ignored", async () => {
  const {doc, focused, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  fire("out", "input", filterEvent("text", "blocked"));
  const drawn = focused.length;
  fire("out", "change", filterEvent("text", "blocked"));
  assert.equal(focused.length, drawn, "the change event that follows input carries the same value: no second redraw, no focus pulled back");
  for (const key of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
    fire("out", "change", {target: {dataset: {filter: key}, value: "x", id: "flt-" + key}});
  }
  assert.equal(focused.length, drawn, "a control that is not a filter never redraws the page");
});

test("test_after_a_click_focus_returns_to_that_very_control", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(populatedFetch()));
  const selectors = [];
  elements.out.querySelector = (selector) => { selectors.push(selector); return {focus() {}}; };
  fire("out", "click", {target: {dataset: {tileColumn: "status", tileValue: "Partially implemented"}}});
  fire("out", "click", {target: {dataset: {toggle: "hardening"}}});
  assert.deepEqual(selectors, ['[data-tile-column="status"][data-tile-value="Partially implemented"]', '[data-toggle="hardening"]']);
});

test("test_a_product_change_after_a_failed_read_is_ignored", async () => {
  const {doc, elements, fire} = fakeDom();
  await load().boot(doc, fakeWindow(async () => response(null, {status: 500})));
  assert.doesNotThrow(() => fire("product", "change"));
  assert.equal(elements.out.innerHTML, "");
});

test("test_ampersands_and_entities_in_titles_are_escaped_exactly_once", () => {
  assert.equal(WS.esc(`&<>"'`), "&amp;&lt;&gt;&quot;&#39;");
  const html = WS.renderPage(WS.buildModel([issue(1, FULL, {title: "R&amp;D &lt;b&gt;"})], VOCAB, {}), ui());
  assert.match(html, /<bdi>R&amp;amp;D &amp;lt;b&amp;gt;<\/bdi>/);
});

// ---- safety ----
test("test_text_escaping_and_url_validation", () => {
  const hostile = issue(1, [...FULL.slice(1), "status:<img src=x onerror=alert(1)>"], {
    title: "<script>alert(1)</script>",
    html_url: "https://evil.example/phish",
  });
  const child = issue(2, FULL, {title: "ok", parent_issue_url: parentUrl(1)});
  const html = WS.renderPage(WS.buildModel([hostile, child], VOCAB, {}), ui());
  assert.doesNotMatch(html, /<script>|<img/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /evil\.example/);
  const good = WS.renderPage(WS.buildModel([issue(2, FULL)], VOCAB, {}), ui());
  assert.match(good, new RegExp(`href="https://github.com/${REPO}/issues/2"`));
  const quoted = WS.renderPage(WS.buildModel([issue(3, FULL)], VOCAB, {}), uiWith("follow-ups", {text: '"><img src=x onerror=1>'}));
  assert.doesNotMatch(quoted, /<img/);
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
