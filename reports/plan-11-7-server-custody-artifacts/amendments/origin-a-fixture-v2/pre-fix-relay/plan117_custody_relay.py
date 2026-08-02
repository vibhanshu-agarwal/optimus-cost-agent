"""Opaque full-duplex byte relay for Plan 11.7 custody feasibility.

Capture layout (documented): ``{capture-root}/{run-id}/``

  - ``zed-to-agent.bin`` — raw bytes from parent stdin to child stdin
  - ``agent-to-zed.bin`` — raw bytes from child stdout to parent stdout
  - ``relay-index.ndjson`` — gap-free per-chunk index (LF)
  - ``relay-summary.json`` — terminal summary via ``atomic_write_json`` (LF)

CLI::

    plan117_custody_relay.py --capture-root ABS --run-id ID --child-executable ABS -- <argv>

Relay-only args never reach the child. The live path never decodes ACP bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, BinaryIO, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan117_custody_contract import (  # noqa: E402
    CustodyContractError,
    atomic_write_json,
    sha256_file,
)

SCHEMA_INDEX = "plan117-custody-relay-index-v1"
SCHEMA_SUMMARY = "plan117-custody-relay-summary-v1"
DIR_ZED_TO_AGENT = "zed_to_agent"
DIR_AGENT_TO_ZED = "agent_to_zed"
EOF_ZED_TO_AGENT = "zed_to_agent_eof"
EOF_AGENT_TO_ZED = "agent_to_zed_eof"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
READ_CHUNK = 1 << 16  # 64 KiB
REASON_RECORDER_FAILURE = "relay_recorder_failure"
REASON_INTERRUPTED = "relay_interrupted"
REASON_BROKEN_PIPE = "relay_broken_pipe"

PopenFactory = Callable[..., Any]


class RelayRecorderError(RuntimeError):
    """Internal recorder failure; never falls back to an uncaptured path."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class _LockedRecorder:
    """Append-only raw + index recorder with one lock for both directions."""

    def __init__(self, run_dir: Path, run_id: str, origin_monotonic: float) -> None:
        self._lock = threading.Lock()
        self._run_id = run_id
        self._origin = origin_monotonic
        self._sequence = 0
        self._offsets = {DIR_ZED_TO_AGENT: 0, DIR_AGENT_TO_ZED: 0}
        self._failed = False
        self._reason: str | None = None
        run_dir.mkdir(parents=True, exist_ok=True)
        self._bins = {
            DIR_ZED_TO_AGENT: (run_dir / "zed-to-agent.bin").open("wb"),
            DIR_AGENT_TO_ZED: (run_dir / "agent-to-zed.bin").open("wb"),
        }
        self._index = (run_dir / "relay-index.ndjson").open("w", encoding="utf-8", newline="\n")

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def reason_code(self) -> str | None:
        return self._reason

    def record_chunk(self, direction: str, chunk: bytes) -> None:
        if direction not in self._bins:
            raise RelayRecorderError("relay_invalid_direction")
        with self._lock:
            if self._failed:
                raise RelayRecorderError(self._reason or REASON_RECORDER_FAILURE)
            try:
                handle = self._bins[direction]
                offset = self._offsets[direction]
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                digest = hashlib.sha256(chunk).hexdigest()
                record = {
                    "schema": SCHEMA_INDEX,
                    "run_id": self._run_id,
                    "sequence": self._sequence,
                    "direction": direction,
                    "monotonic_offset_ns": int((time.monotonic() - self._origin) * 1_000_000_000),
                    "directional_offset": offset,
                    "size": len(chunk),
                    "sha256": digest,
                }
                self._index.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
                self._index.write("\n")
                self._index.flush()
                os.fsync(self._index.fileno())
                self._sequence += 1
                self._offsets[direction] = offset + len(chunk)
            except (OSError, ValueError) as exc:
                self._failed = True
                self._reason = REASON_RECORDER_FAILURE
                raise RelayRecorderError(REASON_RECORDER_FAILURE) from exc

    def record_eof(self, direction: str) -> None:
        eof_direction = {
            DIR_ZED_TO_AGENT: EOF_ZED_TO_AGENT,
            DIR_AGENT_TO_ZED: EOF_AGENT_TO_ZED,
        }[direction]
        with self._lock:
            if self._failed:
                raise RelayRecorderError(self._reason or REASON_RECORDER_FAILURE)
            try:
                record = {
                    "schema": SCHEMA_INDEX,
                    "run_id": self._run_id,
                    "sequence": self._sequence,
                    "direction": eof_direction,
                    "monotonic_offset_ns": int((time.monotonic() - self._origin) * 1_000_000_000),
                    "directional_offset": self._offsets[direction],
                    "size": 0,
                    "sha256": EMPTY_SHA256,
                }
                self._index.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
                self._index.write("\n")
                self._index.flush()
                os.fsync(self._index.fileno())
                self._sequence += 1
            except (OSError, ValueError) as exc:
                self._failed = True
                self._reason = REASON_RECORDER_FAILURE
                raise RelayRecorderError(REASON_RECORDER_FAILURE) from exc

    def close(self) -> None:
        with self._lock:
            for handle in self._bins.values():
                try:
                    handle.close()
                except OSError:
                    pass
            try:
                self._index.close()
            except OSError:
                pass

    def totals(self) -> dict[str, int]:
        with self._lock:
            return dict(self._offsets)


def _forward_parent_to_child(
    *,
    parent_in: BinaryIO,
    child_stdin: BinaryIO,
    recorder: _LockedRecorder,
    stop: threading.Event,
    errors: list[BaseException],
) -> None:
    try:
        while not stop.is_set():
            chunk = parent_in.read(READ_CHUNK)
            if not chunk:
                break
            recorder.record_chunk(DIR_ZED_TO_AGENT, chunk)
            try:
                child_stdin.write(chunk)
                child_stdin.flush()
            except BrokenPipeError as exc:
                errors.append(exc)
                return
        recorder.record_eof(DIR_ZED_TO_AGENT)
        try:
            child_stdin.close()
        except OSError:
            pass
    except (RelayRecorderError, KeyboardInterrupt, OSError) as exc:
        errors.append(exc)


def _forward_child_to_parent(
    *,
    child_stdout: BinaryIO,
    parent_out: BinaryIO,
    recorder: _LockedRecorder,
    stop: threading.Event,
    errors: list[BaseException],
) -> None:
    try:
        while not stop.is_set():
            chunk = child_stdout.read(READ_CHUNK)
            if not chunk:
                break
            recorder.record_chunk(DIR_AGENT_TO_ZED, chunk)
            parent_out.write(chunk)
            parent_out.flush()
        recorder.record_eof(DIR_AGENT_TO_ZED)
    except (RelayRecorderError, KeyboardInterrupt, OSError) as exc:
        errors.append(exc)


def _terminate_owned_child(proc: Any) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=2.0)
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass


def _close_child_pipes(proc: Any) -> None:
    for name in ("stdin", "stdout"):
        stream = getattr(proc, name, None)
        if stream is None:
            continue
        try:
            stream.close()
        except OSError:
            pass


def _argv_digest(argv: Sequence[str]) -> str:
    encoded = "\0".join(argv).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relay_module_digest() -> str:
    return sha256_file(Path(__file__).resolve())


def _emit_stderr(stderr: TextIO | BinaryIO, reason_code: str) -> None:
    line = reason_code + "\n"
    try:
        # Prefer text path for TextIO / StringIO; fall back to bytes for binary buffers.
        write = stderr.write
        try:
            write(line)  # type: ignore[arg-type]
        except TypeError:
            write(line.encode("utf-8"))  # type: ignore[arg-type]
        stderr.flush()
    except OSError:
        pass


def _write_summary(
    run_dir: Path,
    *,
    run_id: str,
    child_argv: Sequence[str],
    child_exit_code: int | None,
    totals: dict[str, int],
    zed_eof: bool,
    agent_eof: bool,
    terminal_disposition: str,
    reason_code: str | None,
) -> None:
    argv_list = [str(item) for item in child_argv]
    payload = {
        "schema": SCHEMA_SUMMARY,
        "run_id": run_id,
        "child_argv": argv_list,
        "child_argv_sha256": _argv_digest(argv_list),
        "relay_sha256": _relay_module_digest(),
        "child_exit_code": child_exit_code,
        "zed_to_agent_bytes": totals.get(DIR_ZED_TO_AGENT, 0),
        "agent_to_zed_bytes": totals.get(DIR_AGENT_TO_ZED, 0),
        "zed_to_agent_eof": zed_eof,
        "agent_to_zed_eof": agent_eof,
        "terminal_disposition": terminal_disposition,
        "reason_code": reason_code,
    }
    atomic_write_json(run_dir / "relay-summary.json", payload)


def run_relay(
    *,
    capture_root: Path,
    run_id: str,
    child_executable: str | Path,
    child_args: Sequence[str],
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | BinaryIO | None = None,
    popen_factory: PopenFactory | None = None,
    recorder_hook: Callable[[_LockedRecorder], None] | None = None,
) -> int:
    """Launch the child and relay opaque bytes; return the child exit code (or nonzero on failure)."""
    parent_in = stdin if stdin is not None else sys.stdin.buffer
    parent_out = stdout if stdout is not None else sys.stdout.buffer
    err_out: TextIO | BinaryIO = stderr if stderr is not None else sys.stderr
    run_dir = Path(capture_root) / run_id
    child_argv = [str(child_executable), *[str(a) for a in child_args]]
    factory = popen_factory or subprocess.Popen
    origin = time.monotonic()
    recorder = _LockedRecorder(run_dir, run_id, origin)
    if recorder_hook is not None:
        recorder_hook(recorder)

    stop = threading.Event()
    errors: list[BaseException] = []
    proc: Any | None = None
    terminal_disposition = "child_exited"
    reason_code: str | None = None
    child_exit: int | None = None

    try:
        proc = factory(
            child_argv,
            env=None,
            cwd=None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # inherit
            shell=False,
            bufsize=0,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None

        t_in = threading.Thread(
            target=_forward_parent_to_child,
            kwargs={
                "parent_in": parent_in,
                "child_stdin": proc.stdin,
                "recorder": recorder,
                "stop": stop,
                "errors": errors,
            },
            name="relay-zed-to-agent",
            daemon=True,
        )
        t_out = threading.Thread(
            target=_forward_child_to_parent,
            kwargs={
                "child_stdout": proc.stdout,
                "parent_out": parent_out,
                "recorder": recorder,
                "stop": stop,
                "errors": errors,
            },
            name="relay-agent-to-zed",
            daemon=True,
        )
        t_in.start()
        t_out.start()
        t_in.join()
        t_out.join()

        if errors:
            first = errors[0]
            if isinstance(first, KeyboardInterrupt):
                terminal_disposition = "interrupted"
                reason_code = REASON_INTERRUPTED
            elif isinstance(first, RelayRecorderError):
                terminal_disposition = "recorder_failure"
                reason_code = first.reason_code
            elif isinstance(first, BrokenPipeError):
                terminal_disposition = "broken_pipe"
                reason_code = REASON_BROKEN_PIPE
            else:
                terminal_disposition = "recorder_failure"
                reason_code = REASON_RECORDER_FAILURE
            stop.set()
            _close_child_pipes(proc)
            _terminate_owned_child(proc)
            _emit_stderr(err_out, reason_code)
            child_exit = proc.poll()
            if child_exit is None:
                child_exit = 1
            return_code = 1 if reason_code else int(child_exit)
        else:
            child_exit = proc.wait()
            return_code = int(child_exit)
    except KeyboardInterrupt:
        terminal_disposition = "interrupted"
        reason_code = REASON_INTERRUPTED
        if proc is not None:
            _close_child_pipes(proc)
            _terminate_owned_child(proc)
        _emit_stderr(err_out, reason_code)
        return_code = 1
        child_exit = proc.poll() if proc is not None else 1
    except Exception:
        terminal_disposition = "recorder_failure"
        reason_code = REASON_RECORDER_FAILURE
        if proc is not None:
            _close_child_pipes(proc)
            _terminate_owned_child(proc)
        _emit_stderr(err_out, reason_code)
        return_code = 1
        child_exit = proc.poll() if proc is not None else 1
    finally:
        totals = recorder.totals()
        index_path = run_dir / "relay-index.ndjson"
        zed_eof = False
        agent_eof = False
        recorder.close()
        if index_path.is_file():
            try:
                for line in index_path.read_text(encoding="utf-8").splitlines():
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("direction") == EOF_ZED_TO_AGENT:
                        zed_eof = True
                    elif record.get("direction") == EOF_AGENT_TO_ZED:
                        agent_eof = True
            except (OSError, json.JSONDecodeError):
                pass
        try:
            _write_summary(
                run_dir,
                run_id=run_id,
                child_argv=child_argv,
                child_exit_code=child_exit,
                totals=totals,
                zed_eof=zed_eof,
                agent_eof=agent_eof,
                terminal_disposition=terminal_disposition,
                reason_code=reason_code,
            )
        except Exception:
            # Summary write failure still leaves prior reason on stderr.
            if reason_code is None:
                reason_code = REASON_RECORDER_FAILURE
                _emit_stderr(err_out, reason_code)
            return_code = 1

    return int(return_code)


def verify_relay_capture(run_dir: Path) -> None:
    """Offline verification of a relay capture directory.

    Rejects mutated raw bytes, chunk sizes, offsets, sequences, directions,
    digests, run IDs, child argv digest, relay digest, and terminal exit
    records. Requires both directional EOF markers.
    """
    run_dir = Path(run_dir)
    summary_path = run_dir / "relay-summary.json"
    index_path = run_dir / "relay-index.ndjson"
    zed_path = run_dir / "zed-to-agent.bin"
    agent_path = run_dir / "agent-to-zed.bin"

    for path, field in (
        (summary_path, "relay-summary.json"),
        (index_path, "relay-index.ndjson"),
        (zed_path, "zed-to-agent.bin"),
        (agent_path, "agent-to-zed.bin"),
    ):
        if not path.is_file() or path.is_symlink():
            raise CustodyContractError("relay_capture_incomplete", field)

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CustodyContractError("relay_summary_invalid", "relay-summary.json") from exc
    if not isinstance(summary, dict):
        raise CustodyContractError("relay_summary_invalid", "relay-summary.json")
    if summary.get("schema") != SCHEMA_SUMMARY:
        raise CustodyContractError("relay_summary_schema_mismatch", "schema")
    run_id = summary.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise CustodyContractError("relay_run_id_invalid", "run_id")

    if "child_argv_sha256" not in summary or not isinstance(summary["child_argv_sha256"], str):
        raise CustodyContractError("relay_child_argv_digest_missing", "child_argv_sha256")
    child_argv = summary.get("child_argv")
    if not isinstance(child_argv, list) or not all(isinstance(item, str) for item in child_argv):
        raise CustodyContractError("relay_child_argv_missing", "child_argv")
    expected_argv_digest = _argv_digest(child_argv)
    if str(summary["child_argv_sha256"]).lower() != expected_argv_digest.lower():
        raise CustodyContractError("relay_child_argv_digest_mismatch", "child_argv_sha256")
    if "relay_sha256" not in summary or not isinstance(summary["relay_sha256"], str):
        raise CustodyContractError("relay_digest_missing", "relay_sha256")
    if "terminal_disposition" not in summary:
        raise CustodyContractError("relay_terminal_disposition_missing", "terminal_disposition")
    if "child_exit_code" not in summary:
        raise CustodyContractError("relay_terminal_exit_missing", "child_exit_code")

    expected_relay = _relay_module_digest()
    if str(summary["relay_sha256"]).lower() != expected_relay.lower():
        raise CustodyContractError("relay_digest_mismatch", "relay_sha256")

    zed_raw = zed_path.read_bytes()
    agent_raw = agent_path.read_bytes()
    if int(summary.get("zed_to_agent_bytes", -1)) != len(zed_raw):
        raise CustodyContractError("relay_directional_length_mismatch", "zed_to_agent_bytes")
    if int(summary.get("agent_to_zed_bytes", -1)) != len(agent_raw):
        raise CustodyContractError("relay_directional_length_mismatch", "agent_to_zed_bytes")

    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CustodyContractError("relay_index_unreadable", "relay-index.ndjson") from exc

    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines):
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CustodyContractError("relay_index_invalid", f"relay-index.ndjson:{line_no}") from exc
        if not isinstance(record, dict):
            raise CustodyContractError("relay_index_invalid", f"relay-index.ndjson:{line_no}")
        records.append(record)

    if not records:
        raise CustodyContractError("relay_index_empty", "relay-index.ndjson")

    seen_eof = {EOF_ZED_TO_AGENT: False, EOF_AGENT_TO_ZED: False}
    expected_seq = 0
    cursors = {DIR_ZED_TO_AGENT: 0, DIR_AGENT_TO_ZED: 0}
    blobs = {DIR_ZED_TO_AGENT: zed_raw, DIR_AGENT_TO_ZED: agent_raw}
    prev_mono = -1

    for index, record in enumerate(records):
        field = f"relay-index.ndjson[{index}]"
        if record.get("schema") != SCHEMA_INDEX:
            raise CustodyContractError("relay_index_schema_mismatch", f"{field}.schema")
        if record.get("run_id") != run_id:
            raise CustodyContractError("relay_run_id_mismatch", f"{field}.run_id")
        if int(record.get("sequence", -1)) != expected_seq:
            raise CustodyContractError("relay_sequence_gap", f"{field}.sequence")
        expected_seq += 1
        mono = int(record.get("monotonic_offset_ns", -1))
        if mono < prev_mono:
            raise CustodyContractError("relay_monotonic_regression", f"{field}.monotonic_offset_ns")
        prev_mono = mono
        direction = record.get("direction")
        if direction in (EOF_ZED_TO_AGENT, EOF_AGENT_TO_ZED):
            if int(record.get("size", -1)) != 0:
                raise CustodyContractError("relay_eof_size_nonzero", f"{field}.size")
            if record.get("sha256") != EMPTY_SHA256:
                raise CustodyContractError("relay_eof_digest_mismatch", f"{field}.sha256")
            base = DIR_ZED_TO_AGENT if direction == EOF_ZED_TO_AGENT else DIR_AGENT_TO_ZED
            if int(record.get("directional_offset", -1)) != cursors[base]:
                raise CustodyContractError("relay_offset_mismatch", f"{field}.directional_offset")
            seen_eof[direction] = True
            continue
        if direction not in blobs:
            raise CustodyContractError("relay_direction_invalid", f"{field}.direction")
        size = int(record.get("size", -1))
        offset = int(record.get("directional_offset", -1))
        if size < 0:
            raise CustodyContractError("relay_chunk_size_invalid", f"{field}.size")
        if offset != cursors[direction]:
            raise CustodyContractError("relay_offset_mismatch", f"{field}.directional_offset")
        chunk = blobs[direction][offset : offset + size]
        if len(chunk) != size:
            raise CustodyContractError("relay_raw_bytes_mismatch", f"{field}.size")
        digest = hashlib.sha256(chunk).hexdigest()
        if digest != record.get("sha256"):
            raise CustodyContractError("relay_chunk_digest_mismatch", f"{field}.sha256")
        cursors[direction] = offset + size

    if cursors[DIR_ZED_TO_AGENT] != len(zed_raw) or cursors[DIR_AGENT_TO_ZED] != len(agent_raw):
        raise CustodyContractError("relay_raw_bytes_mismatch", "directional_bins")

    if not seen_eof[EOF_ZED_TO_AGENT] or not summary.get("zed_to_agent_eof"):
        raise CustodyContractError("relay_missing_directional_eof", "zed_to_agent_eof")
    if not seen_eof[EOF_AGENT_TO_ZED] or not summary.get("agent_to_zed_eof"):
        raise CustodyContractError("relay_missing_directional_eof", "agent_to_zed_eof")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--child-executable", type=Path, required=True)
    parser.add_argument(
        "child_args",
        nargs=argparse.REMAINDER,
        help="Exact child argv after --",
    )
    args = parser.parse_args(argv)
    child_args = list(args.child_args)
    if child_args and child_args[0] == "--":
        child_args = child_args[1:]
    return run_relay(
        capture_root=args.capture_root.resolve(),
        run_id=args.run_id,
        child_executable=args.child_executable.resolve(),
        child_args=child_args,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
