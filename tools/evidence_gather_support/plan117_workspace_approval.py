"""Local approval ceremony and recovery for the Plan 11.7 current-client collector."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from optimus.acp.launch_approvals import ApprovalError, DurableWriteIntent
from optimus.runtime import process_tree
from tools.evidence_gather_support import plan117_current_client_contract as contract
from tools.evidence_gather_support.common import HostError

_TTY_SECONDS = 180.0
_VERIFY_SECONDS = 45.0
_STOP_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class ApprovalWorkspace:
    arm: str
    workspace: Path
    source: Path


@dataclass(frozen=True, slots=True)
class LaunchApproval:
    workspace_digest: str
    approval_id: str
    record_digest: str


def scoped_process_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {
        name: value for name, value in environ.items()
        if not name.upper().startswith("PYTHON") or name.upper() == "PYTHON_KEYRING_BACKEND"
    }


def _write_journal(path: Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class NativeWorkspaceApprovals:
    """The TTY and every potentially written receipt stay in the run's custody."""

    def __init__(self, control_dir: Path | None, workspaces: Sequence[ApprovalWorkspace], environment: Mapping[str, str]):
        if control_dir is None or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise HostError("scoped_approval_tty_or_control_missing")
        self.directory = control_dir
        self.workspaces = {item.arm: item for item in workspaces}
        self.environment = dict(environment)
        self.interpreter = Path(sys.executable).resolve(strict=True)
        self.launcher_hashes: dict[Path, str] = {}
        self.states: dict[str, dict[str, str]] = {}
        self.intent_paths = {item.arm: self.directory / f"{item.arm}.intent.json" for item in workspaces}
        self.command_stop_unconfirmed = False

    @classmethod
    def resume(cls, control_dir: Path, run_root: Path, environment: Mapping[str, str]) -> NativeWorkspaceApprovals:
        try:
            control_dir = control_dir.resolve(strict=True)
            run_root = run_root.resolve(strict=True)
            if control_dir.is_relative_to(run_root) or run_root.is_relative_to(control_dir):
                raise ValueError
            journal = control_dir / "approval-recovery.json"
            with journal.open("rb") as stream:
                document = contract.strict_json_loads(stream.read(65536))
            states = document["arms"]
            if (
                type(states) is not dict or document["control"] != control_dir.name
                or not states or not states.keys() <= set(contract.ARM_IDS)
            ):
                raise ValueError
            workspaces = []
            for arm, state in states.items():
                workspace = run_root / "arms" / arm / "workspace"
                source_kind = contract.source_kind_for_arm(arm)
                source = run_root / "src" / source_kind.replace(":", "-").replace("_", "-")
                if (
                    workspace.resolve() != workspace or source.resolve(strict=True) != source
                    or (Path(state["workspace"]), Path(state["source"])) != (workspace, source)
                ):
                    raise ValueError
                workspaces.append(ApprovalWorkspace(arm, workspace, source))
            resumed = cls(control_dir, workspaces, environment)
            for item in workspaces:
                state = states[item.arm]
                launcher = control_dir / f"trust-{item.source.name}.py"
                expected = resumed._launcher_bytes(item)
                digest = hashlib.sha256(expected).hexdigest()
                if (
                    launcher.read_bytes() != expected or state["trust_launcher_sha256"] != digest
                    or state["trust_source_sha256"] != resumed._source_hash(item)
                    or state["interpreter"] != str(resumed.interpreter)
                    or state["interpreter_sha256"] != hashlib.sha256(resumed.interpreter.read_bytes()).hexdigest()
                ):
                    raise ValueError
                resumed.launcher_hashes[launcher] = digest
            resumed.states = states
            return resumed
        except (OSError, KeyError, TypeError, ValueError, contract.ContractError) as exc:
            raise HostError("scoped_approval_recovery_journal_invalid") from exc

    @staticmethod
    def _launcher_bytes(item: ApprovalWorkspace) -> bytes:
        return (
            "import sys\n"
            f"sys.path.insert(0, {str(item.source / 'src')!r})\n"
            "from optimus.acp.launch_approval_cli import main\n"
            "raise SystemExit(main())\n"
        ).encode("utf-8")

    @staticmethod
    def _source_hash(item: ApprovalWorkspace) -> str:
        return hashlib.sha256((item.source / "src/optimus/acp/launch_approval_cli.py").read_bytes()).hexdigest()

    def _state(self, arm: str, state: str, **fields: str) -> None:
        self.states[arm] = {
            **self.states.get(arm, {}), "state": state, "updated_utc": datetime.now(timezone.utc).isoformat(), **fields,
        }
        _write_journal(self.directory / "approval-recovery.json", {"control": self.directory.name, "arms": self.states})

    def _command(self, item: ApprovalWorkspace, *args: str, tty: bool = False) -> subprocess.CompletedProcess[str]:
        launcher = self.directory / f"trust-{item.source.name}.py"
        if hashlib.sha256(launcher.read_bytes()).hexdigest() != self.launcher_hashes.get(launcher):
            raise HostError("scoped_trust_launcher_changed")
        command = [str(self.interpreter), "-I", str(launcher), "--workspace-root", str(item.workspace), *args]
        self.command_stop_unconfirmed = True
        try:
            child = process_tree.popen(
                command, cwd=self.directory, env=dict(self.environment), text=True, encoding="utf-8",
                stdin=None if tty else subprocess.DEVNULL,
                stdout=None if tty else subprocess.PIPE,
                stderr=None if tty else subprocess.PIPE,
            )
        except process_tree.ContainmentError as exc:
            self.command_stop_unconfirmed = not exc.stopped
            raise HostError("scoped_approval_process_refused") from exc
        deadline = time.monotonic() + (_TTY_SECONDS if tty else _VERIFY_SECONDS)
        try:
            stdout, stderr = child.communicate(timeout=max(0.0, deadline - time.monotonic()))
            if not process_tree.wait_for_empty(child, deadline=deadline):
                raise subprocess.TimeoutExpired(command, 0)
        except BaseException:
            self.command_stop_unconfirmed = True
            try:
                process_tree.kill_tree(child)
                stopped = process_tree.wait_for_empty(child, deadline=time.monotonic() + _STOP_SECONDS)
            except Exception:  # noqa: BLE001 - an unknown cleanup must retain the journal and workspace
                stopped = False
            self.command_stop_unconfirmed = not stopped
            raise
        self.command_stop_unconfirmed = False
        if not tty:
            with (self.directory / "approval-diagnostics.ndjson").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"arm": item.arm, "command": args[0], "exit": child.returncode, "stderr": stderr[-4096:]}) + "\n")
        return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)

    def approve_all(self) -> None:
        self.directory.mkdir()
        for item in self.workspaces.values():
            launcher = self.directory / f"trust-{item.source.name}.py"
            if launcher not in self.launcher_hashes:
                with launcher.open("xb") as stream:
                    stream.write(self._launcher_bytes(item))
                self.launcher_hashes[launcher] = hashlib.sha256(launcher.read_bytes()).hexdigest()
            result = self._command(item, "scoped-preflight")
            if result.returncode:
                raise HostError("scoped_approval_preflight_refused")
            try:
                identity = json.loads(result.stdout)
                digest = identity["workspace_digest"]
                if len(bytes.fromhex(digest)) != 32 or len(digest) != 64 or identity["git_context"] != "absent":
                    raise ValueError
                if Path(identity["canonical_path"]).resolve(strict=True) != item.workspace:
                    raise ValueError
            except (ValueError, TypeError, KeyError) as exc:
                raise HostError("scoped_approval_identity_invalid") from exc
            self._state(
                item.arm, "prepared", workspace=str(item.workspace), workspace_digest=digest, source=str(item.source),
                interpreter=str(self.interpreter), trust_launcher_sha256=self.launcher_hashes[launcher],
                interpreter_sha256=hashlib.sha256(self.interpreter.read_bytes()).hexdigest(),
                trust_source_sha256=self._source_hash(item),
                device=str(identity["device"]), inode=str(identity["inode"]), git_context=identity["git_context"],
            )

        for item in self.workspaces.values():
            digest = self.states[item.arm]["workspace_digest"]
            self._state(item.arm, "ceremony_pending")
            result = self._command(item, "scoped-approve", str(self.intent_paths[item.arm]), digest, tty=True)
            if result.returncode != 0:
                if result.returncode == 1 and not self.intent_paths[item.arm].exists():
                    self._state(item.arm, "prepared")
                raise HostError("scoped_approval_declined_or_failed")
            self.verify(item.arm)
            self._state(item.arm, "verified", approved="true")

    def verify(self, arm: str) -> LaunchApproval:
        state = self.states[arm]
        digest = state["workspace_digest"]
        path = self.intent_paths[arm]
        result = self._command(self.workspaces[arm], "scoped-verify", str(path), digest)
        if result.returncode:
            raise HostError("scoped_approval_verification_refused")
        try:
            verified = json.loads(result.stdout)
            intent = DurableWriteIntent.read(path)
            expected = {
                "workspace_digest": digest, "approval_id": intent.approval_id, "record_digest": intent.record_digest,
                "configuration_sha256": verified["configuration_sha256"],
            }
            if verified != expected or any(state.get(key, value) != value for key, value in expected.items()):
                raise ValueError
        except (ValueError, TypeError, KeyError) as exc:
            raise HostError("scoped_approval_identity_changed") from exc
        self._state(arm, state["state"], **expected)
        return LaunchApproval(digest, intent.approval_id, intent.record_digest)

    def recover(self, *, processes_stopped: bool) -> bool:
        if not processes_stopped or self.command_stop_unconfirmed:
            for arm, state in list(self.states.items()):
                if state["state"] not in {"prepared", "cleared"}:
                    self._state(arm, "held_unconfirmed")
            return False
        clean = True
        for arm, state in reversed(list(self.states.items())):
            if state["state"] in {"prepared", "cleared"}:
                continue
            try:
                if state.get("recovery_discrepancy") == "unexpected_absence":
                    clean = False
                    continue
                if not self.intent_paths[arm].exists() and state.get("approved") != "true":
                    preflight = self._command(self.workspaces[arm], "scoped-preflight", state["workspace_digest"])
                    if preflight.returncode:
                        raise HostError("scoped_approval_recovery_mismatch")
                    self._state(arm, "cleared")
                    continue
                intent = DurableWriteIntent.read(self.intent_paths[arm])
                if (
                    intent.workspace_digest != state["workspace_digest"]
                    or state.get("approval_id", intent.approval_id) != intent.approval_id
                    or state.get("record_digest", intent.record_digest) != intent.record_digest
                ):
                    raise HostError("scoped_approval_recovery_mismatch")
                self._state(arm, "revoke_intent", approval_id=intent.approval_id, record_digest=intent.record_digest, revoke_started="true")
                result = self._command(self.workspaces[arm], "scoped-revoke", str(self.intent_paths[arm]), tty=True)
                if result.returncode == 3 and state.get("approved") == "true" and state.get("revoke_started") != "true":
                    clean = False
                    self._state(arm, "conflict", recovery_discrepancy="unexpected_absence")
                    continue
                if result.returncode not in {0, 3}:
                    raise HostError("scoped_approval_revoke_refused")
                self._state(arm, "cleared")
            except (ApprovalError, HostError, OSError, subprocess.SubprocessError):
                clean = False
                self._state(arm, "conflict")
                if self.command_stop_unconfirmed:
                    break
        return clean
