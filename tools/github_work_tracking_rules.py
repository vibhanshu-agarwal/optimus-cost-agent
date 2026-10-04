"""Plan 11.29: the reviewed rules that draft the migration inventory from the authority sources.

Every judgement that shapes ``reports/github-work-tracking-migration.json`` lives here as data or as a named rule, so the
inventory can be re-derived at any base and reviewed by re-running ``python -m tools.github_work_tracking draft <commit>``:

* how each ``##`` section is classified, and which reference tables were read and hold no work (``SECTION_RULES``);
* which unreadable constructs were read and accepted (``REVIEWED_ANOMALIES``);
* which units with free-text statuses were read and given a terminal disposition (``REVIEWED_UNITS``);
* parent, related-link, product, priority, alias and title rules (``_derive``), and per-record reviewed calls
  (``OVERRIDES``), each carried into the manifest with ``reviewed: true`` and its note.

Drafting is pure: sources in, manifest data out. It refuses a source section no rule classifies.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from tools import github_work_tracking as gwt

SOURCES = {
    "pool": "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md",
    "masterplan": "docs/superpowers/plans/hardening-runtime-quality-masterplan.md",
    "roadmap": "docs/superpowers/plans/2026-07-01-phase-1-roadmap.md",
}
PIN_NOTE = "# pragma: allowlist secret - git blob id of this source at the baseline commit, not a secret"
COMMIT_PIN_NOTE = "# pragma: allowlist secret - baseline git commit id, not a secret"
PILOT_ISSUES = {"plan:11.23": 222, "P11-FU-20": 223, "P11-FU-40": 224, "A2A-C1": 225}

# (classification, rationale, statusless rows read and found to hold no work)
SECTION_RULES: dict[tuple[str, str], tuple[str, str, bool]] = {
    ("pool", "Purpose"): ("not-work", "pool governance prose; replaced by the cutover authority statement", False),
    ("pool", "How to use this document"): ("not-work", "pool usage rules; replaced by the issue maintenance contract", False),
    ("pool", "Live implementation plan registry"): ("migrated", "each live plan becomes a kind:plan tracking issue", False),
    ("pool", "Frozen approval bytes and live-status authority"): (
        "migrated",
        "each frozen artifact's live-owner mapping is carried into the manifest",
        False,
    ),
    ("pool", "Feature slices"): ("mixed", "open/partial features become parent issues; closed/retired rows are history", False),
    ("pool", "Plan 12 Context Engine package A custody"): (
        "migrated",
        "section-level custody record of Plan 12.2 Package A (a duplicate of the plan issue)",
        False,
    ),
    ("pool", "Plan 11.26 reviewed disposition and remediation custody"): (
        "migrated",
        "ACCEPTED_OPEN candidates and UNRUN obligations are open work",
        False,
    ),
    ("pool", "MAIN-5 residuals under existing 11.x owners"): ("mixed", "open residual entries migrate; closed ones are history", False),
    ("pool", "Plan 11.x resource-lifetime and live-evidence residuals from FU33"): ("migrated", "P11-FU-38..41 are open", False),
    ("pool", "Plan 11.26 H4 verifier follow-ups from Seam 2 checkpoint A"): ("migrated", "section-level open follow-up record", False),
    ("pool", "Plan 11.26 Task 13 reviewed duplication disposition"): (
        "migrated",
        "ACCEPTED_OPEN duplication candidates are open work",
        False,
    ),
    ("pool", "Follow-up status index"): (
        "mixed",
        "index rows are projections of their entries; unresolved rows migrate with the entry",
        False,
    ),
    ("pool", "Evidence and handoff feature registry"): ("mixed", "open evidence/A2A features migrate; closed rows are history", False),
    ("pool", "A2A ledger audit obligations"): ("mixed", "open obligations migrate; M17 closed is history", False),
    ("pool", "Settled risks and historical entries"): (
        "history",
        "the accepted risk (its own record) and struck closed historical rows",
        False,
    ),
    ("pool", "Open items"): ("mixed", "unresolved entries migrate; closed entries are history", False),
    ("pool", "Accepted risks and warnings"): (
        "not-work",
        "operator-accepted limitation with its own risk record; no outstanding mitigation",
        False,
    ),
    ("pool", "P9.96 Task 9 Disclosed Follow-Ups (Closed; historical Plan 10 custody)"): (
        "history",
        "closed by Plan 10; the summary table has no status column and its seven ids are Closed in the disposition table",
        True,
    ),
    ("pool", "Closed Historical Follow-Ups (formerly tracked lightweight notes)"): ("history", "closed historical notes", False),
    ("pool", "Closed custody excluded from the open pool"): ("history", "P9.85-FU-7 and P9.9-FU-1 closed with Plan 9.96 Task 9", False),
    ("masterplan", "Authority chain"): ("not-work", "masterplan governance prose", False),
    ("masterplan", "Prerequisites"): (
        "not-work",
        "the masterplan's own prerequisites; each no/unknown row is owned by a migrating item, UNRUN obligation or the operator",
        True,
    ),
    ("masterplan", "Global constraints"): ("not-work", "governance prose", False),
    ("masterplan", "Source-of-truth map"): ("not-work", "authority map, superseded by the issue authority at cutover", True),
    ("masterplan", "Program inventory boundary"): ("not-work", "scope boundary statements, not work items", True),
    ("masterplan", "New-work custody register"): ("migrated", "each HARDENING-ITEM is open work under its track", False),
    ("masterplan", "Existing candidate sequence"): (
        "migrated",
        "projection of the pool candidates (sequence only; status lives in the pool)",
        False,
    ),
    ("masterplan", "Child-plan status board"): ("migrated", "each HARDENING-TRACK becomes a tracking issue", False),
    ("masterplan", "What is actually usable today"): ("not-work", "current-capability statements, not work items", True),
    ("masterplan", "Existing obligation sequence"): (
        "migrated",
        "sequence projection of the three P11.26-UNRUN obligations; rows join their records",
        False,
    ),
    ("masterplan", "Program waves"): ("not-work", "sequencing narrative over records owned elsewhere", True),
    ("masterplan", "Logging child-plan boundary"): ("not-work", "boundary prose", False),
    ("masterplan", "Child-plan pickup contract"): ("not-work", "process contract", False),
    ("masterplan", "Promotion mechanics"): ("not-work", "process prose", False),
    ("masterplan", "Verification for promotion"): ("not-work", "process prose", False),
    ("masterplan", "Program completion"): ("not-work", "completion criteria prose", False),
    ("masterplan", "Reviewer checklist"): ("not-work", "review checklist", False),
}

# Roadmap sections that point at live owners rather than holding history; everything else in the roadmap is history.
ROADMAP_POINTERS = {
    "Plan 11 (v1.0 Milestone; Unified Gateway Capabilities Broker and ACP Release)": (
        "milestone narrative and a snapshot table of terminal lane outcomes; live state is owned by the P11-FEAT-* features"
        " and their records",
        True,
    ),
    "Plan 12 (Post-v1.0 v1.x Phase; Context Window Optimization and Intelligent Selection)": (
        "pointer; open work is owned by the Plan 12 feature and plans 12.1/12.2",
        False,
    ),
    "Backlog: Re-pin FU-4A/FU-5 Live Evidence": ("pointer; owned by P11-FU-4", False),
    "Backlog: Windows Subprocess Handle-Duplication Flake, WinError 6/50": ("pointer; owned by P11-FU-5", False),
}
ROADMAP_GOVERNANCE = {"Roadmap Rules", "Operator Provenance", "Recommended Sequence"}

# Constructs the parser reports as unreadable, read by a reviewer and accepted: (source, text the line starts with).
REVIEWED_ANOMALIES = {
    ("pool", "Status for pickup: **Needs deeper investigation before scoping"): (
        "pickup-readiness note inside P11-FU-8; the entry's lifecycle status is its **Status:** line (Open)"
    ),
}

# Units whose status is not a known token, read and given an explicit record: (source, kind, title) -> spec.
REVIEWED_UNITS = {
    ("masterplan", "entry", "Runtime candidates"): (
        "structure:masterplan:runtime-candidates",
        "not-work",
        "table heading; its rows are claimed by the candidate records",
    ),
    ("masterplan", "entry", "Duplication candidates"): (
        "structure:masterplan:duplication-candidates",
        "not-work",
        "table heading; its rows are claimed by the T13 candidate records",
    ),
    ("masterplan", "entry", "Parent update checklist"): (
        "structure:masterplan:parent-update-checklist",
        "not-work",
        "process checklist heading in the pickup contract, not a work record",
    ),
    ("roadmap", "section-record", "Plan 9.5: Agent Orchestration and End-to-End Coding Workflow"): (
        "history:roadmap:plan-9-5",
        "history",
        "status prose: the build plan completes with its completion plan; Plan 9.5 is closed history",
    ),
    ("roadmap", "entry", "Plan 9.6 closure — complete"): (
        "history:roadmap:plan-9-6-closure",
        "history",
        "closure heading; Plan 9.6 is Complete (2026-07-11)",
    ),
    ("roadmap", "section-record", "Plan 10 (Retired): Consolidated Deferred Follow-Ups Pool"): (
        "history:roadmap:plan-10",
        "history",
        "the former Plan 10.x lanes are closed; open work moved to the pool",
    ),
    ("roadmap", "entry", "Execution snapshot"): (
        "structure:roadmap:plan-11-execution-snapshot",
        "not-work",
        "snapshot of terminal Plan 11 lane outcomes; it defers live state to the pool",
    ),
    ("roadmap", "section-record", "Plan 12 (Post-v1.0 v1.x Phase; Context Window Optimization and Intelligent Selection)"): (
        "structure:roadmap:plan-12-pointer",
        "not-work",
        "pointer prose; Plan 12 work is owned by the Plan 12 feature and its plans",
    ),
}

RISK_RECORD = {
    "id": "risk:plan-11-7-redis-durability",
    "rationale": (
        "operator-accepted 2026-07-30: optimus-redis gives no container-lifecycle durability; revisit only if session-state loss occurs or"
        " a future plan changes Redis persistence; no mitigation is outstanding"
    ),
}

EXTERNAL_ISSUES = (
    {
        "id": "issue:33",
        "kind": "external-issue",
        "status": "Open",
        "disposition": "migrate",
        "units": [],
        "title": "P0: Zed ACP session/prompt hangs — no visible response after prompt (HITL deadlock)",
        "related": ["P11-FEAT-ZED-RESUME"],
        "target_issue": 33,
        "status_disposition": "no source unit states it: the existing GitHub issue's state (open since 2026-07-09), re-read before any write",
        "priority": "HIGH",
        "priority_disposition": (
            "the issue body states Priority P0, kept verbatim in its body and evidence; HIGH is the disclosed label mapping (the label"
            " vocabulary has no P0), not an operator priority assertion"
        ),
        "reviewed": True,
        "review_note": (
            "existing issue, kept open and linked as-is. Task 2 reconciles it read-only against existing evidence"
            " (reports/plan-9-75-zed-hitl-runtime-evidence.md and the P11-FEAT-ZED-RESUME records) and records a reviewed applicability"
            " disposition; Plan 11.29 runs no Zed, acpx or Gateway drive. A new reproduction, if one is needed, belongs to"
            " P11-FEAT-ZED-RESUME under that lane's own plan and authority, with #33 open and linked meanwhile. This inventory authorizes"
            " no closure, relabel or duplicate issue; later plan coverage never proves closure"
        ),
        "rationale": "pre-existing GitHub issue (2026-07-09); related to, not owned by, P11-FEAT-ZED-RESUME",
    },
)

COMPAT_ANCHORS = {
    "p11-fu-11-plan-117-retry-preflight-and-live-session-proof": "P11-FU-11",
    "durable-effect-aware-mcp-indeterminate-call-custody": "P11-FU-22",
    "live-implementation-plan-registry": "section:live-implementation-plan-registry",
    "plan-1126-h4-verifier-follow-ups-from-seam-2-checkpoint-a": "H4-VERIFIER-FOLLOW-UPS",
    "p11-fu-9-client-supplied-acp-mcpservers-disposition": "P11-FU-9",
    "p11-fu-5-windows-subprocess-handle-duplication-flake-winerror-650": "P11-FU-5",
    "p11-fu-4-re-pin-fu-4a-fu-5-live-evidence": "P11-FU-4",
}

OVERRIDES: dict[str, dict] = {
    "plan:12.1": {
        "parent": "feature:plan-12",
        "review_note": "Plan 12 slice; its registry backlog owner P12-FU-1 is its own child item, so the parent is the Plan 12 feature",
    },
    "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER": {
        "review_note": (
            "Reviewed disposition: not shipped/not supported/not trusted after the NOT SOUND audit; closure plan archived. Open work"
            " continues under the LEDGER-* slices and A2A obligations; this umbrella stays history and remains the live owner of the"
            " frozen v1 design"
        ),
    },
    "HARDENING-ITEM-LOCKFILE-CI-ENFORCEMENT": {
        "review_note": (
            "the CI-GUARDRAILS track reports locked dependency sync merged (PR #194); the source still lists this item, so it migrates"
            " Open, but its body must quote the track's next gate and it is a closure-review candidate at Checkpoint 3"
        ),
    },
}

_UNOWNED_OWNER = re.compile(r"(?i)^\W*(coordinat|future)")
_PLAN_NUMBER = re.compile(r"Plan (\d+(?:\.\d+)*)")
_CONTRACT_TERM = re.compile(r"\(contract term: ([A-Za-z0-9.-]+)\)")


def classify(source: str, title: str) -> tuple[str, str, bool]:
    if source == "roadmap":
        if title in ROADMAP_GOVERNANCE or title.startswith("Cross-Cutting"):
            return "not-work", "roadmap governance/narrative", False
        if title in ROADMAP_POINTERS:
            rationale, statusless = ROADMAP_POINTERS[title]
            return "not-work", rationale, statusless
        return "history", "plan history; live state is owned by the pool (and by issues after cutover)", False
    if (source, title) not in SECTION_RULES:
        raise ValueError(f"no reviewed classification for section {source}:{title!r}; add one to SECTION_RULES")
    return SECTION_RULES[(source, title)]


def _record(**fields) -> dict:
    record = {
        name: ([] if name in ("units", "aliases", "anchors", "related") else None) for name in gwt.InventoryRecord.__dataclass_fields__
    }
    record.update(
        title="",
        mitigation_outstanding=False,
        product="optimus",
        reviewed=False,
        rationale="",
        status=None,
        kind="item",
        disposition="migrate",
    )
    record.update(fields)
    return record


def _plan_id(text: str) -> str:
    number = _PLAN_NUMBER.match(text)
    if number:
        return f"plan:{number.group(1)}"
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return "plan:" + (slug[:40].rsplit("-", 1)[0] if len(slug) > 40 else slug)


def _kind(identity: str) -> str:
    if re.match(r"P\d+(\.\d+)*-FU-", identity):
        return "follow-up"
    if "-FEAT-" in identity or identity == "Plan 12":
        return "feature"
    if re.match(r"(P11\.26-CAND|T13-CAND)-", identity):
        return "candidate"
    if re.match(r"P11\.26-UNRUN", identity) or identity.startswith("A2A-"):
        return "obligation"
    return "item"


def draft_inventory(commit: str, sources: Mapping[str, bytes]) -> dict:
    texts = {name: sources[name].decode("utf-8") for name in SOURCES}
    scans = {name: gwt.scan_source(name, texts[name]) for name in SOURCES}
    lines = {name: texts[name].splitlines() for name in SOURCES}

    sections = []
    retiring = {}
    for name in SOURCES:
        for title in scans[name].sections:
            classification, rationale, statusless = classify(name, title)
            sections.append(
                {
                    "source": name,
                    "title": title,
                    "classification": classification,
                    "rationale": rationale,
                    "statusless_reviewed": statusless,
                }
            )
            retiring[(name, title)] = (classification in gwt.RETIRING_DISPOSITIONS, statusless)

    reviewed_anomalies = {}
    for name in SOURCES:
        for anomaly in scans[name].anomalies:
            key = anomaly.split(" ", 1)[0]
            line_text = lines[name][int(key.split(":")[1]) - 1].strip()
            note = next((n for (src, prefix), n in REVIEWED_ANOMALIES.items() if src == name and line_text.startswith(prefix)), None)
            if note:
                reviewed_anomalies[key] = note

    records: list[dict] = []
    claimed: set[str] = set()

    def claim(units: list) -> list[str]:
        keys = [unit.key for unit in units]
        claimed.update(keys)
        return keys

    for unit in scans["pool"].units:
        if unit.section == "Live implementation plan registry":
            records.append(
                _record(
                    id=_plan_id(unit.title),
                    kind="plan",
                    status=gwt._clean(unit.stated_status),
                    units=claim([unit]),
                    title=unit.title,
                    aliases=[unit.identity] if unit.identity and unit.identity.startswith("Plan ") else [],
                    rationale="live plan registry row",
                )
            )
    for unit in scans["masterplan"].units:
        if unit.section == "Child-plan status board":
            records.append(
                _record(
                    id=unit.identity,
                    kind="track",
                    status=gwt._clean(unit.stated_status),
                    units=claim([unit]),
                    title=unit.identity,
                    aliases=[unit.identity],
                    parent="HARDENING-FEAT-RUNTIME-QUALITY",
                    rationale="hardening child-plan track",
                )
            )

    for name in SOURCES:
        for unit in scans[name].units:
            spec = REVIEWED_UNITS.get((name, unit.kind, unit.title))
            if spec:
                record_id, disposition, note = spec
                records.append(
                    _record(
                        id=record_id,
                        kind="structure",
                        status=gwt._clean(unit.stated_status) or None,
                        disposition=disposition,
                        units=claim([unit]),
                        title=unit.title,
                        terminal_disposition=note,
                        reviewed=True,
                        review_note=note,
                        rationale="unit without a known status token, read and given a terminal disposition",
                    )
                )

    risk_units = [
        unit
        for unit in scans["pool"].units
        if unit.key not in claimed
        and gwt.normalized_status(unit.stated_status) == gwt.REVIEWED_DISPOSITION
        and "accepted risk" in unit.title.lower()
    ]
    if risk_units:
        records.append(
            _record(
                id=RISK_RECORD["id"],
                kind="risk",
                status=gwt._clean(risk_units[0].stated_status),
                disposition="not-work",
                units=claim(risk_units),
                title=next((u.title for u in risk_units if u.kind == "entry"), risk_units[0].title),
                reviewed=True,
                review_note=RISK_RECORD["rationale"],
                rationale=RISK_RECORD["rationale"],
            )
        )

    groups: dict[str, list] = defaultdict(list)
    for name in ("pool", "masterplan"):
        for unit in scans[name].units:
            if unit.key in claimed or unit.kind in ("frozen-mapping", "section-record") or unit.section in gwt.PLAN_UNIT_SECTIONS:
                continue
            retires, _statusless = retiring[(name, unit.section)]
            if retires and unit.status_class in ("resolved", "statusless"):
                continue
            ident = unit.identity or f"{name}:{unit.line}"
            if unit.section == "A2A ledger audit obligations":
                ident = "A2A-" + ident
            groups[ident].append(unit)
    for ident, units in groups.items():
        entry = next((u for u in units if u.kind == "entry"), None)
        status_unit = entry if entry and entry.stated_status else next((u for u in units if u.stated_status), None)
        status = gwt._clean(status_unit.stated_status) if status_unit else None
        unresolved = any(u.unresolved for u in units)
        record_id = "feature:plan-12" if ident == "Plan 12" else ident
        records.append(
            _record(
                id=record_id,
                kind=_kind(ident),
                status=status,
                disposition="migrate" if unresolved or status is None else "history",
                units=claim(units),
                title=(entry.title if entry else units[0].title),
                aliases=[ident],
                rationale="grouped source units with one identity",
            )
        )

    for unit in scans["pool"].units:
        if unit.kind != "section-record" or unit.key in claimed:
            continue
        if unit.section.startswith("Plan 12 Context Engine package A"):
            records.append(
                _record(
                    id="custody:plan-12.2-package-a",
                    kind="item",
                    status=gwt._clean(unit.stated_status),
                    disposition="duplicate",
                    units=claim([unit]),
                    title=unit.section,
                    duplicate_of="plan:12.2",
                    duplicate_rationale="Package A custody prose for the same Plan 12.2 plan; the plan issue carries it",
                    rationale="section-level custody record",
                )
            )
        elif unit.section.startswith("Plan 11.26 H4 verifier"):
            records.append(
                _record(
                    id="H4-VERIFIER-FOLLOW-UPS",
                    kind="follow-up",
                    status=gwt._clean(unit.stated_status),
                    units=claim([unit]),
                    title=unit.section,
                    parent="P11-FEAT-ACP-RUNTIME-HARDENING",
                    anchors=[gwt.heading_anchor(unit.section)],
                    rationale="section-level open follow-up with no ID",
                )
            )

    frozen: dict[str, list] = defaultdict(list)
    for unit in scans["pool"].units:
        if unit.kind == "frozen-mapping":
            frozen[unit.identity].append(unit)
    for path, units in frozen.items():
        owners = [gwt._clean(u.stated_status) for u in units if u.stated_status]
        records.append(
            _record(
                id=f"frozen:{path.rsplit('/', 1)[-1]}",
                kind="frozen-mapping",
                disposition="not-work",
                units=claim(units),
                title=path,
                product="evidence-a2a" if "evidence-handoff" in path else "optimus",
                related=list(dict.fromkeys(identity for owner in owners for identity in gwt.owner_identities(owner))),
                rationale="frozen artifact; " + ("; ".join(o for o in owners if o) or "historical provenance (no live owner)"),
            )
        )

    for issue in EXTERNAL_ISSUES:
        records.append(_record(**issue))

    _derive(records, {name: scans[name] for name in SOURCES})
    return {
        "schema": gwt.SCHEMA,
        "baseline": {
            "commit": commit,
            "commit_pin": COMMIT_PIN_NOTE,
            "sources": {name: {"path": SOURCES[name], "blob": gwt.git_blob_id(sources[name]), "pin": PIN_NOTE} for name in SOURCES},
        },
        "sections": sections,
        "reviewed_anomalies": reviewed_anomalies,
        "compat_anchors": COMPAT_ANCHORS,
        "records": records,
    }


def _derive(records: list[dict], scans: Mapping[str, gwt.SourceScan]) -> None:
    """Titles, anchors, aliases, severity, priority, product, parents and related links, then reviewed overrides."""
    units = {unit.key: unit for scan in scans.values() for unit in scan.units}
    by_id = {record["id"]: record for record in records}
    ids = set(by_id)
    board = {}
    for unit in scans["masterplan"].units:
        if unit.section == "Child-plan status board":
            for item in re.findall(r"HARDENING-ITEM-[A-Z0-9-]*[A-Z0-9]", unit.cells.get("scope owned by that plan", "")):
                board[item] = unit.identity

    def mentioned(text: str, self_id: str) -> list[str]:
        found = []
        for ident in re.findall(r"[A-Z0-9][A-Z0-9.]*-[A-Z0-9-]*[A-Z0-9]", gwt._clean(text)):
            if ident in ids and ident != self_id and ident not in found:
                found.append(ident)
        for number in _PLAN_NUMBER.findall(text or ""):
            target = f"plan:{number}" if f"plan:{number}" in ids else ("feature:plan-12" if number == "12" else None)
            if target and target != self_id and target not in found:
                found.append(target)
        return found

    for record in records:
        claimed = [units[key] for key in record["units"] if key in units]
        rows = [unit for unit in claimed if unit.kind == "row"]
        rid = record["id"]
        for unit in claimed:
            if unit.kind == "entry":
                record["anchors"].append(gwt.heading_anchor(unit.title))
            for term in _CONTRACT_TERM.findall(unit.title):
                if term not in record["aliases"]:
                    record["aliases"].append(term)
        record["severity"] = record["severity"] or next((u.severity for u in claimed if u.severity), None)
        if rid.startswith(("EVIDENCE-HANDOFF-", "A2A-")) or rid == "plan:evidence-collector":
            record["product"] = "evidence-a2a"
        if record["disposition"] == "migrate":
            record["priority"] = record["priority"] or next((u.priority.upper() for u in claimed if u.priority), None) or "MEDIUM"
            if rid.startswith("A2A-"):
                record["title"] = f"A2A obligation {rid[4:]}"
        if record["parent"] or record["disposition"] not in ("migrate", "duplicate"):
            continue
        if record["kind"] == "follow-up":
            for row in rows:
                status = row.cells.get("status", "")
                owner = row.cells.get("owning slice / designated plan") or row.cells.get("owner") or ""
                if "Promoted" in status:
                    record["parent"] = next(iter(mentioned(status, rid)), None)
                    break
                if owner:
                    if _UNOWNED_OWNER.match(gwt._clean(owner)):
                        record["related"] = mentioned(owner, rid)
                        record["rationale"] += "; the source owner cell coordinates with or defers to a future lane, so no parent"
                    else:
                        record["parent"] = next(iter(mentioned(owner, rid)), None)
                    break
        elif rid.startswith("A2A-"):
            record["parent"] = next((t for row in rows for t in mentioned(row.cells.get("owning slice", ""), rid)), None)
        elif rid.startswith("P11.26-CAND-"):
            record["parent"] = "P11-FEAT-ACP-RUNTIME-HARDENING"
        elif rid.startswith("P11.26-UNRUN-"):
            owner = next((row.cells.get("owner-to-be", "") for row in rows if row.cells.get("owner-to-be")), "")
            record["parent"] = "P11-FEAT-ZED-RESUME" if "ZED-RESUME" in owner else "P11-FEAT-ACP-RUNTIME-HARDENING"
            if "ZED-RESUME" not in owner:
                record["rationale"] += f"; source owner-to-be is {gwt._clean(owner)!r}, so the issue sits under the Plan 11.26 feature"
        elif rid.startswith("T13-CAND-"):
            record["parent"] = "HARDENING-TRACK-DUPLICATION"
        elif rid.startswith("HARDENING-ITEM-"):
            record["parent"] = board.get(rid)
            record["rationale"] = "new-work custody register item under its hardening track"
            if not record["status"]:
                record["status"] = "Open"
                record["status_disposition"] = (
                    "synthesized: the masterplan omits item status by design (its track reports it); open until its track delivers"
                )
        elif record["kind"] == "plan":
            owner = next((row.cells.get("backlog owner", "") for row in rows), "")
            parent = next(iter(mentioned(owner, rid)), None)
            record["parent"] = parent if parent and by_id[parent]["kind"] == "feature" else None

    for record in records:
        if record["id"] in PILOT_ISSUES:
            record["target_issue"] = PILOT_ISSUES[record["id"]]
        override = OVERRIDES.get(record["id"])
        if override:
            record.update({name: value for name, value in override.items()})
            record["reviewed"] = True
    for record in records:
        parent = by_id.get(record["parent"]) if record["parent"] else None
        if record["disposition"] == "migrate" and parent and parent["disposition"] != "migrate":
            record["rationale"] += f"; source owner {parent['id']} is {parent['disposition']}, so this issue has no parent"
            record["parent"] = None
    index = gwt.identity_index((record["id"], record["aliases"]) for record in records)
    for record in records:
        if record["kind"] == "frozen-mapping":  # every owner with a record is linked; a closed owner with none stays a name
            record["related"] = list(dict.fromkeys(index[identity] for identity in record["related"] if identity in index))
