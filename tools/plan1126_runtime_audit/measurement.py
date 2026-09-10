"""Execution identity and the fresh-measurement gate for the Plan 11.26 audit.

Three operations are kept apart deliberately, because conflating them is what let a
current measurement be filed as historical evidence:

* **Historical replay** reads and validates sealed observations against their original
  schema and immutable source binding. It runs no current probe, so it needs no
  historical runtime installed -- it makes no new execution claim at all.
* **Fresh measurement** requires an explicit :class:`MeasurementSpecification`, a
  dependency closure validated against its installed-file RECORD *before* anything runs,
  and a :class:`VerifiedExecution` that only :func:`establish_verified_execution` can
  mint. Probes run in a FRESH child interpreter with controlled import roots and a
  private, empty bytecode cache, and the evidence is retained rather than hashed away.
* **Fresh historical measurement** would execute a selected historical revision in a
  matching isolated environment. It is not offered here, and the honest behaviour is to
  refuse rather than substitute the installed current runtime.

Four things this module learned from counterexamples, each of which had beaten an
earlier version of it:

1. **A binding argument is not provenance -- and neither is a generic capability.** A
   structurally valid binding naming a wrong interpreter and a nonexistent module was once
   enough to make the public H5 entry admit 65 probe calls. Probes therefore take a
   :class:`VerifiedExecution`, which cannot be constructed -- only minted by the function
   that performs the verification it attests to. That alone was still not enough: a
   *genuine* context, issued through the documented public issuer from a caller-chosen
   specification binding one unrelated module with no dependencies and no fresh child,
   authorized the same 65 probe calls. A capability that proves *some* verification
   occurred does not prove *the verification this entry requires* occurred. So the issuer
   now takes the entry name, applies that entry's requirements itself, demands a private
   and empty bytecode cache, and stamps both into the context; the consumer re-checks that
   the context it was handed was issued for it and is still open.
2. **A caller-chosen module set binds nothing.** The public H9 child once ran with only a
   harmless reviewer-created module bound and no Redis dependency at all. Each entry now
   declares its own minimum: its product runtime, its bridge, the probe implementation
   that executes, and the dependency closure. A caller may widen that; it cannot narrow it.
3. **A fresh interpreter does not guarantee fresh source.** It will happily read an
   existing ``.pyc``: with a preserved timestamp and an equal-length edit, a child bound
   to the *new* file executed the *old* bytecode. ``-B`` does not help -- it stops
   bytecode being written, not read. The child therefore runs against a private,
   freshly-created and empty ``PYTHONPYCACHEPREFIX``, and refuses to measure at all if
   that prefix is absent or if any bound module was loaded from a cache outside it.
4. **Hashing a dependency describes it; it does not accept or reject it.** Capturing a
   digest and later comparing it with itself detects change *during* the run and nothing
   else. Dependencies are validated against their RECORD hashes before capture, so a file
   already modified, or already missing, is refused rather than fingerprinted.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping

from .source import (
    ExecutingSourceMismatch,
    GitCommitSource,
    SourceTree,
    executing_module_digest,
    source_fingerprint,
    verify_executing_module,
)

#: Bounded so a wedged child cannot hang an audit run.
FRESH_MEASUREMENT_TIMEOUT_SECONDS = 1800.0

#: The environment variable the child's bytecode-cache defence depends on.
CACHE_PREFIX_VARIABLE = "PYTHONPYCACHEPREFIX"

#: This module lives at <repository>/tools/plan1126_runtime_audit/measurement.py, so the
#: repository root is derivable rather than something a caller has to supply correctly.
#: The issuer needs it to admit the audit's own probe modules as an import root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9._-]+)")


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _module_name_for(path: str) -> str:
    # A package's `__init__.py` is imported under the package name; without this a probe
    # that executes package-level code could not be bound at all.
    dotted = path.removesuffix(".py").replace("/", ".").removeprefix("src.")
    return dotted.removesuffix(".__init__")


def _module_for(path: str):
    return importlib.import_module(_module_name_for(path))


@dataclass(frozen=True)
class MeasurementSpecification:
    """What the caller REQUIRES a fresh measurement to run against.

    Supplied before anything executes: it is the standard the environment is held to, not
    a description of whatever happened to be importable. An identity derived from the
    running process could never disagree with that process.

    It is a floor the caller raises, never one it lowers. The entry's own requirements are
    unioned in by :func:`run_child_measurement`, so an entry that measures Redis binds the
    Redis runtime, the bridge, its own probe implementation and the dependency closure
    whether or not the caller listed them.
    """

    #: Module paths whose EXECUTION identity is bound: imported, origin-checked, digested.
    paths: tuple[str, ...]
    #: Every root a bound module may legitimately be imported from.
    import_roots: tuple[str, ...]
    #: Distribution names; each is expanded to its installed closure before verification.
    dependencies: tuple[str, ...]
    #: Fingerprint of the whole MEASURED tree -- the tree the inventory is discovered
    #: from, not of ``paths`` alone.
    source_fingerprint: str

    def __post_init__(self) -> None:
        if not self.paths or len(set(self.paths)) != len(self.paths):
            raise ValueError("measurement specification paths must be nonempty and unique")
        if not self.import_roots or any(not Path(root).is_absolute() for root in self.import_roots):
            raise ValueError("measurement specification import roots must be nonempty and absolute")
        if not _is_hex64(self.source_fingerprint):
            raise ValueError("measurement specification source fingerprint is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "paths": list(self.paths),
            "import_roots": list(self.import_roots),
            "dependencies": list(self.dependencies),
            "source_fingerprint": self.source_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MeasurementSpecification:
        return cls(
            paths=tuple(payload["paths"]),
            import_roots=tuple(payload["import_roots"]),
            dependencies=tuple(payload["dependencies"]),
            source_fingerprint=payload["source_fingerprint"],
        )

    def widened(
        self,
        *,
        paths: tuple[str, ...] = (),
        import_roots: tuple[str, ...] = (),
        dependencies: tuple[str, ...] = (),
    ) -> "MeasurementSpecification":
        """Return this specification widened to at least the supplied requirements."""
        return MeasurementSpecification(
            paths=tuple(sorted(set(self.paths) | set(paths))),
            import_roots=tuple(dict.fromkeys((*self.import_roots, *import_roots))),
            dependencies=tuple(sorted(set(self.dependencies) | set(dependencies))),
            source_fingerprint=self.source_fingerprint,
        )


@dataclass(frozen=True)
class EnvironmentBinding:
    """The environment a measurement actually executed in, verified against a spec.

    Deliberately stronger than a process label: ``CPython 3.14`` says nothing about which
    interpreter, which virtual environment, where each module was imported from, or
    whether a same-version dependency had its installed files edited.
    """

    interpreter_executable: str
    interpreter_version: str
    prefix: str
    source_fingerprint: str
    module_origins: tuple[tuple[str, str, str], ...]
    dependency_files: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        for name in ("interpreter_executable", "interpreter_version", "prefix"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"environment binding {name} is missing")
        if not _is_hex64(self.source_fingerprint):
            raise ValueError("environment binding source fingerprint is invalid")
        if not self.module_origins:
            raise ValueError("an environment binding must bind at least one executing module")
        seen: set[str] = set()
        for row in self.module_origins:
            if len(row) != 3:
                raise ValueError("module origin rows must be (path, origin, digest)")
            path, origin, digest = row
            if not isinstance(path, str) or not path or path in seen:
                raise ValueError("module origin paths must be unique and nonempty")
            seen.add(path)
            if not isinstance(origin, str) or not Path(origin).is_absolute():
                raise ValueError(f"module origin for {path!r} must be an absolute resolved path")
            if not _is_hex64(digest):
                raise ValueError(f"module digest for {path!r} is invalid")
        for row in self.dependency_files:
            if len(row) != 2 or not isinstance(row[0], str) or not row[0] or not _is_hex64(row[1]):
                raise ValueError("dependency rows must be (name, 64-hex content digest)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "interpreter_executable": self.interpreter_executable,
            "interpreter_version": self.interpreter_version,
            "prefix": self.prefix,
            "source_fingerprint": self.source_fingerprint,
            "module_origins": [list(row) for row in self.module_origins],
            "dependency_files": [list(row) for row in self.dependency_files],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentBinding":
        expected = {
            "interpreter_executable", "interpreter_version", "prefix",
            "source_fingerprint", "module_origins", "dependency_files",
        }
        if set(payload) != expected:
            raise ValueError("environment binding fields do not match the canonical schema")
        return cls(
            interpreter_executable=payload["interpreter_executable"],
            interpreter_version=payload["interpreter_version"],
            prefix=payload["prefix"],
            source_fingerprint=payload["source_fingerprint"],
            module_origins=tuple(tuple(row) for row in payload["module_origins"]),
            dependency_files=tuple(tuple(row) for row in payload["dependency_files"]),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _recorded_sha256(field: str) -> str | None:
    """The sha256 a RECORD row claims for one installed file, as lowercase hex."""
    if not field.startswith("sha256="):
        return None
    encoded = field.removeprefix("sha256=")
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(padded).hex()
    except (ValueError, binascii.Error):
        return None


def distribution_closure(name: str) -> tuple[str, ...]:
    """The named distribution plus every INSTALLED distribution it requires.

    The named distribution must be installed; a measurement that cannot establish its
    identity is refused, not downgraded. Transitive requirements are conditional by
    nature -- extras and environment markers -- so an absent one is genuinely not part of
    this environment and is skipped rather than reported as damage.
    """
    order: list[str] = []
    seen: set[str] = set()
    queue: list[tuple[str, bool]] = [(name, True)]
    while queue:
        current, required = queue.pop(0)
        key = current.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            dist = metadata.distribution(current)
        except metadata.PackageNotFoundError as exc:
            if required:
                raise ExecutingSourceMismatch(
                    f"dependency {current!r} is not installed, so the measurement identity "
                    "cannot be established"
                ) from exc
            continue
        order.append(dist.metadata["Name"] or current)
        for requirement in dist.requires or []:
            if "extra ==" in requirement:
                continue
            matched = _REQUIREMENT_NAME.match(requirement)
            if matched:
                queue.append((matched.group(1), False))
    return tuple(sorted(set(order), key=str.lower))


def verify_dependency_integrity(name: str) -> str:
    """Validate a distribution's installed files against RECORD, then bind their content.

    Rejection, not description. A required file that is missing, or whose bytes disagree
    with RECORD, fails here -- before any probe runs -- rather than being folded into a
    digest that only proves the damage stayed constant during the run.
    """
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError as exc:
        raise ExecutingSourceMismatch(
            f"dependency {name!r} is not installed, so the measurement identity cannot be established"
        ) from exc
    # RECORD is parsed directly rather than iterated through `metadata.files()`, which
    # silently OMITS rows whose file is absent -- so a deleted installed file would never
    # be reached by the missing-file check below. A control that deleted one proved it.
    manifest = dist.read_text("RECORD")
    if not manifest:
        raise ExecutingSourceMismatch(
            f"dependency {name!r} publishes no RECORD manifest, so its installed files cannot be validated"
        )

    digest = hashlib.sha256()
    checked = 0
    for row in sorted(csv.reader(manifest.splitlines()), key=lambda item: item[0] if item else ""):
        if not row:
            continue
        relative = row[0].replace("\\", "/")
        if relative.endswith(".pyc") or "__pycache__" in relative:
            continue
        recorded = _recorded_sha256(row[1] if len(row) > 1 else "")
        if recorded is None:
            continue
        located = Path(dist.locate_file(relative))
        if not located.is_file():
            raise ExecutingSourceMismatch(
                f"dependency {name!r} is missing the installed file {relative!r} that its RECORD "
                "requires; the installed distribution is not the one this measurement would bind"
            )
        actual = hashlib.sha256(located.read_bytes()).hexdigest()
        if actual != recorded:
            raise ExecutingSourceMismatch(
                f"dependency {name!r} installed file {relative!r} does not match its RECORD hash; "
                "the installed distribution has been modified"
            )
        checked += 1
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(actual.encode("ascii"))
        digest.update(b"\0")
    if not checked:
        raise ExecutingSourceMismatch(
            f"dependency {name!r} has no RECORD hashes to verify, so its integrity cannot be established"
        )
    return digest.hexdigest()


class _Mint:
    """A single-use authorization to build one context.

    A shared module-level sentinel was not enough: ``dataclasses.replace`` carries it into
    a copy, so a context issued for one entry could be re-badged for another through a
    documented public API. A token is issued per context and consumed when that context is
    built, so the copy has nothing left to present.
    """

    __slots__ = ("claimed",)

    def __init__(self) -> None:
        self.claimed = False


class _ExecutionWindow:
    """The lifetime of one measurement, so a context cannot outlive the run that issued it."""

    __slots__ = ("open",)

    def __init__(self) -> None:
        self.open = True


def current_bytecode_cache() -> str:
    """The private, empty bytecode cache THIS interpreter started with, or a refusal.

    ``sys.pycache_prefix`` is populated from ``PYTHONPYCACHEPREFIX`` at interpreter
    startup, so it is a statement about how this process began rather than about a value
    a caller passed in afterwards. Together with ``sys.dont_write_bytecode`` and an empty
    prefix directory it establishes the condition the measurement depends on: no cached
    bytecode from any earlier compilation is reachable, and none accumulates during the
    run.

    This is a correctness contract across the supplied public APIs, not a security
    boundary against code that rewrites interpreter internals.
    """
    prefix = sys.pycache_prefix
    if not prefix:
        raise ExecutingSourceMismatch(
            "this interpreter did not start with a private bytecode cache, so a measurement "
            "taken here could execute cached bytecode compiled from source that no longer "
            "exists; run the measurement through run_fresh_measurement()"
        )
    directory = Path(prefix)
    if not directory.is_dir():
        raise ExecutingSourceMismatch(
            f"the declared private bytecode cache {prefix!r} is not a directory"
        )
    if not sys.dont_write_bytecode:
        raise ExecutingSourceMismatch(
            "this interpreter writes bytecode, so its private cache does not stay empty and "
            "cannot establish that every measured module was compiled from verified source"
        )
    existing = next(directory.rglob("*.pyc"), None)
    if existing is not None:
        raise ExecutingSourceMismatch(
            f"the private bytecode cache already holds compiled bytecode ({existing}); a fresh "
            "measurement requires a cache no earlier compilation could have populated"
        )
    return str(directory.resolve())


@dataclass(frozen=True)
class VerifiedExecution:
    """Proof that THIS process performed the verification a NAMED entry requires.

    A probe entry takes one of these, never a bare :class:`EnvironmentBinding`: a binding
    is data a caller can invent, while this can only be obtained by passing the
    verification. But an unscoped capability is barely better than a binding -- a genuine
    context issued for a caller-chosen module set authorized H5's probes without binding
    the Redis runtime, the bridge, the probe implementation or any dependency at all.

    So the context records **which entry it was issued for** and **the private bytecode
    cache it was issued under**, and it lives only as long as the measurement that issued
    it. :meth:`authorizes` re-checks all three at the consumer, which is what makes this
    a scope rather than a badge.
    """

    binding: EnvironmentBinding
    specification: MeasurementSpecification
    #: The allowlisted entry this context authorizes, and nothing else.
    entry: str
    #: The private bytecode cache this interpreter started with when the context was issued.
    cache_prefix: str
    _mint: Any = None
    _window: Any = None

    def __post_init__(self) -> None:
        token = self._mint
        if not isinstance(token, _Mint) or token.claimed:
            raise ExecutingSourceMismatch(
                "a verified execution context cannot be constructed directly, nor copied into a "
                "different shape; obtain one from establish_verified_execution(), which performs "
                "the verification it attests to"
            )
        token.claimed = True

    def matches(self, source: SourceTree | GitCommitSource) -> bool:
        return source_fingerprint(source, source.paths()) == self.binding.source_fingerprint

    def close(self) -> None:
        """End the measurement window, so the context cannot authorize a later run."""
        if self._window is not None:
            self._window.open = False

    def authorizes(self, entry: str) -> None:
        """Refuse unless this context was issued FOR ``entry`` and is still live.

        Type and source fingerprints were never enough: they say the object is genuine and
        describes the same tree, not that the verification behind it covered what this
        entry executes.
        """
        from .registry import entry_requirements

        if self._window is None or not self._window.open:
            raise ExecutingSourceMismatch(
                f"the measurement window that issued this context has closed, so it no longer "
                f"authorizes {entry!r}; issue a context inside the measurement that uses it"
            )
        if self.entry != entry:
            raise ExecutingSourceMismatch(
                f"this context was issued for {self.entry!r} and does not authorize {entry!r}; "
                "an entry is authorized by the verification its own requirements demand"
            )
        requirements = entry_requirements(entry)
        covered = {path for path, _, _ in self.binding.module_origins}
        missing = sorted(set(requirements.paths) - covered)
        if missing:
            raise ExecutingSourceMismatch(
                f"this context does not bind the modules {entry!r} executes: {missing}"
            )
        absent = sorted(set(requirements.dependencies) - {name for name, _ in self.binding.dependency_files})
        if absent:
            raise ExecutingSourceMismatch(
                f"this context does not bind the dependencies {entry!r} executes: {absent}"
            )
        prefix = sys.pycache_prefix
        if not prefix or self.cache_prefix != str(Path(prefix).resolve()):
            raise ExecutingSourceMismatch(
                "this context was issued under a different bytecode cache than the interpreter "
                "now running, so its freshness claim does not describe this execution"
            )


def _verify_no_foreign_bytecode(path: str, module: object, cache_prefix: str | None) -> None:
    """Refuse a module that was loaded from a bytecode cache we did not create.

    A fresh process defeats a stale *parent import*; it does not defeat a stale ``.pyc``.
    The parent creates an empty cache prefix for every measurement, so nothing cached can
    be reached -- and this check refuses rather than trusts, so removing the prefix breaks
    the measurement instead of silently weakening it.
    """
    if cache_prefix is None:
        return
    cached = getattr(module, "__cached__", None)
    if cached is None:
        return
    resolved = Path(cached)
    if not resolved.exists():
        return
    if not resolved.resolve().is_relative_to(Path(cache_prefix).resolve()):
        raise ExecutingSourceMismatch(
            f"{path}: the executing module was loaded from the bytecode cache {resolved}, which is "
            "outside this measurement's private cache; cached bytecode can execute source that no "
            "longer exists on disk, so the binding would attest to a file that never ran"
        )


def capture_environment_binding(
    *,
    measured: "SourceTree | GitCommitSource",
    identity: "SourceTree | GitCommitSource",
    spec: MeasurementSpecification,
    cache_prefix: str | None,
) -> EnvironmentBinding:
    """Capture and CHECK the environment against ``spec`` before anything is measured.

    ``measured`` is the tree the inventory is discovered from and the tree the binding's
    fingerprint names. ``identity`` supplies the bound text for every module in
    ``spec.paths`` -- product modules and the audit's own probe implementations alike, so
    the evidence names the exact probe code that ran, not only the code it measured.

    ``cache_prefix`` has no default on purpose. Passing ``None`` turns the foreign-bytecode
    refusal below into a no-op, and a defaulted no-op is invisible at the call site. This
    function produces a binding, which authorizes nothing on its own; the authorization
    path is :func:`establish_verified_execution`, which always passes a real prefix.
    """
    roots = [Path(root).resolve() for root in spec.import_roots]
    origins: list[tuple[str, str, str]] = []
    for path in sorted(spec.paths):
        module = _module_for(path)
        origin = getattr(module, "__file__", None)
        if origin is None:
            raise ExecutingSourceMismatch(f"{path}: the executing module exposes no __file__")
        resolved = Path(origin).resolve()
        if not any(resolved.is_relative_to(root) for root in roots):
            raise ExecutingSourceMismatch(
                f"{path}: executing module {resolved} is outside every declared import root"
            )
        _verify_no_foreign_bytecode(path, module, cache_prefix)
        verify_executing_module(identity, path, module)
        origins.append((path, str(resolved), executing_module_digest(module)))

    # RECORD-validated BEFORE capture: a distribution already modified, or already
    # missing a file it declares, is refused here rather than fingerprinted and carried
    # into the evidence as though it were intact.
    dependencies = [(name, verify_dependency_integrity(name)) for name in sorted(spec.dependencies)]

    binding = EnvironmentBinding(
        interpreter_executable=str(Path(sys.executable).resolve()),
        interpreter_version=sys.version,
        prefix=str(Path(sys.prefix).resolve()),
        source_fingerprint=source_fingerprint(measured, measured.paths()),
        module_origins=tuple(origins),
        dependency_files=tuple(dependencies),
    )
    verify_environment_binding(binding, spec)
    return binding


def establish_verified_execution(
    *,
    entry: str,
    measured: "SourceTree | GitCommitSource",
    identity: "SourceTree | GitCommitSource",
    spec: MeasurementSpecification,
) -> VerifiedExecution:
    """The ONLY way to obtain a context the probe entries will accept, scoped to ``entry``.

    ``entry`` is required, and the caller's specification is a floor RAISED here rather
    than downstream: the entry's own runtime, bridge, probe implementation and installed
    dependency closure are unioned in before anything is verified. That is the difference
    between a context that proves some verification happened and one that proves the
    verification this entry requires happened -- and a caller-chosen specification bought
    65 H5 probe calls while that widening lived only in the child bootstrap.

    The fresh-execution condition is checked here too, so there is no route to an
    authorizing context outside a measurement child.
    """
    from .registry import entry_requirements

    requirements = entry_requirements(entry)
    cache_prefix = current_bytecode_cache()
    scoped = spec.widened(
        paths=requirements.paths,
        import_roots=(str(REPOSITORY_ROOT),),
        dependencies=requirements.dependencies,
    )
    binding = capture_environment_binding(
        measured=measured, identity=identity, spec=scoped, cache_prefix=cache_prefix
    )
    execution = VerifiedExecution(binding, scoped, entry, cache_prefix, _Mint(), _ExecutionWindow())
    execution.authorizes(entry)
    return execution


def verify_environment_binding(binding: EnvironmentBinding, spec: MeasurementSpecification) -> None:
    """Re-verify a binding against its spec AND against the live environment."""
    if binding.source_fingerprint != spec.source_fingerprint:
        raise ExecutingSourceMismatch("the environment binding does not match the requested source fingerprint")
    if tuple(path for path, _, _ in binding.module_origins) != tuple(sorted(spec.paths)):
        raise ExecutingSourceMismatch("the environment binding does not cover exactly the specified modules")
    if tuple(name for name, _ in binding.dependency_files) != tuple(sorted(spec.dependencies)):
        raise ExecutingSourceMismatch("the environment binding does not cover exactly the specified dependencies")
    if binding.interpreter_executable != str(Path(sys.executable).resolve()):
        raise ExecutingSourceMismatch("the environment binding names a different interpreter than the running one")
    if binding.interpreter_version != sys.version:
        raise ExecutingSourceMismatch("the environment binding names a different interpreter version")
    if binding.prefix != str(Path(sys.prefix).resolve()):
        raise ExecutingSourceMismatch("the environment binding names a different interpreter prefix")
    for path, origin, digest in binding.module_origins:
        module = _module_for(path)
        actual_origin = getattr(module, "__file__", None)
        if actual_origin is None or str(Path(actual_origin).resolve()) != origin:
            raise ExecutingSourceMismatch(f"{path}: the executing module origin changed")
        if executing_module_digest(module) != digest:
            raise ExecutingSourceMismatch(
                f"{path}: the executing module changed during the measurement; "
                "the result is not bound to a single revision"
            )
    for name, digest in binding.dependency_files:
        if verify_dependency_integrity(name) != digest:
            raise ExecutingSourceMismatch(f"dependency {name!r} installed files changed during the measurement")


class ExecutionClosureRecorder:
    """What a measurement ACTUALLY executed: product files and installed distributions.

    Seam 2, checkpoint B (round 2, R3). A registry entry declares the modules and
    distributions it binds, and the issuer refuses a context that does not cover them --
    but a declaration is only as good as its author's enumeration. The reviewer traced
    nine executing product files outside S1's declared floor. This recorder observes the
    real closure from inside the measurement, on every thread started while it is armed
    (``threading.setprofile`` covers the owner and executor threads a scenario starts),
    and :func:`verify_execution_closure` refuses the measurement when anything executed
    is not in the binding. The declaration is a floor; this is the check that it was not
    lowered below what ran.
    """

    def __init__(self, repository_root: "str | Path") -> None:
        import sysconfig
        import threading

        self._root = Path(repository_root).resolve()
        self._site = Path(sysconfig.get_paths()["purelib"]).resolve()
        self._threading = threading
        self.product_files: set[str] = set()
        self.site_top_levels: set[str] = set()
        self._previous = None

    def _profile(self, frame, event, arg):
        if event != "call":
            return
        filename = frame.f_code.co_filename
        if not filename or filename.startswith("<"):
            return
        path = Path(filename)
        if not path.is_absolute():
            return
        # Site-packages FIRST: a lane venv usually lives inside the checkout, so a root-first
        # test would swallow every installed module as "under the repository" and record
        # no distribution at all.
        if path.is_relative_to(self._site):
            parts = path.relative_to(self._site).parts
            if parts and not parts[0].endswith((".dist-info", ".pth")):
                top = parts[0][:-3] if len(parts) == 1 and parts[0].endswith(".py") else parts[0]
                self.site_top_levels.add(top)
            return
        if path.is_relative_to(self._root):
            relative = path.relative_to(self._root).as_posix()
            if relative.startswith(("src/", "tools/")) and relative.endswith(".py"):
                self.product_files.add(relative)

    def __enter__(self) -> "ExecutionClosureRecorder":
        self._previous = sys.getprofile()
        sys.setprofile(self._profile)
        self._threading.setprofile(self._profile)
        return self

    def __exit__(self, *exc_info) -> None:
        sys.setprofile(self._previous)
        self._threading.setprofile(None)


def _canonical_distribution(name: str) -> str:
    return name.lower().replace("_", "-")


def executed_distributions(top_levels: "set[str]") -> "set[str]":
    """Map executed site-packages top levels to installed distribution names."""
    from importlib.metadata import packages_distributions

    mapping = packages_distributions()
    found: set[str] = set()
    for top in top_levels:
        for distribution in mapping.get(top, ()):
            found.add(_canonical_distribution(distribution))
    return found


def verify_execution_closure(recorder: ExecutionClosureRecorder, binding: "EnvironmentBinding") -> None:
    """Refuse a measurement that executed anything its binding does not cover."""
    bound_paths = {path for path, _, _ in binding.module_origins}
    missing_paths = sorted(recorder.product_files - bound_paths)
    if missing_paths:
        raise ExecutingSourceMismatch(
            "the measurement executed product files its binding does not cover, so its identity "
            f"claim is incomplete: {missing_paths}"
        )
    bound_distributions = {_canonical_distribution(name) for name, _ in binding.dependency_files}
    missing_distributions = sorted(executed_distributions(recorder.site_top_levels) - bound_distributions)
    if missing_distributions:
        raise ExecutingSourceMismatch(
            "the measurement executed installed distributions its binding does not cover: "
            f"{missing_distributions}"
        )


def fresh_child_environment(cache_directory: "str | Path") -> dict[str, str]:
    """The environment every measurement child runs in.

    ``PYTHONPYCACHEPREFIX`` points at a freshly created, EMPTY directory, so the child
    cannot reach any pre-existing ``.pyc``: with a preserved timestamp and an
    equal-length edit, a child bound to the new file otherwise executes the old bytecode.
    ``-B`` does not fix that -- it prevents bytecode being written, not read.
    """
    return {
        **os.environ,
        CACHE_PREFIX_VARIABLE: str(cache_directory),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


_CHILD = r"""
import json, sys
payload = json.loads(sys.stdin.read())
# Controlled import roots, placed FIRST; the standard library and this environment's own
# site paths stay reachable, because an interpreter that cannot import `__future__` is
# unusable rather than controlled. `capture_environment_binding` then refuses any measured
# module whose origin falls outside a declared root. This is a FRESH process, so no MEASURED
# module can have been imported before this bootstrap -- the interpreter's own startup
# imports run first, and that is not a claim this makes about the measured modules. With an
# empty private bytecode cache, no existing .pyc is reachable either.
sys.path[:0] = [payload["repository_root"], *payload["spec"]["import_roots"]]
from tools.plan1126_runtime_audit.measurement import run_child_measurement
sys.stdout.write(json.dumps(run_child_measurement(payload)))
"""


def run_child_measurement(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Executed INSIDE the fresh child: widen the spec, verify identity, then measure."""
    from .registry import resolve_measurement_entry

    cache_prefix = os.environ.get(CACHE_PREFIX_VARIABLE)
    if not cache_prefix or not Path(cache_prefix).is_dir():
        raise ExecutingSourceMismatch(
            "the measurement child has no private bytecode cache, so it could execute cached "
            "bytecode compiled from source that no longer exists; refusing to measure"
        )
    del cache_prefix  # established again, and enforced, by the issuer below
    measured = SourceTree(payload["source_files"])
    # What the measurement MEASURES is a floor too. The entry re-discovers its inventory
    # from this tree, so a caller passing a truncated one would produce a smaller contract
    # that is internally consistent and quietly incomplete.
    from .registry import entry_source_paths

    absent = sorted(set(entry_source_paths(payload["entry"])) - set(measured.paths()))
    if absent:
        raise ExecutingSourceMismatch(
            f"the measured tree omits paths {payload['entry']!r} discovers its contract from: {absent}"
        )
    identity = SourceTree(payload["identity_files"])
    # The issuer applies this entry's requirements; the bootstrap deliberately no longer
    # does, so the widening cannot be true here and absent on the public route.
    execution = establish_verified_execution(
        entry=payload["entry"],
        measured=measured,
        identity=identity,
        spec=MeasurementSpecification.from_dict(payload["spec"]),
    )
    try:
        entry = resolve_measurement_entry(payload["entry"])
        result = entry(source=measured, execution=execution, options=payload.get("options", {}))
    finally:
        # The context authorizes THIS measurement and nothing after it.
        execution.close()
    # Re-verified AFTER the probes: an installed file edited mid-run must not pass merely
    # because it happened to be intact when the binding was captured.
    verify_environment_binding(execution.binding, execution.specification)
    return {
        "binding": execution.binding.to_dict(),
        "specification": execution.specification.to_dict(),
        "result": result,
    }


def _locate_identity_text(path: str, roots: tuple[Path, ...]) -> str:
    for root in roots:
        candidate = root / path
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise ExecutingSourceMismatch(
        f"{path}: no declared import root holds this bound module, so its executing identity "
        "cannot be established"
    )


def run_fresh_measurement(
    *,
    source: SourceTree,
    spec: MeasurementSpecification,
    entry: str,
    options: Mapping[str, Any] | None = None,
    repository_root: "str | Path",
) -> tuple[EnvironmentBinding, Any]:
    """Run a measurement in a FRESH child interpreter and return its verified binding.

    An identity that cannot be established is a hard failure before any probe runs: there
    is no unbound path and no downgrade to a skip or a recorded ``probe_error``.
    """
    from .registry import entry_requirements

    root = Path(repository_root).resolve()
    requirements = entry_requirements(entry)
    roots = (*(Path(item).resolve() for item in spec.import_roots), root)
    source_files = {path: source.read_text(path) for path in source.paths()}
    identity_files = dict(source_files)
    for path in sorted(set(spec.paths) | set(requirements.paths)):
        if path not in identity_files:
            identity_files[path] = _locate_identity_text(path, roots)

    payload = {
        "spec": spec.to_dict(),
        # The WHOLE measured tree: the child discovers its inventory from exactly the
        # source this measurement is bound to, not from a subset of it.
        "source_files": source_files,
        # Bound text for every module whose execution is claimed, product and probe alike.
        "identity_files": identity_files,
        "entry": entry,
        "options": dict(options or {}),
        "repository_root": str(root),
    }
    with tempfile.TemporaryDirectory(prefix="plan1126-pycache-") as cache:
        completed = subprocess.run(
            [sys.executable, "-c", _CHILD],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=FRESH_MEASUREMENT_TIMEOUT_SECONDS,
            cwd=str(root),
            env=fresh_child_environment(cache),
        )
    if completed.returncode != 0:
        detail = (completed.stderr.strip().splitlines() or ["<no stderr>"])[-1]
        raise ExecutingSourceMismatch(
            "the fresh measurement child interpreter refused or failed before producing "
            "observations: " + detail
        )
    result = json.loads(completed.stdout)
    binding = EnvironmentBinding.from_dict(result["binding"])
    if binding.source_fingerprint != spec.source_fingerprint:
        raise ExecutingSourceMismatch("the child returned a binding for a different source")
    covered = {path for path, _, _ in binding.module_origins}
    missing = set(requirements.paths) - covered
    if missing:
        raise ExecutingSourceMismatch(
            f"the child returned a binding that omits required modules: {sorted(missing)}"
        )
    absent = set(requirements.dependencies) - {name for name, _ in binding.dependency_files}
    if absent:
        raise ExecutingSourceMismatch(
            f"the child returned a binding that omits required dependencies: {sorted(absent)}"
        )
    return binding, result["result"]
