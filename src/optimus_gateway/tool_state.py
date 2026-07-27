"""Gateway-owned search provenance and call-cap state.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 3. This module is a separately
deployable Gateway boundary: its live backend talks directly to Redis through
the already-declared top-level ``redis>=5`` dependency. It must never import
``optimus.*``, reuse ``optimus.redis.*`` helpers, or depend on the agent-side
``RedisAgentStateStore``/wrapper -- ``optimus_gateway`` stays independently
deployable. Provenance is keyed by ``run_id``; call caps are keyed by
``run_id`` + ``tool_class``. Provider result bodies never enter this module.

Unavailability of the configured backend always fails closed: callers get a
``GatewayToolStateUnavailable`` exception, never a silent switch to
``InMemoryGatewayToolStateStore``, which exists purely as a unit-test double.
"""
from __future__ import annotations

import itertools
import threading
import uuid
from typing import Protocol

import redis

from optimus_gateway.models import ToolClass

_DEFAULT_PROVENANCE_TTL_SECONDS = 3600
_DEFAULT_CALL_CAP_TTL_SECONDS = 3600

# Direct redis-py exceptions this module treats as "backend unavailable" and
# maps to the fail-closed GatewayToolStateUnavailable boundary.
_REDIS_UNAVAILABLE_ERRORS: tuple[type[Exception], ...] = (
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
    OSError,
)


class GatewayToolCallCapExceeded(RuntimeError):
    """Raised when a run_id + tool_class call counter would exceed its configured cap."""

    def __init__(self, *, run_id: str, tool_class: str, max_calls: int) -> None:
        super().__init__(f"call cap exceeded for run_id={run_id!r} tool_class={tool_class!r} (max_calls={max_calls})")
        self.run_id = run_id
        self.tool_class = tool_class
        self.max_calls = max_calls


class GatewayToolStateUnavailable(RuntimeError):
    """Raised when the configured Gateway tool state backend cannot be reached.

    Callers must fail closed on this exception; there is no automatic
    fallback to an in-memory or otherwise non-authoritative state store.
    """


class GatewayToolStateStore(Protocol):
    def record_search(self, *, run_id: str, source_urls: tuple[str, ...]) -> str: ...

    def search_result_urls(self, *, run_id: str) -> frozenset[str]: ...

    def increment_call(self, *, run_id: str, tool_class: ToolClass, max_calls: int) -> int: ...


class InMemoryGatewayToolStateStore:
    """Unit-test-only dependency double. Never used as the live Gateway state backend."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._search_results: dict[str, set[str]] = {}
        self._call_counts: dict[tuple[str, str], int] = {}
        self._search_id_counter = itertools.count(1)

    def record_search(self, *, run_id: str, source_urls: tuple[str, ...]) -> str:
        with self._lock:
            bucket = self._search_results.setdefault(run_id, set())
            bucket.update(source_urls)
            search_id = f"search-{next(self._search_id_counter)}"
        return search_id

    def search_result_urls(self, *, run_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self._search_results.get(run_id, ()))

    def increment_call(self, *, run_id: str, tool_class: ToolClass, max_calls: int) -> int:
        key = (run_id, str(tool_class))
        with self._lock:
            count = self._call_counts.get(key, 0) + 1
            if count > max_calls:
                raise GatewayToolCallCapExceeded(run_id=run_id, tool_class=str(tool_class), max_calls=max_calls)
            self._call_counts[key] = count
            return count


class RedisGatewayToolStateStore:
    """Direct ``redis>=5`` client boundary for Gateway-owned tool state.

    Uses atomic ``INCR`` for the call-cap counter and a bounded-TTL Redis set
    for search-result provenance. Constructed with an already-connected
    client (or via :meth:`from_url`); never wraps or delegates to the
    agent-side Redis runtime.
    """

    def __init__(
        self,
        *,
        client: object,
        provenance_ttl_seconds: int = _DEFAULT_PROVENANCE_TTL_SECONDS,
        call_cap_ttl_seconds: int = _DEFAULT_CALL_CAP_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._provenance_ttl_seconds = provenance_ttl_seconds
        self._call_cap_ttl_seconds = call_cap_ttl_seconds

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        provenance_ttl_seconds: int = _DEFAULT_PROVENANCE_TTL_SECONDS,
        call_cap_ttl_seconds: int = _DEFAULT_CALL_CAP_TTL_SECONDS,
        socket_connect_timeout: float = 2.0,
        socket_timeout: float = 2.0,
    ) -> "RedisGatewayToolStateStore":
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )
        return cls(
            client=client,
            provenance_ttl_seconds=provenance_ttl_seconds,
            call_cap_ttl_seconds=call_cap_ttl_seconds,
        )

    @property
    def redis_client(self) -> object:
        return self._client

    def record_search(self, *, run_id: str, source_urls: tuple[str, ...]) -> str:
        search_id = f"search-{uuid.uuid4().hex}"
        key = _search_key(run_id)
        with _fail_closed():
            if source_urls:
                self._client.sadd(key, *source_urls)
                self._client.expire(key, self._provenance_ttl_seconds)
        return search_id

    def search_result_urls(self, *, run_id: str) -> frozenset[str]:
        key = _search_key(run_id)
        with _fail_closed():
            members = self._client.smembers(key)
        return frozenset(members)

    def increment_call(self, *, run_id: str, tool_class: ToolClass, max_calls: int) -> int:
        key = _call_cap_key(run_id=run_id, tool_class=tool_class)
        with _fail_closed():
            new_count = self._client.incr(key)
            if new_count == 1:
                self._client.expire(key, self._call_cap_ttl_seconds)
            if new_count > max_calls:
                self._client.decr(key)
                raise GatewayToolCallCapExceeded(run_id=run_id, tool_class=str(tool_class), max_calls=max_calls)
        return new_count

    def ping(self) -> None:
        with _fail_closed():
            self._client.ping()


class _fail_closed:
    """Context manager mapping direct redis-py connection failures to GatewayToolStateUnavailable."""

    def __enter__(self) -> "_fail_closed":
        return self

    def __exit__(self, exc_type, exc, _tb) -> bool:
        if exc_type is not None and issubclass(exc_type, _REDIS_UNAVAILABLE_ERRORS):
            raise GatewayToolStateUnavailable(str(exc)) from exc
        return False


def _search_key(run_id: str) -> str:
    return f"gateway:tool:search:{run_id}"


def _call_cap_key(*, run_id: str, tool_class: ToolClass) -> str:
    return f"gateway:tool:callcap:{run_id}:{tool_class}"
