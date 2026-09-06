"""Local secret-scan hook: encoding boundary regressions (local-hook UTF-8 repair plan, 2026-09-06).

Two layers of evidence:

* **Configured-hook tests** drive the real ``optimus-secret-scan`` hook (the exact entry from
  ``.pre-commit-config.yaml``, the real ``tools/local_secret_scan.py`` copied to the same relative
  path, the approved baseline copied in) through ``pre-commit run --files`` in a disposable Git
  repository. Detection is proved by the scanner's own ``Secret Type`` / ``Location`` diagnostic
  naming the fixture, never by "any nonzero exit".
* **Adapter unit tests** call ``tools.local_secret_scan.run`` directly with a recording stub for the
  delegate, so validation order, status codes and baseline immutability are proved without the
  scanner.

Defect under test (root cause, reproduced by Codex 2026-09-06): the pinned ``detect_secrets`` file
reader opens files in the process locale and swallows ``UnicodeDecodeError``, so a selected text
file the locale cannot decode contributes zero lines and the hook passes. Canaries are assembled at
write time from split fragments so this module never contains a detectable value itself.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.unit.guardrails import test_ci_parity as parity

ROOT = parity.ROOT
LOCAL_HOOK_ID = "optimus-secret-scan"
ADAPTER_RELPATH = Path("tools") / "local_secret_scan.py"

# U+0081 is a valid Unicode code point (UTF-8: C2 81) that CP1252 cannot decode.
CP1252_UNDECODABLE_TEXT = "# note \u0081 marker\n"
# A lone 0xFF byte is never valid UTF-8.
INVALID_UTF8_BYTES = b"# corrupt \xff marker\n"
CANARY_LINE = "access_key = " + repr(parity.CANARY_VALUE) + "\n"
CANARY_DETECTOR = "AWS Access Key"
CLEAN_UNICODE_LINE = "greeting = 'héllo wörld — ünïcode'\n"
CLEAN_ASCII_LINE = "answer = 42\n"
UTF8_BOM_TEXT = "\ufeff" + CLEAN_ASCII_LINE
SPACED_UNICODE_RELPATH = Path("pkg") / "spaced dir é" / "módule name.py"
ADAPTER_PROGRAM = "local-secret-scan"
CHUNK = 64 * 1024  # must equal tools.local_secret_scan.CHUNK_BYTES; asserted in the adapter fixture


# ---------------------------------------------------------------------------
# Fixture repository and hook invocation
# ---------------------------------------------------------------------------


def _configured_local_hook() -> dict:
    """The real local hook definition, taken from the repository's pre-commit config."""
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [
        hook
        for repo in config["repos"]
        if repo.get("repo") == "local"
        for hook in repo["hooks"]
        if hook["id"] == LOCAL_HOOK_ID
    ]
    assert len(hooks) == 1, f"expected exactly one {LOCAL_HOOK_ID} hook, found {len(hooks)}"
    return hooks[0]


def _make_hook_repo(tmp_path: Path, name: str) -> Path:
    """Disposable Git repo holding the configured local hook, the approved baseline and the real adapter.

    Only the local ``optimus-secret-scan`` entry is written so pre-commit never needs to clone the
    remote hook repository; the entry, types, baseline and adapter bytes are the real ones. Every
    repository-relative path named by the entry is copied to the same relative path.
    """
    repo = parity._make_fixture_repo(tmp_path, name)
    hook = _configured_local_hook()
    config = {"repos": [{"repo": "local", "hooks": [hook]}]}
    (repo / ".pre-commit-config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    for token in str(hook["entry"]).split():
        source = ROOT / token
        if source.is_file():
            target = repo / token
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    assert (repo / ADAPTER_RELPATH).read_bytes() == (ROOT / ADAPTER_RELPATH).read_bytes(), (
        "the fixture must run the candidate adapter bytes"
    )
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    return repo


def _hook_env(repo: Path, *, utf8_mode: bool) -> dict[str, str]:
    """pre-commit environment with the parent locale pinned explicitly.

    ``parity._sanitized_env`` forces ``PYTHONUTF8=1``; the defect only shows when the scanner process
    runs without UTF-8 mode, so the parent value is set per test and the configured entry decides
    the scanner's real mode (it must override a parent ``PYTHONUTF8=0`` without global changes).
    """
    env = parity._sanitized_env(repo)
    env["PYTHONUTF8"] = "1" if utf8_mode else "0"
    return env


def _run_local_hook(
    repo: Path, files: list[Path], *, utf8_mode: bool, stage: bool = True
) -> subprocess.CompletedProcess[str]:
    if stage:
        parity.stage_fixture_files(repo)
    argv = [
        str(parity._venv_scripts_dir() / ("pre-commit.exe" if os.name == "nt" else "pre-commit")),
        "run",
        LOCAL_HOOK_ID,
        "--files",
        *[str(path.relative_to(repo)) for path in files],
    ]
    return subprocess.run(
        argv,
        cwd=str(repo),
        env=_hook_env(repo, utf8_mode=utf8_mode),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=parity.STEP_TIMEOUT_SECONDS,
    )


def _baseline_bytes(repo: Path) -> bytes:
    return (repo / ".secrets.baseline").read_bytes()


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8", newline="\n")
    else:
        path.write_bytes(data)
    return path


def _assert_detected(result: subprocess.CompletedProcess[str], relpath: str) -> None:
    """Scanner detection, not any failure: the scanner named the detector and the fixture path."""
    out = result.stdout + result.stderr
    assert result.returncode == 1, f"expected the scanner's finding status 1, got {result.returncode}: {out}"
    assert f"Secret Type: {CANARY_DETECTOR}" in out, out
    assert f"Location:    {relpath}" in out.replace("\\", "/"), out
    assert ADAPTER_PROGRAM not in out, f"adapter validation error must not be mistaken for detection: {out}"


def _assert_adapter_rejected(result: subprocess.CompletedProcess[str], relpath: str, *reasons: str) -> None:
    out = result.stdout + result.stderr
    assert result.returncode != 0, out
    assert f"{ADAPTER_PROGRAM}:" in out, f"expected an adapter diagnostic: {out}"
    assert relpath in out.replace("\\", "/"), out
    for reason in reasons:
        assert reason in out, out
    assert "Secret Type:" not in out, f"validation must reject before the scanner runs: {out}"


def _venv_python() -> Path:
    return parity._venv_scripts_dir() / ("python.exe" if os.name == "nt" else "python")


# ---------------------------------------------------------------------------
# Environment record and direct-reader controls
# ---------------------------------------------------------------------------


def test_environment_record_for_this_boundary():
    """Pins the facts the controls depend on: interpreter, UTF-8 mode default and preferred encoding."""
    probe = subprocess.run(
        [
            str(_venv_python()),
            "-c",
            "import sys, locale, json; print(json.dumps({'utf8_mode': sys.flags.utf8_mode, "
            "'preferred': locale.getpreferredencoding(False), 'version': sys.version.split()[0]}))",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={k: v for k, v in os.environ.items() if k != "PYTHONUTF8"},
    )
    assert probe.returncode == 0, probe.stderr
    facts = json.loads(probe.stdout)
    major, minor = (int(part) for part in facts["version"].split(".")[:2])
    assert (major, minor) >= (3, 14), f"locked interpreter below the repository minimum: {facts}"
    # Evidence only: the host default is recorded, never whitelisted (a UTF-8 or other code-page
    # Windows host is a valid installation; the CP1252 control below decides its own applicability).
    print(f"environment record: {facts}")


_READER_SCRIPT = (
    "import sys, json, locale\n"
    "from detect_secrets.core.scan import _get_lines_from_file\n"
    "print(json.dumps({'lines': len(list(_get_lines_from_file(sys.argv[1]))), "
    "'utf8_mode': sys.flags.utf8_mode, 'preferred': locale.getpreferredencoding(False)}))\n"
)


def _classify_cp1252_control(off_facts: dict) -> str:
    """Decide whether the historical CP1252 control can execute on this host.

    Returns ``"execute"`` only for a real UTF-8-mode-off process whose preferred encoding is CP1252;
    otherwise a ``"skip: ..."`` reason carrying the measured facts. Classification only: it never
    stands in for an actual CP1252 execution, which the commission requires on a CP1252 host.
    """
    if off_facts.get("utf8_mode") != 0:
        return f"skip: the UTF-8-off probe still reports utf8_mode={off_facts.get('utf8_mode')}"
    preferred = str(off_facts.get("preferred", "")).lower()
    if preferred != "cp1252":
        return (
            f"skip: the UTF-8-off process reports preferred encoding {preferred!r}, not cp1252; "
            "historical control not executable on this host"
        )
    return "execute"


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ({"utf8_mode": 0, "preferred": "cp1252"}, "execute"),
        ({"utf8_mode": 0, "preferred": "utf-8"}, "skip"),
        ({"utf8_mode": 0, "preferred": "cp1250"}, "skip"),
        ({"utf8_mode": 1, "preferred": "cp1252"}, "skip"),
    ],
    ids=["cp1252-executes", "utf8-host-skips", "other-codepage-skips", "utf8-mode-on-skips"],
)
def test_cp1252_control_classification(facts: dict, expected: str):
    """Controlled classification check with synthetic facts; it establishes no platform execution."""
    outcome = _classify_cp1252_control(facts)
    assert outcome.startswith(expected), outcome


@pytest.mark.skipif(os.name != "nt", reason="the CP1252 omission requires a real CP1252 Windows process (disclosed skip)")
def test_historical_reader_omits_cp1252_undecodable_text(tmp_path: Path):
    """Control: an actual CP1252 process (UTF-8 mode forced off) yields zero lines for valid UTF-8 it cannot decode.

    On a Windows host whose UTF-8-off process is not CP1252 (for example a UTF-8 system locale) this
    control skips with the measured reason; that skip never satisfies the commission's separate
    requirement for a real CP1252 execution.
    """
    target = _write(tmp_path / "u0081.py", CP1252_UNDECODABLE_TEXT + CANARY_LINE)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    off = subprocess.run(
        [str(_venv_python()), "-X", "utf8=0", "-c", _READER_SCRIPT, str(target)],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    assert off.returncode == 0, off.stderr
    off_facts = json.loads(off.stdout)
    outcome = _classify_cp1252_control(off_facts)
    if outcome != "execute":
        pytest.skip(outcome)
    on = subprocess.run(
        [str(_venv_python()), "-X", "utf8=1", "-c", _READER_SCRIPT, str(target)],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    assert on.returncode == 0, on.stderr
    on_facts = json.loads(on.stdout)
    assert off_facts["lines"] == 0, "CP1252 process should have silently dropped the file (defect control)"
    assert on_facts["utf8_mode"] == 1 and on_facts["lines"] >= 1, "UTF-8 process must read the file"


def test_historical_reader_omits_invalid_utf8_even_in_utf8_mode(tmp_path: Path):
    target = _write(tmp_path / "invalid.py", INVALID_UTF8_BYTES + CANARY_LINE.encode("utf-8"))
    result = subprocess.run(
        [str(_venv_python()), "-X", "utf8=1", "-c", _READER_SCRIPT, str(target)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["lines"] == 0, "UTF-8 process silently drops invalid UTF-8 (defect control)"


# ---------------------------------------------------------------------------
# Configured-hook regressions (the acceptance oracle)
# ---------------------------------------------------------------------------


def test_configured_entry_runs_the_adapter_in_utf8_mode():
    hook = _configured_local_hook()
    assert hook["entry"] == f"python -X utf8 {ADAPTER_RELPATH.as_posix()} --baseline .secrets.baseline src"
    assert hook["types"] == ["text"] and hook.get("pass_filenames", True) is True
    assert (ROOT / ADAPTER_RELPATH).is_file()


def test_canary_in_plain_ascii_file_is_detected_by_configured_hook(tmp_path: Path):
    """Detection control: the configured hook detects a readable canary and names it."""
    repo = _make_hook_repo(tmp_path, "ascii-canary")
    target = _write(repo / "src" / "probe.py", CANARY_LINE)
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    _assert_detected(result, "src/probe.py")
    assert _baseline_bytes(repo) == before


@pytest.mark.parametrize("parent_utf8", [False, True], ids=["parent-utf8-off", "parent-utf8-on"])
def test_valid_utf8_with_cp1252_undecodable_text_cannot_hide_a_canary(tmp_path: Path, parent_utf8: bool):
    """The repaired hook detects the canary regardless of the parent locale (the entry's -X utf8 must win)."""
    repo = _make_hook_repo(tmp_path, "u0081-canary")
    target = _write(repo / "src" / "probe_u0081.py", CP1252_UNDECODABLE_TEXT + CANARY_LINE)
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=parent_utf8)
    _assert_detected(result, "src/probe_u0081.py")
    assert _baseline_bytes(repo) == before


@pytest.mark.parametrize("parent_utf8", [False, True], ids=["parent-utf8-off", "parent-utf8-on"])
def test_clean_valid_utf8_with_cp1252_undecodable_text_passes(tmp_path: Path, parent_utf8: bool):
    """Same U+0081 text without a canary: readable and clean, so the hook passes under both parents."""
    repo = _make_hook_repo(tmp_path, "u0081-clean")
    target = _write(repo / "src" / "clean_u0081.py", CP1252_UNDECODABLE_TEXT + CLEAN_ASCII_LINE)
    result = _run_local_hook(repo, [target], utf8_mode=parent_utf8)
    assert result.returncode == 0, f"clean U+0081 file rejected: {result.stdout}\n{result.stderr}"


def test_invalid_utf8_selected_text_is_rejected_with_path_and_reason(tmp_path: Path):
    """Unreadable selected text fails the hook with a diagnostic before the scanner or the baseline is touched."""
    repo = _make_hook_repo(tmp_path, "invalid-utf8")
    target = _write(repo / "src" / "corrupt.py", INVALID_UTF8_BYTES + CANARY_LINE.encode("utf-8"))
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    _assert_adapter_rejected(result, "src/corrupt.py", "cannot decode", "UTF-8", "byte offset")
    assert _baseline_bytes(repo) == before, "a validation failure must never change the baseline"


def test_utf16_bom_text_selected_by_pre_commit_is_rejected_not_skipped(tmp_path: Path):
    """A BOM-marked UTF-16 '.txt' (the shape of the 50 frozen Plan 11.7 transcripts) is selected as text and rejected."""
    repo = _make_hook_repo(tmp_path, "utf16")
    target = _write(repo / "src" / "transcript.txt", ("transcript line\n" + CANARY_LINE).encode("utf-16"))
    assert target.read_bytes().startswith(b"\xff\xfe")
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    # The adapter diagnostic naming the file proves pre-commit selected it (types: [text]) and passed it through.
    _assert_adapter_rejected(result, "src/transcript.txt", "cannot decode", "byte offset 0")
    assert _baseline_bytes(repo) == before


@pytest.mark.parametrize(
    ("relpath", "content"),
    [
        (Path("src") / "clean_ascii.py", CLEAN_ASCII_LINE),
        (Path("src") / "clean_unicode.py", CLEAN_UNICODE_LINE),
        (Path("src") / "bom.py", UTF8_BOM_TEXT),
        (Path("src") / SPACED_UNICODE_RELPATH, CLEAN_UNICODE_LINE),
    ],
    ids=["ascii", "unicode", "utf8-bom", "spaced-non-ascii-path"],
)
def test_clean_selected_text_passes_under_either_parent_locale(tmp_path: Path, relpath: Path, content: str):
    repo = _make_hook_repo(tmp_path, "clean")
    target = _write(repo / relpath, content)
    before = _baseline_bytes(repo)
    for utf8_mode in (False, True):
        result = _run_local_hook(repo, [target], utf8_mode=utf8_mode)
        assert result.returncode == 0, f"clean file rejected (parent utf8={utf8_mode}): {result.stdout}\n{result.stderr}"
    assert _baseline_bytes(repo) == before


def test_only_selected_files_are_scanned_among_staged_files(tmp_path: Path):
    """Selected-versus-unselected among *staged* files: pre-commit's --files selection is honoured."""
    repo = _make_hook_repo(tmp_path, "selection-staged")
    selected = _write(repo / "src" / "selected.py", CLEAN_ASCII_LINE)
    _write(repo / "src" / "unselected.py", CANARY_LINE)
    result = _run_local_hook(repo, [selected], utf8_mode=True)
    assert result.returncode == 0, f"unselected staged file leaked into the scan: {result.stdout}\n{result.stderr}"


def test_untracked_unselected_canary_is_not_pulled_in(tmp_path: Path):
    """A canary that is neither staged nor selected is not scanned; the selected clean file passes."""
    repo = _make_hook_repo(tmp_path, "selection-untracked")
    selected = _write(repo / "src" / "selected.py", CLEAN_ASCII_LINE)
    parity.stage_fixture_files(repo)
    _write(repo / "src" / "untracked_canary.py", CANARY_LINE)  # written after staging: untracked
    result = _run_local_hook(repo, [selected], utf8_mode=True, stage=False)
    assert result.returncode == 0, f"untracked canary leaked into the scan: {result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# Adapter unit tests (direct invocation, recording delegate)
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter():
    sys.path.insert(0, str(ROOT))
    try:
        module = importlib.import_module("tools.local_secret_scan")
    finally:
        sys.path.pop(0)
    module = importlib.reload(module)
    assert module.CHUNK_BYTES == CHUNK, "boundary fixtures must straddle the adapter's real chunk size"
    return module


class _Delegate:
    def __init__(self, status: int = 0) -> None:
        self.status = status
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(list(argv))
        return self.status


def _adapter_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "adapter-repo"
    (repo / "src").mkdir(parents=True)
    baseline = repo / ".secrets.baseline"
    shutil.copy2(ROOT / ".secrets.baseline", baseline)
    return repo, baseline


def _run_adapter(adapter, repo: Path, argv: list[str], *, delegate: _Delegate, monkeypatch, utf8_mode: bool = True):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(adapter, "_utf8_mode_enabled", lambda: utf8_mode)
    err = io.StringIO()
    status = adapter.run(argv, delegate=delegate, stderr=err)
    return status, err.getvalue()


def test_adapter_delegates_original_argv_unchanged_and_preserves_status(adapter, tmp_path: Path, monkeypatch):
    repo, _ = _adapter_repo(tmp_path)
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)
    for status in (0, 1, 3):
        delegate = _Delegate(status)
        argv = ["--baseline", ".secrets.baseline", "src", "src/a.py"]
        got, err = _run_adapter(adapter, repo, argv, delegate=delegate, monkeypatch=monkeypatch)
        assert got == status and delegate.calls == [argv], (got, err, delegate.calls)


@pytest.mark.parametrize(
    ("name", "content", "expected_offset"),
    [
        ("start", b"\xff" + b"x" * 10, 0),
        ("late-multichunk", b"x" * (70 * 1024) + b"\xff" + b"y" * 5, 70 * 1024),
        ("truncated-sequence-at-eof", b"ok\n" + b"\xc3", 3),
        ("split-lead-byte-then-invalid-continuation", b"x" * (CHUNK - 1) + b"\xc3(", CHUNK - 1),
        ("split-two-byte-then-bad-byte", b"x" * (CHUNK - 1) + b"\xc3\xa9\xff", CHUNK + 1),
    ],
    ids=["start", "late-multichunk", "truncated-sequence-at-eof", "split-lead-then-invalid", "split-two-byte-then-bad"],
)
def test_adapter_rejects_invalid_utf8_before_delegation(adapter, tmp_path: Path, monkeypatch, name, content, expected_offset):
    repo, baseline = _adapter_repo(tmp_path)
    target = _write(repo / "src" / f"{name}.py", content)
    before = baseline.read_bytes()
    delegate = _Delegate()
    status, err = _run_adapter(
        adapter, repo, ["--baseline", ".secrets.baseline", "src", f"src/{name}.py"], delegate=delegate, monkeypatch=monkeypatch
    )
    assert status == 2 and delegate.calls == [], (status, err)
    assert f"src/{name}.py" in err and "cannot decode" in err and f"byte offset {expected_offset}" in err, err
    assert "xxxxxxxx" not in err, "diagnostics must not echo file contents"
    assert baseline.read_bytes() == before and target.read_bytes() == content


@pytest.mark.parametrize(
    ("name", "prefix_len", "sequence"),
    [
        ("two-byte-spans-boundary", CHUNK - 1, "\u00e9"),
        ("three-byte-spans-boundary", CHUNK - 2, "\u20ac"),
        ("four-byte-spans-boundary", CHUNK - 3, "\U0001f600"),
        ("four-byte-spans-boundary-late", CHUNK - 1, "\U0001f600"),
    ],
    ids=["two-byte", "three-byte", "four-byte", "four-byte-late"],
)
def test_adapter_accepts_valid_sequences_spanning_chunk_boundaries(
    adapter, tmp_path: Path, monkeypatch, name, prefix_len, sequence
):
    repo, baseline = _adapter_repo(tmp_path)
    content = b"x" * prefix_len + sequence.encode("utf-8") + b"\nok\n"
    content.decode("utf-8")  # fixture self-check: valid UTF-8 straddling the boundary
    _write(repo / "src" / f"{name}.py", content)
    before = baseline.read_bytes()
    delegate = _Delegate(1)
    argv = ["--baseline", ".secrets.baseline", "src", f"src/{name}.py"]
    status, err = _run_adapter(adapter, repo, argv, delegate=delegate, monkeypatch=monkeypatch)
    assert status == 1 and delegate.calls == [argv] and err == "", (status, err, delegate.calls)
    assert baseline.read_bytes() == before


def test_adapter_rejects_undecodable_baseline(adapter, tmp_path: Path, monkeypatch):
    repo, baseline = _adapter_repo(tmp_path)
    baseline.write_bytes(b"{\xff}")
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)
    delegate = _Delegate()
    status, err = _run_adapter(
        adapter, repo, ["--baseline", ".secrets.baseline", "src", "src/a.py"], delegate=delegate, monkeypatch=monkeypatch
    )
    assert status == 2 and delegate.calls == [] and ".secrets.baseline" in err and "cannot decode" in err, err


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        (["src", "src/a.py"], "--baseline <path> is required"),
        (["--baseline"], "must appear once"),
        (["--baseline", ".secrets.baseline", "--baseline", ".secrets.baseline", "src"], "must appear once"),
        (["--baseline", ".secrets.baseline", "--verbose", "src"], "unsupported option"),
        (["--baseline", ".secrets.baseline", "src", "src/missing.py"], "file not found"),
        (["--baseline", ".secrets.baseline", "src", "src/subdir"], "unexpected directory argument"),
        (["--baseline", ".secrets.baseline", "src/subdir"], "unexpected directory argument"),
    ],
    ids=[
        "no-baseline", "dangling-baseline", "duplicate-baseline", "unknown-option",
        "missing-file", "directory-arg", "directory-arg-without-marker",
    ],
)
def test_adapter_rejects_malformed_or_unexpected_arguments(adapter, tmp_path: Path, monkeypatch, argv, fragment):
    repo, baseline = _adapter_repo(tmp_path)
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)
    (repo / "src" / "subdir").mkdir()
    before = baseline.read_bytes()
    delegate = _Delegate()
    status, err = _run_adapter(adapter, repo, argv, delegate=delegate, monkeypatch=monkeypatch)
    assert status == 2 and delegate.calls == [] and fragment in err, (status, err)
    assert baseline.read_bytes() == before


def test_adapter_rejects_missing_directory_marker(adapter, tmp_path: Path, monkeypatch):
    repo, _ = _adapter_repo(tmp_path)
    shutil.rmtree(repo / "src")
    delegate = _Delegate()
    status, err = _run_adapter(adapter, repo, ["--baseline", ".secrets.baseline", "src"], delegate=delegate, monkeypatch=monkeypatch)
    assert status == 2 and delegate.calls == [] and "existing directory" in err, err


def test_adapter_reports_unreadable_candidate_without_delegating(adapter, tmp_path: Path, monkeypatch):
    """Controlled I/O error: opening the candidate raises PermissionError."""
    repo, _ = _adapter_repo(tmp_path)
    target = _write(repo / "src" / "locked.py", CLEAN_ASCII_LINE)
    real_open = open

    def fake_open(path, *args, **kwargs):
        if Path(path) == Path("src/locked.py") or Path(path) == target:
            raise PermissionError(13, "Permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    delegate = _Delegate()
    status, err = _run_adapter(
        adapter, repo, ["--baseline", ".secrets.baseline", "src", "src/locked.py"], delegate=delegate, monkeypatch=monkeypatch
    )
    assert status == 2 and delegate.calls == [] and "src/locked.py" in err and "permission denied" in err, err


def test_adapter_refuses_to_run_outside_utf8_mode(adapter, tmp_path: Path, monkeypatch):
    repo, _ = _adapter_repo(tmp_path)
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)
    delegate = _Delegate()
    status, err = _run_adapter(
        adapter, repo, ["--baseline", ".secrets.baseline", "src", "src/a.py"], delegate=delegate, monkeypatch=monkeypatch, utf8_mode=False
    )
    assert status == 2 and delegate.calls == [] and "-X utf8" in err, err


def test_adapter_process_without_utf8_flag_refuses(tmp_path: Path):
    """Real process control: the same script invoked with UTF-8 mode explicitly off refuses before doing anything."""
    repo, _ = _adapter_repo(tmp_path)
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)
    result = subprocess.run(
        [str(_venv_python()), "-X", "utf8=0", str(ROOT / ADAPTER_RELPATH), "--baseline", ".secrets.baseline", "src", "src/a.py"],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2 and "-X utf8" in result.stderr, (result.returncode, result.stderr)
