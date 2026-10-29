"""Synthetic retained H5 evidence, never a fresh H5 measurement or acceptance run."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support import h5_failure_capture as capture
from tools.plan1126_runtime_audit import shutdown
from tools.plan1126_runtime_audit.measurement import EnvironmentBinding
from tools.testing.run_context import RunContext

_WINDOWS_CAPTURE_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows H5 capture")


@pytest.fixture(autouse=True)
def isolated_activation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", raising=False)
    # Fault injection is local to capture: never patch the recorder/sampler's os module.
    monkeypatch.setattr(capture, "os", SimpleNamespace(path=os.path, getpid=os.getpid, lstat=os.lstat, rename=os.rename))


@pytest.fixture
def specimen(tmp_path: Path):
    root = tmp_path / "repository"
    root.mkdir()
    directory = tmp_path / "capture"
    directory.mkdir()
    context = RunContext(
        run_id=f"20261023T000000-{os.getpid()}-abc123", mode="passive", reason="synthetic_fixture",
        record_dir=tmp_path / "records", started_utc="2026-10-23T00:00:00+00:00", worktree=str(root),
        head="a" * 40, root={"pid": os.getpid(), "creation_time": 123456},
    )
    binding = EnvironmentBinding(sys.executable, sys.version, sys.prefix, "a" * 64,
                                 (("src/fixture.py", str(root / "src/fixture.py"), "b" * 64),), ())
    resource = shutdown.ResourceOwnershipRecord("h5-synthetic", "Fixture", "Fixture.close", "fixture", "fixture",
                                                "fixture", "fixture", "fixture", "fixture", 1, ("merged",), True)
    rows = []
    for cause in capture.CAUSES:
        for _ in range(100):
            row = shutdown.ShutdownScheduleObservation("h5-synthetic", cause, True, 3, ("MainThread",), (), (),
                                                       "WITHIN_100MS", 1, "CLOSED_ONCE", f"{cause}:prepared").to_dict()
            rows.append({"observation_id": "h5-synthetic", **row})
    return dict(directory=directory, repository_root=root, context=context, binding=binding,
                result={"inventory": {"kind": "shutdown-close-paths", "source_fingerprint": "a" * 64,
                                      "close_path_count": 1, "close_sites": [], "resources": [resource.to_dict()]},
                        "inventory_identifiers": ["h5-synthetic"], "observations": rows},
                requester=capture.TARGET, earlier=None, depth="full", options={"repeats": 100},
                request_started_utc="2026-10-23T00:00:01+00:00", request_finished_utc="2026-10-23T00:00:02+00:00")


def _final(specimen) -> Path:
    return specimen["directory"] / specimen["context"].run_id / "h5"


def _verify(specimen, **overrides):
    expected = dict(expected_run_id=specimen["context"].run_id, expected_head="a" * 40,
                    expected_pid=os.getpid(), expected_creation_time=123456,
                    expected_repository_root=specimen["repository_root"])
    expected.update(overrides)
    return capture.verify_h5_capture_bundle(_final(specimen), **expected)


@_WINDOWS_CAPTURE_ONLY
def test_retains_every_ordered_row_and_long_error_metadata(specimen):
    effect = "orderly_eof:probe_error:OSError | errno=-5 | winerror=unknown | origin=" + "界" * 1200 + ":9 in close | probe=unknown | chain=none | group=none"
    specimen["result"]["observations"][7].update(close_outcome="ERROR", cause_effect=effect)
    before = copy.deepcopy(specimen["result"])
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    restored = _verify(specimen)
    assert restored["observations"] == before["observations"]
    assert restored["observations"][7]["cause_effect"] == effect
    assert restored["receipt"]["binding"] == specimen["binding"].to_dict()
    assert specimen["result"] == before


@_WINDOWS_CAPTURE_ONLY
@pytest.mark.parametrize("defect", ["repeat", "binding", "identifier", "extra", "bool", "number", "private", "legacy_extra", "schema_field"])
def test_refuses_malformed_or_private_data_before_publication(specimen, defect):
    rows = specimen["result"]["observations"]
    if defect == "repeat":
        rows.pop()
    elif defect == "binding":
        specimen["result"]["inventory"]["source_fingerprint"] = "c" * 64
    elif defect == "identifier":
        rows[0]["observation_id"] = "other"
    elif defect == "extra":
        rows[0]["message"] = "PRIVATE_MESSAGE"
    elif defect == "bool":
        rows[0]["underlying_close_count"] = True
    elif defect == "number":
        rows[0]["underlying_close_count"] = 2**64
    elif defect == "private":
        rows[0]["cause_effect"] = "password=PRIVATE_MESSAGE"
    elif defect == "legacy_extra":
        rows[0].update(close_outcome="ERROR", cause_effect="orderly_eof:probe_error:OSError | errno=05")
    else:
        specimen["result"]["inventory"]["resources"][0]["message"] = "PRIVATE_MESSAGE"
    status = capture.capture_h5_measurement(**specimen)
    assert status.state == "INVALID" and "PRIVATE_MESSAGE" not in repr(status)
    assert not _final(specimen).exists()
    assert not (specimen["directory"] / specimen["context"].run_id).exists()


@_WINDOWS_CAPTURE_ONLY
def test_verifier_rejects_missing_repeats_and_wrong_binding(specimen):
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    receipt_path = _final(specimen) / "capture.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["binding"]["source_fingerprint"] = "c" * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="^ISSUE287_H5_CAPTURE_INVALID$"):
        _verify(specimen)


@_WINDOWS_CAPTURE_ONLY
@pytest.mark.parametrize("change", [dict(expected_run_id="20261023T000000-1-abc123"), dict(expected_head="b"*40),
                                  dict(expected_pid=1), dict(expected_creation_time=999), dict(expected_creation_time=True)])
def test_wrong_run_head_pid_or_scratch_is_never_accepted(specimen, change):
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    with pytest.raises(ValueError, match="^ISSUE287_H5_CAPTURE_INVALID$"):
        _verify(specimen, **change)


@_WINDOWS_CAPTURE_ONLY
def test_verifier_rejects_pid_reuse_with_different_creation_time(specimen):
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    with pytest.raises(ValueError):
        _verify(specimen, expected_creation_time=123457)
    receipt_path = _final(specimen) / "capture.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["creation_time"] = None
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        _verify(specimen)
    assert _verify(specimen, expected_creation_time=None)["receipt"]["mode"] == "passive"


@_WINDOWS_CAPTURE_ONLY
def test_collision_and_publication_failure_leave_no_valid_bundle(specimen, monkeypatch):
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    original = (_final(specimen) / "capture.json").read_bytes()
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"
    assert (_final(specimen) / "capture.json").read_bytes() == original


@_WINDOWS_CAPTURE_ONLY
@pytest.mark.parametrize("failure", ["write", "verify", "rename"])
def test_failed_write_verify_rename_preserves_invalid_scratch(specimen, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_MESSAGE")
    if failure == "write":
        monkeypatch.setattr(capture.evidence_store, "write_evidence_sidecar", fail)
    elif failure == "verify":
        monkeypatch.setattr(capture, "_verify_bundle", fail)
    else:
        monkeypatch.setattr(capture.os, "rename", fail)
    status = capture.capture_h5_measurement(**specimen)
    assert status.state == "INVALID" and not _final(specimen).exists()
    assert (specimen["directory"] / specimen["context"].run_id).is_dir()
    assert "PRIVATE_MESSAGE" not in repr(status)


@_WINDOWS_CAPTURE_ONLY
def test_stage_and_final_share_the_validated_parent(specimen, monkeypatch):
    real = capture.os.rename
    calls = []
    def rename(stage, final):
        assert stage.parent == final.parent == _final(specimen).parent
        calls.append((stage, final))
        return real(stage, final)
    monkeypatch.setattr(capture.os, "rename", rename)
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    assert len(calls) == 1


@_WINDOWS_CAPTURE_ONLY
@pytest.mark.parametrize("bad_id", [0, None, "unstable"])
def test_unusable_windows_identity_prevents_rename(specimen, monkeypatch, bad_id):
    real = capture.os.lstat
    calls = []
    def lstat(path, *args, **kwargs):
        info = real(path, *args, **kwargs)
        inode = bad_id if bad_id != "unstable" else info.st_ino + len(calls)
        calls.append(path)
        return SimpleNamespace(st_mode=info.st_mode, st_ino=inode, st_dev=info.st_dev,
                               st_file_attributes=getattr(info, "st_file_attributes", 0))
    monkeypatch.setattr(capture.os, "lstat", lstat)
    monkeypatch.setattr(capture.os, "rename", lambda *a: pytest.fail("rename must not run"))
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"


@_WINDOWS_CAPTURE_ONLY
def test_large_stable_nonzero_windows_file_identity_has_no_width_bound(specimen, monkeypatch):
    real = capture.os.lstat
    def lstat(path, *args, **kwargs):
        info = real(path, *args, **kwargs)
        return SimpleNamespace(st_mode=info.st_mode, st_ino=info.st_ino + 2**100, st_dev=info.st_dev,
                               st_file_attributes=getattr(info, "st_file_attributes", 0))
    monkeypatch.setattr(capture.os, "lstat", lstat)
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    assert len(_verify(specimen)["observations"]) == 500


@_WINDOWS_CAPTURE_ONLY
def test_capture_metrics_are_retained_without_changing_rows(specimen):
    before = copy.deepcopy(specimen["result"])
    status = capture.capture_h5_measurement(**specimen)
    assert status.state == "CAPTURED" and type(status.elapsed_ns) is int and status.elapsed_ns >= 0
    assert status.published_files == 2
    receipt = json.loads((_final(specimen) / "capture.json").read_text())
    paths = (_final(specimen)/"capture.json", _final(specimen)/"evidence"/receipt["evidence"]["location"])
    assert status.logical_bytes == sum(p.stat().st_size for p in paths)
    assert specimen["result"] == before


@_WINDOWS_CAPTURE_ONLY
def test_metrics_unavailable_does_not_invalidate_verified_bundle(specimen, monkeypatch):
    monkeypatch.setattr(capture, "_published_metrics", lambda *args: (_ for _ in ()).throw(OSError()))
    status = capture.capture_h5_measurement(**specimen)
    assert status.state == "CAPTURED" and status.logical_bytes is None and status.published_files is None
    assert len(_verify(specimen)["observations"]) == 500


@_WINDOWS_CAPTURE_ONLY
def test_reused_receipt_does_not_claim_fresh_producer_window(specimen):
    specimen["earlier"] = "tests/unit/acp/test_fixture.py::test_earlier"
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    receipt = _verify(specimen)["receipt"]
    assert receipt["reuse_state"] == "REUSED" and receipt["producer_window"] == "unknown"
    assert receipt["producer_nodeid"] == specimen["earlier"]


@_WINDOWS_CAPTURE_ONLY
@pytest.mark.parametrize("error", [KeyboardInterrupt(), shutdown.ExecutingSourceMismatch("SOURCE_REFUSAL")])
def test_control_flow_and_source_refusal_escape_capture(specimen, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(capture, "_validate_result", fail)
    with pytest.raises(type(error)) as found:
        capture.capture_h5_measurement(**specimen)
    assert found.value is error


def test_non_windows_branch_is_simulated_and_does_no_io(specimen, monkeypatch):
    """SIMULATED platform branch on Windows; never WSL/native non-Windows evidence."""
    monkeypatch.setattr(capture, "_platform", "linux")
    monkeypatch.setattr(capture, "validate_capture_directory", lambda *a: pytest.fail("no filesystem on unsupported platform"))
    assert capture.capture_h5_measurement(**specimen).state == "UNSUPPORTED"


@_WINDOWS_CAPTURE_ONLY
def test_schema_with_reference_is_refused_before_writing(specimen, monkeypatch):
    monkeypatch.setattr(capture, "_schema_definitions", lambda: [{"$ref": "#/$defs/other"}])
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"
    assert not _final(specimen).exists()


@_WINDOWS_CAPTURE_ONLY
@pytest.mark.parametrize("length", [301, 1025, 1400])
@pytest.mark.parametrize("suffix", ["", "|\x01password=metadata"])
def test_formatter_outputs_fit_both_frozen_content_free_schemas(specimen, length, suffix):
    filename = "<" + "界" * length + suffix + ">"
    error = None
    try:
        exec(compile("raise OSError(5, 'PRIVATE_MESSAGE')", filename, "exec"), {})
    except OSError as exc:
        error = exc
    assert error is not None
    effect = shutdown._probe_error_effect("orderly_eof", error)
    assert "PRIVATE_MESSAGE" not in effect and "password=" not in effect and len(effect) > length
    assert "\x01" not in effect
    if suffix:
        assert "<label>=metadata" in effect  # Existing formatter masks labels, not arbitrary path substrings.
    specimen["result"]["observations"][0].update(close_outcome="ERROR", cause_effect=effect)
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    assert _verify(specimen)["observations"][0]["cause_effect"] == effect


@_WINDOWS_CAPTURE_ONLY
def test_formatter_unknown_locations_fit_both_frozen_schemas(specimen):
    effect = shutdown._probe_error_effect("orderly_eof", OSError("PRIVATE_MESSAGE"))
    assert "PRIVATE_MESSAGE" not in effect and "origin=unknown" in effect and "probe=unknown" in effect
    specimen["result"]["observations"][0].update(close_outcome="ERROR", cause_effect=effect)
    assert capture.capture_h5_measurement(**specimen).state == "CAPTURED"
    assert _verify(specimen)["observations"][0]["cause_effect"] == effect


@_WINDOWS_CAPTURE_ONLY
def test_root_mismatch_relative_paths_and_escaped_sidecar_are_refused(specimen):
    specimen["context"].worktree = str(specimen["repository_root"].parent)
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"
    specimen["context"].worktree = str(specimen["repository_root"])
    specimen["directory"] = Path("relative-capture")
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"


def _junction(link: Path, target: Path) -> None:
    # Windows owned temporary junctions require no elevation or live service.
    import _winapi
    _winapi.CreateJunction(str(target), str(link))


@_WINDOWS_CAPTURE_ONLY
def test_parent_replaced_by_owned_junction_aborts_before_rename(specimen, monkeypatch, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"unchanged")
    real = capture.evidence_store.write_evidence_sidecar
    real_rename = capture.os.rename
    def write(**kwargs):
        reference = real(**kwargs)
        parent = _final(specimen).parent
        real_rename(parent, parent.with_name(parent.name + "-retained"))
        _junction(parent, outside)
        return reference
    monkeypatch.setattr(capture.evidence_store, "write_evidence_sidecar", write)
    monkeypatch.setattr(capture.os, "rename", lambda *a: pytest.fail("rename must not run"))
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"
    assert sentinel.read_bytes() == b"unchanged" and not (outside / "h5").exists()


@_WINDOWS_CAPTURE_ONLY
def test_race_created_junction_destination_is_never_replaced(specimen, monkeypatch, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"unchanged")
    real = capture.evidence_store.write_evidence_sidecar
    def write(**kwargs):
        reference = real(**kwargs)
        _junction(_final(specimen), outside)
        return reference
    monkeypatch.setattr(capture.evidence_store, "write_evidence_sidecar", write)
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"
    assert sentinel.read_bytes() == b"unchanged" and not (outside / "capture.json").exists()


@_WINDOWS_CAPTURE_ONLY
def test_capture_os_fault_does_not_patch_process_os(specimen, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_LSTAT")
    monkeypatch.setattr(capture.os, "lstat", fail)
    # A sampler/recorder still uses the real process-wide OS module.
    assert os.lstat(specimen["repository_root"]).st_ino > 0
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"



@pytest.mark.skipif(sys.platform != "win32", reason="native Windows IO")
def test_capture_path_budget(specimen, tmp_path, monkeypatch):
    from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _budget_tempfile_facade, _pad_budget_directory

    before = copy.deepcopy(specimen["result"])
    _, _, reference = capture.evidence_store.build_evidence_payload(record_id=capture.RECORD_ID,
        entry=capture.ENTRY, binding=specimen["binding"].to_dict(), result=specimen["result"])
    # mkdtemp has '.h5-' + eight random characters; its evidence parent must be 175.
    tail = len(str(Path(specimen["context"].run_id) / (".h5-" + "0" * 8) / "evidence"))
    specimen["directory"] = _pad_budget_directory(tmp_path, 175 - tail - 1)
    facts = {"kind": "ISSUE287_V19_PATH_BUDGET", "mode": "native_capture", "pid": os.getpid()}
    monkeypatch.setattr(capture.evidence_store, "tempfile", _budget_tempfile_facade(reference.location, facts, simulated=False))
    try:
        status = capture.capture_h5_measurement(**specimen)
        facts["capture_status"] = status.state
        assert status.state == "CAPTURED", "ISSUE287_CAPTURE_PATH_PUBLICATION"
        restored = _verify(specimen)
        assert len(restored["observations"]) == 500 and restored["observations"] == before["observations"]
        assert restored["receipt"]["binding"] == specimen["binding"].to_dict()
        assert specimen["result"] == before and facts["created_temp_length"] < 260
    finally:
        (tmp_path / "path-budget.json").write_text(json.dumps(facts, sort_keys=True), encoding="utf-8")
        print("ISSUE287_V19_PATH_FACTS " + json.dumps({**facts, "proof": str(tmp_path / "path-budget.json")}, sort_keys=True))


@_WINDOWS_CAPTURE_ONLY
def test_non_ascii_error_type_is_refused_before_publication(specimen):
    error = type("Échec", (OSError,), {})("PRIVATE_MESSAGE")
    effect = shutdown._probe_error_effect("orderly_eof", error)
    specimen["result"]["observations"][0].update(close_outcome="ERROR", cause_effect=effect)
    assert capture.capture_h5_measurement(**specimen).state == "INVALID"
    assert not (specimen["directory"] / specimen["context"].run_id).exists()
