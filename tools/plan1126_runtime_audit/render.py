"""Deterministic, content-free Markdown rendering from canonical audit JSON."""

from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any, Mapping

from .model import AuditArtifact, Classification

_STATUS_FIELDS = (
    "static_audit_status",
    "runtime_characterization_status",
    "live_redis_status",
    "acpx_status",
    "additional_client_status",
    "zed_status",
    "live_interoperability_status",
)
_SECRET_SHAPE = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+)"
)


def _safe_markdown(value: object) -> str:
    text = " ".join(str(value).splitlines())
    text = _SECRET_SHAPE.sub("[REDACTED]", text)
    return html.escape(text, quote=True).replace("|", "&#124;").replace("`", "&#96;")


def render_markdown(payload: Mapping[str, Any]) -> str:
    """Regenerate metadata-only Markdown; JSON remains the sole authority."""

    artifact = AuditArtifact.from_dict(payload)
    canonical = artifact.to_dict()
    lines = [
        "# Plan 11.26 ACP runtime audit",
        "",
        "This report is deterministically regenerated from the canonical JSON artifact.",
        "",
        "## Baselines",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Merged commit | `{canonical['merged_commit']}` |",
        f"| Overlay commit | `{canonical['overlay_commit']}` |",
        f"| Binding commit | `{canonical['binding_commit'] or 'not nominated'}` |",
        f"| Reconciliation | `{canonical['baseline_reconciliation_status']}` |",
        "",
        "## Status",
        "",
        "| Surface | Status |",
        "|---|---|",
    ]
    lines.extend(f"| {field.replace('_', ' ').title()} | `{canonical[field]}` |" for field in _STATUS_FIELDS)
    lines.extend([
        f"| Gate | `{canonical['gate_status']}` |",
        "",
        "## Finding counts",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ])
    lines.extend(
        f"| `{classification.value}` | {canonical['finding_counts_by_classification'][classification.value]} |"
        for classification in Classification
    )
    lines.extend([
        "",
        "## Discovered multipliers",
        "",
        "| Multiplier | Count |",
        "|---|---:|",
    ])
    lines.extend(
        f"| {name.replace('_', ' ').title()} | {value} |"
        for name, value in sorted(canonical["discovered_multipliers"].items())
    )
    cost = canonical["computed_run_cost"]
    lines.extend([
        "",
        "## Computed run cost",
        "",
        "| Family | Count |",
        "|---|---:|",
        f"| Cancellation controls | {cost['cancellation_control_schedules']:,} |",
        f"| Cancellation races (levels 2/4/8) | {cost['cancellation_schedules']:,} |",
        f"| Queue admissions | {cost['queue_admissions']:,} |",
        f"| Sink failure runs | {cost['sink_failure_runs']:,} |",
        f"| Idempotent close invocations | {cost['idempotent_close_invocations']:,} |",
        "",
        "Measured scenario durations:",
        "",
        "| Scenario | p50 ms | p95 ms |",
        "|---|---:|---:|",
    ])
    duration_names = sorted(set(cost["scenario_p50_ms"]) | set(cost["scenario_p95_ms"]))
    if duration_names:
        lines.extend(
            f"| `{_safe_markdown(name)}` | {cost['scenario_p50_ms'][name]:.3f} | "
            f"{cost['scenario_p95_ms'][name]:.3f} |"
            for name in duration_names
        )
    else:
        lines.append("| not yet measured | 0.000 | 0.000 |")
    lines.extend(["", "## Evidence records"])
    for record in canonical["evidence_records"]:
        if record["hypothesis_id"] == "H6":
            lines.extend([
                "", f"### `H6` — {_safe_markdown(record['subject'])}", "",
                "| Field | Value |", "|---|---|",
                f"| Record | `{record['record_id']}` |",
                f"| Baseline scope | `{record['baseline_scope']}` |",
                f"| Schema oracle | `{record['schema_oracle_status']}` |",
                f"| AST oracle | `{record['ast_oracle_status']}` |",
                f"| Legacy allowlist entries | {record['legacy_allowlist_count']} |",
                f"| Reviewer status | `{record['reviewer_status']}` |", "",
                f"Ruling: {_safe_markdown(record['ruling'])}",
            ])
            continue
        if record["hypothesis_id"] == "H7":
            semantic = record["observations"]
            inventory = record["inventory"]
            category_counts = Counter(item["category"] for item in inventory["sites"])
            classification_counts = Counter(item["classification"] for item in inventory["sites"])
            lines.extend([
                "", f"### `H7` — {_safe_markdown(record['subject'])}", "",
                "| Field | Value |", "|---|---|",
                f"| Record | `{record['record_id']}` |",
                f"| Baseline scope | `{record['baseline_scope']}` |",
                f"| Derived semantic sites | {inventory['site_count']} |",
                "| Seeded expected site count | `null` |",
                f"| Sanitizer observations | {semantic['total_observation_count']:,} |",
                f"| Reviewer status | `{record['reviewer_status']}` |", "",
                "Site categories: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(category_counts.items())
                ), "",
                "Site classifications: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(classification_counts.items())
                ), "",
                f"Observation closure: {semantic['complete_observation_count']:,}/"
                f"{semantic['total_observation_count']:,} structurally closed records "
                f"(`{semantic['observation_closure_status']}`). This is record-shape closure, not "
                "settled-vocabulary completeness.", "",
                f"Settled-vocabulary coverage: `{semantic['vocabulary_coverage_status']}`.", "",
                "Semantic category coverage and all other settled observation vocabularies:", "",
                "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |",
                "|---|---|---|---|---|---|---|---|",
            ])
            for assessment in semantic["coverage_assessments"]:
                observed = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["observed_values"])
                missing = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["missing_values"]) or "none"
                lines.append(
                    f"| `{assessment['field_name']}` | `{assessment['type_name']}` | "
                    f"`{assessment['status']}` | {observed} | {missing} | "
                    f"{_safe_markdown(assessment['owner'] or 'not applicable')} | "
                    f"{_safe_markdown(assessment['next_gate'] or 'not applicable')} | "
                    f"{_safe_markdown(assessment['reason'] or 'All declared values were observed.')} |"
                )
            lines.extend(["", f"Observation digest: `{semantic['digest']}`", "", f"Ruling: {_safe_markdown(record['ruling'])}"])
            continue
        if record["hypothesis_id"] == "H8":
            inventory = record["inventory"]
            s2 = record["s2_ruling"]
            lines.extend([
                "", f"### `H8` — {_safe_markdown(record['subject'])}", "",
                "| Field | Value |", "|---|---|",
                f"| Record | `{record['record_id']}` |",
                f"| Baseline scope | `{record['baseline_scope']}` |",
                f"| Derived telemetry sites | {inventory['site_count']} |",
                "| Seeded expected site count | `null` |",
                f"| Reviewed event kinds | {inventory['event_kind_count']} |",
                f"| Derived terminal sinks (`N_sinks`) | {inventory['sink_count']} |",
                f"| Sink identities | {', '.join(f'`{_safe_markdown(value)}`' for value in inventory['sink_ids'])} |",
                f"| Required trace correlation fields | {', '.join(f'`{_safe_markdown(value)}`' for value in inventory['required_correlation_fields'])} |",
                f"| Reviewer status | `{record['reviewer_status']}` |", "",
                "S2 scalar/plural Gateway-ID ruling:", "",
                "| Scalar | Plural | Relationship | Classification |",
                "|---|---|---|---|",
                f"| `{s2['scalar_field']}` | `{s2['plural_field']}` | `{s2['relationship']}` | `{s2['classification']}` |",
                "", _safe_markdown(s2["ruling"]),
            ])
            for heading, summary_key in (
                ("Event-schema matrix", "schema_observations"),
                ("Redaction matrix", "redaction_observations"),
                ("Correlation chain", "correlation_observations"),
                ("Sink-failure matrix", "sink_failure_observations"),
            ):
                summary = record[summary_key]
                lines.extend([
                    "", f"#### {heading}", "",
                    f"Observation closure: {summary['complete_observation_count']:,}/"
                    f"{summary['total_observation_count']:,} structurally closed records "
                    f"(`{summary['observation_closure_status']}`). This is record-shape closure, not "
                    "settled-vocabulary completeness.", "",
                    f"Settled-vocabulary coverage: `{summary['vocabulary_coverage_status']}`.", "",
                    "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |",
                    "|---|---|---|---|---|---|---|---|",
                ])
                for assessment in summary["coverage_assessments"]:
                    observed = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["observed_values"])
                    missing = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["missing_values"]) or "none"
                    lines.append(
                        f"| `{assessment['field_name']}` | `{assessment['type_name']}` | "
                        f"`{assessment['status']}` | {observed} | {missing} | "
                        f"{_safe_markdown(assessment['owner'] or 'not applicable')} | "
                        f"{_safe_markdown(assessment['next_gate'] or 'not applicable')} | "
                        f"{_safe_markdown(assessment['reason'] or 'All declared values were observed.')} |"
                    )
                lines.extend(["", f"Observation digest: `{summary['digest']}`"])
            lines.extend(["", f"Ruling: {_safe_markdown(record['ruling'])}"])
            continue
        if record["hypothesis_id"] == "H9":
            inventory = record["inventory"]
            admissions = record["admission_observations"]
            health = record["health_observations"]
            admission_outcomes = Counter(item["observed_outcome"] for item in admissions["rows"])
            inference_counts = Counter(item["inference"] for item in admissions["rows"])
            health_outcomes = Counter(item["outcome"] for item in health["rows"])
            lines.extend([
                "", f"### `H9` — {_safe_markdown(record['subject'])}", "",
                "| Field | Value |", "|---|---|",
                f"| Record | `{record['record_id']}` |",
                f"| Baseline scope | `{record['baseline_scope']}` |",
                f"| Derived queues (`N_queues`) | {inventory['queue_count']} |",
                "| Seeded expected queue count | `null` |",
                f"| Queue/health source sites | {len(inventory['sites'])} |",
                f"| Stopped-consumer admissions | {admissions['total_observation_count']:,} |",
                f"| Health scenarios | {health['total_observation_count']:,} |",
                f"| Reviewer status | `{record['reviewer_status']}` |", "",
                "Derived queue policy inventory:", "",
                "| Queue | Constructor | Declared bound | Constructor policy | Admission API | Stop behavior | Overflow result |",
                "|---|---|---:|---|---|---|---|",
            ])
            for queue in inventory["queues"]:
                lines.append(
                    f"| `{_safe_markdown(queue['queue_id'])}` | "
                    f"`{_safe_markdown(queue['path'])}:{queue['line']}` | "
                    f"{queue['declared_bound']} | `{queue['constructor_policy']}` | "
                    f"`{queue['admission_api']}` | `{queue['stop_behavior']}` | "
                    f"`{queue['overflow_result']}` |"
                )
            lines.extend([
                "", "The 10,000-admission probe is behavioural evidence only. `DECLARED_UNBOUNDED` "
                "is assigned only where the independently scanned constructor declares the standard-library "
                "unbounded value; otherwise the strongest accepted-only conclusion is "
                "`NO_OBSERVED_BOUND_BELOW_10000`.", "",
                "Admission outcomes: " + ", ".join(
                    f"`{name}`={count:,}" for name, count in sorted(admission_outcomes.items())
                ), "",
                "Queue inferences: " + ", ".join(
                    f"`{name}`={count:,}" for name, count in sorted(inference_counts.items())
                ), "",
                "Health outcomes: " + ", ".join(
                    f"`{name}`={count:,}" for name, count in sorted(health_outcomes.items())
                ),
            ])
            for heading, summary in (
                ("Queue-admission coverage", admissions),
                ("Connection-health coverage", health),
            ):
                lines.extend([
                    "", f"#### {heading}", "",
                    f"Observation closure: {summary['complete_observation_count']:,}/"
                    f"{summary['total_observation_count']:,} structurally closed records "
                    f"(`{summary['observation_closure_status']}`). This is record-shape closure, not "
                    "settled-vocabulary completeness.", "",
                    f"Settled-vocabulary coverage: `{summary['vocabulary_coverage_status']}`.", "",
                    "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |",
                    "|---|---|---|---|---|---|---|---|",
                ])
                for assessment in summary["coverage_assessments"]:
                    observed = ", ".join(
                        f"`{_safe_markdown(value)}`" for value in assessment["observed_values"]
                    )
                    missing = ", ".join(
                        f"`{_safe_markdown(value)}`" for value in assessment["missing_values"]
                    ) or "none"
                    lines.append(
                        f"| `{assessment['field_name']}` | `{assessment['type_name']}` | "
                        f"`{assessment['status']}` | {observed} | {missing} | "
                        f"{_safe_markdown(assessment['owner'] or 'not applicable')} | "
                        f"{_safe_markdown(assessment['next_gate'] or 'not applicable')} | "
                        f"{_safe_markdown(assessment['reason'] or 'All declared values were observed.')} |"
                    )
                lines.extend(["", f"Observation digest: `{summary['digest']}`"])
            lines.extend(["", f"Ruling: {_safe_markdown(record['ruling'])}"])
            continue
        observations = record["schedule_observations"]
        observation_rows = observations["observations"]
        contradiction = record["contradiction_search"]
        if record["hypothesis_id"] == "H3":
            inventory_counts = Counter(site["kind"] for site in record["discovered_sites"])
            ownership_counts = Counter(item["classification"] for item in record["task_units"])
            phase_counts = Counter(item["phase"] for item in observation_rows)
            request_states = Counter(item["request_task_state"] for item in observation_rows)
            child_states = Counter(item["child_work_state"] for item in observation_rows)
            lines.extend([
                "",
                f"### `H3` — {_safe_markdown(record['subject'])}",
                "",
                "| Field | Value |",
                "|---|---|",
                f"| Record | `{record['record_id']}` |",
                f"| Baseline scope | `{record['baseline_scope']}` |",
                f"| Seed anchor (merged, not binding) | `{record['baseline_anchor_commit']}` |",
                f"| Overlay identity | `{record['overlay_commit']}` |",
                f"| Binding commit | `{record['binding_commit'] or 'not nominated'}` |",
                f"| Reviewer status | `{record['reviewer_status']}` |",
                f"| Derived cancellation points | {record['cancellation_point_count']} |",
                f"| Created task/thread/future units | {len(record['task_units'])} |",
                "",
                "Inventory counts: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(inventory_counts.items())
                ),
                "",
                "Ownership-role counts: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(record["ownership_role_counts"].items())
                ),
                "",
                "Ownership classifications: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(ownership_counts.items())
                ),
                "",
                "TurnControl ruling: " + ", ".join(
                    f"`{name}`=`{value}`" for name, value in sorted(record["turn_control_ruling"].items())
                ),
                "",
                f"Contradiction search: {contradiction['contradictory_site_count']} contradictory site(s) "
                f"across {contradiction['searched_reference_count']} mechanically discovered references. "
                f"{_safe_markdown(contradiction['conclusion'])}",
                "",
                f"Schedule observations replayed {len(observations['literal_seeds'])} frozen literal seeds and "
                f"{observations['derived_seed_count_per_family']} commit-derived seeds in each point/level family.",
                "",
                f"Derived terminal cost: {observations['derived_control_schedule_count']:,} control schedules plus "
                f"{observations['derived_race_schedule_count']:,} race schedules.",
                "",
                f"Observation closure: {observations['complete_observation_count']:,}/"
                f"{observations['total_observation_count']:,} structurally closed records "
                f"(`{observations['observation_closure_status']}`). This is record-shape closure, not "
                "settled-vocabulary completeness.",
                "",
                f"Settled-vocabulary coverage: `{observations['vocabulary_coverage_status']}`.",
                "",
                "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |",
                "|---|---|---|---|---|---|---|---|",
            ])
            for assessment in observations["coverage_assessments"]:
                observed = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["observed_values"])
                missing = (
                    ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["missing_values"])
                    or "none"
                )
                lines.append(
                    f"| `{assessment['field_name']}` | `{assessment['type_name']}` | "
                    f"`{assessment['status']}` | {observed} | {missing} | "
                    f"{_safe_markdown(assessment['owner'] or 'not applicable')} | "
                    f"{_safe_markdown(assessment['next_gate'] or 'not applicable')} | "
                    f"{_safe_markdown(assessment['reason'] or 'All declared values were observed.')} |"
                )
            lines.extend([
                "",
                "Cancellation phase counts: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(phase_counts.items())
                ),
                "",
                "Request task terminal states: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(request_states.items())
                ),
                "",
                "Child work terminal states: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(child_states.items())
                ),
                "",
                f"Schedule observation digest: `{observations['digest']}`",
                "",
                "Commands:",
                "",
            ])
            lines.extend(f"- `{_safe_markdown(command)}`" for command in record["commands"])
            lines.extend([
                "",
                f"Ruling: {_safe_markdown(record['ruling'])}",
                "",
                "Content-free evidence:",
                "",
            ])
            lines.extend(
                f"- `{item['evidence_id']}` (`{item['baseline_scope']}`): `{item['digest']}`"
                for item in record["content_free_evidence"]
            )
            continue
        if record["hypothesis_id"] == "H5":
            cause_counts = Counter(item["terminal_cause"] for item in observation_rows)
            outcome_counts = Counter(item["close_outcome"] for item in observation_rows)
            lines.extend([
                "",
                f"### `H5` — {_safe_markdown(record['subject'])}",
                "",
                "| Field | Value |",
                "|---|---|",
                f"| Record | `{record['record_id']}` |",
                f"| Baseline scope | `{record['baseline_scope']}` |",
                f"| Reviewer status | `{record['reviewer_status']}` |",
                f"| Derived close paths | {record['close_path_count']} |",
                f"| Scheduled merged close paths | {observations['close_path_count']} |",
                f"| Raw observations | {observations['total_observation_count']:,} |",
                "",
                "S1 serving RedisRuntime: " + ", ".join(
                    f"`{name}`=`{value}`"
                    for name, value in sorted(record["s1_redis_runtime_ruling"].items())
                ),
                "",
                "Shutdown order: " + "; ".join(
                    f"`{name}`: " + " → ".join(f"`{_safe_markdown(value)}`" for value in order)
                    for name, order in sorted(record["shutdown_order"].items())
                ),
                "",
                "Overlay-only close-path scope-outs:",
                "",
            ])
            lines.extend(
                f"- `{item['resource_type']}.{item['close_method']}` (`{item['close_path_id']}`): "
                f"{_safe_markdown(item['reason'])} Owner: {_safe_markdown(item['owner'])}. "
                f"Next gate: {_safe_markdown(item['next_gate'])}."
                for item in record["close_path_scope_outs"]
            )
            lines.extend([
                "",
                f"Observation closure: {observations['complete_observation_count']:,}/"
                f"{observations['total_observation_count']:,} structurally closed records "
                f"(`{observations['observation_closure_status']}`). This is record-shape closure, not "
                "settled-vocabulary completeness.",
                "",
                f"Settled-vocabulary coverage: `{observations['vocabulary_coverage_status']}`.",
                "",
                "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |",
                "|---|---|---|---|---|---|---|---|",
            ])
            for assessment in observations["coverage_assessments"]:
                observed = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["observed_values"])
                missing = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["missing_values"]) or "none"
                lines.append(
                    f"| `{assessment['field_name']}` | `{assessment['type_name']}` | "
                    f"`{assessment['status']}` | {observed} | {missing} | "
                    f"{_safe_markdown(assessment['owner'] or 'not applicable')} | "
                    f"{_safe_markdown(assessment['next_gate'] or 'not applicable')} | "
                    f"{_safe_markdown(assessment['reason'] or 'All declared values were observed.')} |"
                )
            lines.extend([
                "",
                "Terminal-cause counts: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(cause_counts.items())
                ),
                "",
                "Close-outcome counts: " + ", ".join(
                    f"`{name}`={count}" for name, count in sorted(outcome_counts.items())
                ),
                "",
                f"Schedule observation digest: `{observations['digest']}`",
                "",
                "Commands:",
                "",
            ])
            lines.extend(f"- `{_safe_markdown(command)}`" for command in record["commands"])
            lines.extend(["", f"Ruling: {_safe_markdown(record['ruling'])}"])
            continue
        phase_counts = Counter(site["delivery_phase"] for site in record["discovered_sites"])
        site_classifications = Counter(site["classification"] for site in record["discovered_sites"])
        scenario_counts = Counter(item["scenario"] for item in observation_rows)
        cancellation_timings = Counter(item["cancellation_timing"] for item in observation_rows)
        conversation_states = Counter(
            (item["conversation_commit"], item["primary_conversation_record_count"])
            for item in observation_rows
        )
        lines.extend([
            "",
            f"### `{record['hypothesis_id']}` — {_safe_markdown(record['subject'])}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Record | `{record['record_id']}` |",
            f"| Baseline scope | `{record['baseline_scope']}` |",
            f"| Seed anchor (merged, not binding) | `{record['baseline_anchor_commit']}` |",
            f"| Overlay identity | `{record['overlay_commit']}` |",
            f"| Binding commit | `{record['binding_commit'] or 'not nominated'}` |",
            f"| Reviewer status | `{record['reviewer_status']}` |",
            f"| Discovered sites | {len(record['discovered_sites'])} |",
            "",
            "Settled vocabulary: " + ", ".join(f"`{name}`" for name in record["vocabulary_names"]),
            "",
            "Delivery-phase counts: " + ", ".join(
                f"`{name}`={count}" for name, count in sorted(phase_counts.items())
            ),
            "",
            "Site-classification counts: " + ", ".join(
                f"`{name}`={count}" for name, count in sorted(site_classifications.items())
            ),
            "",
            f"Contradiction search: {contradiction['contradictory_site_count']} contradictory site(s) "
            f"across {contradiction['searched_reference_count']} mechanically discovered references. "
            f"{_safe_markdown(contradiction['conclusion'])}",
            "",
            "The canonical JSON `evidence_records[].discovered_sites` array contains every phase, "
            "classification, line, symbol, reference, invariant, and content-free AST digest; "
            "`contradiction_search.contradictory_citations` is the exact contradictory subset.",
            "",
            f"Schedule observations replayed {len(observations['literal_seeds'])} frozen literal seeds first, then "
            f"{observations['derived_seed_count']:,} commit-derived seeds anchored to "
            f"`{observations['derived_seed_anchor_commit']}`.",
            "",
            f"Observation closure: {observations['complete_observation_count']:,}/"
            f"{observations['total_observation_count']:,} structurally closed records "
            f"(`{observations['observation_closure_status']}`). This is record-shape closure, not "
            "settled-vocabulary completeness.",
            "",
            f"Settled-vocabulary coverage: `{observations['vocabulary_coverage_status']}`.",
            "",
            "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for assessment in observations["coverage_assessments"]:
            observed = ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["observed_values"])
            missing = (
                ", ".join(f"`{_safe_markdown(value)}`" for value in assessment["missing_values"])
                or "none"
            )
            owner = _safe_markdown(assessment["owner"] or "not applicable")
            next_gate = _safe_markdown(assessment["next_gate"] or "not applicable")
            reason = _safe_markdown(assessment["reason"] or "All declared values were observed.")
            lines.append(
                f"| `{assessment['field_name']}` | `{assessment['type_name']}` | "
                f"`{assessment['status']}` | {observed} | {missing} | {owner} | {next_gate} | {reason} |"
            )
        lines.extend([
            "",
            "Constant metadata dimensions are not vocabulary-coverage claims:",
            "",
        ])
        lines.extend(
            f"- `{note['field_name']}` = `{_safe_markdown(note['constant_value'])}` "
            f"(`{note['claim_status']}`): {_safe_markdown(note['reason'])}"
            for note in observations["constant_metadata_notes"]
        )
        lines.extend([
            "",
            "Primary scenario counts: " + ", ".join(
                f"`{_safe_markdown(name)}`={count}"
                for name, count in sorted(scenario_counts.items())
            ),
            "",
            "Primary attempts: "
            f"write attempted={sum(item['write_attempted'] for item in observation_rows)}, "
            f"write not attempted={sum(not item['write_attempted'] for item in observation_rows)}, "
            f"flush attempted={sum(item['flush_attempted'] for item in observation_rows)}, "
            f"flush not attempted={sum(not item['flush_attempted'] for item in observation_rows)}.",
            "",
            "Cancellation timing counts: " + ", ".join(
                f"`{_safe_markdown(name)}`={count}"
                for name, count in sorted(cancellation_timings.items())
            ),
            "",
            "Primary conversation states: " + ", ".join(
                f"`{_safe_markdown(state)}`/records={record_count}: {count}"
                for (state, record_count), count in sorted(conversation_states.items())
            ),
            "",
            f"Schedule observation digest: `{observations['digest']}`",
            "",
            "Commands:",
            "",
        ])
        lines.extend(f"- `{_safe_markdown(command)}`" for command in record["commands"])
        lines.extend([
            "",
            f"Ruling: {_safe_markdown(record['ruling'])}",
            "",
            "Content-free evidence:",
            "",
        ])
        lines.extend(
            f"- `{item['evidence_id']}` (`{item['baseline_scope']}`): `{item['digest']}`"
            for item in record["content_free_evidence"]
        )
    lines.extend([
        "",
        "## Running scope-out register",
        "",
        "| Hypothesis | Field | Missing values | Owning gate | Reachability | Owner | Reason |",
        "|---|---|---|---|---|---|---|",
    ])
    if canonical["scope_out_register"]:
        for entry in canonical["scope_out_register"]:
            missing = ", ".join(f"`{_safe_markdown(value)}`" for value in entry["missing_values"])
            reachability = entry["reachable_in_gate"]
            lines.append(
                f"| `{entry['hypothesis_id']}` | `{entry['field_name']}` | {missing} | "
                f"{_safe_markdown(entry['owning_gate'])} | `{reachability}` | "
                f"{_safe_markdown(entry['owner'])} | {_safe_markdown(entry['reachability_reason'])} |"
            )
    else:
        lines.append("| none | none | none | none | none | none | No open vocabulary scope-outs. |")
    lines.extend(["", "## Finding index", "", "| ID | Classification | Baseline | Owner |", "|---|---|---|---|"])
    lines.extend(
        f"| `{finding['finding_id']}` | `{finding['classification']}` | `{finding['baseline_scope']}` | {_safe_markdown(finding['owner'])} |"
        for finding in sorted(canonical["findings"], key=lambda item: item["finding_id"])
    )
    lines.append("")
    return "\n".join(lines)
