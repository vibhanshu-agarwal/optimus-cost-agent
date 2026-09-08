"""Seam 1: run the actual ast-grep literal-message gate against safe and regressed snippets.

Ported from sandbox tag `sandbox-seam1` (commit ad9deeb7). Main has no lifecycle
adapter, so the sandbox's narrow `log_lifecycle_event` exception and its tests are
deliberately omitted: on main EVERY `acp_debug_log(message=...)` must be literal.

Resolves the configured hook's existing pre-commit Node environment read-only. Missing
tooling fails explicitly: no skips, downloads or cache provisioning.
"""

from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
import tempfile
from contextlib import closing
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
        pytest.fail("ast-grep hook environment not provisioned or unhealthy", pytrace=False)
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


@pytest.fixture(scope="module")
def ast_grep():
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


def test_rule_runner_uses_provisioned_hook_without_shell_path(monkeypatch):
    monkeypatch.setenv("PATH", os.defpath)
    try:
        runner = _resolve_runner()
    except pytest.skip.Exception:  # pragma: no cover - guards against a future skip
        pytest.fail("provisioned rule evidence must not skip when ast-grep is absent from PATH")
    code, matches = _scan(runner, 'acp_debug_log(location="test", message=str(exc))')
    assert code == 1 and len(matches) == 1


def test_missing_hook_environment_fails_instead_of_skipping(monkeypatch, tmp_path):
    cache = tmp_path / "unprovisioned-cache"
    monkeypatch.setenv("PRE_COMMIT_HOME", str(cache))
    monkeypatch.setenv("PATH", os.defpath)
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
