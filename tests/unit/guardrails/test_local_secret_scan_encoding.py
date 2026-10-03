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

import contextlib
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


# ---------------------------------------------------------------------------
# BOM-marked UTF-16 reports (scanner decoding repair, 2026-10-03)
# ---------------------------------------------------------------------------
#
# The 50 frozen Plan 11.7 custody transcripts are BOM-marked UTF-16 '.txt' files that pre-commit
# selects as text. They used to be rejected as undecodable UTF-8, so the all-files hook could never
# pass; the pinned scanner on its own would have opened them with the locale codec and silently
# scanned nothing. The adapter now validates a BOM-marked file *inside the custody namespace* as
# strict UTF-16 and reads it as UTF-16 for the scanner, in place, under its own path, so detector
# plugins, filters and baseline identities are unchanged and the bytes on disk are never rewritten.
# The baseline and every selected file outside that namespace stay strict UTF-8 (Codex R2).

REPORT_NAMESPACE = "reports/plan-11-7-server-custody-artifacts"
REPORT_RELPATH = f"{REPORT_NAMESPACE}/amendments/transcript.txt"
UTF16_BOMS = {"le": b"\xff\xfe", "be": b"\xfe\xff"}


def _utf16(text: str, order: str = "le") -> bytes:
    return UTF16_BOMS[order] + text.encode(f"utf-16-{order}")


@pytest.mark.parametrize("order", ["le", "be"])
def test_canary_in_utf16_bom_report_is_detected_by_configured_hook(tmp_path: Path, order: str):
    repo = _make_hook_repo(tmp_path, f"utf16-{order}-canary")
    content = _utf16("transcript line\n" + CANARY_LINE, order)
    target = _write(repo / REPORT_RELPATH, content)
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    _assert_detected(result, REPORT_RELPATH)
    assert target.read_bytes() == content, "the report's bytes must not be rewritten"
    assert _baseline_bytes(repo) == before


@pytest.mark.parametrize("order", ["le", "be"])
def test_clean_utf16_bom_report_passes(tmp_path: Path, order: str):
    repo = _make_hook_repo(tmp_path, f"utf16-{order}-clean")
    content = _utf16("transcript line\r\n" + CLEAN_UNICODE_LINE + CLEAN_ASCII_LINE, order)
    target = _write(repo / REPORT_RELPATH, content)
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    assert result.returncode == 0, f"clean UTF-16 report rejected: {result.stdout}\n{result.stderr}"
    assert target.read_bytes() == content and _baseline_bytes(repo) == before


MALFORMED_UTF16 = [
    ("odd-length", _utf16("ab") + b"\x61", 6, "truncated data"),
    ("lone-high-surrogate", UTF16_BOMS["le"] + b"\x00\xd8" + "a".encode("utf-16-le"), 2, "illegal UTF-16 surrogate"),
    ("lone-low-surrogate", _utf16("a") + b"\x00\xdc" + "b".encode("utf-16-le"), 4, "illegal encoding"),
    ("late-multichunk", _utf16("x" * (40 * 1024)) + b"\x00\xdc", 2 + 2 * 40 * 1024, "illegal encoding"),
    ("nul-character", _utf16("a\x00b\n"), 4, "NUL"),
    ("utf32-le-bom", b"\xff\xfe\x00\x00" + "ab".encode("utf-32-le"), 2, "NUL"),
]
MALFORMED_IDS = [case[0] for case in MALFORMED_UTF16]


@pytest.mark.parametrize(("name", "content", "offset", "reason"), MALFORMED_UTF16, ids=MALFORMED_IDS)
def test_malformed_utf16_bom_report_is_rejected_with_path_offset_and_reason(
    tmp_path: Path, name: str, content: bytes, offset: int, reason: str
):
    """A BOM that promises UTF-16 the file does not deliver fails the hook before the scanner runs."""
    repo = _make_hook_repo(tmp_path, f"utf16-{name}")
    target = _write(repo / REPORT_RELPATH, content)
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    _assert_adapter_rejected(result, REPORT_RELPATH, "cannot decode", "UTF-16", f"byte offset {offset}", reason)
    assert _baseline_bytes(repo) == before


def test_utf16_bom_does_not_loosen_utf8_validation_of_other_selected_files(tmp_path: Path):
    """A UTF-16 report and an invalid-UTF-8 source file in one invocation: the source file still rejects."""
    repo = _make_hook_repo(tmp_path, "utf16-beside-invalid-utf8")
    report = _write(repo / REPORT_RELPATH, _utf16("transcript line\n"))
    corrupt = _write(repo / "src" / "corrupt.py", INVALID_UTF8_BYTES + CANARY_LINE.encode("utf-8"))
    result = _run_local_hook(repo, [report, corrupt], utf8_mode=True)
    _assert_adapter_rejected(result, "src/corrupt.py", "cannot decode", "UTF-8", "byte offset")


@pytest.mark.parametrize(
    "relpath",
    ["src/transcript.txt", "reports/other-plan/transcript.txt", "docs/transcript.txt"],
    ids=["source", "other-report", "docs"],
)
def test_utf16_bom_text_outside_the_report_namespace_is_rejected_not_skipped(tmp_path: Path, relpath: str):
    """UTF-16 is supported for the custody reports only; elsewhere a BOM-marked file is still undecodable UTF-8."""
    repo = _make_hook_repo(tmp_path, "utf16-outside-namespace")
    target = _write(repo / relpath, _utf16("transcript line\n" + CANARY_LINE))
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    _assert_adapter_rejected(result, relpath, "cannot decode", "UTF-8", "byte offset 0")
    assert _baseline_bytes(repo) == before


def test_utf16_bom_baseline_is_rejected_before_delegation_without_writes(tmp_path: Path):
    """The baseline is a UTF-8 JSON input to the pinned hook; a BOM-marked baseline never reaches it."""
    repo = _make_hook_repo(tmp_path, "utf16-baseline")
    baseline = repo / ".secrets.baseline"
    utf16_baseline = _utf16(baseline.read_text(encoding="utf-8"))
    baseline.write_bytes(utf16_baseline)
    target = _write(repo / "src" / "probe.py", CANARY_LINE)
    result = _run_local_hook(repo, [target], utf8_mode=True)
    _assert_adapter_rejected(result, ".secrets.baseline", "cannot decode", "UTF-8", "byte offset 0")
    assert baseline.read_bytes() == utf16_baseline, "a rejected baseline must not be written"


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


@pytest.mark.parametrize("order", ["le", "be"])
def test_adapter_validates_utf16_bom_candidates_and_delegates_argv_unchanged(adapter, tmp_path: Path, monkeypatch, order):
    """The report is delegated under its own path (no decoded copy), so baseline identities are unchanged."""
    repo, baseline = _adapter_repo(tmp_path)
    content = _utf16("transcript line\n" + CANARY_LINE, order)
    target = _write(repo / REPORT_RELPATH, content)
    before = baseline.read_bytes()
    for status in (0, 1, 3):
        delegate = _Delegate(status)
        argv = ["--baseline", ".secrets.baseline", "src", REPORT_RELPATH]
        got, err = _run_adapter(adapter, repo, argv, delegate=delegate, monkeypatch=monkeypatch)
        assert got == status and delegate.calls == [argv] and err == "", (got, err, delegate.calls)
    assert target.read_bytes() == content and baseline.read_bytes() == before


@pytest.mark.parametrize(("name", "content", "offset", "reason"), MALFORMED_UTF16, ids=MALFORMED_IDS)
def test_adapter_rejects_malformed_utf16_before_delegation(adapter, tmp_path: Path, monkeypatch, name, content, offset, reason):
    repo, baseline = _adapter_repo(tmp_path)
    target = _write(repo / REPORT_RELPATH, content)
    before = baseline.read_bytes()
    delegate = _Delegate()
    status, err = _run_adapter(
        adapter, repo, ["--baseline", ".secrets.baseline", "src", REPORT_RELPATH], delegate=delegate, monkeypatch=monkeypatch
    )
    assert status == 2 and delegate.calls == [], (status, err)
    assert REPORT_RELPATH in err and "cannot decode" in err and "UTF-16" in err, err
    assert f"byte offset {offset}" in err and reason in err, err
    assert "xxxxxxxx" not in err, "diagnostics must not echo file contents"
    assert baseline.read_bytes() == before and target.read_bytes() == content


def test_adapter_rejects_utf16_bom_baseline_before_delegation(adapter, tmp_path: Path, monkeypatch):
    repo, baseline = _adapter_repo(tmp_path)
    utf16_baseline = _utf16(baseline.read_text(encoding="utf-8"))
    baseline.write_bytes(utf16_baseline)
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)
    delegate = _Delegate()
    status, err = _run_adapter(
        adapter, repo, ["--baseline", ".secrets.baseline", "src", "src/a.py"], delegate=delegate, monkeypatch=monkeypatch
    )
    assert status == 2 and delegate.calls == [], (status, err)
    assert ".secrets.baseline" in err and "cannot decode" in err and "UTF-8" in err and "byte offset 0" in err, err
    assert baseline.read_bytes() == utf16_baseline


# The scanner's reader. It reads a file once, validates exactly those bytes by the rules above and
# hands the decoded text to the scanner's transformers under the original name, so a file that
# became unreadable, vanished or changed shape after validation fails the hook (ValidationError is
# neither the IOError that scan_file swallows nor the UnicodeDecodeError the pinned reader swallows).


def test_strict_reader_decodes_reports_as_utf16_and_everything_else_as_utf8(adapter, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reader = adapter._strict_reader()
    report_bytes = _utf16("transcript line\r\n" + CANARY_LINE)
    report = _write(tmp_path / REPORT_RELPATH, report_bytes)
    source = _write(tmp_path / "src" / "module.py", CLEAN_UNICODE_LINE.encode("utf-8") + b"second\r\nthird\rfourth\n")

    assert list(reader(REPORT_RELPATH)) == [["transcript line\n", CANARY_LINE]]
    assert report.read_bytes() == report_bytes, "the report's bytes must not be rewritten"
    assert list(reader(str(Path("src") / "module.py"))) == [[CLEAN_UNICODE_LINE, "second\n", "third\n", "fourth\n"]], (
        "universal newlines, as the pinned open() produced them"
    )
    assert list(reader(str(source))) == list(reader(str(Path("src") / "module.py"))), "absolute and relative paths read alike"


@pytest.mark.parametrize(
    ("relpath", "content", "fragment"),
    [
        ("src/transcript.txt", _utf16("x\n"), "as UTF-8 at byte offset 0"),
        (REPORT_NAMESPACE, _utf16("x\n"), "as UTF-8 at byte offset 0"),  # the namespace itself as a file: not below it
        (REPORT_RELPATH, _utf16("a") + b"\x00\xdc", "as UTF-16 at byte offset 4: illegal encoding"),
        (REPORT_RELPATH, b"\xff\xfe\x00\x00" + "ab".encode("utf-32-le"), "as UTF-16 at byte offset 2: NUL character"),
        ("src/corrupt.py", INVALID_UTF8_BYTES, "as UTF-8 at byte offset 10"),
        ("src/missing.py", None, "file not found"),
    ],
    ids=["utf16-outside-namespace", "utf16-namespace-as-a-file", "malformed-utf16-report", "utf32-report", "invalid-utf8-source", "missing"],
)
def test_strict_reader_fails_closed_instead_of_yielding_nothing(adapter, tmp_path: Path, monkeypatch, relpath, content, fragment):
    monkeypatch.chdir(tmp_path)
    if content is not None:
        _write(tmp_path / relpath, content)
    with pytest.raises(adapter.ValidationError, match=fragment):
        list(adapter._strict_reader()(relpath))


def _scan_in_process(
    adapter, repo: Path, relpath: str, *, before_scan=None, deny: Path | None = None, vanish_after_check: Path | None = None
) -> tuple[int, str]:
    """Run the adapter with its real delegate (the pinned scanner, in process) in a staged fixture repo.

    ``before_scan`` runs after validation succeeded and before the scanner starts, which is the
    window Codex's R1 reproduction exercises; ``deny`` makes every open of that path raise
    PermissionError for the duration of the scan; ``vanish_after_check`` deletes that path right
    after the wrapper's own scan-time read returns, before the scanner's existence filter sees it
    (Codex's second residual case). The UTF-8-mode gate is satisfied as the other adapter unit tests
    satisfy it (the configured entry passes ``-X utf8``; the test process, on Linux in particular,
    need not), so what is exercised is the scan-time read, not that gate.
    """
    parity.stage_fixture_files(repo)
    real_open = open
    real_read = adapter._read_strictly
    vanished = False

    def denied_open(path, *args, **kwargs):
        if deny is not None and Path(path).resolve() == deny.resolve():
            raise PermissionError(13, "Permission denied")
        return real_open(path, *args, **kwargs)

    def read_then_vanish(filename: str) -> str:
        nonlocal vanished
        text = real_read(filename)
        if vanish_after_check is not None and not vanished and Path(filename).resolve() == vanish_after_check.resolve():
            vanish_after_check.unlink()
            vanished = True
        return text

    def delegate(argv: list[str]) -> int:
        if before_scan is not None:
            before_scan()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("builtins.open", denied_open)
            patch.setattr(adapter, "_read_strictly", read_then_vanish)
            return adapter._delegate(argv)

    err = io.StringIO()
    out = io.StringIO()
    previous = Path.cwd()
    os.chdir(repo)
    try:
        with pytest.MonkeyPatch.context() as patch, contextlib.redirect_stdout(out):
            patch.setattr(adapter, "_utf8_mode_enabled", lambda: True)
            status = adapter.run(["--baseline", ".secrets.baseline", "src", relpath], delegate=delegate, stderr=err)
    finally:
        os.chdir(previous)
    return status, out.getvalue() + err.getvalue()


@pytest.mark.parametrize(
    ("relpath", "content"),
    [(REPORT_RELPATH, _utf16(CANARY_LINE)), ("src/probe.py", CANARY_LINE.encode("utf-8"))],
    ids=["utf16-report", "utf8-source"],
)
def test_in_process_scan_detects_an_unchanged_canary(adapter, tmp_path: Path, relpath: str, content: bytes):
    """Positive control for the scan-time failure cases: the real delegate still finds and names the canary."""
    repo = _make_hook_repo(tmp_path, "in-process-canary")
    _write(repo / relpath, content)
    before = _baseline_bytes(repo)
    status, text = _scan_in_process(adapter, repo, relpath)
    assert status == 1 and f"Secret Type: {CANARY_DETECTOR}" in text and ADAPTER_PROGRAM not in text, text
    assert _baseline_bytes(repo) == before


@pytest.mark.parametrize(
    ("relpath", "content"),
    [(REPORT_RELPATH, _utf16(CLEAN_ASCII_LINE)), ("src/probe.py", CLEAN_ASCII_LINE.encode("utf-8"))],
    ids=["utf16-report", "utf8-source"],
)
def test_in_process_scan_passes_an_unchanged_clean_file(adapter, tmp_path: Path, relpath: str, content: bytes):
    repo = _make_hook_repo(tmp_path, "in-process-clean")
    _write(repo / relpath, content)
    before = _baseline_bytes(repo)
    status, text = _scan_in_process(adapter, repo, relpath)
    assert status == 0 and "Secret Type:" not in text and ADAPTER_PROGRAM not in text, text
    assert _baseline_bytes(repo) == before


def _replace_with(path: Path, data: bytes):
    return lambda: path.write_bytes(data)


def _replace_with_directory(path: Path):
    def replace() -> None:
        path.unlink()
        path.mkdir()

    return replace


UTF16_CANARY = _utf16(CANARY_LINE)
UTF8_CANARY = CANARY_LINE.encode("utf-8")
SCAN_TIME_FAILURES = [
    ("report-denied", REPORT_RELPATH, _utf16(CLEAN_ASCII_LINE), "deny", "permission denied"),
    ("report-deleted", REPORT_RELPATH, _utf16(CLEAN_ASCII_LINE), "delete", "file not found"),
    ("report-to-invalid-utf8", REPORT_RELPATH, _utf16(CLEAN_ASCII_LINE), INVALID_UTF8_BYTES, "as UTF-8 at byte offset 10"),
    ("report-to-utf32-canary", REPORT_RELPATH, _utf16(CLEAN_ASCII_LINE), CANARY_LINE.encode("utf-32"), "NUL character"),
    ("report-to-malformed-utf16", REPORT_RELPATH, _utf16(CLEAN_ASCII_LINE), _utf16("a") + b"\x00\xdc", "illegal encoding"),
    ("report-to-directory", REPORT_RELPATH, UTF16_CANARY, "directory", "unexpected directory argument"),
    ("report-vanishes-after-scan-check", REPORT_RELPATH, UTF16_CANARY, "vanish-after-check", "file not found"),
    ("source-denied", "src/probe.py", CLEAN_ASCII_LINE.encode("utf-8"), "deny", "permission denied"),
    ("source-deleted", "src/probe.py", CLEAN_ASCII_LINE.encode("utf-8"), "delete", "file not found"),
    ("source-to-invalid-utf8", "src/probe.py", CLEAN_ASCII_LINE.encode("utf-8"), INVALID_UTF8_BYTES + UTF8_CANARY, "as UTF-8 at byte offset 10"),
    ("source-to-utf16-canary", "src/probe.py", CLEAN_ASCII_LINE.encode("utf-8"), UTF16_CANARY, "as UTF-8 at byte offset 0"),
    ("source-to-directory", "src/probe.py", UTF8_CANARY, "directory", "unexpected directory argument"),
    ("source-vanishes-after-scan-check", "src/probe.py", UTF8_CANARY, "vanish-after-check", "file not found"),
]


@pytest.mark.parametrize(("name", "relpath", "content", "change", "fragment"), SCAN_TIME_FAILURES, ids=[c[0] for c in SCAN_TIME_FAILURES])
def test_a_file_that_fails_to_read_or_decode_at_scan_time_cannot_be_reported_clean(
    adapter, tmp_path: Path, name: str, relpath: str, content: bytes, change, fragment: str
):
    """Codex R1: after validation the file is denied, deleted or replaced; the hook must not return 0."""
    repo = _make_hook_repo(tmp_path, f"scan-time-{name}")
    target = _write(repo / relpath, content)
    before = _baseline_bytes(repo)
    if change == "deny":
        status, text = _scan_in_process(adapter, repo, relpath, deny=target)
    elif change == "delete":
        status, text = _scan_in_process(adapter, repo, relpath, before_scan=target.unlink)
    elif change == "directory":
        status, text = _scan_in_process(adapter, repo, relpath, before_scan=_replace_with_directory(target))
    elif change == "vanish-after-check":
        status, text = _scan_in_process(adapter, repo, relpath, vanish_after_check=target)
        assert not target.exists(), "the fixture must have vanished after the wrapper's scan-time read"
    else:
        status, text = _scan_in_process(adapter, repo, relpath, before_scan=_replace_with(target, change))
    assert status == 2, (status, text)
    assert f"{ADAPTER_PROGRAM}:" in text and relpath.split("/")[-1] in text.replace("\\", "/") and fragment in text, text
    assert "Secret Type:" not in text and "baseline file was updated" not in text, text
    assert _baseline_bytes(repo) == before, "no baseline write on a scan-time failure"


@pytest.mark.parametrize(
    ("relpath", "content"),
    [("src/package-lock.json", UTF8_CANARY), (".secrets.baseline", None)],
    ids=["lock-file-filter", "baseline-file-filter"],
)
def test_a_configured_filename_exclusion_is_still_honoured_not_mistaken_for_a_vanished_file(
    adapter, tmp_path: Path, relpath: str, content: bytes | None
):
    """The scanner's own filename filters still skip what they are configured to skip, silently and clean."""
    repo = _make_hook_repo(tmp_path, "configured-exclusion")
    if content is not None:
        _write(repo / relpath, content)
    before = _baseline_bytes(repo)
    status, text = _scan_in_process(adapter, repo, relpath)
    assert status == 0 and "Secret Type:" not in text and ADAPTER_PROGRAM not in text, text
    assert _baseline_bytes(repo) == before


def test_only_the_literal_directory_marker_is_left_to_the_scanner(adapter, tmp_path: Path):
    """A directory under any other name is a validation failure at scan time, not a silent skip."""
    reads: list[str] = []
    wrapped = adapter._strict_scan_file(lambda filename: iter(()), reads)
    (tmp_path / "src").mkdir()
    (tmp_path / "other").mkdir()
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(tmp_path)
        assert list(wrapped("src")) == []
        with pytest.raises(adapter.ValidationError, match="unexpected directory argument: other"):
            list(wrapped("other"))
        _write(tmp_path / "src" / "filtered.py", CLEAN_ASCII_LINE)
        assert list(wrapped(str(Path("src") / "filtered.py"))) == [], "a regular file the scanner filtered is not an error"


def test_adapter_reports_a_validation_failure_raised_during_delegation(adapter, tmp_path: Path, monkeypatch):
    repo, _ = _adapter_repo(tmp_path)
    _write(repo / "src" / "a.py", CLEAN_ASCII_LINE)

    def delegate(argv: list[str]) -> int:
        raise adapter.ValidationError("cannot decode src/a.py as UTF-16 at byte offset 4: illegal encoding")

    status, err = _run_adapter(adapter, repo, ["--baseline", ".secrets.baseline", "src", "src/a.py"], delegate=delegate, monkeypatch=monkeypatch)
    assert status == 2 and "local-secret-scan: cannot decode src/a.py as UTF-16" in err, (status, err)


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


# ---------------------------------------------------------------------------
# Byte-identical archive moves (docs archive convention, 2026-09-29)
# ---------------------------------------------------------------------------
#
# Archiving a frozen document moves it from a docs/ folder into the archive/ beside it. The hook
# would rescan bytes the repository already holds, and frozen documents cannot take inline
# allowlist pragmas, so such a move could never be committed. Exactly that move is not rescanned:
# a staged rename (R100, identical blob ids) whose destination is its source path with one
# "archive" folder inserted, below docs/. Every other move, any changed byte and any copy is
# scanned as before (Codex post-merge review of cc78573: the first version skipped every
# byte-identical move, which also skipped first scans of content outside the archive convention).


def _commit_all(repo: Path) -> None:
    parity.stage_fixture_files(repo)
    result = parity._run(["git", "commit", "-q", "--no-verify", "-m", "seed"], repo)
    assert result.returncode == 0, f"fixture commit failed: {result.stderr}"


def _git_mv(repo: Path, source: str, destination: str) -> Path:
    (repo / destination).parent.mkdir(parents=True, exist_ok=True)
    result = parity._run(["git", "mv", source, destination], repo)
    assert result.returncode == 0, f"fixture move failed: {result.stderr}"
    return repo / destination


def _seed_committed(repo: Path, relpath: str, content: str = CANARY_LINE) -> None:
    _write(repo / relpath, content)
    _commit_all(repo)


def test_byte_identical_archive_move_under_docs_is_not_rescanned(tmp_path: Path):
    repo = _make_hook_repo(tmp_path, "archive-move")
    _seed_committed(repo, "docs/specs/frozen.md")
    moved = _git_mv(repo, "docs/specs/frozen.md", "docs/specs/archive/frozen.md")
    before = _baseline_bytes(repo)
    result = _run_local_hook(repo, [moved], utf8_mode=True, stage=False)
    assert result.returncode == 0, f"archive move was rescanned: {result.stdout}\n{result.stderr}"
    assert _baseline_bytes(repo) == before


def test_byte_identical_folder_move_into_archive_is_not_rescanned(tmp_path: Path):
    """A whole bundle moves as a folder: docs/sources/X/f -> docs/sources/archive/X/f."""
    repo = _make_hook_repo(tmp_path, "archive-folder-move")
    _seed_committed(repo, "docs/sources/bundle/manifest.md")
    moved = _git_mv(repo, "docs/sources/bundle", "docs/sources/archive/bundle") / "manifest.md"
    result = _run_local_hook(repo, [moved], utf8_mode=True, stage=False)
    assert result.returncode == 0, f"archive folder move was rescanned: {result.stdout}\n{result.stderr}"


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("src/frozen.py", "src/archive/frozen.py"),  # archive move outside docs/
        ("docs/specs/frozen.md", "docs/other/frozen.md"),  # docs move, not into archive/
        ("docs/specs/archive/frozen.md", "docs/specs/frozen.md"),  # out of archive/
        ("docs/specs/frozen.md", "docs/specs/archive/renamed.md"),  # into archive/ under a new name
    ],
    ids=["outside-docs", "not-into-archive", "out-of-archive", "renamed"],
)
def test_any_other_byte_identical_move_is_scanned(tmp_path: Path, source: str, destination: str):
    repo = _make_hook_repo(tmp_path, "other-move")
    _seed_committed(repo, source)
    moved = _git_mv(repo, source, destination)
    result = _run_local_hook(repo, [moved], utf8_mode=True, stage=False)
    _assert_detected(result, destination)


def test_archive_move_with_changed_bytes_is_scanned(tmp_path: Path):
    repo = _make_hook_repo(tmp_path, "edited-move")
    _seed_committed(repo, "docs/specs/frozen.md")
    moved = _git_mv(repo, "docs/specs/frozen.md", "docs/specs/archive/frozen.md")
    _write(moved, CANARY_LINE + CLEAN_ASCII_LINE)
    result = _run_local_hook(repo, [moved], utf8_mode=True)
    _assert_detected(result, "docs/specs/archive/frozen.md")


def test_copy_into_archive_is_scanned(tmp_path: Path):
    repo = _make_hook_repo(tmp_path, "copy")
    _seed_committed(repo, "docs/specs/frozen.md")
    copied = _write(repo / "docs" / "specs" / "archive" / "frozen.md", CANARY_LINE)
    result = _run_local_hook(repo, [copied], utf8_mode=True)
    _assert_detected(result, "docs/specs/archive/frozen.md")


def test_archive_move_plus_identical_copy_still_scans_one_copy(tmp_path: Path):
    """Git pairs the deleted path with only one identical destination; the other is scanned."""
    repo = _make_hook_repo(tmp_path, "move-and-copy")
    _seed_committed(repo, "docs/specs/frozen.md")
    moved = _git_mv(repo, "docs/specs/frozen.md", "docs/specs/archive/frozen.md")
    copied = _write(repo / "docs" / "specs" / "copy.md", CANARY_LINE)
    result = _run_local_hook(repo, [moved, copied], utf8_mode=True)
    out = result.stdout + result.stderr
    assert result.returncode == 1 and f"Secret Type: {CANARY_DETECTOR}" in out, out


def test_real_commit_skips_an_archive_move_but_blocks_an_edited_one(tmp_path: Path):
    """Through the installed hook and a real `git commit`, where pre-commit stashes unstaged edits."""
    repo = _make_hook_repo(tmp_path, "real-commit")
    _seed_committed(repo, "docs/specs/frozen.md")
    install = parity._run([str(parity._venv_scripts_dir() / ("pre-commit.exe" if os.name == "nt" else "pre-commit")), "install"], repo)
    assert install.returncode == 0, install.stderr

    moved = _git_mv(repo, "docs/specs/frozen.md", "docs/specs/archive/frozen.md")
    _write(moved, CANARY_LINE + CLEAN_ASCII_LINE)  # unstaged edit: stashed, never committed
    committed = parity._run(["git", "commit", "-q", "-m", "archive frozen.md"], repo)
    assert committed.returncode == 0, f"archive move rejected: {committed.stdout}\n{committed.stderr}"
    blob = parity._run(["git", "show", "HEAD:docs/specs/archive/frozen.md"], repo)
    assert blob.stdout == CANARY_LINE, "the committed blob must be the original bytes"

    parity.stage_fixture_files(repo)  # now stage the edit
    blocked = parity._run(["git", "commit", "-q", "-m", "edit archived file"], repo)
    assert blocked.returncode != 0 and f"Secret Type: {CANARY_DETECTOR}" in blocked.stdout + blocked.stderr


def test_adapter_drops_only_byte_identical_archive_moves(adapter, tmp_path: Path, monkeypatch):
    repo = _make_hook_repo(tmp_path, "adapter-move")
    for name in ("frozen.md", "edited.md"):
        _write(repo / "docs" / "specs" / name, f"# {name}\n")
    _write(repo / "src" / "frozen.py", CLEAN_ASCII_LINE)
    _commit_all(repo)
    _git_mv(repo, "docs/specs/frozen.md", "docs/specs/archive/frozen.md")
    _git_mv(repo, "docs/specs/edited.md", "docs/specs/archive/edited.md")
    _write(repo / "docs" / "specs" / "archive" / "edited.md", "# edited.md\n" + CLEAN_UNICODE_LINE)
    _git_mv(repo, "src/frozen.py", "src/archive/frozen.py")
    parity.stage_fixture_files(repo)
    delegate = _Delegate(0)
    argv = [
        "--baseline", ".secrets.baseline", "src",
        "docs/specs/archive/frozen.md", "docs/specs/archive/edited.md", "src/archive/frozen.py",
    ]
    status, err = _run_adapter(adapter, repo, argv, delegate=delegate, monkeypatch=monkeypatch)
    assert status == 0, err
    assert delegate.calls == [[
        "--baseline", ".secrets.baseline", "src", "docs/specs/archive/edited.md", "src/archive/frozen.py",
    ]]


SHA1_BLOB = "1" * 40


def _archive_move_record(
    old: str = "docs/a.md",
    new: str = "docs/archive/a.md",
    *,
    old_mode: str = "100644",
    new_mode: str = "100644",
    old_blob: str = SHA1_BLOB,
    new_blob: str = SHA1_BLOB,
    status: str = "R100",
) -> bytes:
    return f":{old_mode} {new_mode} {old_blob} {new_blob} {status}\0{old}\0{new}\0".encode()


def _fake_git(adapter, monkeypatch, diff_stdout: bytes, *, object_format: bytes = b"sha1\n") -> None:
    """Answer the adapter's two git queries: the object format, then the raw staged diff."""

    def run(argv, **_kwargs):
        stdout = object_format if argv[1:3] == ["rev-parse", "--show-object-format"] else diff_stdout
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=stdout)

    monkeypatch.setattr(adapter.subprocess, "run", run)


@pytest.mark.parametrize(
    "failure",
    [
        OSError("git missing"),
        subprocess.TimeoutExpired(cmd="git", timeout=60),
        subprocess.CalledProcessError(returncode=128, cmd="git"),
    ],
    ids=["missing-git", "timeout", "nonzero-exit"],
)
def test_git_failure_drops_nothing(adapter, monkeypatch, failure):
    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(adapter.subprocess, "run", fail)
    assert adapter._byte_identical_archive_moves() == frozenset()


VALID = _archive_move_record()
VALID_SECOND = _archive_move_record("docs/b.md", "docs/archive/b.md")


@pytest.mark.parametrize(
    "stdout",
    [
        VALID.replace(b"a.md", b"\xff.md"),  # path bytes that are not UTF-8
        b"garbage without separators",
        VALID[:-20],  # truncated record
        VALID[:-1],  # missing only its final NUL
        VALID + VALID_SECOND[:30],  # valid record followed by a partial record
        VALID + b"trailing garbage\0",  # valid record followed by a stray field
        _archive_move_record(old_blob="short", new_blob="short") + VALID,  # malformed record, then valid
        b"no-colon 100644 " + VALID[16:],  # header without its leading colon
        _archive_move_record(status="X100") + VALID,  # not a rename status, then valid
        _archive_move_record(old_mode="10064x") + VALID,  # non-octal mode, then valid
        _archive_move_record(old_blob="1" * 64, new_blob="1" * 64),  # sha256-length id in a sha1 repo
    ],
    ids=[
        "undecodable-path", "garbage", "truncated", "missing-final-nul", "valid-then-partial",
        "valid-then-stray-field", "malformed-then-valid", "no-colon", "bad-status-then-valid",
        "bad-mode-then-valid", "wrong-id-length",
    ],
)
def test_malformed_git_output_drops_nothing(adapter, monkeypatch, stdout):
    _fake_git(adapter, monkeypatch, stdout)
    assert adapter._byte_identical_archive_moves() == frozenset()


def test_unknown_object_format_drops_nothing(adapter, monkeypatch):
    _fake_git(adapter, monkeypatch, VALID, object_format=b"blake3\n")
    assert adapter._byte_identical_archive_moves() == frozenset()


@pytest.mark.parametrize(
    "record",
    [
        _archive_move_record(old_mode="100644", new_mode="100755"),  # mode changed with the move
        _archive_move_record(old_mode="120000", new_mode="120000"),  # symlink, not a regular file
        _archive_move_record(old_blob="2" * 40),  # different blobs
        _archive_move_record(old_blob="0" * 40, new_blob="0" * 40),  # null blob
        _archive_move_record(status="R099"),  # not identical
        _archive_move_record("docs/../src/x.md", "docs/../src/archive/x.md"),  # leaves docs/
        _archive_move_record("docs/./a.md", "docs/./archive/a.md"),  # dot component
        _archive_move_record("docs/archive/a.md", "docs/archive/archive/a.md"),  # already archived
        _archive_move_record("Docs/a.md", "Docs/archive/a.md"),  # case differs from docs/
        _archive_move_record("docs/a.md", "docs/Archive/a.md"),  # case differs from archive
    ],
    ids=[
        "mode-change", "symlink", "different-blobs", "null-blob", "not-100", "dotdot",
        "dot", "already-archived", "Docs", "Archive",
    ],
)
def test_well_formed_record_outside_the_rule_is_not_exempt(adapter, monkeypatch, record):
    _fake_git(adapter, monkeypatch, record + VALID_SECOND)
    assert adapter._byte_identical_archive_moves() == frozenset({"docs/archive/b.md"})


def test_well_formed_archive_records_are_recognised(adapter, monkeypatch):
    """Controls for the cases above: the same parser accepts well-formed archive records."""
    _fake_git(adapter, monkeypatch, VALID + VALID_SECOND)
    assert adapter._byte_identical_archive_moves() == frozenset({"docs/archive/a.md", "docs/archive/b.md"})

    sha256 = "a" * 64
    _fake_git(adapter, monkeypatch, _archive_move_record(old_blob=sha256, new_blob=sha256), object_format=b"sha256\n")
    assert adapter._byte_identical_archive_moves() == frozenset({"docs/archive/a.md"})

    _fake_git(adapter, monkeypatch, b"")  # no staged renames at all
    assert adapter._byte_identical_archive_moves() == frozenset()
