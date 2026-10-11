"""Test profiles: exactly one cost tier per collected test, and the static profiles built on them.

Test tooling only (Plan 11.30). Pure: nothing here reads a file, runs a process or imports a test.
`tests/profiles.toml` is the one manifest; `tests/support/profiles_plugin.py` applies it.

A tier rule names files (`paths`, matched with `PurePosixPath.full_match`) or node IDs (`nodes`, a
node ID or a prefix of one ending where a `::` child or a `[` parameter begins). For each node the
longest matching node rule decides; otherwise the single matching path rule; otherwise `core`. Two
path rules claiming one file are a conflict, never a silent precedence. Tags are additive and
independent of tiers. A rule that decides no node is reported, so a stale rule cannot hide.
"""

from __future__ import annotations

import ast
import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import PurePosixPath

SCHEMA = "test-profiles-v1"
TIERS = ("core", "gates", "proc", "audit-current", "audit-sealed", "e2e-local")
DEFAULT_TIER = "core"
DEFAULT_ORIGIN = "default"
TAGS = ("concurrency", "platform")
# Static profiles: a tier set, a tag, or one side of core's reviewed parallel split. `full` is the unchanged
# default selection. `core-parallel` is the only selection xdist workers may run (Plan 11.30 Task 5): core nodes
# the manifest's reviewed [parallel] rule admits; `core-serial` is the rest of core.
STATIC_PROFILES = {
    "full": None,
    "core": ("tier", frozenset({"core"})),
    "core-parallel": ("parallel", True),
    "core-serial": ("parallel", False),
    "proc": ("tier", frozenset({"proc"})),
    "audit": ("tier", frozenset({"audit-current", "audit-sealed"})),
    "platform": ("tag", "platform"),
    "concurrency": ("tag", "concurrency"),
}
_RULE_KEYS = {"tier", "paths", "nodes", "why"}
_TAG_KEYS = {"name", "paths", "nodes", "why"}
_MEASUREMENT_KEYS = {"source", "explicit_seconds", "slow_nodes"}
_SELECTION_KEYS = {"broad_paths", "prose_gates", "platform_paths"}
_INPUT_KEYS = {"paths", "tiers", "files", "why"}
_PARALLEL_KEYS = {"serial", "why"}
_TOP_KEYS = {"schema", "rules", "tags", "measurement", "selection", "inputs", "parallel"}


class ManifestError(ValueError):
    """The manifest text is not a valid test-profiles manifest."""


class ClassificationError(ValueError):
    """The manifest cannot classify these nodes unambiguously, or a profile is not static."""


@dataclass(frozen=True)
class Rule:
    label: str  # `rules[N]` or `tags[N]`, 1-based, for messages
    value: str  # the tier, or the tag name
    kind: str  # "paths" or "nodes"
    patterns: tuple[str, ...]
    why: str


@dataclass(frozen=True)
class InputRule:
    """A declared data/launch input: changed paths matching `patterns` select these tiers or test files."""

    label: str
    patterns: tuple[str, ...]
    tiers: tuple[str, ...]
    files: tuple[str, ...]
    why: str


@dataclass(frozen=True)
class ProfileManifest:
    rules: tuple[Rule, ...]
    tags: tuple[Rule, ...]
    measurement_source: str
    explicit_seconds: float
    slow_nodes: tuple[str, ...]
    digest: str
    broad_paths: tuple[str, ...] = ()
    prose_gates: tuple[str, ...] = ()
    platform_paths: tuple[str, ...] = ()
    inputs: tuple[InputRule, ...] = ()
    # The reviewed [parallel] rule's serial patterns, or None when the manifest has no such rule (then no node is
    # admitted to xdist workers).
    parallel_serial: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Classification:
    tiers: dict[str, str]
    origins: dict[str, str]
    tags: dict[str, frozenset[str]]
    unmatched: tuple[str, ...]
    # Core nodes admitted to xdist workers by the reviewed [parallel] rule (Plan 11.30 Task 5).
    parallel: frozenset[str] = frozenset()


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ManifestError(f"{where}: must be a list of non-empty strings")
    return tuple(value)


def _rule(table: object, label: str, keys: set[str], value_key: str, allowed: tuple[str, ...]) -> Rule:
    if not isinstance(table, dict):
        raise ManifestError(f"{label}: must be a table")
    unknown = sorted(set(table) - keys)
    if unknown:
        raise ManifestError(f"{label}: unknown keys {unknown}")
    value = table.get(value_key)
    if value not in allowed:
        noun = "tier" if value_key == "tier" else "tag"
        raise ManifestError(f"{label}: {noun} {value!r} is not one of {list(allowed)}")
    why = table.get("why")
    if not isinstance(why, str) or not why.strip():
        raise ManifestError(f"{label}: a non-empty why is required")
    kinds = [kind for kind in ("paths", "nodes") if kind in table]
    if len(kinds) != 1:
        raise ManifestError(f"{label}: exactly one of paths or nodes is required")
    patterns = _strings(table[kinds[0]], f"{label}.{kinds[0]}")
    if not patterns:
        raise ManifestError(f"{label}.{kinds[0]}: empty")
    for pattern in patterns:
        if (kinds[0] == "nodes") != ("::" in pattern):
            raise ManifestError(f"{label}: {pattern!r} — a node rule names a `::` node ID, a path rule never does")
    return Rule(label, str(value), kinds[0], patterns, why)


def _input(table: object, label: str) -> InputRule:
    if not isinstance(table, dict):
        raise ManifestError(f"{label}: must be a table")
    unknown = sorted(set(table) - _INPUT_KEYS)
    if unknown:
        raise ManifestError(f"{label}: unknown keys {unknown}")
    why = table.get("why")
    if not isinstance(why, str) or not why.strip():
        raise ManifestError(f"{label}: a non-empty why is required")
    patterns = _strings(table.get("paths"), f"{label}.paths")
    if not patterns:
        raise ManifestError(f"{label}.paths: empty")
    kinds = [kind for kind in ("tiers", "files") if kind in table]
    if len(kinds) != 1:
        raise ManifestError(f"{label}: exactly one of tiers or files is required")
    selected = _strings(table[kinds[0]], f"{label}.{kinds[0]}")
    if not selected:
        raise ManifestError(f"{label}.{kinds[0]}: empty")
    if kinds[0] == "tiers" and set(selected) - set(TIERS):
        raise ManifestError(f"{label}: tier {sorted(set(selected) - set(TIERS))} is not one of {list(TIERS)}")
    return InputRule(label, patterns, selected if kinds[0] == "tiers" else (), selected if kinds[0] == "files" else (), why)


def _selection(table: object) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if not isinstance(table, dict):
        raise ManifestError("selection: must be a table")
    unknown = sorted(set(table) - _SELECTION_KEYS)
    if unknown:
        raise ManifestError(f"selection: unknown keys {unknown}")
    return tuple(_strings(table.get(key, []), f"selection.{key}") for key in ("broad_paths", "prose_gates", "platform_paths"))  # type: ignore[return-value]


def load_manifest(text: str) -> ProfileManifest:
    """Parse and validate the manifest text. Every problem is a ManifestError naming where it is."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"not valid TOML: {error}") from None
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise ManifestError(f"unknown keys {unknown}")
    if data.get("schema") != SCHEMA:
        raise ManifestError(f"schema must be {SCHEMA!r}")
    rule_tables, tag_tables = data.get("rules", []), data.get("tags", [])
    if not isinstance(rule_tables, list) or not isinstance(tag_tables, list):
        raise ManifestError("rules and tags must be arrays of tables")
    rules = tuple(_rule(table, f"rules[{index}]", _RULE_KEYS, "tier", TIERS) for index, table in enumerate(rule_tables, 1))
    tags = tuple(_rule(table, f"tags[{index}]", _TAG_KEYS, "name", TAGS) for index, table in enumerate(tag_tables, 1))
    for group in (rules, tuple(tag for tag in tags if tag.value == "concurrency"), tuple(tag for tag in tags if tag.value == "platform")):
        seen: set[str] = set()
        for rule in group:
            for pattern in rule.patterns:
                if pattern in seen:
                    raise ManifestError(f"{rule.label}: {pattern!r} appears more than once")
                seen.add(pattern)
    measurement = data.get("measurement", {"source": "", "explicit_seconds": 2.0, "slow_nodes": []})
    if not isinstance(measurement, dict) or sorted(set(measurement) - _MEASUREMENT_KEYS):
        raise ManifestError(f"measurement: unknown keys {sorted(set(measurement) - _MEASUREMENT_KEYS) if isinstance(measurement, dict) else 'not a table'}")
    seconds = measurement.get("explicit_seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        raise ManifestError("measurement.explicit_seconds must be a positive number")
    source = measurement.get("source")
    if not isinstance(source, str):
        raise ManifestError("measurement.source must be text")
    slow = _strings(measurement.get("slow_nodes"), "measurement.slow_nodes")
    for node in slow:
        if "::" not in node:
            raise ManifestError(f"measurement.slow_nodes: {node!r} is not a `::` node ID")
    broad, prose, platform = _selection(data.get("selection", {}))
    input_tables = data.get("inputs", [])
    if not isinstance(input_tables, list):
        raise ManifestError("inputs must be an array of tables")
    inputs = tuple(_input(table, f"inputs[{index}]") for index, table in enumerate(input_tables, 1))
    parallel = _parallel(data["parallel"]) if "parallel" in data else None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ProfileManifest(rules, tags, source, float(seconds), slow, digest, broad, prose, platform, inputs, parallel)


def _parallel(table: object) -> tuple[str, ...]:
    """The reviewed [parallel] rule: the core patterns that stay serial, and why the rest may run on xdist workers."""
    if not isinstance(table, dict) or sorted(set(table) - _PARALLEL_KEYS):
        raise ManifestError(f"parallel: unknown keys {sorted(set(table) - _PARALLEL_KEYS) if isinstance(table, dict) else 'not a table'}")
    why = table.get("why")
    if not isinstance(why, str) or not why.strip():
        raise ManifestError("parallel: a reviewed rule needs a non-empty why")
    serial = _strings(table.get("serial", []), "parallel.serial")
    if len(set(serial)) != len(serial):
        raise ManifestError("parallel.serial: a pattern appears more than once")
    return serial


def _node_match(nodeid: str, pattern: str) -> bool:
    return nodeid == pattern or nodeid.startswith((pattern + "::", pattern + "["))


def _file(nodeid: str) -> PurePosixPath:
    return PurePosixPath(nodeid.split("::", 1)[0])


def classify_nodes(nodeids: tuple[str, ...], manifest: ProfileManifest) -> Classification:
    """The tier, deciding rule and tags of every node. A file claimed by two path rules is a conflict."""
    tiers: dict[str, str] = {}
    origins: dict[str, str] = {}
    deciding: set[tuple[str, str]] = set()
    node_rules = [(pattern, rule) for rule in manifest.rules if rule.kind == "nodes" for pattern in rule.patterns]
    path_rules = [(pattern, rule) for rule in manifest.rules if rule.kind == "paths" for pattern in rule.patterns]
    for nodeid in nodeids:
        matching = [(pattern, rule) for pattern, rule in node_rules if _node_match(nodeid, pattern)]
        if matching:
            pattern, rule = max(matching, key=lambda found: len(found[0]))
        else:
            file = _file(nodeid)
            claims = [(pattern, rule) for pattern, rule in path_rules if file.full_match(pattern)]
            if len(claims) > 1:
                named = ", ".join(f"{rule.label} {pattern!r}" for pattern, rule in claims)
                raise ClassificationError(f"{file} is claimed by more than one path rule: {named}")
            if not claims:
                tiers[nodeid], origins[nodeid] = DEFAULT_TIER, DEFAULT_ORIGIN
                continue
            pattern, rule = claims[0]
        tiers[nodeid], origins[nodeid] = rule.value, f"{rule.label}: {pattern}"
        deciding.add((rule.label, pattern))
    tags: dict[str, frozenset[str]] = {}
    for nodeid in nodeids:
        found = set()
        for rule in manifest.tags:
            for pattern in rule.patterns:
                hit = _node_match(nodeid, pattern) if rule.kind == "nodes" else _file(nodeid).full_match(pattern)
                if hit:
                    found.add(rule.value)
                    deciding.add((rule.label, pattern))
        tags[nodeid] = frozenset(found)
    unmatched = tuple(
        f"{rule.label}: {pattern}"
        for rule in (*manifest.rules, *manifest.tags) for pattern in rule.patterns
        if (rule.label, pattern) not in deciding
    )
    parallel, dead = _parallel_members(tiers, tags, manifest.parallel_serial)
    return Classification(tiers, origins, tags, unmatched + dead, parallel)


def _parallel_members(
    tiers: dict[str, str], tags: dict[str, frozenset[str]], serial: tuple[str, ...] | None,
) -> tuple[frozenset[str], tuple[str, ...]]:
    """The core nodes admitted to xdist workers, and the serial patterns that match no core node. Without a reviewed
    rule nothing is admitted. A tagged node (concurrency, platform) always stays serial."""
    if serial is None:
        return frozenset(), ()
    core = [node for node, tier in tiers.items() if tier == "core"]

    def kept_serial(node: str, pattern: str) -> bool:
        return _node_match(node, pattern) if "::" in pattern else _file(node).full_match(pattern)

    dead = tuple(f"parallel: {pattern}" for pattern in serial if not any(kept_serial(node, pattern) for node in core))
    admitted = frozenset(
        node for node in core if not tags.get(node) and not any(kept_serial(node, pattern) for pattern in serial)
    )
    return admitted, dead


def profile_members(classification: Classification, profile: str) -> frozenset[str]:
    """The node IDs a static profile selects. Change-selected profiles need the selector."""
    if profile not in STATIC_PROFILES:
        raise ClassificationError(f"profile {profile!r} is not static; static profiles are {sorted(STATIC_PROFILES)}")
    selector = STATIC_PROFILES[profile]
    if selector is None:
        return frozenset(classification.tiers)
    kind, wanted = selector
    if kind == "tier":
        return frozenset(node for node, tier in classification.tiers.items() if tier in wanted)
    if kind == "parallel":
        core = frozenset(node for node, tier in classification.tiers.items() if tier == "core")
        return core & classification.parallel if wanted else core - classification.parallel
    return frozenset(node for node, tags in classification.tags.items() if wanted in tags)


def unexplained_slow_nodes(classification: Classification, manifest: ProfileManifest) -> tuple[str, ...]:
    """Collected nodes measured above the explicit threshold whose tier no rule decided."""
    return tuple(node for node in manifest.slow_nodes if classification.origins.get(node) == DEFAULT_ORIGIN)


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


_CONCURRENCY_MODULES = {"tests.support.concurrency", "tests.support.fault_injection"}
_PLATFORM_ATTRIBUTES = {
    ("sys", "platform"), ("sys", "getwindowsversion"), ("os", "name"),
    ("platform", "system"), ("platform", "platform"), ("platform", "win32_ver"), ("platform", "uname"),
}


def concurrency_signal(source: str) -> bool:
    """Whether a test module imports the shared concurrency or fault-injection helpers."""
    return bool(_imports(ast.parse(source)) & _CONCURRENCY_MODULES)


def platform_signal(source: str) -> bool:
    """Whether a test module reads the running platform (`sys.platform`, `os.name`, `platform.system()`...)."""
    return any(
        isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and (node.value.id, node.attr) in _PLATFORM_ATTRIBUTES
        for node in ast.walk(ast.parse(source))
    )


# --- Change selection (Plan 11.30 Task 2). Pure: the runner reads Git and the files and passes them in. ---

CHANGE_SELECTED = ("commit", "checkpoint", "quick")
EXPENSIVE_TIERS = ("proc", "audit-sealed", "audit-current", "e2e-local")
WSL_OBLIGATION = "wsl-platform: next checkpoint"
_NATIVE_MODULES = {"ctypes", "msvcrt", "winreg", "keyring", "_winapi"}
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_PATH_CALLS = {"Path", "PurePath", "PurePosixPath", "PureWindowsPath", "joinpath"}


class SelectionError(ValueError):
    """The changes or the request cannot be turned into a selection: an ordinary nonzero failure."""


@dataclass(frozen=True)
class Change:
    status: str  # A, M, D, R, C or T (git's first letter)
    path: str  # the new path; for a deletion, the deleted path
    old_path: str | None = None  # renames and copies


@dataclass(frozen=True)
class ChangeSet:
    view: str  # "commit": index against HEAD; "checkpoint": base against the working tree
    changes: tuple[Change, ...]
    provisional: tuple[tuple[str, str | None], ...] = ()  # uncommitted paths and the sha256 of their working bytes
    old_graph: bool = True  # False when the HEAD/base view could not be read


@dataclass(frozen=True)
class ProfileRequest:
    profile: str


@dataclass(frozen=True)
class DependencyMap:
    module_of: dict[str, str]  # tracked .py path -> importable module name
    importers: dict[str, frozenset[str]]  # module name -> files that import it, as code or as a string
    # (path or folder a file names, that file, "data" | "scan"): data is consumed; a folder of code is scanned or run
    references: tuple[tuple[str, str, str], ...]
    platform_files: frozenset[str]  # sources whose change triggers platform tests
    unparsed: frozenset[str]  # tracked .py files that are not valid Python
    tracked: frozenset[str]
    manifest: ProfileManifest


@dataclass(frozen=True)
class Selection:
    profile: str
    label: str  # "selected"; "no-commit-input" / "no-change-input" when there is nothing to select from
    nodes: tuple[str, ...]
    reasons: dict[str, str]
    fallback: tuple[str, ...]
    platform_triggers: tuple[str, ...]
    domains: dict[str, str]
    obligations: tuple[str, ...]
    provisional: tuple[tuple[str, str | None], ...]
    concurrency: tuple[str, ...]  # checkpoint: the selected nodes repeated under load
    audit_depth: str  # "full" at a checkpoint; "quick" when a commit selects a current audit (R5 after G); else "none"


def parse_name_status(raw: bytes) -> tuple[Change, ...]:
    """`git diff --name-status -z` output. Paths are opaque text up to NUL, so any name survives."""
    try:
        fields = raw.decode("utf-8").split("\0")
    except UnicodeDecodeError:
        raise SelectionError("name-status output is not UTF-8") from None
    if fields and fields[-1] == "":
        fields.pop()
    changes: list[Change] = []
    index = 0
    while index < len(fields):
        status = fields[index][:1]
        width = 2 if status in {"R", "C"} else 1
        if not status or index + width >= len(fields):
            raise SelectionError(f"malformed name-status output at field {index}")
        if width == 2:
            changes.append(Change(status, fields[index + 2], fields[index + 1]))
        else:
            changes.append(Change(status, fields[index + 1]))
        index += 1 + width
    return tuple(changes)


def module_name(path: str) -> str | None:
    """The module a tracked .py file is imported as: `src/` is a source root; the rest is rooted at the checkout."""
    if not path.endswith(".py"):
        return None
    parts = (path[4:] if path.startswith("src/") else path)[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _prefixes(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[: index + 1]) for index in range(len(parts))]


def _imported_names(tree: ast.AST, module: str | None, package: bool) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.update(_prefixes(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if module is None:
                    continue
                parts = module.split(".") if package else module.split(".")[:-1]
                if node.level > 1:
                    parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join([*parts, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            if not base:
                continue
            names.update(_prefixes(base))
            names.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return names


def _flatten_division(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [*_flatten_division(node.left), *_flatten_division(node.right)]
    return [node]


def _path_texts(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Path-like text a module names: (string constants, segments joined by `/` or passed to a Path call)."""
    loose: set[str] = set()
    joined: set[str] = set()
    # Only a whole `a / b / c` chain names a path; its inner sub-chains are prefixes nobody named.
    inner = {id(child) for node in ast.walk(tree) if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) for child in (node.left, node.right)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 300:
            loose.add(node.value)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and id(node) not in inner:
            run: list[str] = []
            for part in [*_flatten_division(node), None]:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    run.append(part.value)
                    continue
                if run:
                    joined.add("/".join(run))
                run = []
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if name in _PATH_CALLS and node.args and all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args):
                joined.add("/".join(str(arg.value) for arg in node.args))  # type: ignore[attr-defined]
    return loose, joined


def _normal(text: str) -> str:
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def build_dependency_map(sources: dict[str, str], tracked: tuple[str, ...] | list[str] | frozenset[str], manifest: ProfileManifest) -> DependencyMap:
    """Import, string-import and path-reference edges of every tracked Python source."""
    tracked_set = frozenset(tracked) | frozenset(sources)
    folders = {str(parent) for path in tracked_set for parent in PurePosixPath(path).parents if str(parent) != "."}
    # A folder holding Python code (outside fixtures) is scanned or run when named, never read as data.
    code_folders = {
        str(parent) for path in tracked_set if path.endswith(".py")
        for parent in PurePosixPath(path).parents if str(parent) != "." and not str(parent).startswith("tests/fixtures")
    }
    module_of = {path: name for path in sources if (name := module_name(path)) is not None}
    top_packages = {name.split(".", 1)[0] for name in module_of.values()}
    importers: dict[str, set[str]] = {}
    references: set[tuple[str, str, str]] = set()
    platform: set[str] = set()
    unparsed: set[str] = set()
    for path, source in sorted(sources.items()):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            unparsed.add(path)
            continue
        names = _imported_names(tree, module_of.get(path), path.endswith("__init__.py"))
        loose, joined = _path_texts(tree)
        for text in loose:
            if _DOTTED.fullmatch(text) and text.split(".", 1)[0] in top_packages:
                names.update(_prefixes(text))
        for name in names:
            importers.setdefault(name, set()).add(path)
        for text in loose | joined:
            candidate = _normal(text)
            if not candidate or candidate.startswith("/") or ".." in candidate.split("/"):
                continue
            # A one-segment name counts only when built as a path or when it is a dotted file name.
            if "/" not in candidate and text not in joined and "." not in candidate:
                continue
            if candidate in tracked_set:
                references.add((candidate, path, "data"))
            elif candidate in folders:
                references.add((candidate, path, "scan" if candidate in code_folders else "data"))
        imported = _imports(tree)
        if platform_signal(source) or imported & _NATIVE_MODULES or (path.startswith("src/") and "subprocess" in imported):
            platform.add(path)
    return DependencyMap(
        module_of=module_of, importers={name: frozenset(files) for name, files in importers.items()},
        references=tuple(sorted(references)), platform_files=frozenset(platform), unparsed=frozenset(unparsed),
        tracked=tracked_set, manifest=manifest,
    )


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    pure = PurePosixPath(path)
    return any(pure.full_match(pattern) for pattern in patterns)


_MACHINE_SUFFIXES = (".json", ".jsonl", ".yml", ".yaml", ".toml", ".py", ".csv")


def _is_prose(path: str) -> bool:
    """`docs/**` except machine-readable data, root `*.md`, and prose under `reports/` (v4 standing prose rule)."""
    if path.startswith("docs/"):
        return not path.endswith(_MACHINE_SUFFIXES)
    return path.endswith(".md") and ("/" not in path or path.startswith("reports/"))


def _is_test_module(path: str) -> bool:
    name = PurePosixPath(path).name
    return path.startswith("tests/") and name.startswith("test_") and name.endswith(".py")


def _scanners(path: str, dependencies: DependencyMap, *, through_tools: bool = False) -> list[str]:
    """Test files that scan or run a folder of code holding the changed path (`ROOT / "src"`, `"tests/unit"`).
    They are selected, but they consume no particular file, so they never make a change count as mapped.
    With `through_tools` (prose), the tests a scanning tool reaches by import count too: a tool that reads every
    document (`tools/doc_paths.py`) reads a new one as well, while a code change already runs every gate and a
    tool that runs a code folder gives its own tests nothing from each file there."""
    readers = {
        reader for referenced, reader, kind in dependencies.references
        if kind == "scan" and path.startswith(referenced + "/")
    }
    found = {reader for reader in readers if _is_test_module(reader)}
    if through_tools:
        for tool in sorted(readers - found):
            found.update(file for file in _dependents(tool, dependencies) if _is_test_module(file))
    return sorted(found)


def _dependents(path: str, dependencies: DependencyMap) -> list[str]:
    """Files reached from a changed path: its importers (by module name, so a removed module still finds
    them) and the readers of it as data, then transitively whatever imports those. Only the changed
    path's own bytes changed, so data references apply to it alone; imports carry the change. Stable order."""
    reached_order: list[str] = []
    found: set[str] = {path}
    queue = [path]
    while queue:
        current = queue.pop(0)
        name = dependencies.module_of.get(current) or module_name(current)
        reached = set(dependencies.importers.get(name, ())) if name else set()
        if current == path:
            reached |= {
                reader for referenced, reader, kind in dependencies.references
                if kind == "data" and (path == referenced or path.startswith(referenced + "/"))
            }
        for file in sorted(reached - found):
            found.add(file)
            reached_order.append(file)
            queue.append(file)
    return reached_order


def select_tests(changes: ChangeSet, classification: Classification, dependencies: DependencyMap, request: ProfileRequest) -> Selection:
    """The deterministic selection of a change-selected profile, with one reason per node."""
    profile = request.profile
    if profile not in CHANGE_SELECTED:
        raise SelectionError(f"profile {profile!r} is not change-selected; change-selected profiles are {list(CHANGE_SELECTED)}")
    manifest = dependencies.manifest
    tiers = classification.tiers
    by_file: dict[str, list[str]] = {}
    for node in sorted(tiers):
        by_file.setdefault(node.split("::", 1)[0], []).append(node)
    reasons: dict[str, str] = {}

    def add(nodes: list[str], reason: str) -> None:
        for node in sorted(nodes):
            reasons.setdefault(node, reason)

    paths = sorted({path for change in changes.changes for path in (change.path, change.old_path) if path})
    # A rename or copy is one change: it is mapped when either of its paths is.
    partner = {change.path: change.old_path for change in changes.changes if change.old_path}
    partner.update({old: new for new, old in list(partner.items())})
    mapped_paths: set[str] = set()
    unmapped_candidates: list[str] = []
    fallback: list[str] = [] if changes.old_graph else ["old view unavailable"]
    triggers: list[str] = []
    non_prose = False
    for path in paths:
        if _is_prose(path):
            add([node for file, nodes in by_file.items() if _matches(file, manifest.prose_gates) for node in nodes], f"prose: docs gate for {path}")
            for file in _dependents(path, dependencies):
                add(by_file.get(file, []), f"reads {path}")
            # Whole-folder readers read a new document too; the gates among them are the known gates for it.
            for file in _scanners(path, dependencies, through_tools=True):
                add([node for node in by_file.get(file, []) if tiers[node] == "gates"], f"prose: gate scans the folder of {path}")
            continue
        non_prose = True
        broad_path = _matches(path, manifest.broad_paths)
        if broad_path:
            fallback.append(f"broad: {path}")
        mapped = False
        if _is_test_module(path) and path not in dependencies.unparsed:
            add(by_file.get(path, []), f"changed {path}")
            mapped = True
        for rule in manifest.inputs:
            if _matches(path, rule.patterns):
                chosen = [node for node, tier in tiers.items() if tier in rule.tiers]
                chosen += [node for file, nodes in by_file.items() if _matches(file, rule.files) for node in nodes]
                add(chosen, f"input {rule.label} ({path}): {rule.why}")
                mapped = True
        reached = [] if path in dependencies.unparsed else _dependents(path, dependencies)
        for file in reached:
            add(by_file.get(file, []), f"depends on {path}")
        for file in _scanners(path, dependencies):
            add(by_file.get(file, []), f"scans the folder of {path}")
        # Mapped means the change reaches a test: reaching only other sources leaves it untested here.
        reaches_test = any(_is_test_module(file) or file in by_file for file in reached)
        if mapped or reaches_test or broad_path:
            mapped_paths.add(path)
        else:
            unmapped_candidates.append(path)
        if path in dependencies.platform_files or _matches(path, manifest.platform_paths):
            triggers.append(path)
    fallback += [f"unmapped: {path}" for path in unmapped_candidates if partner.get(path) not in mapped_paths]
    broad = bool(fallback)
    gates = [node for node, tier in tiers.items() if tier == "gates"]
    if profile == "checkpoint":
        add(gates, "checkpoint: every gate")
    elif non_prose:
        add(gates, "commit: global gates for a code or data change")
    if broad:
        add([node for node, tier in tiers.items() if tier in {"core", "gates"}], "fallback:broad (" + "; ".join(fallback) + ")")
        triggers.append("fallback:broad")
    if triggers:
        platform_nodes = [node for node, tier in tiers.items() if tier in {"core", "gates"} and "platform" in classification.tags.get(node, ())]
        add(platform_nodes, f"platform trigger: {', '.join(sorted(triggers))}")
    current_audits = [node for node, tier in tiers.items() if tier == "audit-current"]
    if profile == "checkpoint":
        add(current_audits, "checkpoint: full-depth current audit")
    elif profile != "commit":
        for node in current_audits:
            reasons.pop(node, None)
    # R5 after G (accepted at Plan 11.30 Task 4): a commit keeps the current audits a changed input reached (by
    # dependency or declared input; broad fallback adds only core and gates) and runs them at quick depth.
    if profile == "quick":
        for node in [node for node in reasons if tiers.get(node) != "core"]:
            reasons.pop(node)
        if broad:
            add([node for node, tier in tiers.items() if tier == "core"], "fallback:broad (" + "; ".join(fallback) + ")")
    nodes = tuple(sorted(reasons))
    domains: dict[str, str] = {}
    for tier in EXPENSIVE_TIERS:
        members = [node for node in nodes if tiers[node] == tier]
        if members:
            domains[tier] = f"included: {reasons[members[0]]}"
        elif tier == "audit-current" and profile == "quick":
            domains[tier] = "omitted: the quick profile runs core only"
        else:
            domains[tier] = "omitted: no dependency or declared input of this domain changed"
    label = "selected"
    if not changes.changes and profile != "checkpoint":
        label = "no-commit-input" if profile == "commit" else "no-change-input"
    concurrency = tuple(node for node in nodes if "concurrency" in classification.tags.get(node, ())) if profile == "checkpoint" else ()
    real_triggers = tuple(sorted(set(triggers)))
    return Selection(
        profile=profile, label=label, nodes=nodes, reasons={node: reasons[node] for node in nodes},
        fallback=tuple(fallback), platform_triggers=real_triggers, domains=domains,
        obligations=(WSL_OBLIGATION,) if real_triggers and profile == "commit" else (),
        provisional=tuple(changes.provisional), concurrency=concurrency,
        audit_depth="full" if profile == "checkpoint" else "quick" if any(tiers[node] == "audit-current" for node in nodes) else "none",
    )
