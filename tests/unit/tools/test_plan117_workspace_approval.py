"""Offline recovery and drain checks for the scoped Plan 11.7 acquisition."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp.launch_approvals import DurableWriteIntent
from tests.unit.acp.test_launch_approvals_multipart import WindowsLimitKeyring, _record, _store
from tools import evidence_gather
from tools import probe_p11_zed_session_load as probe
from tools.evidence_gather_support import plan117_workspace_approval as scope


def test_recovery_command_requires_explicit_stop_attestation(tmp_path, monkeypatch):
    control = tmp_path / "control"
    run = tmp_path / "run"
    command = ["recover-plan117-v5-approvals", "--control-dir", str(control), "--run-root", str(run)]
    calls = []

    def recover(args):
        calls.append((args.control_dir, args.run_root, args.confirm_processes_stopped))
        return 0

    monkeypatch.setattr(evidence_gather, "_handle_recover_plan117_v5_approvals", recover)
    with pytest.raises(SystemExit) as missing_attestation:
        evidence_gather.main(command)
    assert missing_attestation.value.code == 2
    assert not calls
    assert evidence_gather.main([*command, "--confirm-processes-stopped"]) == 0
    assert calls == [(control, run, True)]


@pytest.fixture
def coordinator(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    root = tmp_path / "run"
    sources = {"a_prime": "load-only-stub", "r_refusal": "refusal-stub-r-refusal"}
    records = []
    for arm, token in sources.items():
        source = root / "src" / token
        workspace = root / "arms" / arm / "workspace"
        workspace.mkdir(parents=True)
        cli = source / "src" / "optimus" / "acp" / "launch_approval_cli.py"
        cli.parent.mkdir(parents=True)
        cli.write_text("# fake source", encoding="utf-8")
        records.append(scope.ApprovalWorkspace(arm, workspace, source))
    session = scope.NativeWorkspaceApprovals(tmp_path / "control", records, {})
    return session, root, _store(tmp_path, WindowsLimitKeyring())


@pytest.mark.parametrize("failure", ["decline", "before-intent", "after-intent", "receipt-mismatch", "held", "revoke-interrupt", "unexpected-absence", None])
def test_journal_recovers_the_exact_owned_scopes(coordinator, monkeypatch, failure):
    session, root, store = coordinator
    commands = []
    interrupted = False

    def invoke(self, item, command, *args, tty=False):
        nonlocal interrupted
        digest = hashlib.sha256(item.arm.encode()).hexdigest()
        record = _record(digest=digest)
        commands.append((item.arm, command, tty))
        reply = {}
        code = 0
        if command == "scoped-preflight":
            store.require_empty_durable(digest, "b" * 64)
            reply = dict(workspace_digest=digest, canonical_path=str(item.workspace), device=1, inode=2, git_context="absent")
        elif command == "scoped-approve":
            if item.arm == "r_refusal" and failure in {"decline", "before-intent"}:
                code = 1 if failure == "decline" else 2
            else:
                store.publish_durable_if_absent(record, "b" * 64, lambda intent: intent.persist(Path(args[0])))
                code = 2 if item.arm == "r_refusal" and failure == "after-intent" else 0
        else:
            receipt = DurableWriteIntent.read(Path(args[0]))
            if command == "scoped-verify":
                reply = dict(workspace_digest=digest, approval_id=receipt.approval_id, record_digest=receipt.record_digest,
                             configuration_sha256="a" * 64)
                if item.arm == "r_refusal" and failure == "receipt-mismatch":
                    reply["record_digest"] = "c" * 64
            elif command == "scoped-revoke":
                removed = store.revoke_exact_durable(receipt)
                if item.arm == "r_refusal" and failure == "revoke-interrupt" and not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt
                code = 0 if removed else 3
        return subprocess.CompletedProcess([command], code, json.dumps(reply), "")

    monkeypatch.setattr(scope.NativeWorkspaceApprovals, "_command", invoke)
    if failure in {"decline", "before-intent", "after-intent", "receipt-mismatch"}:
        with pytest.raises(scope.HostError):
            session.approve_all()
    else:
        session.approve_all()
    assert [command[1] for command in commands[:2]] == ["scoped-preflight", "scoped-preflight"]
    if failure == "held":
        prior_commands = list(commands)
        assert not session.recover(processes_stopped=False)
        assert commands == prior_commands
        assert {state["state"] for state in session.states.values()} == {"held_unconfirmed"}
    if failure == "revoke-interrupt":
        with pytest.raises(KeyboardInterrupt):
            session.recover(processes_stopped=True)
        assert session.states["r_refusal"]["state"] == "revoke_intent"
    if failure == "unexpected-absence":
        store.revoke_exact_durable(DurableWriteIntent.read(session.intent_paths["r_refusal"]))
    resumed = scope.NativeWorkspaceApprovals.resume(session.directory, root, {})
    assert resumed.recover(processes_stopped=True) is (failure != "unexpected-absence")
    assert resumed.states["a_prime"]["state"] == "cleared"
    assert resumed.states["r_refusal"]["state"] in {"cleared", "prepared", "conflict"}
    assert not store._keyring.keys()
    assert all(tty for _, command, tty in commands if command in {"scoped-approve", "scoped-revoke"})


def test_noninteractive_command_keeps_diagnostics_in_private_control_directory(coordinator, monkeypatch):
    session, _, _ = coordinator
    item = session.workspaces["a_prime"]
    session.directory.mkdir()
    launcher = session.directory / f"trust-{item.source.name}.py"
    launcher.write_bytes(session._launcher_bytes(item))
    session.launcher_hashes[launcher] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    diagnostic = "test-private-diagnostic" * 250
    child = SimpleNamespace(communicate=lambda **_: ("{}", diagnostic), returncode=2)
    monkeypatch.setattr(scope.process_tree, "popen", lambda argv, **kwargs: child)
    monkeypatch.setattr(scope.process_tree, "wait_for_empty", lambda *args, **kwargs: True)

    result = session._command(item, "scoped-verify")

    assert result.returncode == 2
    retained = session.directory / "approval-diagnostics.ndjson"
    assert json.loads(retained.read_text(encoding="utf-8")) == {
        "arm": "a_prime", "command": "scoped-verify", "exit": 2, "stderr": diagnostic[-4096:],
    }
    assert retained.parent == session.directory


def test_tty_deadline_kills_the_owned_ceremony_and_checks_drain(coordinator, monkeypatch):
    session, _, _ = coordinator
    item = session.workspaces["a_prime"]
    session.directory.mkdir()
    launcher = session.directory / f"trust-{item.source.name}.py"
    launcher.write_bytes(session._launcher_bytes(item))
    session.launcher_hashes[launcher] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    events = []

    def timeout(*, timeout):
        assert 0 < timeout <= scope._TTY_SECONDS
        raise subprocess.TimeoutExpired("scoped-approve", timeout)

    child = SimpleNamespace(communicate=timeout)
    monkeypatch.setattr(scope.process_tree, "popen", lambda argv, **kwargs: child)
    monkeypatch.setattr(scope.process_tree, "kill_tree", lambda process: events.append(("kill", process)))
    monkeypatch.setattr(scope.process_tree, "wait_for_empty", lambda process, *, deadline: events.append(("drain", process)) or True)
    with pytest.raises(subprocess.TimeoutExpired):
        session._command(item, "scoped-approve", tty=True)
    assert events == [("kill", child), ("drain", child)]
    assert not session.command_stop_unconfirmed


@pytest.mark.parametrize("outcome", ["drained", "forced", "untracked", "interrupted"])
def test_scoped_zed_waits_for_job_drain_before_final_observation(monkeypatch, outcome):
    order = []

    def poll():
        if outcome == "interrupted" and not order:
            order.append("interrupted")
            raise KeyboardInterrupt
        return 0

    def wait(process, *, deadline):
        order.append("drain")
        if outcome == "untracked":
            raise ValueError("untracked Job")
        return outcome != "forced" or "kill" in order

    monkeypatch.setattr(probe.process_tree, "wait_for_empty", wait)
    monkeypatch.setattr(probe.process_tree, "kill_tree", lambda process: order.append("kill"))
    result = probe._wait_scoped_zed(
        SimpleNamespace(pid=42, poll=poll), lambda notify: order.append(notify) or True, timeout_s=1, drain_timeout_s=1,
    )
    assert result["tree_stopped"] is (outcome != "untracked")
    assert result["readiness_verified"] is (outcome in {"forced", "drained"})
    assert result["timed_out"] is (outcome != "drained")
    assert result["interrupted"] is (outcome == "interrupted")
    assert (False in order and order[-1] is False) is (outcome in {"forced", "drained"})
