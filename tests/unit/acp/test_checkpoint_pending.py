"""#598: the continuation checkpoint's ``pending`` is true only when an approval was requested and left unanswered.

The real ACP adapter with the scripted runner, and a recording stand-in for the session's continuity writer, so the
test sees the exact ``Settled`` the turn submits.
"""

from __future__ import annotations

from pathlib import Path

from optimus.context.memory_continuity import Settled
from tests.unit.acp.test_prompt_stop_reason_meta import BIG_PLAN, _Scripted, _scripted_turn, _Turn


class _Recorder:
    def __init__(self) -> None:
        self.settled: list[Settled] = []

    def submit(self, settled: Settled) -> None:
        self.settled.append(settled)


async def _open(tmp_path: Path, runner: _Scripted, *, small_record: bool = False) -> tuple[_Turn, _Recorder]:
    turn = _scripted_turn(tmp_path, runner, small_record=small_record)
    await turn.open()
    recorder = _Recorder()
    turn.adapter._sessions.get(turn.session_id).continuity = recorder
    return turn, recorder


async def test_an_oversized_plan_refusal_checkpoints_no_pending_approval(tmp_path: Path) -> None:
    turn, recorder = await _open(tmp_path, _Scripted(plan_text=BIG_PLAN), small_record=True)

    await turn.prompt()

    assert turn.outbound.requests == [], "no permission was asked"
    [settled] = recorder.settled
    assert (settled.outcome, settled.pending) == ("failed", False)


async def test_a_plan_without_a_hash_checkpoints_no_pending_approval(tmp_path: Path) -> None:
    turn, recorder = await _open(tmp_path, _Scripted(hashed=False), small_record=True)

    await turn.prompt()

    assert turn.outbound.requests == [], "no permission was asked"
    [settled] = recorder.settled
    assert (settled.outcome, settled.pending) == ("rejected", False)
