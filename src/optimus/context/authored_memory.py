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

from context_engine.memory_contracts import MemoryCandidate, MemoryCommitResult, StoredEvent
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
    def lease(self) -> Iterator[int]:
        """The project's write lease for one job, released afterwards. Another session's lease is a refusal, not a wait."""
        token = int(self.call("lease", project=self.project, owner=self._owner, action="acquire", ttl_ms=LEASE_TTL_MS)["token"])
        try:
            yield token
        finally:
            with contextlib.suppress(MemoryStoreUnavailable, MemoryStoreRefused):  # an expired lease ends by itself
                self.call("lease", project=self.project, owner=self._owner, action="release", token=token)

    def append(self, token: int, candidate: MemoryCandidate, draft: EventDraft) -> MemoryCommitResult:
        key = digest(f"{candidate.idempotency_key}\0{draft.item}\0{draft.expected_version}")
        event = {"event_id": f"e-{key[:24]}", "item": draft.item, "version": draft.expected_version + 1, "action": draft.action,
                 "trust": draft.trust, "status": draft.status, "kind": draft.kind, "scope": draft.scope, "title": draft.title,
                 "statement": draft.statement, "anchors": list(draft.anchors), "lineage": list(draft.lineage), "valid_from_ms": 0,
                 "valid_until_ms": 0}
        reply = self.call("append", project=self.project, token=token, expected_version=draft.expected_version, idempotency_key=key,
                          event=event)
        return MemoryCommitResult(reply["event_id"], reply["item"], reply["version"], reply["durable_state"], reply["projection_state"])

    def read(self, item: str) -> StoredEvent | None:
        record = self.call("read", project=self.project, item=item)["item"]
        return None if record is None else StoredEvent.from_record(self.project, record)

    def items(self, scope: str, *, limit: int, cursor: str | None = None) -> tuple[list[StoredEvent], str | None]:
        """One page of every confirmed item in a scope (live, off, withdrawn and purged), for `/memory`."""
        reply = self.call("list", project=self.project, scope=scope, limit=limit, **({"cursor": cursor} if cursor else {}))
        return [StoredEvent.from_record(self.project, record) for record in reply["items"]], reply["cursor"]

    def history(self, item: str, *, limit: int, before: int | None = None) -> tuple[list[dict[str, Any]], bool]:
        """One page of an item's versions, newest first, and whether older ones remain (Q4)."""
        reply = self.call("history", project=self.project, item=item, limit=limit, **({"before": before} if before else {}))
        return list(reply["versions"]), bool(reply["more"])

    def purge(self, token: int, item: str, key: str) -> dict[str, Any]:
        return self.call("purge", project=self.project, token=token, item=item, idempotency_key=key)

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
