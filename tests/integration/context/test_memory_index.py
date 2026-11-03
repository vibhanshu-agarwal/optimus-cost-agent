"""Plan 12.10 Task 2: the context-index route over real HTTP, on the released dedicated Redis under its real ACL.

Selected with `-m requires_plan12_index_redis`, excluded from every default and profile run; see this folder's conftest for how
the resource is provisioned. Each test works in scopes of its own.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import struct
import threading
import uuid
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
import redis

from optimus_gateway import memory_index
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_security import memory_index_contract as mic
from tests.integration.context.conftest import Provisioned

pytestmark = [pytest.mark.requires_plan12_index_redis]

_SECRET = "index-test-secret"  # pragma: allowlist secret - synthetic test fixture
_DIMENSIONS = 8
_REVISION = "a" * 64


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vector(*leading: float) -> str:
    values = [*leading, *([0.0] * (_DIMENSIONS - len(leading)))]
    return mic.encode_vector(struct.pack(f"<{_DIMENSIONS}f", *values))


def _file(path: str, content_hash: str, **extra: Any) -> dict[str, Any]:
    return {"id": _h(f"file:{path}:{content_hash}"), "kind": "file", "path": path, "path_id": _h(path), "file_hash": content_hash,
            "language": "python", "terms": path.replace("/", " ").replace(".", " ").lower(), "modified": 100, **extra}


def _symbol(path: str, content_hash: str, symbol: str, terms: str, vector: str) -> dict[str, Any]:
    return {"id": _h(f"sym:{path}:{content_hash}:{symbol}"), "kind": "symbol", "path": path, "path_id": _h(path), "file_hash": content_hash,
            "language": "python", "symbol": symbol, "signature": f"def {symbol}()", "terms": terms, "start_line": 1, "end_line": 2,
            "vector": vector}


@pytest.fixture(scope="module")
def client(provisioned: Provisioned) -> Iterator[redis.Redis]:
    connection = provisioned.connect()
    yield connection
    connection.close()


@pytest.fixture
def gateway(client: redis.Redis) -> Iterator[int]:
    store = memory_index.IndexStore(client, cursor_key=b"c" * 32)
    config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=_SECRET, provider="openrouter",
                                  provider_api_key="sk-or-test",  # pragma: allowlist secret - synthetic test fixture
                                  base_url="http://127.0.0.1:9/api/v1")
    server = serve_gateway(config=replace(config, memory_index=memory_index.IndexService(store)), upstream_client=object())  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(5)


class Rpc:
    def __init__(self, port: int) -> None:
        self.port = port
        self.scope = _h(uuid.uuid4().hex)

    def raw(self, body: bytes, *, secret: str = _SECRET) -> tuple[int, dict[str, Any]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("POST", mic.PATH, body, {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def call(self, op: str, *, scope: str | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
        return self.raw(json.dumps({"op": op, "scope": scope or self.scope, **fields}).encode("utf-8"))

    def ok(self, op: str, **fields: Any) -> dict[str, Any]:
        status, body = self.call(op, **fields)
        assert status == 200, body
        return body

    def refused(self, code: str, op: str, **fields: Any) -> None:
        status, body = self.call(op, **fields)
        assert status != 200 and body == mic.error_body(code), (status, body)

    def open_line(self) -> int:
        self.ok("generation", action="open", embedding="test-embedding", dimensions=_DIMENSIONS, schema_version=1)
        return self.ok("lease", action="acquire", owner="ab" * 8, ttl_ms=30000, kind="scope")["token"]

    def publish(self, token: int, epoch: int, *, complete: bool = True, files: int = 1) -> dict[str, Any]:
        return self.ok("generation", action="publish", token=token, epoch=epoch, revision=_REVISION, dirty=False,
                       coverage={"complete": complete, "files_indexed": files, "files_total": files})


@pytest.fixture
def rpc(gateway: int) -> Rpc:
    return Rpc(gateway)


def _paths(body: dict[str, Any]) -> list[str]:
    return sorted(file["path"] for file in body["files"])


def test_nothing_is_visible_until_it_is_published(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=epoch, records=[_file("a.py", "1" * 64), _symbol("a.py", "1" * 64, "alpha", "alpha one", _vector(1))])
    rpc.refused("NOT_PUBLISHED", "query", mode="lexical", terms=["alpha"], k=5)
    rpc.refused("NOT_PUBLISHED", "catalogue")
    rpc.publish(token, epoch)
    found = rpc.ok("query", mode="lexical", terms=["alpha"], k=5)
    assert [record["symbol"] for record in found["records"]] == ["alpha"]
    assert found["epoch"] == epoch and found["current"]["revision"] == _REVISION
    assert _paths(rpc.ok("catalogue")) == ["a.py"]


def test_a_reader_pinned_to_an_epoch_keeps_seeing_it_while_the_next_one_is_published(rpc: Rpc) -> None:
    token = rpc.open_line()
    first = rpc.ok("generation", action="begin", token=token)["epoch"]
    old = "1" * 64
    rpc.ok("batch", token=token, epoch=first, records=[_file("a.py", old), _symbol("a.py", old, "alpha", "alpha", _vector(1))])
    rpc.publish(token, first)

    second = rpc.ok("generation", action="begin", token=token)["epoch"]
    new = "2" * 64
    rpc.ok("batch", token=token, epoch=second, removals=[{"path_id": _h("a.py")}], records=[_file("a.py", new), _symbol("a.py", new, "beta", "beta", _vector(0, 1))])
    # Mid-update: the published view is untouched, in both directions.
    assert [r["symbol"] for r in rpc.ok("query", mode="lexical", terms=["alpha"], k=5)["records"]] == ["alpha"]
    assert rpc.ok("query", mode="lexical", terms=["beta"], k=5)["records"] == []

    rpc.publish(token, second)
    assert rpc.ok("query", mode="lexical", terms=["alpha"], k=5)["records"] == []
    assert [r["symbol"] for r in rpc.ok("query", mode="lexical", terms=["beta"], k=5)["records"]] == ["beta"]
    # A reader who pinned the first epoch still sees it, and its file hash.
    assert [r["symbol"] for r in rpc.ok("query", mode="lexical", terms=["alpha"], k=5, epoch=first)["records"]] == ["alpha"]
    assert rpc.ok("catalogue", epoch=first)["files"][0]["file_hash"] == old
    assert rpc.ok("catalogue")["files"][0]["file_hash"] == new


def test_a_deleted_file_leaves_the_published_view(rpc: Rpc) -> None:
    token = rpc.open_line()
    first = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=first, records=[_file("a.py", "1" * 64), _file("b.py", "2" * 64)])
    rpc.publish(token, first, files=2)
    second = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=second, records=[], removals=[{"path_id": _h("a.py")}])
    rpc.publish(token, second)
    assert _paths(rpc.ok("catalogue")) == ["b.py"]


def test_dense_search_finds_the_nearest_vector_and_pins_its_epoch(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=epoch, records=[
        _symbol("a.py", "1" * 64, "near", "near", _vector(1, 0)),
        _symbol("b.py", "2" * 64, "far", "far", _vector(0, 1)),
    ])
    rpc.publish(token, epoch)
    records = rpc.ok("query", mode="dense", vector=_vector(1, 0.1), k=2)["records"]
    assert [record["symbol"] for record in records] == ["near", "far"]
    assert records[0]["score"] > records[1]["score"]


def test_symbol_and_path_lookups_are_exact(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    content = "1" * 64
    rpc.ok("batch", token=token, epoch=epoch, records=[_file("pkg/a.py", content), _symbol("pkg/a.py", content, "Foo.bar", "foo bar", _vector(1)),
                                                       _symbol("pkg/a.py", content, "Foo.baz", "foo baz", _vector(1))])
    rpc.publish(token, epoch)
    assert [r["symbol"] for r in rpc.ok("query", mode="symbol", symbol="Foo.bar", k=5)["records"]] == ["Foo.bar"]
    assert len(rpc.ok("query", mode="path", path_id=_h("pkg/a.py"), k=5, kinds=["symbol"])["records"]) == 2


def test_a_replayed_batch_changes_nothing(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    batch = [_file("a.py", "1" * 64), _symbol("a.py", "1" * 64, "alpha", "alpha", _vector(1))]
    rpc.ok("batch", token=token, epoch=epoch, records=batch)
    rpc.ok("batch", token=token, epoch=epoch, records=batch)
    rpc.publish(token, epoch)
    assert len(rpc.ok("query", mode="lexical", terms=["alpha"], k=5)["records"]) == 1


def test_a_resuming_writer_continues_its_building_epoch(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    assert rpc.ok("generation", action="begin", token=token)["epoch"] == epoch


def test_a_fenced_out_writer_can_change_nothing(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    resumed = rpc.ok("lease", action="acquire", owner="ab" * 8, ttl_ms=30000, kind="scope")["token"]
    assert resumed > token
    rpc.refused("LEASE_LOST", "batch", token=token, epoch=epoch, records=[_file("a.py", "1" * 64)])
    rpc.refused("LEASE_LOST", "generation", action="publish", token=token, epoch=epoch, revision=_REVISION, dirty=False,
                coverage={"complete": False, "files_indexed": 0, "files_total": 0})
    rpc.refused("LEASE_LOST", "cursor", action="set", token=token, value={"phase": "embedding"})
    rpc.ok("batch", token=resumed, epoch=epoch, records=[_file("a.py", "1" * 64)])


def test_another_owner_cannot_take_a_held_lease(rpc: Rpc) -> None:
    rpc.open_line()
    rpc.refused("LEASE_HELD", "lease", action="acquire", owner="cd" * 8, ttl_ms=30000, kind="scope")


def test_competing_writers_leave_one_winner(rpc: Rpc) -> None:
    rpc.ok("generation", action="open", embedding="test-embedding", dimensions=_DIMENSIONS, schema_version=1)
    outcomes: list[int] = []

    def compete(owner: str) -> None:
        outcomes.append(rpc.call("lease", action="acquire", owner=owner, ttl_ms=30000, kind="scope")[0])

    threads = [threading.Thread(target=compete, args=(f"{n:016x}",)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(outcomes) == [200, 409, 409, 409, 409, 409]


def test_a_cursor_cannot_change_scope(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=epoch, records=[_file(f"f{n}.py", "1" * 64) for n in range(5)])
    rpc.publish(token, epoch, files=5)
    page = rpc.ok("catalogue", limit=2)
    assert page["cursor"] is not None
    other = Rpc(rpc.port)
    other.open_line()
    other.refused("CURSOR_INVALID", "catalogue", cursor=page["cursor"])
    rpc.refused("CURSOR_INVALID", "catalogue", cursor=page["cursor"] + "0")


def test_paging_covers_every_file_exactly_once(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=epoch, records=[_file(f"f{n}.py", "1" * 64) for n in range(7)])
    rpc.publish(token, epoch, files=7)
    seen: list[str] = []
    cursor = None
    while True:
        page = rpc.ok("catalogue", limit=3, **({"cursor": cursor} if cursor else {}))
        seen += _paths(page)
        cursor = page["cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(f"f{n}.py" for n in range(7))


def test_a_scope_with_the_same_key_can_read_another_scope_only_by_naming_it(rpc: Rpc) -> None:
    """The stated residual: the Gateway authenticates the shared key, not the workspace. Scopes never leak by accident, but
    a host holding the key that asserts another scope reads it, which is why the trusted host binds scope."""
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=epoch, records=[_symbol("a.py", "1" * 64, "secretish", "secretish", _vector(1))])
    rpc.publish(token, epoch)
    other = Rpc(rpc.port)
    other.open_line()
    other_epoch = other.ok("generation", action="begin", token=other.ok("lease", action="acquire", owner="ab" * 8, ttl_ms=30000, kind="scope")["token"])["epoch"]
    assert other_epoch == 1
    assert other.call("query", mode="lexical", terms=["secretish"], k=5, epoch=1)[1]["records"] == []
    assert len(other.ok("query", scope=rpc.scope, mode="lexical", terms=["secretish"], k=5)["records"]) == 1


def test_prune_keeps_the_published_view_and_drop_removes_the_scope(rpc: Rpc) -> None:
    token = rpc.open_line()
    first = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=first, records=[_file("a.py", "1" * 64), _symbol("a.py", "1" * 64, "alpha", "alpha", _vector(1))])
    rpc.publish(token, first)
    second = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.ok("batch", token=token, epoch=second, removals=[{"path_id": _h("a.py")}], records=[_file("a.py", "2" * 64), _symbol("a.py", "2" * 64, "beta", "beta", _vector(1))])
    rpc.publish(token, second)

    def run(action: str) -> int:
        removed, cursor = 0, None
        while True:
            step = rpc.ok("cleanup", token=token, action=action, **({"cursor": cursor} if cursor else {}))
            removed += step["removed"]
            cursor = step["cursor"]
            if cursor is None:
                return removed

    assert run("prune") == 2
    assert [r["symbol"] for r in rpc.ok("query", mode="lexical", terms=["beta"], k=5)["records"]] == ["beta"]
    assert run("drop") == 2
    rpc.refused("SCOPE_UNKNOWN", "coverage")


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"not json", "REQUEST_INVALID"),
        (b"{}", "REQUEST_INVALID"),
        (json.dumps({"op": "flushall", "scope": "0" * 64}).encode(), "REQUEST_INVALID"),
        (json.dumps({"op": "coverage", "scope": "NOT-HEX"}).encode(), "REQUEST_INVALID"),
        (json.dumps({"op": "coverage", "scope": "0" * 64, "extra": 1}).encode(), "REQUEST_INVALID"),
    ],
    ids=["not-json", "no-op", "unknown-op", "bad-scope", "unknown-field"],
)
def test_malformed_requests_are_refused_with_a_stable_code(rpc: Rpc, body: bytes, code: str) -> None:
    assert rpc.raw(body) == (400, mic.error_body(code))


def test_the_key_is_checked_before_anything_else(rpc: Rpc) -> None:
    assert rpc.raw(b"not json", secret="wrong") == (401, mic.error_body("UNAUTHORIZED"))  # pragma: allowlist secret - synthetic test fixture


def test_a_source_body_field_is_refused(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    rpc.refused("REQUEST_INVALID", "batch", token=token, epoch=epoch, records=[{**_file("a.py", "1" * 64), "body": "print('source')"}])


def test_a_wrong_length_vector_refuses_the_whole_batch(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    bad = _symbol("a.py", "1" * 64, "alpha", "alpha", mic.encode_vector(b"\0" * 12))
    rpc.refused("VECTOR_DIMENSIONS_INVALID", "batch", token=token, epoch=epoch, records=[_file("b.py", "2" * 64), bad])
    rpc.publish(token, epoch, files=0)
    assert rpc.ok("catalogue")["files"] == []


def test_a_scope_cannot_change_its_embedding(rpc: Rpc) -> None:
    rpc.open_line()
    rpc.refused("SCOPE_CONFIGURATION_MISMATCH", "generation", action="open", embedding="another", dimensions=_DIMENSIONS, schema_version=1)


def test_a_batch_or_a_body_over_the_limit_is_refused(rpc: Rpc) -> None:
    token = rpc.open_line()
    epoch = rpc.ok("generation", action="begin", token=token)["epoch"]
    too_many = [_file(f"f{n}.py", "1" * 64) for n in range(mic.MAX_RECORDS + 1)]
    rpc.refused("BATCH_TOO_LARGE", "batch", token=token, epoch=epoch, records=too_many)
    status, body = rpc.raw(b"x" * (mic.MAX_REQUEST_BYTES + 1))
    assert (status, body) == (413, mic.error_body("REQUEST_TOO_LARGE"))


def test_a_different_resource_is_refused_at_startup(client: redis.Redis) -> None:
    client.delete("oidx:resource")
    memory_index.verify_resource(client, "first")
    memory_index.verify_resource(client, "first")
    with pytest.raises(memory_index.IndexStartupError) as raised:
        memory_index.verify_resource(client, "another")
    assert raised.value.code == "INDEX_REDIS_RESOURCE_MISMATCH"
    client.delete("oidx:resource")
