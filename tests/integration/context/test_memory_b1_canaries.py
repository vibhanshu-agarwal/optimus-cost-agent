"""Plan 12.10 Task 3, B1: distinctive source text must not reach anything the index persists, in any encoding.

Scans the real keys and the real AOF and RDB files, after a restart and after a rewrite, for canaries planted where B1 forbids them. Text
B1 allows is planted too, as controls: a scan that cannot find those has proved nothing. Selected with `-m requires_plan12_index_redis`.
"""

from __future__ import annotations

import base64
import codecs
import json
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import redis
from redis.exceptions import ResponseError

from optimus.acp import local_infra
from optimus.config.gateway import OptimusGatewaySettings
from optimus_gateway import memory_index
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from tests.integration.context.conftest import CONTAINER, IMAGE, VOLUME, Provisioned, docker
from tests.integration.context.test_memory_worker import Index

pytestmark = [pytest.mark.requires_plan12_index_redis]

_SECRET = "index-canary-secret"  # pragma: allowlist secret - synthetic test fixture
FORBIDDEN = {
    "python comment": "ZQXCANARYPYCOMMENT",
    "python docstring": "ZQXCANARYPYDOCSTRING",
    "python module docstring": "ZQXCANARYMODULEDOC",
    "python string": "ZQXCANARYPYSTRING",
    "python default": "ZQXCANARYPYDEFAULT",
    "python body text": "ZQXCANARYPYFSTRING",
    "java comment": "ZQXCANARYJAVACOMMENT",
    "java javadoc": "ZQXCANARYJAVADOC",
    "java string": "ZQXCANARYJAVASTRING",
    "java annotation": "ZQXCANARYJAVAANNOT",
    "document code string": "ZQXCANARYDOCCODE",
    "document code comment": "ZQXCANARYDOCCOMMENT",
    "unsupported language": "ZQXCANARYKOTLIN",
}
ALLOWED = {"identifier": "zqxallowedidentifier", "documentation prose": "ZQXALLOWEDPROSE", "path": "zqxallowedpath"}
_PY = f'''"""{FORBIDDEN["python module docstring"]}"""
import os.path

VALUE = "{FORBIDDEN["python string"]}"


def {ALLOWED["identifier"]}(first, second="{FORBIDDEN["python default"]}"):  # {FORBIDDEN["python comment"]}
    """{FORBIDDEN["python docstring"]}"""
    label = f"{FORBIDDEN["python body text"]} {{first}}"
    return label + second
'''
_JAVA = f'''package canary;

/** {FORBIDDEN["java javadoc"]} */
@Deprecated(since = "{FORBIDDEN["java annotation"]}")
public class Canary {{
    // {FORBIDDEN["java comment"]}
    public String value(int count) {{
        return "{FORBIDDEN["java string"]}" + count;
    }}
}}
'''
_DOC = f"""# Guide

{ALLOWED["documentation prose"]} explains this.

```python
def documented():  # {FORBIDDEN["document code comment"]}
    return "{FORBIDDEN["document code string"]}"
```
"""
_KOTLIN = f'fun main() {{ println("{FORBIDDEN["unsupported language"]}") }}\n'


def _encodings(text: str) -> dict[str, bytes]:
    raw = text.encode("utf-8")
    return {
        "plain": raw,
        "lower": text.lower().encode("utf-8"),
        "json": json.dumps(text).encode("utf-8")[1:-1],
        "ascii-escaped": "".join(f"\\u{ord(c):04x}" for c in text).encode("ascii"),
        "base64": base64.b64encode(raw)[:-2],
        "urlsafe-base64": base64.urlsafe_b64encode(raw)[:-2],
        "hex": codecs.encode(raw, "hex"),
        "utf-16": text.encode("utf-16-le"),
    }


def _found(data: bytes, text: str) -> list[str]:
    return [name for name, encoded in _encodings(text).items() if encoded in data]


def _store_dump(client: redis.Redis, scope: str) -> bytes:
    """Every value of every key the index holds for this scope, as stored."""
    parts: list[bytes] = []
    for key in client.scan_iter(match="oidx:*", count=1000):
        parts.append(key)
        # The index user may not ask a key's type, so each is read the way the store itself reads it.
        for read in (client.hgetall, client.get, client.smembers):
            try:
                value = read(key)
            except ResponseError:
                continue
            if isinstance(value, dict):
                for field, item in value.items():
                    parts += [field, item]
            elif isinstance(value, set):
                parts += list(value)
            elif value:
                parts.append(value)
            break
    assert scope.encode() in b"".join(parts)
    return b"\n".join(parts)


def _persisted_files(tmp: Path) -> bytes:
    """Stop the instance, then read the AOF and RDB out of its real volume."""
    tmp.mkdir(parents=True, exist_ok=True)
    docker("stop", CONTAINER, check=True)
    docker("cp", f"{CONTAINER}:/data", str(tmp), check=True)
    files = [path for path in (tmp / "data").rglob("*") if path.is_file()]
    assert any(path.suffix == ".aof" for path in files), [path.name for path in files]
    return b"\n".join(path.read_bytes() for path in files)


def _assert_clean(data: bytes, where: str) -> None:
    leaks = {name: found for name, text in FORBIDDEN.items() if (found := _found(data, text))}
    assert not leaks, f"{where}: {leaks}"


@pytest.fixture(scope="module")
def built(provisioned: Provisioned, tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Index, redis.Redis, Provisioned]]:
    client = provisioned.connect()
    store = memory_index.IndexStore(client, cursor_key=b"c" * 32)
    config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=_SECRET, provider="openrouter",
                                  provider_api_key="sk-or-test",  # pragma: allowlist secret - synthetic test fixture
                                  base_url="http://127.0.0.1:9/api/v1")
    server = serve_gateway(config=replace(config, memory_index=memory_index.IndexService(store)), upstream_client=object())  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    root = tmp_path_factory.mktemp("canary")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    (root / ALLOWED["path"]).mkdir()
    (root / ALLOWED["path"] / "canary.py").write_text(_PY, encoding="utf-8")
    (root / "Canary.java").write_text(_JAVA, encoding="utf-8")
    (root / "guide.md").write_text(_DOC, encoding="utf-8")
    (root / "main.kt").write_text(_KOTLIN, encoding="utf-8")
    settings = OptimusGatewaySettings.from_env({"OPTIMUS_GATEWAY_URL": f"http://127.0.0.1:{server.server_address[1]}", "OPTIMUS_API_KEY": _SECRET})
    index = Index(root, settings, project="canary")
    assert index.build().state == "complete"
    yield index, client, provisioned
    server.shutdown()
    server.server_close()
    thread.join(5)


def test_the_canaries_really_are_in_the_source(built: tuple[Index, redis.Redis, Provisioned]) -> None:
    index, _client, _provisioned = built
    source = b"\n".join(path.read_bytes() for path in index.root.rglob("*") if path.is_file() and ".git" not in path.parts)
    for name, text in FORBIDDEN.items():
        assert text.encode() in source, name


def test_the_scan_can_see_every_encoding() -> None:
    """A positive control for the scanner itself."""
    text = "ZQXPOSITIVECONTROL"
    for name, encoded in _encodings(text).items():
        assert name in _found(b"prefix " + encoded + b" suffix", text)


def test_keys_hold_no_forbidden_text_and_do_hold_the_allowed_text(built: tuple[Index, redis.Redis, Provisioned]) -> None:
    index, client, _provisioned = built
    dump = _store_dump(client, index.scope)
    _assert_clean(dump, "keys")
    for name, text in ALLOWED.items():
        assert _found(dump, text), f"control not found: {name}"


def test_no_query_reply_carries_forbidden_text(built: tuple[Index, redis.Redis, Provisioned]) -> None:
    index, _client, _provisioned = built
    replies = [index.storage.call("query", mode="lexical", terms=[term], k=50) for term in (ALLOWED["identifier"], "canary", "documented", "guide", "value")]
    replies.append(index.storage.call("catalogue"))
    _assert_clean(json.dumps(replies).encode(), "replies")


def test_persisted_files_hold_no_forbidden_text_before_and_after_a_restart_and_a_rewrite(built: tuple[Index, redis.Redis, Provisioned], tmp_path: Path) -> None:
    index, _client, provisioned = built
    first = _persisted_files(tmp_path / "before")
    _assert_clean(first, "AOF and RDB")
    assert _found(first, ALLOWED["documentation prose"]), "control not found on disk"

    docker("start", CONTAINER, check=True)
    assert memory_index_ready(provisioned)
    second = _persisted_files(tmp_path / "after-restart")
    _assert_clean(second, "AOF and RDB after a restart")

    # A rewrite needs an administrative command the index user is rightly denied, so it runs in the released name with no ACL,
    # on the same volume and unpublished, then the real container comes back.
    docker("rm", "-f", CONTAINER, check=True)
    docker("run", "-d", "--name", CONTAINER, "-v", f"{VOLUME}:/data", IMAGE, "redis-server", "--appendonly", "yes", check=True)
    try:
        wait_for_cli()
        assert docker("exec", CONTAINER, "redis-cli", "BGREWRITEAOF", check=True).returncode == 0
        wait_for_rewrite()
        assert docker("exec", CONTAINER, "redis-cli", "SAVE", check=True).stdout.strip() == "OK"
        rewritten = _persisted_files(tmp_path / "after-rewrite")
    finally:
        docker("rm", "-f", CONTAINER)
    _assert_clean(rewritten, "AOF and RDB after a rewrite")
    assert _found(rewritten, ALLOWED["documentation prose"]), "control not found after the rewrite"

    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"
    assert memory_index_ready(provisioned)
    assert index.symbols(ALLOWED["identifier"]) == [ALLOWED["identifier"]]


def test_the_host_side_writes_no_cache_or_journal_with_source_text(built: tuple[Index, redis.Redis, Provisioned]) -> None:
    index, _client, provisioned = built
    for root in (provisioned.root,):
        data = b"\n".join(path.read_bytes() for path in root.rglob("*") if path.is_file())
        _assert_clean(data, "the memory-index folder")
    leftovers = [path for path in index.root.rglob("*") if path.is_file() and ".git" not in path.parts and path.name not in {"canary.py", "Canary.java", "guide.md", "main.kt"}]
    assert leftovers == [], leftovers


def memory_index_ready(provisioned: Provisioned) -> bool:
    client = provisioned.connect()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            return bool(client.ping())
        except redis.RedisError:
            time.sleep(0.5)
    return False


def wait_for_cli() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if docker("exec", CONTAINER, "redis-cli", "PING").stdout.strip() == "PONG":
            return
        time.sleep(0.5)
    raise AssertionError("the instance did not answer")


def wait_for_rewrite() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        info = docker("exec", CONTAINER, "redis-cli", "INFO", "persistence").stdout
        if "aof_rewrite_in_progress:0" in info and "aof_rewrite_scheduled:0" in info:
            return
        time.sleep(0.5)
    raise AssertionError("the rewrite did not finish")
