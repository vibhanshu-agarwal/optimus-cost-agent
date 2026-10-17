"""The source-typing exception budget follows accepted Git history, not a resettable list."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import pytest
import yaml

from optimus.guardrails.ci_parity import GuardrailRuleSet
from tests.support import child_tripwire
from tools.tracked_repository_files import (
    COMMIT_INDEX_FILE,
    COMMIT_INDEX_ROOT,
    TrackedFileInventoryError,
    index_environment,
    tracked_repository_files,
)

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_DIGEST = "b6a756129365762efe42c77593313507fd1be1a039a85ef4ebc22490194c5bab"  # pragma: allowlist secret - approved immutable bootstrap SHA-256


def _git(repo: Path, *args: str, index: str | None = None) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("GIT_", "TEST_RUN_COMMIT_"))}
    if index is not None:
        env["GIT_INDEX_FILE"] = index
    result = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, check=False)
    assert result.returncode == 0, f"Git {' '.join(args)} failed: {result.stderr.decode(errors='replace')}"
    return result.stdout


def _mypy_section(config: bytes) -> dict | None:
    try:
        section = tomllib.loads(config.decode("utf-8")).get("tool", {}).get("mypy")
    except (UnicodeError, tomllib.TOMLDecodeError, AttributeError) as exc:
        raise AssertionError(f"Invalid Mypy configuration: {exc}") from exc
    assert section is None or isinstance(section, dict), "Invalid Mypy configuration section"
    return section


def _source_exceptions(config_bytes: bytes) -> frozenset[str]:
    section = _mypy_section(config_bytes)
    assert section is not None, "Missing Mypy configuration"
    assert set(section) == {"files", "python_version", "show_error_codes", "overrides"}, "Unapproved Mypy globals"
    assert section["files"] == ["src"], "Mypy must check all src"
    assert section["python_version"] == "3.14" and section["show_error_codes"] is True, "Changed Mypy checking policy"
    overrides = section["overrides"]
    assert isinstance(overrides, list), "Invalid overrides"
    import_groups = 0
    source_groups = 0
    modules = frozenset()
    for override in overrides:
        assert isinstance(override, dict), "Invalid override"
        if override == {"module": "confusable_homoglyphs", "ignore_missing_imports": True}:
            assert override["ignore_missing_imports"] is True, "Invalid import suppression"
            import_groups += 1
            continue
        assert set(override) == {"module", "ignore_errors"} and override["ignore_errors"] is True, "Unapproved override"
        names = override["module"]
        assert isinstance(names, list) and names, "Source exceptions must be an exact nonempty module list"
        assert all(isinstance(name, str) and re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", name) for name in names), (
            "Source exception patterns are forbidden"
        )
        assert len(set(names)) == len(names), "Duplicate source exception"
        assert "confusable_homoglyphs" not in names, "Third-party import cannot be a source exception"
        modules = frozenset(names)
        source_groups += 1
    assert import_groups == 1 and source_groups <= 1, "Duplicate or missing approved override group"
    return modules


def _assert_ratchet(candidate: bytes, baseline: bytes, *, bootstrap_modules: frozenset[str] | None = None) -> None:
    current = _source_exceptions(candidate)
    previous = _source_exceptions(baseline) if _mypy_section(baseline) is not None else bootstrap_modules
    assert previous is not None, "Missing baseline configuration without approved bootstrap"
    assert current <= previous, f"Mypy source exception set grew: {sorted(current - previous)}"


def _ancestor(repo: Path, older: str, newer: str) -> bool:
    # rev-list membership avoids treating missing objects or Git errors as 'not ancestor'.
    ancestors = _git(repo, "rev-list", newer).decode().splitlines()
    return older in ancestors


def _resolve_baseline(repo: Path, environ: Mapping[str, str]) -> str:
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    ci = environ.get("CI", "").strip().lower() not in {"", "0", "false", "no"} or environ.get("GITHUB_ACTIONS") == "true"
    if not ci:
        print(f"Mypy ratchet context=local baseline={head}")
        return head
    assert environ.get("GITHUB_ACTIONS") == "true", "Unsupported CI baseline context"
    event_name = environ.get("GITHUB_EVENT_NAME")
    assert event_name in {"pull_request", "push"}, f"Unsupported CI event: {event_name}"
    try:
        event = json.loads(Path(environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        if event_name == "pull_request":
            identity = event["pull_request"]["base"]["sha"]
        else:
            assert event["ref"] == "refs/heads/main", "Push baseline must be previous main"
            identity = event["before"]
    except (KeyError, OSError, ValueError, TypeError) as exc:
        raise AssertionError(f"Missing or invalid CI baseline identity: {exc}") from exc
    assert isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{40}", identity) and identity != "0" * 40, (
        "Baseline must be a full nonzero immutable commit SHA"
    )
    resolved = _git(repo, "rev-parse", "--verify", f"{identity}^{{commit}}").decode().strip()
    assert resolved == identity and _ancestor(repo, identity, head), "CI baseline is not an ancestor of checkout"
    if event_name == "pull_request":
        baseline = _git(repo, "merge-base", head, identity).decode().strip()
        assert baseline == identity, "PR checkout does not contain the actual target"
    else:
        assert identity != head, "Push baseline cannot be candidate HEAD"
        parents = _git(repo, "rev-list", "--parents", "-n", "1", head).decode().split()[1:]
        if len(parents) > 1:
            assert _ancestor(repo, identity, parents[0]), "Previous main must precede the merge's first parent"
        baseline = identity
    print(f"Mypy ratchet context={event_name} baseline={baseline}")
    return baseline


def _module_names(paths: list[str]) -> frozenset[str]:
    names = set()
    for path in paths:
        pure = PurePosixPath(path)
        if pure.parts[:1] != ("src",) or pure.suffix != ".py":
            continue
        parts = list(pure.with_suffix("").parts[1:])
        if parts[-1:] == ["__init__"]:
            parts.pop()
        if parts:
            names.add(".".join(parts))
    return frozenset(names)


def _candidate_configs(repo: Path) -> list[tuple[bytes, frozenset[str]]]:
    try:
        named = index_environment(repo)
    except TrackedFileInventoryError as exc:
        raise AssertionError(f'Invalid commit index: {exc}') from exc
    index = named.get("GIT_INDEX_FILE") if named is not None else os.environ.get("GIT_INDEX_FILE")
    if index is not None:
        index_path = Path(index)
        if not index_path.is_absolute():
            index_path = repo / index_path
        assert index_path.is_file(), "Named commit index is missing"
        index = str(index_path)
    working = (repo / "pyproject.toml").read_bytes()
    staged = _git(repo, "show", ":pyproject.toml", index=index)
    try:
        working_paths = [path.relative_to(repo).as_posix() for path in tracked_repository_files(repo, pathspecs=("src/",))]
    except TrackedFileInventoryError as exc:
        raise AssertionError(f"Invalid source inventory: {exc}") from exc
    candidates = [(working, _module_names(working_paths))]
    if staged != working:
        # The shared helper already validates the selected index and every working source path.
        candidates.append((staged, _module_names(working_paths)))
    return candidates


def _validate_repository(repo: Path, environ: Mapping[str, str], data: bytes, digest: str) -> None:
    assert hashlib.sha256(data).hexdigest() == digest, "Bootstrap fixture digest changed"
    fixture = json.loads(data)
    pin = fixture["source_head"]
    names = fixture["modules"]
    assert isinstance(pin, str) and re.fullmatch(r"[0-9a-f]{40}", pin), "Invalid bootstrap source identity"
    assert isinstance(names, list) and all(isinstance(name, str) for name in names), "Invalid bootstrap modules"
    assert len(set(names)) == len(names), "Duplicate bootstrap module"
    base = _resolve_baseline(repo, environ)
    baseline = _git(repo, "show", f"{base}:pyproject.toml")
    bootstrap = None
    if _mypy_section(baseline) is None:
        assert _git(repo, "rev-parse", "--verify", f"{pin}^{{commit}}").decode().strip() == pin
        assert _ancestor(repo, pin, base), "Bootstrap source must be an ancestor of baseline"
        bootstrap = frozenset(names)
    else:
        baseline_paths = _git(repo, "ls-tree", "-r", "--name-only", base, "--", "src").decode().splitlines()
        assert _source_exceptions(baseline) <= _module_names(baseline_paths), "Baseline exception names nonexistent source"
    for config, source_names in _candidate_configs(repo):
        _assert_ratchet(config, baseline, bootstrap_modules=bootstrap)
        assert _source_exceptions(config) <= source_names, "Candidate exception names nonexistent source"


def _config(modules: tuple[str, ...] = ()) -> bytes:
    text = '[tool.mypy]\nfiles = ["src"]\npython_version = "3.14"\nshow_error_codes = true\n'
    text += '\n[[tool.mypy.overrides]]\nmodule = "confusable_homoglyphs"\nignore_missing_imports = true\n'
    if modules:
        text += '\n[[tool.mypy.overrides]]\nmodule = ' + json.dumps(list(modules)) + '\nignore_errors = true\n'
    return text.encode()


def _commit(repo: Path, config: bytes | None = None) -> str:
    if config is not None:
        (repo / "pyproject.toml").write_bytes(config)
    marker = repo / "sequence.txt"
    branch = _git(repo, "branch", "--show-current").decode().strip()
    marker.write_text((marker.read_text() if marker.exists() else "") + branch + "\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "synthetic ratchet history")
    return _git(repo, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def history(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith(("GIT_", "GITHUB_", "TEST_RUN_COMMIT_")) or key == "CI":
            monkeypatch.delenv(key)
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Ratchet fixture")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    source = tmp_path / "src" / "optimus"
    source.mkdir(parents=True)
    for name in ("a", "b"):
        (source / f"{name}.py").write_text("value: int = 1\n")
    pin = _commit(tmp_path, b'[project]\nname = "fixture"\nversion = "0"\n')
    data = json.dumps({"source_head": pin, "modules": ["optimus.a", "optimus.b"]}).encode()
    return tmp_path, pin, data, hashlib.sha256(data).hexdigest()


def test_exception_sets_only_shrink():
    baseline = _config(("optimus.a", "optimus.b"))
    _assert_ratchet(baseline, baseline)
    _assert_ratchet(_config(("optimus.a",)), baseline)
    with pytest.raises(AssertionError, match="grew"):
        _assert_ratchet(_config(("optimus.a", "optimus.b", "optimus.c")), baseline)


def test_removed_exception_cannot_return(history):
    repo, _, data, digest = history
    _commit(repo, _config(("optimus.a", "optimus.b")))
    _commit(repo, _config(("optimus.a",)))
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a", "optimus.b")))
    _git(repo, "add", "pyproject.toml")
    with pytest.raises(AssertionError, match="grew"):
        _validate_repository(repo, {}, data, digest)


@pytest.mark.parametrize("mutation", [
    "global_ignore", "exclude", "follow_imports", "disabled_code", "wrong_files", "wrong_python", "wildcard",
    "duplicate", "unknown_override", "extra_import", "source_import", "third_party_source", "deleted_config",
])
def test_configuration_cannot_widen_scope(mutation):
    text = _config(("optimus.a",)).decode()
    if mutation in {"global_ignore", "exclude", "follow_imports", "disabled_code"}:
        extra = {
            "global_ignore": "ignore_errors = true", "exclude": 'exclude = "src"',
            "follow_imports": 'follow_imports = "skip"', "disabled_code": 'disable_error_code = ["call-arg"]',
        }[mutation]
        text = text.replace("[tool.mypy]\n", f"[tool.mypy]\n{extra}\n")
    elif mutation == "wrong_files":
        text = text.replace('["src"]', '["src/optimus/telemetry"]')
    elif mutation == "wrong_python":
        text = text.replace('"3.14"', '"3.13"')
    elif mutation == "wildcard":
        text = text.replace('"optimus.a"', '"optimus.*"')
    elif mutation == "duplicate":
        text = text.replace('["optimus.a"]', '["optimus.a", "optimus.a"]')
    elif mutation == "unknown_override":
        text += 'follow_imports = "skip"\n'
    elif mutation == "extra_import":
        text += '\n[[tool.mypy.overrides]]\nmodule = "yaml"\nignore_missing_imports = true\n'
    elif mutation == "source_import":
        text = text.replace('module = "confusable_homoglyphs"', 'module = "optimus.a"')
    elif mutation == "third_party_source":
        text = text.replace('"optimus.a"', '"confusable_homoglyphs"')
    else:
        text = '[project]\nname = "deleted"\n'
    with pytest.raises(AssertionError):
        _source_exceptions(text.encode())


def test_bootstrap_is_exact_and_one_time(history):
    repo, pin, data, digest = history
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a", "optimus.b")))
    _git(repo, "add", "pyproject.toml")
    _validate_repository(repo, {}, data, digest)
    _git(repo, "restore", "--staged", "--worktree", "pyproject.toml")
    descendant = _commit(repo)
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a",)))
    _git(repo, "add", "pyproject.toml")
    _validate_repository(repo, {}, data, digest)
    with pytest.raises(AssertionError, match="digest"):
        _validate_repository(repo, {}, data + b" ", digest)
    sibling_data = json.dumps({"source_head": descendant, "modules": ["optimus.a", "optimus.b"]}).encode()
    _git(repo, "restore", "--staged", "--worktree", "pyproject.toml")
    _git(repo, "checkout", "-b", "sibling", pin)
    _commit(repo)
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a",)))
    _git(repo, "add", "pyproject.toml")
    with pytest.raises(AssertionError, match="ancestor"):
        _validate_repository(repo, {}, sibling_data, hashlib.sha256(sibling_data).hexdigest())
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a", "optimus.c")))
    _git(repo, "add", "pyproject.toml")
    with pytest.raises(AssertionError, match="grew"):
        _validate_repository(repo, {}, data, digest)
    (repo / "pyproject.toml").write_bytes(b'[project]\nname = "deleted"\n')
    _git(repo, "add", "pyproject.toml")
    with pytest.raises(AssertionError, match="configuration"):
        _validate_repository(repo, {}, data, digest)


def test_baseline_contexts_fail_closed(history, tmp_path):
    repo, pin, _, _ = history
    _git(repo, "checkout", "-b", "feature")
    candidate = _commit(repo)
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "feature", "-m", "synthetic merge")
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    event = tmp_path / "event.json"
    env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request"}
    event.write_text(json.dumps({"pull_request": {"base": {"sha": pin}}}))
    assert _resolve_baseline(repo, {}) == head
    assert _resolve_baseline(repo, {"GITHUB_TOKEN": "fixture-value"}) == head
    assert _resolve_baseline(repo, env) == pin
    env["GITHUB_EVENT_NAME"] = "push"
    event.write_text(json.dumps({"ref": "refs/heads/main", "before": pin}))
    assert _resolve_baseline(repo, env) == pin
    _commit(repo)
    assert _resolve_baseline(repo, env) == pin  # multi-commit push uses previous main
    for before in ("0" * 40, "f" * 40, "HEAD", "", candidate + "x"):
        event.write_text(json.dumps({"ref": "refs/heads/main", "before": before}))
        with pytest.raises(AssertionError):
            _resolve_baseline(repo, env)
    event.write_text(json.dumps({"ref": "refs/heads/feature", "before": pin}))
    with pytest.raises(AssertionError):
        _resolve_baseline(repo, env)
    event.write_text(json.dumps({"pull_request": {"base": {"sha": "f" * 40}}}))
    env["GITHUB_EVENT_NAME"] = "pull_request"
    with pytest.raises(AssertionError):
        _resolve_baseline(repo, env)
    for broken in ({"CI": "true"}, {**env, "GITHUB_EVENT_NAME": "workflow_dispatch"}, {**env, "GITHUB_EVENT_PATH": "missing"}):
        with pytest.raises(AssertionError):
            _resolve_baseline(repo, broken)


def test_staged_growth_is_not_hidden(history, monkeypatch):
    repo, _, data, digest = history
    _commit(repo, _config(("optimus.a",)))
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a", "optimus.b")))
    _git(repo, "add", "pyproject.toml")
    alternate = repo / "alternate-index"
    alternate.write_bytes((repo / ".git" / "index").read_bytes())
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a",)))
    with pytest.raises(AssertionError, match="grew"):
        _validate_repository(repo, {}, data, digest)
    _git(repo, "add", "pyproject.toml")
    _validate_repository(repo, {}, data, digest)
    monkeypatch.setenv(COMMIT_INDEX_FILE, str(alternate))
    monkeypatch.setenv(COMMIT_INDEX_ROOT, str(repo))
    with pytest.raises(AssertionError, match="grew"):
        _validate_repository(repo, {}, data, digest)
    monkeypatch.setenv(COMMIT_INDEX_FILE, str(repo / "missing-index"))
    with pytest.raises(AssertionError, match="index"):
        _validate_repository(repo, {}, data, digest)


def test_new_module_is_checked(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "new_module.py").write_text('value: int = "wrong"\n')
    (tmp_path / "pyproject.toml").write_bytes(_config())
    tripwire_record = tmp_path / "mypy-child-tripwire.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", "pyproject.toml", "--no-incremental"],
        cwd=tmp_path, env=child_tripwire.hooked_environment(os.environ.copy(), tripwire_record),
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "new_module.py:1" in result.stdout and "[assignment]" in result.stdout
    child_tripwire.assert_no_real_adapter_access(tripwire_record)


def test_repository_mypy_exception_ratchet():
    data = (ROOT / "tests/fixtures/typing/mypy-bootstrap.json").read_bytes()
    named = index_environment(ROOT)
    index = named.get('GIT_INDEX_FILE') if named is not None else os.environ.get('GIT_INDEX_FILE')
    staged_data = _git(ROOT, 'show', ':tests/fixtures/typing/mypy-bootstrap.json', index=index)
    assert hashlib.sha256(staged_data).hexdigest() == BOOTSTRAP_DIGEST, 'Staged bootstrap fixture digest changed'
    _validate_repository(ROOT, os.environ, data, BOOTSTRAP_DIGEST)


def test_candidate_source_must_exist_in_each_tree(history):
    repo, _, data, digest = history
    (repo / "pyproject.toml").write_bytes(_config(("optimus.a", "optimus.b")))
    _git(repo, "add", "pyproject.toml")
    _validate_repository(repo, {}, data, digest)
    # Same config bytes in both candidates cannot hide a source removed from the index.
    _git(repo, "rm", "--cached", "src/optimus/b.py")
    with pytest.raises(AssertionError, match="source"):
        _validate_repository(repo, {}, data, digest)
    _git(repo, "add", "src/optimus/b.py")
    (repo / "src/optimus/b.py").unlink()
    with pytest.raises(AssertionError, match="source"):
        _validate_repository(repo, {}, data, digest)


def test_mypy_gate_wiring():
    assert "mypy" in GuardrailRuleSet.phase1().check_names
    hooks_config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    all_hooks = [hook for repository in hooks_config["repos"] for hook in repository["hooks"]]
    matched_hooks = [hook for hook in all_hooks if hook["id"] == "optimus-mypy"]
    assert len(matched_hooks) == 1
    hook = matched_hooks[0]
    hooks = {hook["id"]: hook for hook in all_hooks}
    assert hook["name"] == "optimus-check: mypy"
    assert shlex.split(hook["entry"]) == ["python", "-m", "mypy", "--config-file", "pyproject.toml"]
    assert (hook["language"], hook["pass_filenames"], hook.get("always_run")) == ("system", False, True)
    assert not {"files", "exclude", "stages"} & hook.keys()
    pytest_hook = hooks["optimus-pytest-coverage"]
    assert shlex.split(pytest_hook["entry"]) == ["python", "-m", "tools.testing.run_profile", "--profile", "commit"]
    assert pytest_hook.get("always_run") is True and pytest_hook["pass_filenames"] is False
    assert "stages" not in pytest_hook
    rules = tomllib.loads((ROOT / "tests/profiles.toml").read_text(encoding="utf-8"))["rules"]
    for name in ("test_repository_mypy_exception_ratchet", "test_mypy_gate_wiring"):
        node = f"tests/unit/tools/test_mypy_ratchet.py::{name}"
        matched = [rule for rule in rules if node in rule.get("nodes", [])]
        assert len(matched) == 1 and matched[0]["tier"] == "gates"
    workflow = yaml.safe_load((ROOT / ".github/workflows/guardrails.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["clean-environment-recheck"]["steps"]
    checkouts = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkouts) == 1 and checkouts[0]["with"]["fetch-depth"] == 0
    command = ["uv", "run", "--no-sync", "python", "-m", "mypy", "--config-file", "pyproject.toml"]
    for name, expected in (("optimus-check: mypy", command), ("optimus-check: mypy-win32", [*command, "--platform", "win32"])):
        matched = [step for step in steps if step.get("name") == name]
        assert len(matched) == 1 and shlex.split(matched[0]["run"]) == expected
