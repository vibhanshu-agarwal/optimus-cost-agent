"""The host's side of the memory store route (Plan 12.11; ADR-042): `POST /v1/context/memory` through the host's own Gateway URL
and key, so the attach identity binds this traffic too. Engine contracts in and out; the Gateway owns Redis and its secret.

Only the Gate's drafts are appended. A change's idempotency key is derived from the candidate and the version it was decided
against, so a retry of the same decision replays the first result and a decision taken on a moved head is a new change.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from context_engine.memory_contracts import (
    CheckpointResult,
    ContinuationCheckpoint,
    MemoryCandidate,
    MemoryCommitResult,
    StoredCheckpoint,
    StoredEvent,
)
from context_engine.memory_gate import EventDraft
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.memory_extraction import ExistingItem, digest
from optimus.usage.savings_report import ReportTransportError, gateway_post
from optimus_security import memory_store_contract as msc

LEASE_TTL_MS = 30_000  # one job's writes; released when the job ends


class MemoryStoreUnavailable(Exception):
    """The store cannot answer now (outage, timeout, verification). Whatever was sent is uncertain until a retry reconciles it."""


class MemoryStoreRefused(Exception):
    """The store answered no; `code` is its stable reason (LEASE_HELD, VERSION_CONFLICT, MEMORY_NOT_ADMITTING, ...)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GatewayMemoryStore:
    def __init__(self, settings: OptimusGatewaySettings, *, project: str, owner: str,
                 post: Callable[..., Callable[[bytes], tuple[int, Any]]] = gateway_post) -> None:
        self.project = project
        self._owner = owner
        self._post = post(settings, timeout=msc.DEADLINE_SECONDS + 2.0, path=msc.PATH)
        # Plan 12.11 recovery: `guard` says the project needs recovery (no write may land first); `written` hears of each
        # confirmed change, so the recovery copy knows it is dirty and what a withdrawal retires.
        self.guard: Callable[..., bool] | None = None
        self.written: Callable[[str, str], None] | None = None

    def call(self, op: str, **fields: Any) -> dict[str, Any]:
        body = json.dumps({"op": op, **fields}, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        try:
            status, reply = self._post(body)
        except (ReportTransportError, OSError) as exc:
            raise MemoryStoreUnavailable("the memory route cannot be reached") from exc
        if status == 200 and isinstance(reply, Mapping):
            return dict(reply)
        code = reply.get("error") if isinstance(reply, Mapping) else None
        if status in {502, 503, 504} or code is None:
            raise MemoryStoreUnavailable(str(code or f"status {status}"))
        raise MemoryStoreRefused(str(code))

    @contextlib.contextmanager
    def lease(self, *, guarded: bool = True) -> Iterator[int]:
        """The project's write lease for one job, released afterwards. Another session's lease is a refusal, not a wait. A
        project that needs recovery takes no write but the restore (`guarded=False`)."""
        if guarded and self.guard is not None and self.guard():
            raise MemoryStoreRefused("RECOVERY_REQUIRED")
        token = int(self.call("lease", project=self.project, owner=self._owner, action="acquire", ttl_ms=LEASE_TTL_MS)["token"])
        try:
            # asked again now, under the lease: a store emptied since the cached answer takes no write (Codex CP3 review 1, finding 4)
            if guarded and self.guard is not None and self.guard(fresh=True):
                raise MemoryStoreRefused("RECOVERY_REQUIRED")
            yield token
        finally:
            with contextlib.suppress(MemoryStoreUnavailable, MemoryStoreRefused):  # an expired lease ends by itself
                self.call("lease", project=self.project, owner=self._owner, action="release", token=token)

    def renew(self, token: int) -> None:
        """Keep this job's lease for another `LEASE_TTL_MS` (a long import); a lost lease is refused, never retaken."""
        self.call("lease", project=self.project, owner=self._owner, action="renew", ttl_ms=LEASE_TTL_MS, token=token)

    def append(self, token: int, candidate: MemoryCandidate, draft: EventDraft) -> MemoryCommitResult:
        key = digest(f"{candidate.idempotency_key}\0{draft.item}\0{draft.expected_version}")
        event = {"event_id": f"e-{key[:24]}", "item": draft.item, "version": draft.expected_version + 1, "action": draft.action,
                 "trust": draft.trust, "status": draft.status, "kind": draft.kind, "scope": draft.scope, "title": draft.title,
                 "statement": draft.statement, "anchors": list(draft.anchors), "lineage": list(draft.lineage), "valid_from_ms": 0,
                 "valid_until_ms": 0}
        reply = self.call("append", project=self.project, token=token, expected_version=draft.expected_version, idempotency_key=key,
                          event=event)
        result = MemoryCommitResult(reply["event_id"], reply["item"], reply["version"], reply["durable_state"], reply["projection_state"])
        self._heard(draft.action, result.item, result.durable_state)
        return result

    def _heard(self, action: str, item: str, durable_state: str) -> None:
        if durable_state == "confirmed" and self.written is not None:
            with contextlib.suppress(Exception):  # the copy's bookkeeping never fails a confirmed change
                self.written(action, item)

    def read(self, item: str) -> StoredEvent | None:
        record = self.call("read", project=self.project, item=item)["item"]
        return None if record is None else StoredEvent.from_record(self.project, record)

    def items(self, scope: str, *, limit: int, cursor: str | None = None) -> tuple[list[StoredEvent], str | None]:
        """One page of every confirmed item in a scope (live, off, withdrawn and purged), for `/memory`."""
        rows, after, _watermark = self.page(scope, limit=limit, cursor=cursor)
        return rows, after

    def page(self, scope: str, *, limit: int, cursor: str | None = None) -> tuple[list[StoredEvent], str | None, str]:
        """`items`, with the confirmed stream position the Gateway answered from (#514)."""
        reply = self.call("list", project=self.project, scope=scope, limit=limit, **({"cursor": cursor} if cursor else {}))
        return [StoredEvent.from_record(self.project, record) for record in reply["items"]], reply["cursor"], str(reply["watermark"])

    def history(self, item: str, *, limit: int, before: int | None = None) -> tuple[list[dict[str, Any]], bool]:
        """One page of an item's versions, newest first, and whether older ones remain (Q4)."""
        reply = self.call("history", project=self.project, item=item, limit=limit, **({"before": before} if before else {}))
        return list(reply["versions"]), bool(reply["more"])

    def checkpoint(self, token: int, point: ContinuationCheckpoint) -> CheckpointResult:
        """One settled turn's continuation checkpoint, under the project's lease; a retry of the same one replays it."""
        reply = self.call("checkpoint", project=self.project, token=token, checkpoint=point.to_record())
        return CheckpointResult(reply["session"], reply["sequence"], reply["stream_id"], reply["durable_state"], reply["projection_state"],
                                bool(reply.get("replayed", False)))

    def checkpoints(self, *, limit: int, branch: str | None = None, worktree: str | None = None) -> list[StoredCheckpoint]:
        """The project's newest confirmed checkpoints, newest first: all of them, or one branch's, or one branch and worktree's."""
        scope = {**({"branch": branch} if branch is not None else {}), **({"worktree": worktree} if worktree is not None else {})}
        reply = self.call("checkpoints", project=self.project, limit=limit, **scope)
        return [StoredCheckpoint.from_record(self.project, record) for record in reply["checkpoints"]]

    def purge(self, token: int, item: str, key: str) -> dict[str, Any]:
        reply = self.call("purge", project=self.project, token=token, item=item, idempotency_key=key)
        self._heard("tombstone", item, str(reply.get("durable_state")))
        return reply

    def purge_status(self, item: str) -> dict[str, Any]:
        return self.call("purge_status", project=self.project, item=item)

    def user_items(self, scope: str, *, limit: int) -> list[ExistingItem]:
        """Live user-authored items in one scope, for a retraction to name; at most `limit`, never the payloads."""
        found: list[ExistingItem] = []
        cursor: str | None = None
        while len(found) < limit:
            reply = self.call("list", project=self.project, scope=scope, limit=msc.MAX_LIST, **({"cursor": cursor} if cursor else {}))
            found += [ExistingItem(record["item"], record["title"]) for record in reply["items"]
                      if record["trust"] == "user-authored" and record["status"] in ("active", "reverify")]
            cursor = reply["cursor"]
            if cursor is None:
                break
        return found[:limit]
