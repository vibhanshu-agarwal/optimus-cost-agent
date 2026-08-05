"""Path A: run real origin-a-prompt-retry against dead control endpoint; record fail-closed."""

from __future__ import annotations

import hashlib
import json
import shutil
import traceback
from pathlib import Path

from tools.plan117_custody_relay import SCHEMA_CONTROL_DESCRIPTOR, _descriptor_sha256
from tools.run_plan117_custody_feasibility import (
    STATE_FILENAME,
    CustodyRunnerError,
    init_phase_state,
    main,
    mark_phase_complete,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate"
)
WS = BASE / "path-a-workspace"
CAP = BASE / "path-a-capture"
CUSTODY = CAP / "custody"
OUT_DIR = BASE / "path-a-run"


def main_path_a() -> int:
    for path in (WS, CAP, CUSTODY, OUT_DIR):
        path.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(ROOT / "pyproject.toml", WS / "pyproject.toml")

    # Settings under custody so Path A never touches operator Zed settings.
    settings_path = CUSTODY / "settings.json"
    if not settings_path.is_file():
        settings_path.write_text("{}\n", encoding="utf-8")
    settings_before = settings_path.read_bytes()

    zed_source = CAP / "zed-source-placeholder"
    zed_source.mkdir(exist_ok=True)
    (zed_source / "README.path-a.txt").write_text(
        "Path A placeholder zed-source; no Zed launch authorized.\n",
        encoding="utf-8",
    )
    debug_log = CAP / "debug-acp.ndjson"
    debug_log.write_text("", encoding="utf-8")
    zed_exe = Path(r"C:\Users\pc\AppData\Local\Programs\Zed\bin\Zed.exe")

    state_path = CAP / STATE_FILENAME
    if state_path.exists():
        state_path.unlink()
    init_phase_state(state_path)
    for phase in ("direct-control", "relay-control", "origin-a"):
        mark_phase_complete(state_path, phase)

    exchange = json.loads(
        (
            ROOT
            / "reports/plan-11-7-server-custody-artifacts/amendments/"
            "origin-a-fixture-v2/origin-a-3-exchange-facts.json"
        ).read_text(encoding="utf-8")
    )
    launch_identity_path = OUT_DIR / "launch-session-identity.json"
    launch_payload = {
        "schema": "plan117-custody-launch-session-identity-v1",
        "run_attempt_id": "origin-a-3",
        "zed_pid": 0,
        "zed_process_start_time_utc": "1970-01-01T00:00:00Z",
        "connection_id": "path-a-no-live-connection",
        "acp_session_id": exchange["acp_session_id"],
        "notes": {
            "path": "A",
            "source": (
                "public origin-a-3-exchange-facts.json session id; "
                "pid/connection placeholders because live session is dead "
                "and Path A does not read private custody"
            ),
        },
    }
    launch_identity_path.write_text(
        json.dumps(launch_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    descriptor_path = OUT_DIR / "relay-control-descriptor.json"
    provisional = {
        "schema": SCHEMA_CONTROL_DESCRIPTOR,
        "run_attempt_id": "origin-a-3",
        "endpoint_kind": "af_pipe",
        "endpoint_path": r"\\.\pipe\plan117-relay-control-origin-a-3-path-a-dead",
        "connection_id": "path-a-no-live-connection",
        "owner_id": "path-a-operator",
        "authkey_hex": "00" * 32,
        "terminal": False,
        "prompt_sealed": False,
    }
    provisional["descriptor_sha256"] = _descriptor_sha256(provisional)
    descriptor_path.write_text(
        json.dumps(
            provisional, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )

    stage_ledger = (
        ROOT
        / "reports/plan-11-7-server-custody-artifacts/amendments/"
        "origin-a-fixture-v2/stage-ledger.json"
    )
    prompt_fixture = (
        ROOT / "tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt"
    )

    argv = [
        "origin-a-prompt-retry",
        "--run-attempt-id",
        "origin-a-3",
        "--prompt-fixture",
        str(prompt_fixture),
        "--workspace-root",
        str(WS),
        "--capture-root",
        str(CAP),
        "--zed-executable",
        str(zed_exe),
        "--zed-source",
        str(zed_source),
        "--settings-path",
        str(settings_path),
        "--debug-log",
        str(debug_log),
        "--custody-root",
        str(CUSTODY),
        "--stage-ledger",
        str(stage_ledger),
        "--launch-identity",
        str(launch_identity_path),
        "--relay-control-descriptor",
        str(descriptor_path),
        "--caller-owner-id",
        "path-a-operator",
        "--no-operator-wait",
    ]

    result: dict[str, object] = {
        "schema": "plan117-retry-preflight-path-a-cli-result-v1",
        "path": "A",
        "argv": argv,
        "settings_path_used": str(settings_path),
        "settings_is_operator_zed_settings": False,
        "ok": False,
    }
    try:
        code = main(argv)
        result["exit_code"] = code
        result["ok"] = code == 0
        result["unexpected_success"] = True
    except CustodyRunnerError as exc:
        result["exit_code"] = 1
        result["ok"] = False
        result["reason_code"] = exc.reason_code
        result["field_path"] = exc.field_path
        result["exception_type"] = type(exc).__name__
        result["traceback"] = traceback.format_exc()
    except Exception as exc:  # noqa: BLE001
        result["exit_code"] = 1
        result["ok"] = False
        result["exception_type"] = type(exc).__name__
        result["exception_message"] = str(exc)
        result["traceback"] = traceback.format_exc()

    settings_after = settings_path.read_bytes()
    result["settings_bytes_sha256"] = hashlib.sha256(settings_after).hexdigest()
    result["settings_unchanged"] = settings_after == settings_before
    result["settings_mutated"] = False
    result["zed_launched"] = False
    result["reservation_exists"] = (
        CAP / "reservations" / "origin-a-3-prompt-3.json"
    ).is_file()
    result["origin_a4_attempt_exists"] = (CAP / "attempts" / "origin-a-4").exists()

    out_path = OUT_DIR / "cli-result.json"
    out_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    printable = {k: v for k, v in result.items() if k != "traceback"}
    print(json.dumps(printable, indent=2, sort_keys=True))
    print("WROTE", out_path)
    return 0 if result.get("reason_code") else 1


if __name__ == "__main__":
    raise SystemExit(main_path_a())
