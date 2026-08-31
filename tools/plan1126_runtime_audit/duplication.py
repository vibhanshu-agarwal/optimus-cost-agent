"""Deterministic Task 13 duplication discovery, verification, and rendering."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Protocol, Sequence

_ALGORITHM_VERSION = "plan1126-duplication-v1"
_INVENTORY_SCHEMA_VERSION = "plan-11-26-duplication-candidates-v1"
_AUDIT_SCHEMA_VERSION = "plan-11-26-duplication-audit-v1"
_DISPOSITIONS = frozenset({
    "CONFIRMED_DUPLICATION",
    "INTENTIONAL_REPETITION",
    "STRUCTURAL_SIMILARITY_ONLY",
})
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_CONSTANT_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]+$")


class SourceView(Protocol):
    def paths(self) -> tuple[str, ...]: ...

    def read_text(self, path: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ScopeExclusion:
    exclusion_id: str
    owner: str
    reason: str
    path_prefixes: tuple[str, ...]

    def matches(self, path: str) -> bool:
        return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in self.path_prefixes)


@dataclass(frozen=True, slots=True)
class ScopeManifest:
    allowed_roots: tuple[str, ...]
    exclusions: tuple[ScopeExclusion, ...]


@dataclass(frozen=True, slots=True)
class PriorSeed:
    seed_id: str
    symbol_leaves: tuple[str, ...]
    minimum_matches: int


DEFAULT_SCOPE = ScopeManifest(
    allowed_roots=("src/", "tools/"),
    exclusions=(
        ScopeExclusion(
            exclusion_id="tests",
            owner="Plan 11.26 / production-risk boundary",
            reason=(
                "Duplicated test scaffolding does not carry the production latent-defect risk "
                "that motivated Task 13."
            ),
            path_prefixes=("tests/",),
        ),
        ScopeExclusion(
            exclusion_id="evidence-collector",
            owner="EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR",
            reason=(
                "Evidence Collector is a separate product; cross-product similarity is deliberate "
                "product separation, not core-agent duplication debt."
            ),
            path_prefixes=(
                "src/evidence_handoff/collector/",
                "tools/evidence_gather.py",
                "tools/evidence_gather_support/",
            ),
        ),
        ScopeExclusion(
            exclusion_id="a2a-ledger",
            owner="EVIDENCE-HANDOFF-FEAT-A2A-LEDGER",
            reason=(
                "A2A Ledger is a separate product; cross-product similarity is deliberate product "
                "separation, not core-agent duplication debt."
            ),
            path_prefixes=(
                "src/evidence_handoff/ledger/",
                "src/evidence_handoff_runtime/",
                "tools/evidence_handoff_live_support/",
                "tools/verify_evidence_handoff_live.py",
            ),
        ),
    ),
)

DEFAULT_PRIOR_SEEDS = (
    PriorSeed("resolver-pairs", ("_resolve_acpx", "_resolve_optimus_agent"), 4),
    PriorSeed("hex-validators", ("_is_hex", "_is_lower_hex"), 3),
    PriorSeed("canonical-digest", ("_canonical_digest",), 3),
    PriorSeed("symbol-builders", ("_symbol",), 3),
    PriorSeed("keyring-service", ("_KEYRING_SERVICE",), 3),
    PriorSeed("claude-haiku-defaults", ("DEFAULT_AGENT_MODEL", "_DEFAULT_LOCAL_AGENT_MODEL"), 2),
    PriorSeed(
        "directive-regex-values",
        (
            "_WRITE_DIRECTIVE",
            "_FINAL_READ_DIRECTIVE",
            "_READ_DIRECTIVE",
            "_TEST_DIRECTIVE",
            "_FINAL_TEST_DIRECTIVE",
        ),
        2,
    ),
)


def canonical_json_bytes(value: object) -> bytes:
    """Return one content-stable JSON encoding."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _lf_normalized_text_digest(payload: bytes) -> str:
    text = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _module(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".")


def _call_name(node: ast.expr) -> tuple[str, str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return (parts[-1] if parts else "", ".".join(parts))


class _ShapeNormalizer(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_name", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        annotation = self.visit(node.annotation) if node.annotation is not None else None
        return ast.copy_location(ast.arg(arg="_arg", annotation=annotation, type_comment=None), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        return ast.copy_location(ast.Attribute(value=self.visit(node.value), attr="_attr", ctx=node.ctx), node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        marker = type(node.value).__name__
        return ast.copy_location(ast.Constant(value=marker), node)

    def visit_keyword(self, node: ast.keyword) -> ast.AST:
        return ast.copy_location(ast.keyword(arg=None if node.arg is None else "_kw", value=self.visit(node.value)), node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        normalized = self.generic_visit(node)
        assert isinstance(normalized, ast.FunctionDef)
        normalized.name = "_function"
        normalized.decorator_list = []
        normalized.returns = None
        normalized.type_comment = None
        return normalized

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        normalized = self.generic_visit(node)
        assert isinstance(normalized, ast.AsyncFunctionDef)
        normalized.name = "_function"
        normalized.decorator_list = []
        normalized.returns = None
        normalized.type_comment = None
        return normalized


def _nontrivial_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    body = [
        statement
        for statement in body
        if not (
            isinstance(statement, ast.Pass)
            or (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and statement.value.value is Ellipsis
            )
        )
    ]
    if len(body) == 1 and sum(1 for _ in ast.walk(body[0])) < 12:
        return []
    return body


def _signature_shape(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    arguments = node.args
    return ":".join((
        f"posonly={len(arguments.posonlyargs)}",
        f"positional={len(arguments.args)}",
        f"kwonly={len(arguments.kwonlyargs)}",
        f"defaults={len(arguments.defaults)}",
        f"kwdefaults={sum(value is not None for value in arguments.kw_defaults)}",
        f"vararg={int(arguments.vararg is not None)}",
        f"kwarg={int(arguments.kwarg is not None)}",
    ))


def _receiver_role(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        _, dotted = _call_name(node)
        return dotted
    if isinstance(node, ast.Call):
        leaf, _ = _call_name(node.func)
        return f"{leaf}()" if leaf else "call()"
    return type(node).__name__


def _callable_record(
    *, path: str, stack: Sequence[str], node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[dict[str, Any], Counter[str]]:
    copied = copy.deepcopy(node)
    copied.body = _nontrivial_body(copied)
    normalized = _ShapeNormalizer().visit(copied)
    ast.fix_missing_locations(normalized)
    dumped = ast.dump(normalized, include_attributes=False)
    calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]
    call_leaves = sorted(leaf for item in calls if (leaf := _call_name(item.func)[0]))
    receiver_roles = sorted(
        _receiver_role(item.func.value)
        for item in calls
        if isinstance(item.func, ast.Attribute)
    )
    controls = sorted({
        type(item).__name__
        for item in ast.walk(node)
        if isinstance(item, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match, ast.Raise, ast.Await, ast.Yield, ast.YieldFrom))
    })
    feature_counts = Counter(type(item).__name__ for item in ast.walk(normalized))
    symbol = ".".join((_module(path), *stack, node.name))
    material = {
        "path": path,
        "symbol": symbol,
        "line_start": node.lineno,
        "line_end": getattr(node, "end_lineno", node.lineno),
        "shape": dumped,
    }
    record = {
        "member_id": "member-" + _digest(material)[:20],
        "path": path,
        "symbol": symbol,
        "line_start": node.lineno,
        "line_end": getattr(node, "end_lineno", node.lineno),
        "async_kind": "ASYNC" if isinstance(node, ast.AsyncFunctionDef) else "SYNC",
        "signature_shape": _signature_shape(node),
        "shape_digest": hashlib.sha256(dumped.encode("utf-8")).hexdigest(),
        "token_digest": hashlib.sha256(ast.unparse(node).encode("utf-8")).hexdigest(),
        "call_leaves": call_leaves,
        "receiver_roles": receiver_roles,
        "control_flow": controls,
        "node_count": sum(feature_counts.values()),
    }
    return record, feature_counts


class _CallableVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.stack: list[str] = []
        self.records: list[tuple[dict[str, Any], Counter[str]]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if _nontrivial_body(node):
            self.records.append(_callable_record(path=self.path, stack=self.stack, node=node))
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def _constant_value(node: ast.expr) -> tuple[str, str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return "CONSTANT_VALUE", json.dumps(node.value, sort_keys=True, ensure_ascii=True)
    if isinstance(node, ast.Call):
        leaf, _ = _call_name(node.func)
        if leaf == "compile" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            flags = [ast.dump(argument, include_attributes=False) for argument in node.args[1:]]
            flags.extend(ast.dump(keyword.value, include_attributes=False) for keyword in node.keywords)
            return "REGEX_VALUE", json.dumps([node.args[0].value, flags], ensure_ascii=True)
    return None


def _constant_records(path: str, tree: ast.Module) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def visit_body(body: Sequence[ast.stmt], stack: tuple[str, ...] = ()) -> None:
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                # Class constants are predominantly enum/contract vocabularies. Task 13's
                # declaration lane intentionally covers repeated module-owned constants.
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(statement, ast.Assign):
                targets = list(statement.targets)
                value = statement.value
            elif isinstance(statement, ast.AnnAssign):
                targets = [statement.target]
                value = statement.value
            if value is None:
                continue
            classified = _constant_value(value)
            if classified is None:
                continue
            value_kind, normalized_value = classified
            for target in targets:
                if not isinstance(target, ast.Name) or not _CONSTANT_NAME.fullmatch(target.id):
                    continue
                symbol = ".".join((_module(path), *stack, target.id))
                material = {"path": path, "symbol": symbol, "line": statement.lineno, "value": normalized_value}
                records.append({
                    "member_id": "member-" + _digest(material)[:20],
                    "path": path,
                    "symbol": symbol,
                    "line_start": statement.lineno,
                    "line_end": getattr(statement, "end_lineno", statement.lineno),
                    "async_kind": "N/A",
                    "signature_shape": value_kind,
                    "shape_digest": hashlib.sha256(target.id.encode("utf-8")).hexdigest(),
                    "token_digest": hashlib.sha256(normalized_value.encode("utf-8")).hexdigest(),
                    "call_leaves": [],
                    "receiver_roles": [],
                    "control_flow": [],
                    "node_count": sum(1 for _ in ast.walk(value)),
                    "_constant_name": target.id,
                    "_constant_value": normalized_value,
                    "_constant_kind": value_kind,
                })

    visit_body(tree.body)
    return records


def _counter_similarity(left: Counter[str], right: Counter[str]) -> float:
    keys = set(left) | set(right)
    intersection = sum(min(left[key], right[key]) for key in keys)
    union = sum(max(left[key], right[key]) for key in keys)
    return intersection / union if union else 1.0


def _set_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _callable_groups(records: Sequence[tuple[dict[str, Any], Counter[str]]]) -> list[dict[str, Any]]:
    union = _UnionFind(len(records))
    exact: dict[str, list[int]] = defaultdict(list)
    blocks: dict[tuple[str, str, tuple[str, ...]], list[int]] = defaultdict(list)
    for index, (record, _) in enumerate(records):
        exact[record["shape_digest"]].append(index)
        blocks[(record["async_kind"], record["signature_shape"], tuple(record["control_flow"]))].append(index)
    for indices in exact.values():
        for index in indices[1:]:
            union.union(indices[0], index)
    for indices in blocks.values():
        for offset, left_index in enumerate(indices):
            left, left_features = records[left_index]
            for right_index in indices[offset + 1:]:
                right, right_features = records[right_index]
                largest = max(left["node_count"], right["node_count"])
                if largest and abs(left["node_count"] - right["node_count"]) / largest > 0.15:
                    continue
                feature_similarity = _counter_similarity(left_features, right_features)
                call_similarity = _set_similarity(left["call_leaves"], right["call_leaves"])
                receiver_similarity = _set_similarity(left["receiver_roles"], right["receiver_roles"])
                if feature_similarity >= 0.92 and call_similarity >= 0.60 and receiver_similarity >= 0.50:
                    union.union(left_index, right_index)
    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, (record, _) in enumerate(records):
        components[union.find(index)].append(record)
    groups: list[dict[str, Any]] = []
    for members in components.values():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda item: item["member_id"])
        reasons = ["AST_SHAPE_EQUAL"] if len({item["shape_digest"] for item in members}) == 1 else ["FEATURE_SIMILARITY"]
        group_material = {"kind": "CALLABLE_SHAPE", "members": [item["member_id"] for item in members]}
        groups.append({
            "group_id": "group-" + _digest(group_material)[:20],
            "kind": "CALLABLE_SHAPE",
            "join_reasons": reasons,
            "members": members,
        })
    return groups


def _constant_groups(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        buckets[("CONSTANT_NAME", record["_constant_name"])].append(record)
        value_kind = record["_constant_kind"]
        buckets[(value_kind, record["_constant_value"])].append(record)
    groups: list[dict[str, Any]] = []
    for (kind, _), raw_members in buckets.items():
        unique = {member["member_id"]: member for member in raw_members}
        members = sorted(unique.values(), key=lambda item: item["member_id"])
        if len(members) < 2:
            continue
        if kind == "CONSTANT_VALUE" and len({item["_constant_name"] for item in members}) < 2:
            continue
        public_members = [
            {key: value for key, value in member.items() if not key.startswith("_constant_")}
            for member in members
        ]
        material = {"kind": kind, "members": [item["member_id"] for item in public_members]}
        groups.append({
            "group_id": "group-" + _digest(material)[:20],
            "kind": kind,
            "join_reasons": ["REPEATED_NAME" if kind == "CONSTANT_NAME" else "NORMALIZED_VALUE_EQUAL"],
            "members": public_members,
        })
    return groups


def _source_commit(source: SourceView) -> str:
    value = getattr(source, "commit", None)
    return value if isinstance(value, str) else "WORKTREE_FIXTURE"


def _reconcile_seeds(groups: Sequence[Mapping[str, Any]], seeds: Sequence[PriorSeed]) -> list[dict[str, Any]]:
    reconciled: list[dict[str, Any]] = []
    for seed in seeds:
        matched_groups: set[str] = set()
        matched_members: set[str] = set()
        for group in groups:
            for member in group["members"]:
                leaf = str(member["symbol"]).rsplit(".", 1)[-1]
                if leaf in seed.symbol_leaves:
                    matched_groups.add(str(group["group_id"]))
                    matched_members.add(str(member["member_id"]))
        rediscovered = len(matched_members) >= seed.minimum_matches and bool(matched_groups)
        reconciled.append({
            "seed_id": seed.seed_id,
            "status": "REDISCOVERED" if rediscovered else "NOT_REDISCOVERED",
            "candidate_group_ids": sorted(matched_groups),
            "explanation": (
                "Candidate inventory contains the minimum reviewed seed membership."
                if rediscovered
                else f"Only {len(matched_members)} candidate members matched; {seed.minimum_matches} are required under {_ALGORITHM_VERSION}."
            ),
        })
    return sorted(reconciled, key=lambda item: item["seed_id"])


def discover_duplication_candidates(
    source: SourceView,
    scope: ScopeManifest = DEFAULT_SCOPE,
    prior_seeds: Sequence[PriorSeed] = DEFAULT_PRIOR_SEEDS,
) -> dict[str, Any]:
    """Discover high-recall candidates after applying affirmative exclusions."""

    matched: dict[str, list[str]] = {item.exclusion_id: [] for item in scope.exclusions}
    sources: dict[str, str] = {}
    for path in sorted(source.paths()):
        normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
        if not normalized.endswith(".py"):
            continue
        exclusion = next((item for item in scope.exclusions if item.matches(normalized)), None)
        if exclusion is not None:
            matched[exclusion.exclusion_id].append(normalized)
            continue
        if not any(normalized.startswith(root) for root in scope.allowed_roots):
            continue
        sources[normalized] = source.read_text(normalized)

    callable_records: list[tuple[dict[str, Any], Counter[str]]] = []
    constants: list[dict[str, Any]] = []
    for path, text in sources.items():
        tree = ast.parse(text, filename=path)
        visitor = _CallableVisitor(path)
        visitor.visit(tree)
        callable_records.extend(visitor.records)
        constants.extend(_constant_records(path, tree))
    groups = _callable_groups(callable_records) + _constant_groups(constants)
    groups = sorted(groups, key=lambda item: (item["kind"], item["group_id"]))
    source_tree_digest = _digest([
        {"path": path, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        for path, text in sorted(sources.items())
    ])
    inventory: dict[str, Any] = {
        "schema_version": _INVENTORY_SCHEMA_VERSION,
        "algorithm_version": _ALGORITHM_VERSION,
        "source_commit": _source_commit(source),
        "source_tree_digest": source_tree_digest,
        "allowed_roots": list(scope.allowed_roots),
        "scope_exclusions": [
            {
                "exclusion_id": exclusion.exclusion_id,
                "owner": exclusion.owner,
                "reason": exclusion.reason,
                "path_prefixes": list(exclusion.path_prefixes),
                "matched_paths": sorted(matched[exclusion.exclusion_id]),
            }
            for exclusion in scope.exclusions
        ],
        "source_files": sorted(sources),
        "source_file_count": len(sources),
        "excluded_file_count": sum(len(paths) for paths in matched.values()),
        "callable_universe_count": len(callable_records),
        "declaration_universe_count": len(constants),
        "candidate_groups": groups,
        "prior_seed_reconciliation": _reconcile_seeds(groups, prior_seeds),
    }
    inventory["inventory_digest"] = _digest(inventory)
    return inventory


def _validate_inventory_digest(inventory: Mapping[str, Any]) -> None:
    expected = inventory.get("inventory_digest")
    material = {key: value for key, value in inventory.items() if key != "inventory_digest"}
    if expected != _digest(material):
        raise ValueError("candidate inventory digest mismatch")


def _member_index(inventory: Mapping[str, Any]) -> tuple[dict[str, set[str]], dict[str, Mapping[str, Any]]]:
    groups: dict[str, set[str]] = {}
    members: dict[str, Mapping[str, Any]] = {}
    for group in inventory["candidate_groups"]:
        group_id = group["group_id"]
        if group_id in groups:
            raise ValueError("duplicate raw group id")
        group_members = {member["member_id"] for member in group["members"]}
        if len(group_members) != len(group["members"]):
            raise ValueError("duplicate member in raw group")
        groups[group_id] = group_members
        for member in group["members"]:
            prior = members.get(member["member_id"])
            if prior is not None and prior != member:
                raise ValueError("member identity maps to conflicting records")
            members[member["member_id"]] = member
    return groups, members


def verify_duplication_audit(
    inventory: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    frozen_artifact_bytes: Mapping[str, bytes],
) -> None:
    """Fail closed unless every raw member, finding, and candidate is in exact custody."""

    _validate_inventory_digest(inventory)
    if audit.get("schema_version") != _AUDIT_SCHEMA_VERSION:
        raise ValueError("duplication audit schema version mismatch")
    if audit.get("source_commit") != inventory.get("source_commit"):
        raise ValueError("duplication audit source commit mismatch")
    if audit.get("inventory_digest") != inventory.get("inventory_digest"):
        raise ValueError("duplication audit inventory digest mismatch")

    expected_frozen = {
        path: _lf_normalized_text_digest(payload)
        for path, payload in frozen_artifact_bytes.items()
    }
    recorded_frozen = {item["path"]: item["sha256"] for item in audit["frozen_task12_artifacts"]}
    if recorded_frozen != expected_frozen:
        raise ValueError("frozen Task 12 artifact digest mismatch")

    raw_groups, members = _member_index(inventory)
    covered: dict[str, set[str]] = defaultdict(set)
    partitions_by_id: dict[str, Mapping[str, Any]] = {}
    confirmed_partitions: list[Mapping[str, Any]] = []
    for partition in audit["reviewed_partitions"]:
        partition_id = partition["partition_id"]
        if partition_id in partitions_by_id:
            raise ValueError("duplicate partition id")
        partitions_by_id[partition_id] = partition
        raw_group_id = partition["raw_group_id"]
        if raw_group_id not in raw_groups:
            raise ValueError("partition references an unknown raw group")
        disposition = partition["disposition"]
        if disposition not in _DISPOSITIONS:
            raise ValueError("partition disposition is outside the closed vocabulary")
        member_ids = set(partition["member_ids"])
        if not member_ids or not member_ids <= raw_groups[raw_group_id]:
            raise ValueError("partition coverage contains unknown or empty membership")
        if covered[raw_group_id] & member_ids:
            raise ValueError("partition coverage overlaps")
        covered[raw_group_id].update(member_ids)
        if not str(partition["rationale"]).strip():
            raise ValueError("partition rationale is required")
        if disposition == "CONFIRMED_DUPLICATION":
            if not partition.get("finding_id") or not partition.get("candidate_id"):
                raise ValueError("confirmed partition requires finding and candidate custody")
            confirmed_partitions.append(partition)
        elif partition.get("finding_id") is not None or partition.get("candidate_id") is not None:
            raise ValueError("non-confirmed partition cannot claim finding or candidate custody")
    if set(covered) != set(raw_groups) or any(covered[group_id] != raw_groups[group_id] for group_id in raw_groups):
        raise ValueError("partition coverage does not exhaust every raw group exactly once")

    findings = {item["finding_id"]: item for item in audit["findings"]}
    candidates = {item["candidate_id"]: item for item in audit["remediation_candidates"]}
    if len(findings) != len(audit["findings"]) or len(candidates) != len(audit["remediation_candidates"]):
        raise ValueError("duplicate finding or candidate id")
    referenced_findings = {partition["finding_id"] for partition in confirmed_partitions}
    referenced_candidates = {partition["candidate_id"] for partition in confirmed_partitions}
    if referenced_findings != set(findings) or referenced_candidates != set(candidates):
        raise ValueError("confirmed partition custody does not match findings and candidates")
    for finding in findings.values():
        if finding["classification"] != "DUPLICATED" or finding["severity"] not in _SEVERITY_ORDER:
            raise ValueError("confirmed finding vocabulary is invalid")

    candidate_expected: dict[str, set[str]] = defaultdict(set)
    candidate_finding_ids: dict[str, set[str]] = defaultdict(set)
    for partition in confirmed_partitions:
        candidate_expected[partition["candidate_id"]].update(partition["member_ids"])
        candidate_finding_ids[partition["candidate_id"]].add(partition["finding_id"])
        finding_symbols = {members[member_id]["symbol"] for member_id in partition["member_ids"]}
        if finding_symbols != set(findings[partition["finding_id"]]["symbols"]):
            raise ValueError("finding symbols do not match confirmed partition membership")
    for candidate_id, candidate in candidates.items():
        member_ids = candidate_expected[candidate_id]
        symbols = {members[member_id]["symbol"] for member_id in member_ids}
        paths = {members[member_id]["path"] for member_id in member_ids}
        if candidate["latent_surface_closed"] != len(symbols):
            raise ValueError("candidate latent surface mismatch")
        if set(candidate["confirmed_member_symbols"]) != symbols:
            raise ValueError("candidate symbols do not match confirmed partitions")
        if candidate["module_count"] != len(paths):
            raise ValueError("candidate module count mismatch")
        if set(candidate["finding_ids"]) != candidate_finding_ids[candidate_id]:
            raise ValueError("candidate finding custody mismatch")
        if candidate["shape"] not in {"point-fix", "consolidation"}:
            raise ValueError("candidate shape is invalid")
        if not candidate["owner_to_be"] or not candidate["next_gate"]:
            raise ValueError("candidate owner and next gate are required")

    ordered = sorted(
        candidates.values(),
        key=lambda item: (-item["latent_surface_closed"], _SEVERITY_ORDER[item["severity"]], item["candidate_id"]),
    )
    if [item["rank"] for item in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError("candidate ranking does not reproduce latent-surface/severity order")
    if [item["candidate_id"] for item in audit["remediation_candidates"]] != [item["candidate_id"] for item in ordered]:
        raise ValueError("candidate ranking table is not in canonical order")

    dispositions = Counter(partition["disposition"] for partition in audit["reviewed_partitions"])
    expected_counts = {
        "raw_groups": len(raw_groups),
        "reviewed_partitions": len(audit["reviewed_partitions"]),
        "confirmed_partitions": dispositions["CONFIRMED_DUPLICATION"],
        "intentional_partitions": dispositions["INTENTIONAL_REPETITION"],
        "similarity_only_partitions": dispositions["STRUCTURAL_SIMILARITY_ONLY"],
        "confirmed_findings": len(findings),
        "remediation_candidates": len(candidates),
    }
    if audit["counts"] != expected_counts:
        raise ValueError("duplication audit counts do not reproduce")
    gate_status = audit["gate_status"]
    if gate_status not in {"PENDING_G7", "ACCEPTED_OPEN", "ACCEPTED_ZERO"}:
        raise ValueError("duplication audit gate status is invalid")
    if gate_status == "ACCEPTED_ZERO" and findings:
        raise ValueError("duplication audit gate status contradicts confirmed findings")
    if gate_status == "ACCEPTED_OPEN" and not findings:
        raise ValueError("duplication audit gate status contradicts confirmed findings")


def render_duplication_markdown(inventory: Mapping[str, Any], audit: Mapping[str, Any]) -> str:
    """Render sorted reviewer evidence from the two canonical JSON documents."""

    lines = [
        "# Plan 11.26 Task 13 Duplication Audit",
        "",
        f"- Source commit: `{inventory['source_commit']}`",
        f"- Inventory digest: `{inventory['inventory_digest']}`",
        f"- Algorithm: `{inventory['algorithm_version']}`",
        f"- Gate status: `{audit['gate_status']}`",
        "- Historical 78 groups: prior high-recall upper bound only; not a defect count.",
        "",
        "## Affirmative exclusions",
        "",
        "| Exclusion | Owner | Matched files | Reason |",
        "|---|---|---:|---|",
    ]
    for exclusion in inventory["scope_exclusions"]:
        lines.append(
            f"| `{exclusion['exclusion_id']}` | `{exclusion['owner']}` | {len(exclusion['matched_paths'])} | {exclusion['reason']} |"
        )
    lines.extend((
        "",
        "## Raw candidate groups",
        "",
        f"Raw groups: **{audit['counts']['raw_groups']}**; confirmed partitions: "
        f"**{audit['counts']['confirmed_partitions']}**.",
        "",
        "| Raw group | Kind | Members | Join basis |",
        "|---|---|---:|---|",
    ))
    for group in inventory["candidate_groups"]:
        lines.append(
            f"| `{group['group_id']}` | `{group['kind']}` | {len(group['members'])} | "
            f"{', '.join(f'`{reason}`' for reason in group['join_reasons'])} |"
        )
    lines.extend(("", "## Reviewed partitions", "", "| Partition | Raw group | Disposition | Members | Rationale |", "|---|---|---|---:|---|"))
    for partition in audit["reviewed_partitions"]:
        lines.append(
            f"| `{partition['partition_id']}` | `{partition['raw_group_id']}` | "
            f"`{partition['disposition']}` | {len(partition['member_ids'])} | {partition['rationale']} |"
        )
    lines.extend(("", "## Confirmed findings", ""))
    if audit["findings"]:
        lines.extend(("| Finding | Severity | Subject |", "|---|---|---|"))
        for finding in audit["findings"]:
            lines.append(f"| `{finding['finding_id']}` | `{finding['severity']}` | {finding['subject']} |")
    else:
        lines.append("No duplication finding was confirmed.")
    lines.extend(("", "## Ranked remediation custody", ""))
    if audit["remediation_candidates"]:
        lines.extend(("| Rank | Candidate | Shape | Surface | Severity | Owner-to-be |", "|---:|---|---|---:|---|---|"))
        for candidate in audit["remediation_candidates"]:
            lines.append(
                f"| {candidate['rank']} | `{candidate['candidate_id']}` | `{candidate['shape']}` | "
                f"{candidate['latent_surface_closed']} | `{candidate['severity']}` | {candidate['owner_to_be']} |"
            )
    else:
        lines.append("No remediation candidate was produced.")
    return "\n".join(lines) + "\n"
