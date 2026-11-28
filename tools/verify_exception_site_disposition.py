"""Check that the #334 disposition report accounts for the current production exception sites."""

from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.tracked_repository_files import tracked_repository_files

_SCHEMA = "optimus-exception-site-disposition-v1"
# These still-open A2A records retain custody under ADR-022.
_LEDGER_BACKLOG_OWNERS = frozenset({
    "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY",
    "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY",
})
_BROAD = frozenset({"builtins.Exception", "builtins.BaseException", "builtins.ExceptionGroup", "builtins.BaseExceptionGroup"})
_SUPPRESS = "contextlib.suppress"
_AMBIGUOUS = "<unresolved binding>"
# Class decorators trusted to return a distinct class, by resolved name (compared as a one-name set).
_DATACLASS = "dataclasses.dataclass"
_FROZEN_EXCEPTION = "optimus.runtime.frozen_exception.frozen_exception"
_TRUSTED = frozenset({_DATACLASS, _FROZEN_EXCEPTION})
_OUTCOMES = frozenset({"retain", "contain", "translate", "report", "re-raise"})
# These external names are narrow exception types at the pinned dependency boundary.
_EXTERNAL_EXCEPTIONS = frozenset("""
asyncio.CancelledError asyncio.TimeoutError binascii.Error concurrent.futures.CancelledError
concurrent.futures.InvalidStateError decimal.InvalidOperation defusedxml.ElementTree.ParseError
defusedxml.common.DefusedXmlException http.client.HTTPException importlib.metadata.PackageNotFoundError
json.JSONDecodeError keyring.errors.NoKeyringError PIL.Image.DecompressionBombError PIL.UnidentifiedImageError
psycopg.Error psycopg.OperationalError psycopg.errors.LockNotAvailable psycopg.errors.QueryCanceled
pydantic.ValidationError queue.Empty queue.Full redis.exceptions.ConnectionError
redis.exceptions.OutOfMemoryError redis.exceptions.RedisError redis.exceptions.ResponseError
redis.exceptions.TimeoutError redis.exceptions.WatchError subprocess.CalledProcessError
subprocess.TimeoutExpired tomllib.TOMLDecodeError urllib.error.HTTPError urllib.error.URLError
yaml.YAMLError zoneinfo.ZoneInfoNotFoundError
""".split())
_BUILTIN_EXCEPTIONS = frozenset(
    f"builtins.{name}" for name, value in vars(builtins).items()
    if isinstance(value, type) and issubclass(value, BaseException)
)
Lint = tuple[str, int, int, str, bool]


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_id(digest: str) -> str:
    return f"sha256:{digest}"


@dataclass(eq=False)
class Scope:
    name: str
    package: str
    parent: Scope | None = None
    is_class: bool = False
    bindings: dict[str, list[str | ast.expr | None]] = field(default_factory=lambda: defaultdict(list))
    dynamic: bool = False


@dataclass
class Candidate:
    scope: Scope
    kind: str
    node: ast.ExceptHandler | ast.Call
    owner: ast.Try | ast.TryStar | ast.With | ast.AsyncWith
    caught: tuple[ast.expr, ...]


class Collect(ast.NodeVisitor):
    """Collect lexical bindings and source locations before performing discovery."""

    def __init__(self, module: Scope, classes: set[str]) -> None:
        self.scope = self.module = module
        self.classes = classes
        self.candidates: list[Candidate] = []
        # Classes whose decorators are judged after every binding in the tree is collected (#698).
        self.pending: list[tuple[Scope, ast.ClassDef, list[str | ast.expr | None], int]] = []
        # Attribute writes as (scope, target, attribute name or None when computed, line) (#697).
        self.writes: list[tuple[Scope, ast.expr, str | None, int]] = []

    def _bind(self, target: ast.expr, value: str | ast.expr | None) -> None:
        if isinstance(target, ast.Name):
            self.scope.bindings[target.id].append(value)
        else:
            self.visit(target)

    def visit_Import(self, node: ast.Import) -> None:
        for name in node.names:
            key = name.asname or name.name.split(".")[0]
            self.scope.bindings[key].append(name.name if name.asname else key)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        package = self.scope.package.split(".") if self.scope.package else []
        if node.level:
            parent = package[:len(package) - node.level + 1] if len(package) >= node.level else []
            prefix = ".".join([*parent, *([node.module] if node.module else [])])
        else:
            prefix = node.module or ""
        for name in node.names:
            if name.name == "*":
                self.scope.dynamic = True
            else:
                self.scope.bindings[name.asname or name.name].append(".".join(filter(None, (prefix, name.name))))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind(target, node.value)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._bind(node.target, node.value)
        if node.value is not None:
            self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind(node.target, node.value)
        self.visit(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.scope.bindings[node.id].append(None)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self.module.bindings[name].append(None)
            self.scope.bindings[name].append(None)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self.scope.bindings[name].append(None)
            outer = self.scope.parent
            while outer is not None:
                outer.bindings[name].append(None)
                outer = outer.parent

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.writes.append((self.scope, node.value, node.attr, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "exec":
            self.scope.dynamic = True
        if isinstance(node.func, ast.Name) and node.func.id in ("setattr", "delattr") and node.args:
            name = node.args[1] if len(node.args) > 1 else None
            literal = name.value if isinstance(name, ast.Constant) and isinstance(name.value, str) else None
            self.writes.append((self.scope, node.args[0], literal, node.lineno))
        self.generic_visit(node)

    def overwritten(self) -> list[tuple[str, int, str]]:
        """Writes to a trusted name as (name, line, rule).

        The attribute-name rule is deliberately broad: any write of an attribute named like a trusted decorator, on
        any target, untrusts it tree-wide. There is no allowlist; a legitimate attribute with that name is renamed.
        """
        resolve = Resolve({}, set()).expression
        found = []
        for scope, target, attr, line in self.writes:
            for trusted in sorted(_TRUSTED):
                module, _, name = trusted.rpartition(".")
                if attr == name:
                    found.append((trusted, line, f"attribute write named {name}"))
                elif attr is None and module in resolve(target, scope):
                    found.append((trusted, line, f"computed setattr or delattr on {module}"))
        return found

    def trust(self, untrusted: set[str]) -> None:
        """Judge each class's decorators against the enclosing scope's complete bindings."""
        resolve = Resolve({}, set()).expression
        trusted = [{name} for name in _TRUSTED - untrusted]
        for outer, node, slot, index in self.pending:
            # A dataclass decorator (bare or called) preserves a distinct class, and frozen_exception, applied
            # uncalled, returns the class it was given (pinned by test_frozen_exception_returns_the_class_it_decorates).
            # A call of frozen_exception returns whatever it returns. Other decorators can return arbitrary objects.
            if all(
                resolve(item.func, outer) == {_DATACLASS} and _DATACLASS not in untrusted
                if isinstance(item, ast.Call) else resolve(item, outer) in trusted
                for item in node.decorator_list
            ):
                qualified = f"{outer.name}.{node.name}"
                slot[index] = qualified
                self.classes.add(qualified)

    def _visit_body(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, *, is_class: bool
    ) -> None:
        outer = self.scope
        qualified = f"{outer.name}.{node.name}"
        slot = outer.bindings[node.name]
        slot.append(None)
        # A custom metaclass can return an arbitrary object, so a class with keywords stays unresolved.
        if isinstance(node, ast.ClassDef) and not node.keywords:
            self.pending.append((outer, node, slot, len(slot) - 1))
        parent = outer.parent if outer.is_class else outer
        self.scope = Scope(qualified, outer.package, parent, is_class)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for argument in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                if argument is not None:
                    self.scope.bindings[argument.arg].append(None)
        for item in node.body:
            self.visit(item)
        self.scope = outer

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._visit_body(node, is_class=False)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_body(node, is_class=True)

    def visit_Try(self, node: ast.Try | ast.TryStar) -> None:
        for handler in node.handlers:
            if handler.name:
                self.scope.bindings[handler.name].append(None)
            kind = "except_star" if isinstance(node, ast.TryStar) else "except"
            self.candidates.append(Candidate(self.scope, kind, handler, node, (handler.type,) if handler.type else ()))
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            if isinstance(item.context_expr, ast.Call):
                value = item.context_expr
                self.candidates.append(Candidate(self.scope, "suppress", value, node, tuple(value.args)))
        self.generic_visit(node)

    visit_AsyncWith = visit_With


# Out of reach by design: the verifier sees only tracked src files and these forms of decorator overwrite.
# - writes from outside src (tests, plugins, sitecustomize, interpreter startup);
# - vars(m)[...], m.__dict__[...], globals()[...], object.__setattr__(m, ...), m.__setattr__(...);
# - an aliased setattr (s = setattr), or a computed-name setattr on a target that does not resolve to the module;
# - eval, an aliased exec, importlib.reload. A bare exec call or a star import already makes its scope dynamic.
class Resolve:
    def __init__(self, modules: Mapping[str, Scope], classes: set[str]) -> None:
        self.modules = modules
        self.classes = classes

    def _qualified(self, value: str, seen: frozenset[tuple[Scope, str]]) -> frozenset[str]:
        module_name, _, name = value.rpartition(".")
        module = self.modules.get(module_name)
        if value in self.classes or module is None or name not in module.bindings:
            return frozenset({value})
        return self.name(name, module, seen)

    def name(
        self, name: str, scope: Scope, seen: frozenset[tuple[Scope, str]] = frozenset(),
    ) -> frozenset[str]:
        token = scope, name
        if scope.dynamic or token in seen:
            return frozenset()
        choices = scope.bindings.get(name)
        if choices is None:
            if scope.parent is not None:
                return self.name(name, scope.parent, seen)
            value = f"builtins.{name}"
            return frozenset({value}) if value in _BUILTIN_EXCEPTIONS else frozenset()
        result = {
            self._qualified(item, seen | {token}) if isinstance(item, str)
            else self.expression(item, scope, seen | {token})
            for item in choices
        }
        if len(result) != 1:
            return frozenset({_AMBIGUOUS}).union(*result)
        resolved = result.pop()
        if scope.parent is None and f"builtins.{name}" in _BROAD and resolved != {f"builtins.{name}"}:
            # Module-level rebinding is order-sensitive. A prior use can still see the builtin.
            return frozenset()
        return resolved

    def expression(
        self, node: ast.expr | None, scope: Scope, seen: frozenset[tuple[Scope, str]] = frozenset(),
    ) -> frozenset[str]:
        if isinstance(node, ast.Name):
            return self.name(node.id, scope, seen)
        if isinstance(node, ast.Attribute):
            values = self.expression(node.value, scope, seen)
            return frozenset().union(*(self._qualified(f"{value}.{node.attr}", seen) for value in values))
        if isinstance(node, ast.Tuple):
            members = [self.expression(item, scope, seen) for item in node.elts]
            return frozenset().union(*(item or frozenset({_AMBIGUOUS}) for item in members))
        if isinstance(node, ast.NamedExpr):
            return self.expression(node.value, scope, seen)
        if isinstance(node, ast.IfExp):
            one = self.expression(node.body, scope, seen)
            other = self.expression(node.orelse, scope, seen)
            return one if one == other else one | other | {_AMBIGUOUS}
        return frozenset()

    def classification(self, candidate: Candidate) -> tuple[bool, bool]:
        scope, node, caught = candidate.scope, candidate.node, candidate.caught
        values = [self.expression(item, scope) for item in caught]
        known = _BUILTIN_EXCEPTIONS | _EXTERNAL_EXCEPTIONS | self.classes
        unresolved = any(not value or not value.issubset(known) for value in values)
        broad = any(value & _BROAD for value in values)
        if isinstance(node, ast.ExceptHandler):
            return not caught or broad or unresolved, unresolved
        manager = self.expression(node.func, scope)
        if _SUPPRESS in manager:
            unresolved = unresolved or bool(node.keywords) or manager != {_SUPPRESS}
            return broad or unresolved, unresolved
        # A broad exception argument to an opaque manager can hide indirect suppression.
        if broad or any(isinstance(item, ast.Starred) for item in caught) or "suppress" in ast.unparse(node.func):
            return True, True
        return False, False


def _as_site(
    path: str, candidate: Candidate, occurrences: Counter[tuple[str, str]], unresolved: bool,
) -> dict[str, Any]:
    node = candidate.node
    syntax = [ast.dump(node, include_attributes=False)]
    if isinstance(node, ast.Call):
        syntax.extend(ast.dump(stmt, include_attributes=False) for stmt in candidate.owner.body)
    fingerprint = _digest([candidate.kind, syntax])
    slot = candidate.scope.name, fingerprint
    occurrences[slot] += 1
    occurrence = occurrences[slot]
    return {
        "key": _sha256_id(_digest([path, candidate.scope.name, fingerprint, occurrence])),
        "path": path,
        "symbol": candidate.scope.name,
        "kind": candidate.kind,
        "line": node.lineno,
        "column": node.col_offset + 1,
        "fingerprint": _sha256_id(fingerprint),
        "occurrence": occurrence,
        "caught": ", ".join(ast.unparse(item) for item in candidate.caught) or "bare",
        "unresolved": unresolved,
        "lint": [],
    }


def _lint_owner(
    path: str, candidates: Sequence[Candidate], line: int, column: int, code: str,
) -> int:
    matches = []
    for index, candidate in enumerate(candidates):
        owner = candidate.owner
        if code == "SIM105":
            if isinstance(owner, (ast.Try, ast.TryStar)) and len(owner.handlers) == 1 and line == owner.lineno:
                matches.append(index)
        elif code == "BLE001":
            for expr in candidate.caught:
                start = expr.lineno, expr.col_offset + 1
                end = expr.end_lineno or expr.lineno, (expr.end_col_offset or expr.col_offset) + 1
                if start <= (line, column) <= end:
                    matches.append(index)
                    break
    if len(matches) != 1:
        raise ValueError(f"unbound {code} annotation at {path}:{line}:{column}")
    return matches[0]


def discover(source: Mapping[str, str], lint: Iterable[Lint] = ()) -> dict[str, Any]:
    """Discover from source, independently of any supplied disposition report."""
    modules: dict[str, Scope] = {}
    paths: dict[str, str] = {}
    collectors: dict[str, Collect] = {}
    classes: set[str] = set()
    for path, value in sorted(source.items()):
        module = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        is_package = module.endswith(".__init__")
        if is_package:
            module = module.removesuffix(".__init__")
        scope = Scope(module, module if is_package else module.rpartition(".")[0])
        modules[module] = scope
        paths[module] = path
        collectors[path] = Collect(scope, classes)
        collectors[path].visit(ast.parse(value, filename=path))
    triggers = [
        (path, line, trusted, rule) for path, collector in collectors.items()
        for trusted, line, rule in collector.overwritten()
    ]
    for trusted in sorted(_TRUSTED):
        module_name, _, name = trusted.rpartition(".")
        export = modules.get(module_name)
        # The canonical module must bind its export exactly once, by its def, in a static scope.
        # Bindings carry no line numbers, so these triggers point at line 1 of that module.
        if export is not None and export.dynamic:
            triggers.append((paths[module_name], 1, trusted, "canonical module has a star import or exec"))
        elif export is not None and export.bindings.get(name) != [None]:
            count = len(export.bindings.get(name, []))
            triggers.append((paths[module_name], 1, trusted, f"canonical module binds {name} {count} times, not once by its def"))
    untrusted = {trusted for _, _, trusted, _ in triggers}
    for collector in collectors.values():
        collector.trust(untrusted)
    resolver = Resolve(modules, classes)
    annotations: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for path, line, column, rule, effective in lint:
        if path not in collectors:
            raise ValueError(f"untracked lint input {path}")
        index = _lint_owner(path, collectors[path].candidates, line, column, rule)
        annotations[path, index].append({"code": rule, "effective": effective})
    sites = []
    for path, collector in collectors.items():
        occurrences: Counter[tuple[str, str]] = Counter()
        ordered = sorted(enumerate(collector.candidates), key=lambda item: (item[1].node.lineno, item[1].node.col_offset))
        for index, candidate in ordered:
            selected, unresolved = resolver.classification(candidate)
            flags = annotations[path, index]
            if selected or flags:
                row = _as_site(path, candidate, occurrences, unresolved)
                row["lint"] = sorted(flags, key=lambda flag: (str(flag["code"]), bool(flag["effective"])))
                sites.append(row)
    inventory: dict[str, Any] = {"schema": _SCHEMA, "source_sha256": _sha256_id(_digest(source)), "sites": sites}
    if triggers:
        inventory["untrusted_decorators"] = [
            f"{path}:{line} {trusted}: {rule}" for path, line, trusted, rule in sorted(triggers)
        ]
    return inventory


def _has_owner(row: Mapping[str, Any], path: str) -> bool:
    issue = row.get("owning_issue")
    record = row.get("owning_backlog_record")
    if record is None:
        return type(issue) is int and issue > 0
    return (
        issue is None
        and isinstance(record, str)
        and record in _LEDGER_BACKLOG_OWNERS
        and path.startswith("src/evidence_handoff_runtime/")
    )


def verify_report(inventory: Mapping[str, Any], report: object) -> list[str]:
    if not isinstance(report, dict) or report.get("schema") != _SCHEMA or not isinstance(report.get("sites"), list):
        return ["invalid report schema"]
    # Shown first: one write can untrust a decorator tree-wide and turn many catches unresolved.
    errors = [f"untrusted decorator {trigger}" for trigger in inventory.get("untrusted_decorators", ())]
    for label in ("source_sha256", "config_sha256", "ruff"):
        if inventory.get(label) != report.get(label):
            errors.append(f"{label} differs from fresh discovery")
    expected = {row["key"]: row for row in inventory["sites"]}
    copies: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report["sites"]:
        if isinstance(row, dict) and isinstance(row.get("key"), str):
            copies[row["key"]].append(row)
        else:
            errors.append("invalid disposition row")
    for key in sorted(copies.keys() - expected.keys()):
        errors.append(f"stale {key}")
        if len(copies[key]) > 1:
            errors.append(f"duplicate {key}")
    for key, src in expected.items():
        location = f"{src['path']}:{src['line']}"
        if src["unresolved"]:
            errors.append(f"unresolved {location} {key}")
        if key not in copies:
            errors.append(f"missing {location} {key}")
            continue
        if len(copies[key]) != 1:
            errors.append(f"duplicate {location} {key}")
        row = copies[key][0]
        if any(row.get(field) != value for field, value in src.items()):
            errors.append(f"stale source fields {location} {key}")
        if row.get("review_state") == "pending":
            errors.append(f"pending {location} {key}")
            continue
        if (
            row.get("review_state") != "source_reviewed"
            or not isinstance(row.get("disposition"), str) or row["disposition"] not in _OUTCOMES
            or not _has_owner(row, src["path"])
            or not all(isinstance(row.get(name), str) and row[name].strip() for name in ("rationale", "evidence"))
        ):
            errors.append(f"unreviewed {location} {key}")
    return errors


def _ruff(root: Path, paths: Sequence[str], *, ignore_noqa: bool) -> set[tuple[str, int, int, str]]:
    flags = ["--ignore-noqa"] if ignore_noqa else []
    result = subprocess.run(
        [sys.executable, "-I", "-m", "ruff", "check", "--config", "pyproject.toml", "--select", "BLE001,SIM105",
         "--output-format", "json", *flags, "--", *paths],
        cwd=root, capture_output=True, timeout=60, check=False,
    )
    if result.returncode not in (0, 1):
        raise ValueError(f"Ruff returned {result.returncode}: {result.stderr.decode('utf-8', errors='replace').strip()}")
    return {
        (Path(item["filename"]).resolve().relative_to(root).as_posix(),
         item["location"]["row"], item["location"]["column"], item["code"])
        for item in json.loads(result.stdout)
    }


def _inventory(root: Path) -> dict[str, Any]:
    paths = tracked_repository_files(root, pathspecs=("src",))
    source = {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8") for path in paths if path.suffix == ".py"}
    if not source:
        raise ValueError("the tracked production Python inventory is empty")
    config = _digest([path.read_text(encoding="utf-8") for path in (root / "pyproject.toml", root / "uv.lock")])
    effective = _ruff(root, tuple(source), ignore_noqa=False)
    raw = _ruff(root, tuple(source), ignore_noqa=True)
    if not effective <= raw:
        raise ValueError("effective Ruff findings differ from the unsuppressed source")
    inventory = discover(source, [(*entry, entry in effective) for entry in sorted(raw)])
    verified_paths = tracked_repository_files(root, pathspecs=("src",))
    if paths != verified_paths:
        raise ValueError("tracked production inventory changed during discovery")
    for path, contents in source.items():
        if (root / path).read_text(encoding="utf-8") != contents:
            raise ValueError(f"source changed during discovery: {path}")
    if _digest([path.read_text(encoding="utf-8") for path in (root / "pyproject.toml", root / "uv.lock")]) != config:
        raise ValueError("configuration changed during discovery")
    version = subprocess.check_output([sys.executable, "-I", "-m", "ruff", "--version"], cwd=root, timeout=10).decode().strip()
    return dict(inventory, config_sha256=_sha256_id(config), ruff=version)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--report", type=Path, help="Verify a disposition report against fresh discovery.")
    action.add_argument("--inventory", action="store_true", help="Print a fresh source inventory as JSON.")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        inventory = _inventory(root)
        if args.inventory:
            print(json.dumps(inventory, indent=2, ensure_ascii=True))
            return 0
        report = json.loads(args.report.read_bytes())
        errors = verify_report(inventory, report)
    except (OSError, RuntimeError, SyntaxError, ValueError, subprocess.SubprocessError) as exc:
        print(f"exception-site disposition: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"Verified {len(inventory['sites'])} exception-site dispositions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
