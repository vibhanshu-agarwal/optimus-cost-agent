from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BINDING_COMMIT_CHUNKS = ("fac32284", "888850ba", "cde93815", "265cbabe", "3afd4663")
BINDING_COMMIT = "".join(_BINDING_COMMIT_CHUNKS)
OBLIGATION = "P11.26-UNRUN-BINDING"
OWNER = "P11-FEAT-ZED-RESUME"
EXPECTED_NODE_COUNT = 37
_SCHEMA_VERSION = 1
_MANIFEST_RELATIVE_PATH = Path("tests/plan1126_unrun_binding.json")


@dataclass(frozen=True)
class ScopeoutManifest:
    binding_commit: str
    obligation: str
    owner: str
    node_ids: tuple[str, ...]


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"scope-out manifest {key!r} must be a non-empty string")
    return value


def _validate_manifest_shape(manifest: ScopeoutManifest) -> None:
    if manifest.binding_commit != BINDING_COMMIT:
        raise ValueError("scope-out manifest binding commit drifted")
    if manifest.obligation != OBLIGATION:
        raise ValueError("scope-out manifest obligation drifted")
    if manifest.owner != OWNER:
        raise ValueError("scope-out manifest owner drifted")
    if len(manifest.node_ids) != EXPECTED_NODE_COUNT:
        raise ValueError(
            f"scope-out manifest must contain exactly {EXPECTED_NODE_COUNT} node IDs; "
            f"found {len(manifest.node_ids)}"
        )
    if len(set(manifest.node_ids)) != EXPECTED_NODE_COUNT:
        raise ValueError("scope-out manifest contains duplicate node IDs")
    if tuple(sorted(manifest.node_ids)) != manifest.node_ids:
        raise ValueError("scope-out manifest node IDs must use canonical sorted order")


def load_scopeout_manifest(repo_root: Path) -> ScopeoutManifest:
    path = repo_root / _MANIFEST_RELATIVE_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scope-out manifest root must be an object")
    expected_keys = {"schema_version", "binding_commit_chunks", "obligation", "owner", "node_ids"}
    if set(payload) != expected_keys:
        raise ValueError("scope-out manifest keys do not match the governed schema")
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("scope-out manifest schema version drifted")
    raw_node_ids = payload.get("node_ids")
    if not isinstance(raw_node_ids, list) or not all(
        isinstance(node_id, str) and node_id for node_id in raw_node_ids
    ):
        raise ValueError("scope-out manifest node_ids must be non-empty strings")
    raw_commit_chunks = payload.get("binding_commit_chunks")
    if not isinstance(raw_commit_chunks, list) or not all(
        isinstance(chunk, str) and len(chunk) == 8 for chunk in raw_commit_chunks
    ):
        raise ValueError("scope-out manifest binding_commit_chunks must contain eight-character strings")

    manifest = ScopeoutManifest(
        binding_commit="".join(raw_commit_chunks),
        obligation=_require_string(payload, "obligation"),
        owner=_require_string(payload, "owner"),
        node_ids=tuple(raw_node_ids),
    )
    _validate_manifest_shape(manifest)
    return manifest


def validate_scopeout_manifest(
    manifest: ScopeoutManifest,
    collected_nodeids: tuple[str, ...],
) -> None:
    _validate_manifest_shape(manifest)
    collected = set(collected_nodeids)
    missing = tuple(node_id for node_id in manifest.node_ids if node_id not in collected)
    if missing:
        raise ValueError(f"scope-out manifest names uncollected node IDs: {missing!r}")


def binding_commit_available(repo_root: Path, commit: str = BINDING_COMMIT) -> bool:
    repository = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if repository.returncode != 0:
        raise RuntimeError(f"cannot inspect binding commit outside a Git repository: {repository.stderr.strip()}")
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def scopeout_nodeids(
    manifest: ScopeoutManifest,
    collected_nodeids: tuple[str, ...],
    *,
    binding_available: bool,
) -> tuple[str, ...]:
    _validate_manifest_shape(manifest)
    if binding_available:
        return ()
    collected = set(collected_nodeids)
    return tuple(node_id for node_id in manifest.node_ids if node_id in collected)


def scopeout_reason() -> str:
    return (
        f"{OBLIGATION}: binding commit {BINDING_COMMIT} is unavailable; "
        f"owner {OWNER}; claim remains UNRUN and not verified"
    )


def format_terminal_summary(skipped_count: int) -> str:
    return (
        f"{OBLIGATION}: {skipped_count} tests skipped as UNRUN; owner {OWNER}; "
        "their claims are not verified"
    )
