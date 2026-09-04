"""HARDENING-ITEM-GIT-ENV-TEST-IMMUNITY: the suite must survive contaminated `GIT_*`.

Git exports `GIT_DIR`, `GIT_INDEX_FILE` and `GIT_WORK_TREE` to the hooks it runs, so any
test that shells out to git under a pre-commit hook acts on the SURROUNDING repository
regardless of `cwd`. On 2026-09-02 that marked the real repository bare and wrote a
fixture identity into its shared config, breaking `git status` in the main checkout and
every worktree.

`tests/conftest.py::pytest_sessionstart` strips `GIT_*` for the whole session. These tests
verify that protection *from outside pytest*, by launching a fresh pytest process whose
environment points exclusively at a disposable victim repository and whose test makes
ordinary, deliberately unprotected git calls. The negative case asserts the hazard is real
and that the central protection is what prevents it -- without it, a passing suite of
individually-hardened helpers could conceal a broken central fix.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Deliberately NOT isolated: this is the call shape that caused the incident.
UNPROTECTED_GIT_TEST = '''
import subprocess


def test_ordinary_unprotected_git_calls(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    subprocess.run(["git", "init"], cwd=fixture, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Probe"], cwd=fixture, check=True, capture_output=True
    )
'''


def _clean_git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _victim_state(repo: Path) -> dict[str, str]:
    git_dir = repo / ".git"
    index = git_dir / "index"
    refs = subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname) %(objectname)"],
        cwd=repo,
        text=True,
        env=_clean_git_env(),
    )
    return {
        "config": hashlib.sha256((git_dir / "config").read_bytes()).hexdigest(),
        "index": hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else "",
        "head": (git_dir / "HEAD").read_text(encoding="utf-8").strip(),
        "refs": refs,
    }


def _run_contaminated_pytest(tmp_path: Path, *, protected: bool) -> tuple[dict[str, str], dict[str, str]]:
    """Run a fresh pytest whose GIT_* point at a disposable victim; return its before/after."""
    victim = tmp_path / "victim"
    victim.mkdir()
    subprocess.run(
        ["git", "init", "-q"], cwd=victim, check=True, capture_output=True, env=_clean_git_env()
    )
    (tmp_path / "test_contaminated_case.py").write_text(UNPROTECTED_GIT_TEST, encoding="utf-8")

    before = _victim_state(victim)
    env = dict(os.environ)
    env["GIT_DIR"] = str(victim / ".git")
    env["GIT_INDEX_FILE"] = str(victim / ".git" / "index")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")])

    # `-p tests.conftest` loads the REAL central protection; omitting it disables it.
    args = [
        sys.executable, "-m", "pytest",
        str(tmp_path / "test_contaminated_case.py"), "-q", "-p", "no:cacheprovider",
    ]
    if protected:
        args += ["-p", "tests.conftest"]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"inner pytest failed:\n{result.stdout}\n{result.stderr}"
    return before, _victim_state(victim)


def test_central_protection_keeps_the_surrounding_repository_untouched(tmp_path: Path) -> None:
    before, after = _run_contaminated_pytest(tmp_path, protected=True)
    assert after == before, "contaminated GIT_* reached the surrounding repository"


def test_without_central_protection_the_hazard_is_real(tmp_path: Path) -> None:
    """Negative control: proves the protection -- not luck -- is what keeps the victim clean."""
    before, after = _run_contaminated_pytest(tmp_path, protected=False)
    assert after != before, (
        "expected unprotected git calls to damage the victim; if this ever passes, this "
        "regression has stopped testing anything and the positive case is worthless"
    )
    victim_config = (tmp_path / "victim" / ".git" / "config").read_text(encoding="utf-8")
    assert after["config"] != before["config"]
    assert "Probe" in victim_config


@pytest.mark.parametrize("variable", ["GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"])
def test_session_start_removed_git_variables_from_this_process(variable: str) -> None:
    """The running session is itself protected -- this is what a hook run relies on."""
    assert variable not in os.environ
