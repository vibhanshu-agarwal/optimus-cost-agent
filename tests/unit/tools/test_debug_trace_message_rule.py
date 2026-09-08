"""Seam 1: run the actual ast-grep literal-message gate against safe and regressed snippets.

Ported from sandbox tag `sandbox-seam1` (commit ad9deeb7). Main has no lifecycle
adapter, so the sandbox's narrow `log_lifecycle_event` exception and its tests are
deliberately omitted: on main EVERY `acp_debug_log(message=...)` must be literal.

Resolves the configured hook's existing pre-commit Node environment read-only. Missing
tooling fails explicitly: no skips, downloads or cache provisioning.

Resolution must run under the REAL environment. pre-commit picks the Node environment by
asking `node.get_default_version()`, which answers `system` when node and npm are on PATH
and `default` otherwise, and memoises that answer process-wide in an `lru_cache(maxsize=1)`.
The environment directory name embeds the answer (`node_env-system` vs `node_env-default`),
so resolving while PATH is stripped looks for an environment that was never provisioned and
poisons the cache for every later test in the same process. That is exactly what happened on
Linux CI: one failure became 35 fixture errors. Windows always answers `default`, which is
why the fault was invisible there. Every PATH mutation below therefore goes through
`_stripped_shell_path`, and `_pristine_node_version_cache` proves none of them leaks.
"""

from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import pytest
from pre_commit import constants
from pre_commit.clientlib import load_config
from pre_commit.hook import Hook
from pre_commit.languages import node
from pre_commit.parse_shebang import normalize_cmd
from pre_commit.prefix import Prefix
from pre_commit.repository import _hook, _hook_installed
from pre_commit.store import Store

ROOT = Path(__file__).resolve().parents[3]
RULE_ID = "literal-debug-trace-message"


def _resolve_runner():
    """Bind the configured, already-provisioned hook. MUST run under the real environment."""
    config = load_config(str(ROOT / ".pre-commit-config.yaml"))
    [configured] = [
        hook for repo in config["repos"] if repo["repo"] == "local"
        for hook in repo["hooks"] if hook["id"] == "optimus-ast-grep"
    ]
    assert configured["language"] == "node"
    # Reuse pre-commit's version resolution, cache key and health check. Do not
    # instantiate Store: its constructor can create shared cache state.
    resolved = _hook(configured, root_config=config)
    database = Path(Store.get_default_directory()) / "db.db"
    if not database.is_file():
        pytest.fail("ast-grep hook environment not provisioned: cache database absent", pytrace=False)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT path FROM repos WHERE repo = ? AND ref = ?",
            (Store.db_repo_name("local", resolved["additional_dependencies"]), constants.LOCAL_REPO_VERSION),
        ).fetchone()
    if row is None:
        pytest.fail("ast-grep hook environment not provisioned for configured dependencies", pytrace=False)
    hook = Hook.create("local", Prefix(row[0]), resolved)
    if not _hook_installed(hook):
        # Name the environment actually looked for: a bare "unhealthy" cost a CI cycle.
        pytest.fail(
            "ast-grep hook environment not provisioned or unhealthy "
            f"(language_version={hook.language_version!r}, prefix={row[0]!r}); "
            "resolving under a stripped PATH selects a version that was never provisioned",
            pytrace=False,
        )
    # Same activation and entry-command normalization as pre-commit. Capture the
    # environment for the child, restoring the caller's environment here.
    with node.in_env(hook.prefix, hook.language_version):
        entry = shlex.split(hook.entry)
        # Snippets run outside the checkout; retain the gate's configured rules.
        config_index = entry.index("--config") + 1
        entry[config_index] = str(ROOT / entry[config_index])
        command = normalize_cmd(tuple(entry))
        environment = os.environ.copy()
    return command, environment


@contextmanager
def _stripped_shell_path(monkeypatch):
    """Remove PATH for the duration of the block, leaving no cached resolution behind.

    pre-commit memoises its Node version choice process-wide and that choice reads PATH,
    so a bare `setenv("PATH", ...)` leaks into every later test in the session.
    """
    node.get_default_version.cache_clear()
    try:
        with monkeypatch.context() as patched:
            patched.setenv("PATH", os.defpath)
            yield
    finally:
        node.get_default_version.cache_clear()


@pytest.fixture(autouse=True)
def _pristine_node_version_cache():
    """Give every test an EMPTY version cache and fail if one leaves a different answer.

    Starting pristine matters: handing a test a pre-computed `system` would mask exactly
    the defect under repair instead of surfacing it.
    """
    node.get_default_version.cache_clear()
    real = node.get_default_version()
    node.get_default_version.cache_clear()
    yield
    # Read what the test LEFT cached before clearing: clearing first would recompute the
    # honest answer and make this assertion vacuous.
    leaked = node.get_default_version()
    node.get_default_version.cache_clear()
    assert leaked == real, (
        "a test left pre-commit's cached Node version changed; that contamination is what "
        "turned one failure into 35 fixture errors on Linux CI"
    )


@pytest.fixture(scope="module")
def ast_grep():
    # Bound once, under the real environment, before any test strips PATH. Clear first:
    # a module-scoped fixture is created BEFORE the function-scoped guard above, so without
    # this the binding could inherit a memo left by an earlier module in the same session.
    # Nothing else in this repository resolves pre-commit in-process today, but relying on
    # that would make the binding accidental rather than guaranteed.
    node.get_default_version.cache_clear()
    return _resolve_runner()


def _scan(runner, source):
    # A standalone directory exercises the real src/ file boundary and avoids
    # discovering another checkout's config.
    with tempfile.TemporaryDirectory(prefix="optimus-trace-rule-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        (root / "src/probe.py").write_text(source, encoding="utf-8")
        command, environment = runner
        completed = subprocess.run(  # noqa: S603 - the configured hook binary with fixed arguments
            [*command, "--json=compact", "src"],
            cwd=root, env=environment, text=True, capture_output=True, check=False, timeout=15,
        )
    assert completed.returncode in (0, 1), completed.stderr
    matches = json.loads(completed.stdout)
    assert all(match["ruleId"] == RULE_ID for match in matches)
    return completed.returncode, matches


def test_rule_runner_uses_provisioned_hook_without_shell_path(ast_grep, monkeypatch):
    """The gate binary comes from the provisioned store, not from whatever PATH offers."""
    command, _ = ast_grep
    binary = Path(command[0])
    store = Path(Store.get_default_directory()).resolve()
    assert binary.is_absolute(), f"entry {binary} is not absolute, so it would be resolved via PATH"
    assert store in binary.resolve().parents, f"{binary} is not inside the pre-commit store {store}"
    with _stripped_shell_path(monkeypatch):
        code, matches = _scan(ast_grep, 'acp_debug_log(location="test", message=str(exc))')
    assert code == 1 and len(matches) == 1


_FRESH_PROCESS_PROBE = """\
import importlib.util, json, os

spec = importlib.util.spec_from_file_location("rule_harness", {module!r})
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)

from pre_commit.languages import node

# A pristine interpreter: nothing may have decided the Node version before us.
assert node.get_default_version.cache_info().currsize == 0, "cache was not empty in a fresh process"

command, environment = harness._resolve_runner()
resolved_version = node.get_default_version()

# Only now remove PATH, and scan with the binding made under the real environment.
os.environ["PATH"] = os.defpath
code, matches = harness._scan((command, environment), {snippet!r})

print(json.dumps({{
    "resolved_version": resolved_version,
    "binary": command[0],
    "code": code,
    "matches": len(matches),
}}))
"""


def test_fresh_process_resolves_then_scans_without_shell_path(tmp_path):
    """Resolution works in a genuinely fresh interpreter, not because this one primed a cache.

    The parent's `lru_cache` cannot help the child, so a regression that resolves under a
    stripped PATH still fails here even if the in-process tests were arranged to pass.
    """
    probe = tmp_path / "fresh_resolution_probe.py"
    probe.write_text(
        _FRESH_PROCESS_PROBE.format(
            module=str(Path(__file__).resolve()),
            snippet='acp_debug_log(location="test", message=str(exc))',
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(  # noqa: S603 - this interpreter running a generated probe
        [sys.executable, str(probe)],
        text=True, capture_output=True, check=False, timeout=120,
    )
    # Check the child's status and surface both streams BEFORE touching any report key, so a
    # real failure reads as an explicit message rather than a bare KeyError or IndexError.
    assert completed.returncode == 0, f"stdout={completed.stdout}\nstderr={completed.stderr}"
    assert completed.stdout.strip(), f"child produced no report; stderr={completed.stderr}"
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["code"] == 1 and report["matches"] == 1
    assert Path(report["binary"]).is_absolute()
    # The child chose the version itself, under the real environment.
    assert report["resolved_version"] in {"system", "default"}


def test_stripping_path_does_not_leak_a_cached_node_version(monkeypatch):
    """Regression guard for the Linux CI cascade: one strip must not change later answers."""
    real = node.get_default_version()
    with _stripped_shell_path(monkeypatch):
        pass
    # The helper must leave NO memo at all. Asserting only that a recomputed value matches
    # would still pass while a stale answer sat in the cache waiting for the next test.
    assert node.get_default_version.cache_info().currsize == 0
    assert node.get_default_version() == real


def test_missing_hook_environment_fails_instead_of_skipping(monkeypatch, tmp_path):
    cache = tmp_path / "unprovisioned-cache"
    monkeypatch.setenv("PRE_COMMIT_HOME", str(cache))
    with _stripped_shell_path(monkeypatch):
        with pytest.raises(pytest.fail.Exception, match="not provisioned"):
            _resolve_runner()
    assert not cache.exists(), "resolving a test dependency must not provision it"


@pytest.mark.parametrize("expression", [
    "str(exc)", "message", 'f"error: {exc}"', '"error: " + text',
    '"error: %s" % exc', '"error: {}".format(exc)', "None", 'b"bytes"',
    '"literal" f"{exc}"', '("safe" if enabled else message)', 'f"literal"',
    '((message))', '("safe" + "computed")',
])
@pytest.mark.parametrize("callee", ["acp_debug_log", "debug_trace.acp_debug_log"])
def test_gate_rejects_eager_or_non_string_messages(ast_grep, expression, callee):
    code, matches = _scan(ast_grep, f'{callee}(location="test", data={{}}, message={expression})')
    assert code == 1 and len(matches) == 1


@pytest.mark.parametrize("source", [
    'acp_debug_log(message="literal", location="test", data=lambda: expensive())',
    "acp_debug_log(location='test', message='literal')",
    'debug_trace.acp_debug_log(message=("two " "literals"), location="test")',
    'acp_debug_log(message=r"raw literal", location="test")',
    'acp_debug_log(message=((("nested literal"))), location="test")',
    'acp_debug_log(message="escaped\\nline", location="test")',
    'other_logger(message=str(exc))',
])
def test_gate_allows_literals_and_unrelated_functions(ast_grep, source):
    assert _scan(ast_grep, source) == (0, [])


def test_there_is_no_lifecycle_exception_on_main(ast_grep):
    """The sandbox allowed `message=event` inside `log_lifecycle_event`; main has no such adapter."""
    source = 'def log_lifecycle_event(event):\n    acp_debug_log(location="acp.lifecycle", message=event, data={})'
    code, matches = _scan(ast_grep, source)
    assert code == 1 and len(matches) == 1


def test_real_sink_module_passes_the_gate(ast_grep):
    source = (ROOT / "src/optimus/acp/debug_trace.py").read_text(encoding="utf-8")
    assert _scan(ast_grep, source) == (0, [])
    # A dynamic diagnostic appended to the very same file must still be rejected.
    code, matches = _scan(ast_grep, source + '\nacp_debug_log(location="test", message=str(exc))\n')
    assert code == 1 and len(matches) == 1
