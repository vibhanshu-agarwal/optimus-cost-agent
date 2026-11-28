"""Render one composite repeatability result as deterministic JSON and Markdown."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict

from tools.plan1126_runtime_audit.composite_repeatability import CompositeResult, ParsedInput, RowResult

REPORT_SCHEMA = "optimus-repeatability-report-v1"


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _row_key(row: RowResult) -> tuple[str, int, str]:
    raw = row.observation.raw
    index = raw.get("repeat_index")
    return str(raw.get("cohort", "")), index if type(index) is int else 0, str(raw.get("observation_id", ""))


def report_data(result: CompositeResult, source: ParsedInput) -> dict:
    diagnostics = (*source.diagnostics, *result.diagnostics)
    validity = "INVALID" if diagnostics else result.input_validity
    # Retained evidence facts remain visible even when a document digest or another row
    # invalidates the report as a whole.
    return {
        "schema": REPORT_SCHEMA,
        "inputs": {
            "input_sha256": source.input_sha256,
            "manifest_sha256": source.manifest_sha256,
            "manifest": _json_value(source.manifest),
        },
        "input_validity": validity,
        "observed_outcome_counts": {name: result.counts[name] for name in ("pass", "fail", "timeout", "error")},
        "counts": dict(result.counts),
        "harness_instability_observed": result.harness_instability_observed,
        "product_variability_observed": result.product_variability_observed,
        "product_repeatability": result.product_repeatability if validity == "VALID" else "INDETERMINATE",
        "diagnostics": [
            asdict(issue) for issue in sorted(
                diagnostics, key=lambda item: (item.cohort or "", item.observation_id or "", item.code, item.field or ""),
            )
        ],
        "cohorts": [
            {
                "cohort": cohort.cohort,
                "input_validity": "INVALID" if source.diagnostics else cohort.input_validity,
                "counts": dict(cohort.counts),
                "harness_instability_observed": cohort.harness_instability_observed,
                "product_variability_observed": cohort.product_variability_observed,
                "product_repeatability": "INDETERMINATE" if source.diagnostics else cohort.product_repeatability,
            }
            for cohort in sorted(result.cohorts, key=lambda item: item.cohort)
        ],
        "rows": [
            {
                "observation": _json_value(row.observation.raw),
                "observed_outcome": row.observed_outcome,
                "subject": row.subject,
                "product_fingerprint": _json_value(row.fingerprint),
                "diagnostics": [asdict(issue) for issue in row.diagnostics],
            }
            for row in sorted(result.rows, key=_row_key)
        ],
        # Keep the ancillary ledger in exactly the order and shape declared in the manifest.
        "residual_dispositions": [_json_value(item.raw) for item in source.residual_dispositions],
    }


def render_json(result: CompositeResult, source: ParsedInput) -> bytes:
    report = report_data(result, source)
    return (json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _cell(value: object) -> str:
    if value is None:
        return "—"
    if type(value) is bool:
        return str(value).lower()
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)
    # Report fields are data. Escape HTML, table syntax and markdown links/code.
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = value.replace("\r", r"\r").replace("\n", r"\n")
    for character in ("\\", "|", "[", "]", chr(96), "*", "_"):
        value = value.replace(character, "\\" + character)
    return value


def _line(*values: object) -> str:
    return "| " + " | ".join(_cell(value) for value in values) + " |"


def _summary(name: str, record: dict) -> str:
    counts = record["counts"]
    return _line(
        name, record["input_validity"],
        *(counts[key] for key in ("observations", "pass", "fail", "timeout", "error", "harness_count", "unresolved_count")),
        record["harness_instability_observed"], record["product_variability_observed"], record["product_repeatability"],
    )


def render_markdown(result: CompositeResult, source: ParsedInput) -> bytes:
    report = report_data(result, source)
    lines = [
        "# Repeatability attribution", "",
        "This report describes supplied observations. Supported facts on an INVALID input do not establish aggregate acceptance.",
        "A historical PASS or a terminal residual disposition does not establish stable product behavior.", "",
        f"- Input SHA-256: {source.input_sha256}",
        f"- Manifest SHA-256: {source.manifest_sha256}",
        f"- Selection: {_cell(source.manifest.get('selection'))}", "",
        "## Cohort results", "",
        "| Scope | Input | Observations | PASS | FAIL | TIMEOUT | ERROR | HARNESS | UNRESOLVED | Harness instability | Product variability | Product repeatability |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        _summary("Overall", report),
        *(_summary(cohort["cohort"], cohort) for cohort in report["cohorts"]),
        "", "## Observations", "",
        "| Observation | Cohort | Repeat | Outcome | Subject | Original timeout subject | Evidence kind | Valid row |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        raw = row["observation"]
        outcome = raw.get("outcome")
        claim = raw.get("attribution")
        lines.append(_line(
            raw.get("observation_id"), raw.get("cohort"), raw.get("repeat_index"), row["observed_outcome"], row["subject"],
            outcome.get("timeout_subject") if isinstance(outcome, dict) else None,
            claim.get("evidence_kind") if isinstance(claim, dict) else None, not row["diagnostics"],
        ))
    lines += [
        "", "## Ancillary dispositions", "",
        "| ID | Preserved verdict | Decision | Owner | Decision source | Disposition |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["residual_dispositions"]:
        owner = item.get("owning_issue")
        lines.append(_line(
            item.get("id"), item.get("preserved_verdict"), item.get("state"),
            f"#{owner}" if type(owner) is int else owner, item.get("decision_source_ref"), item.get("decision_text"),
        ))
    if not report["residual_dispositions"]:
        lines.append("| — | — | — | — | — | No dispositions declared. |")
    if report["diagnostics"]:
        lines += [
            "", "## Validation diagnostics", "",
            "| Code | Cohort | Observation | Field |", "| --- | --- | --- | --- |",
        ]
        for issue in report["diagnostics"]:
            lines.append(_line(issue["code"], issue["cohort"], issue["observation_id"], issue["field"]))
    return ("\n".join(lines) + "\n").encode("utf-8", errors="backslashreplace")
