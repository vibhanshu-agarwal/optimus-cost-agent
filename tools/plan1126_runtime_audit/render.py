"""Deterministic, content-free Markdown rendering from canonical audit JSON."""

from __future__ import annotations

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
    lines.extend(["", "## Finding index", "", "| ID | Classification | Baseline | Owner |", "|---|---|---|---|"])
    lines.extend(
        f"| `{finding['finding_id']}` | `{finding['classification']}` | `{finding['baseline_scope']}` | {finding['owner']} |"
        for finding in sorted(canonical["findings"], key=lambda item: item["finding_id"])
    )
    lines.append("")
    return "\n".join(lines)
