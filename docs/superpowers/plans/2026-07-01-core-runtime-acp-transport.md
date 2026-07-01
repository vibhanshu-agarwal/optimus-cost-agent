# Core Runtime, ACP Transport, and Test Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 Python package scaffold, test harness, and deterministic ACP/JSON-RPC transport foundation.

**Architecture:** This plan creates a small `src/optimus` package with focused ACP modules for JSON-RPC errors, Content-Length framing, duplicate request ID tracking, dispatch, and a minimal single-message stream handler. The implementation is intentionally local-first and has no gateway/provider access; later plans add continuous stdio serving, modes, mutation gates, gateway routing, tool policy, and cost ledgers.

**Tech Stack:** Python >=3.14, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `asyncio`, stdlib `json`, stdlib dataclasses.

---

## Source Anchors

- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`: ACP protocol framing, stream transport, task lifecycle, and Sprint 1 "Transport & Protocol" gates.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`: Schema Validation Tests, Phase 1 Release Gates, and Transport & Protocol Gates.
- `AGENTS.md`: local-first runtime, expected test tooling, TDD, evidence-bound claims, and no local provider keys.
- `README.md`: package status, one-key project direction, and expected pytest command.

## Scope

### In Scope

- Python package scaffold under `src/optimus`.
- pytest/coverage configuration in `pyproject.toml`.
- JSON-RPC 2.0 success and error response helpers.
- ACP-style `Content-Length` message framing.
- Async byte-stream reader for fragmented headers and bodies.
- Duplicate request ID rejection with app-specific `-32001`.
- Minimal dispatcher and `optimus.ping` smoke method.
- Schema-validation hardening for zero-length bodies, oversized headers, malformed content lengths, and concatenated messages.
- Unit tests and narrow integration smoke tests.

### Out of Scope

- Plan/Chat vs Agent mode enforcement.
- MutationGuard and approval flow.
- Optimus Gateway client/authentication.
- ToolInvocationPolicy and evidence acquisition.
- Redis, usage accounting, cost persistence, telemetry.
- Guardrail permission engine, shell validator, MCP trust, skills, or bounded loops.
- Continuous `run_forever()` stdio loop and 50-burst transport flood simulation.

## File Structure

- Modify: `pyproject.toml` - package metadata, test dependencies, pytest and coverage settings.
- Create: `src/optimus/__init__.py` - package version export.
- Create: `src/optimus/acp/__init__.py` - ACP package exports.
- Create: `src/optimus/acp/errors.py` - JSON-RPC error codes and response helpers.
- Create: `src/optimus/acp/framing.py` - Content-Length encoding and async message reading.
- Create: `src/optimus/acp/request_ids.py` - duplicate request ID tracker.
- Create: `src/optimus/acp/dispatcher.py` - minimal JSON-RPC dispatch surface.
- Create: `src/optimus/acp/server.py` - single-message stream handler that reads, dispatches, and writes one framed response.
- Create: `tests/unit/acp/test_errors.py` - error helper tests.
- Create: `tests/unit/acp/test_framing.py` - header/body framing tests.
- Create: `tests/unit/acp/test_request_ids.py` - duplicate ID tests.
- Create: `tests/unit/acp/test_dispatcher.py` - JSON-RPC dispatch tests.
- Create: `tests/integration/acp/test_server_stream.py` - fragmented stream integration tests.

## Human Agile Sizing

This plan is sized for roughly 2 weeks of human development effort:

- Days 1-2: project scaffold and test harness.
- Days 3-5: framing and error model.
- Days 6-7: request ID lifecycle and dispatcher.
- Days 8-9: stream server integration and fragmented reads.
- Day 10: coverage, refactor, docs, and foundation-gate notes.

## Task 1: Configure Package and Test Harness

**Files:**
- Modify: `pyproject.toml`
- Create: `src/optimus/__init__.py`
- Create: `tests/unit/test_package_imports.py`

- [x] **Step 1: Write the failing package import test**

Create `tests/unit/test_package_imports.py`:

```python
def test_optimus_package_exports_version():
    import optimus

    assert optimus.__version__ == "0.1.0"
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/unit/test_package_imports.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus'`.

- [x] **Step 3: Add project test configuration**

Modify `pyproject.toml` to:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "optimus-cost-agent"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = []

[project.optional-dependencies]
dev = [
  "coverage>=7.6",
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
addopts = [
  "--strict-config",
  "--strict-markers",
]

[tool.coverage.run]
branch = true
source = ["src/optimus"]

[tool.coverage.report]
show_missing = true
skip_covered = false
fail_under = 80

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 4: Add the minimal package**

Create `src/optimus/__init__.py`:

```python
__version__ = "0.1.0"
```

- [x] **Step 5: Run the test to verify it passes**

Run:

```bash
pytest tests/unit/test_package_imports.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add pyproject.toml src/optimus/__init__.py tests/unit/test_package_imports.py
git commit -m "Add Python package and pytest configuration."
```

## Task 2: JSON-RPC Error and Response Helpers

**Files:**
- Create: `src/optimus/acp/__init__.py`
- Create: `src/optimus/acp/errors.py`
- Test: `tests/unit/acp/test_errors.py`

- [x] **Step 1: Write failing tests for JSON-RPC error helpers**

Create `tests/unit/acp/test_errors.py`:

```python
from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INVALID_REQUEST,
    JsonRpcError,
    error_response,
    success_response,
)


def test_success_response_uses_jsonrpc_2_and_preserves_id():
    response = success_response(request_id=7, result={"ok": True})

    assert response == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {"ok": True},
    }


def test_error_response_uses_code_message_and_id():
    response = error_response(
        request_id="abc",
        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": "abc",
        "error": {"code": -32600, "message": "invalid request"},
    }


def test_error_response_includes_optional_data():
    response = error_response(
        request_id=None,
        error=JsonRpcError(
            code=DUPLICATE_REQUEST_ID,
            message="duplicate request id",
            data={"id": "abc"},
        ),
    )

    assert response["error"]["data"] == {"id": "abc"}
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/unit/acp/test_errors.py -v
```

Expected: FAIL with `ModuleNotFoundError` or missing symbols.

- [x] **Step 3: Implement JSON-RPC helpers**

Create `src/optimus/acp/__init__.py`:

```python
"""ACP transport primitives for Optimus Cost Agent."""
```

Create `src/optimus/acp/errors.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
DUPLICATE_REQUEST_ID = -32001


@dataclass(frozen=True)
class JsonRpcError:
    code: int
    message: str
    data: dict[str, Any] | None = None


def success_response(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(
    request_id: str | int | None,
    error: JsonRpcError,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.data is not None:
        payload["error"]["data"] = error.data
    return payload
```

- [x] **Step 4: Run the test to verify it passes**

Run:

```bash
pytest tests/unit/acp/test_errors.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/acp/__init__.py src/optimus/acp/errors.py tests/unit/acp/test_errors.py
git commit -m "Add JSON-RPC response helpers."
```

## Task 3: Content-Length Encoding and Header Parsing

**Files:**
- Create: `src/optimus/acp/framing.py`
- Test: `tests/unit/acp/test_framing.py`

- [x] **Step 1: Write failing tests for encoding and header parsing**

Create `tests/unit/acp/test_framing.py`:

```python
import json

import pytest

from optimus.acp.errors import INVALID_REQUEST, PARSE_ERROR
from optimus.acp.framing import FramingError, encode_message, parse_content_length


def test_encode_message_prefixes_utf8_body_with_content_length():
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"message": "pong"}}

    framed = encode_message(payload)
    header, body = framed.split(b"\r\n\r\n", 1)

    assert header == f"Content-Length: {len(body)}".encode("ascii")
    assert json.loads(body.decode("utf-8")) == payload


def test_parse_content_length_is_case_insensitive():
    headers = b"content-length: 42\r\nX-Ignored: yes\r\n"

    assert parse_content_length(headers) == 42


def test_parse_content_length_rejects_missing_header():
    with pytest.raises(FramingError, match="missing Content-Length"):
        parse_content_length(b"X-Other: 42\r\n")


def test_parse_content_length_rejects_negative_length():
    with pytest.raises(FramingError, match="invalid Content-Length") as exc_info:
        parse_content_length(b"Content-Length: -1\r\n")

    assert exc_info.value.code == PARSE_ERROR


def test_parse_content_length_rejects_non_numeric_length():
    with pytest.raises(FramingError, match="invalid Content-Length") as exc_info:
        parse_content_length(b"Content-Length: nope\r\n")

    assert exc_info.value.code == PARSE_ERROR


def test_header_too_large_error_uses_invalid_request_code():
    error = FramingError("header too large", code=INVALID_REQUEST)

    assert error.code == INVALID_REQUEST
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_framing.py -v
```

Expected: FAIL with missing `optimus.acp.framing`.

- [x] **Step 3: Implement encoding and header parsing**

Create `src/optimus/acp/framing.py`:

```python
from __future__ import annotations

import json
from typing import Any

from optimus.acp.errors import PARSE_ERROR


class FramingError(ValueError):
    """Raised when an ACP message cannot be framed or decoded."""

    def __init__(self, message: str, code: int = PARSE_ERROR) -> None:
        super().__init__(message)
        self.code = code


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def parse_content_length(header_bytes: bytes) -> int:
    for raw_line in header_bytes.splitlines():
        name, separator, value = raw_line.partition(b":")
        if not separator:
            continue
        if name.strip().lower() != b"content-length":
            continue
        try:
            length = int(value.strip())
        except ValueError as exc:
            raise FramingError("invalid Content-Length") from exc
        if length < 0:
            raise FramingError("invalid Content-Length")
        return length
    raise FramingError("missing Content-Length")
```

- [x] **Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/acp/test_framing.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/acp/framing.py tests/unit/acp/test_framing.py
git commit -m "Add ACP Content-Length framing."
```

## Task 4: Async Fragmented Stream Reader

**Files:**
- Modify: `src/optimus/acp/framing.py`
- Test: `tests/unit/acp/test_framing.py`

- [x] **Step 1: Add failing async read tests**

Append to `tests/unit/acp/test_framing.py`:

```python
import asyncio

from optimus.acp.framing import read_message


class ChunkedReader:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, size: int) -> bytes:
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self._chunks.insert(0, chunk[size:])
        return chunk[:size]


async def test_read_message_reassembles_fragmented_header_and_body():
    framed = encode_message({"jsonrpc": "2.0", "id": "a", "method": "optimus.ping"})
    reader = ChunkedReader([framed[:5], framed[5:17], framed[17:25], framed[25:]])

    message = await read_message(reader)

    assert message == {"jsonrpc": "2.0", "id": "a", "method": "optimus.ping"}


async def test_read_message_rejects_truncated_body():
    reader = ChunkedReader([b"Content-Length: 10\r\n\r\n{}"])

    with pytest.raises(FramingError, match="unexpected end of stream"):
        await read_message(reader)


async def test_read_message_rejects_content_length_zero_as_invalid_json_body():
    reader = ChunkedReader([b"Content-Length: 0\r\n\r\n"])

    with pytest.raises(FramingError, match="invalid JSON body") as exc_info:
        await read_message(reader)

    assert exc_info.value.code == PARSE_ERROR


async def test_read_message_rejects_oversized_header_with_invalid_request_code():
    reader = ChunkedReader([b"X-Ignored: 123456\r\nContent-Length: 2\r\n\r\n{}"])

    with pytest.raises(FramingError, match="header too large") as exc_info:
        await read_message(reader, header_limit=8)

    assert exc_info.value.code == INVALID_REQUEST


async def test_read_message_leaves_next_framed_message_available():
    first = encode_message({"jsonrpc": "2.0", "id": "a", "method": "optimus.ping"})
    second = encode_message({"jsonrpc": "2.0", "id": "b", "method": "optimus.ping"})
    reader = ChunkedReader([first + second])

    first_message = await read_message(reader)
    second_message = await read_message(reader)

    assert first_message["id"] == "a"
    assert second_message["id"] == "b"
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_framing.py -v
```

Expected: FAIL with missing `read_message`.

- [x] **Step 3: Implement async read support**

Update `src/optimus/acp/framing.py`:

```python
from __future__ import annotations

import json
from typing import Any, Protocol

from optimus.acp.errors import INVALID_REQUEST, PARSE_ERROR


class AsyncByteReader(Protocol):
    async def read(self, size: int) -> bytes:
        ...


class FramingError(ValueError):
    """Raised when an ACP message cannot be framed or decoded."""

    def __init__(self, message: str, code: int = PARSE_ERROR) -> None:
        super().__init__(message)
        self.code = code


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def parse_content_length(header_bytes: bytes) -> int:
    for raw_line in header_bytes.splitlines():
        name, separator, value = raw_line.partition(b":")
        if not separator:
            continue
        if name.strip().lower() != b"content-length":
            continue
        try:
            length = int(value.strip())
        except ValueError as exc:
            raise FramingError("invalid Content-Length") from exc
        if length < 0:
            raise FramingError("invalid Content-Length")
        return length
    raise FramingError("missing Content-Length")


async def read_message(reader: AsyncByteReader, header_limit: int = 8192) -> dict[str, Any]:
    header = bytearray()
    while b"\r\n\r\n" not in header:
        chunk = await reader.read(1)
        if chunk == b"":
            raise FramingError("unexpected end of stream")
        header.extend(chunk)
        if len(header) > header_limit:
            raise FramingError("header too large", code=INVALID_REQUEST)

    header_bytes, _, remainder = bytes(header).partition(b"\r\n\r\n")
    content_length = parse_content_length(header_bytes)
    body = bytearray(remainder)
    while len(body) < content_length:
        chunk = await reader.read(content_length - len(body))
        if chunk == b"":
            raise FramingError("unexpected end of stream")
        body.extend(chunk)

    try:
        decoded = json.loads(bytes(body[:content_length]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FramingError("invalid JSON body") from exc
    if not isinstance(decoded, dict):
        raise FramingError("JSON-RPC message must be an object")
    return decoded
```

- [x] **Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/acp/test_framing.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/acp/framing.py tests/unit/acp/test_framing.py
git commit -m "Read fragmented ACP messages."
```

## Task 5: Duplicate Request ID Tracker

**Files:**
- Create: `src/optimus/acp/request_ids.py`
- Test: `tests/unit/acp/test_request_ids.py`

- [ ] **Step 1: Write failing duplicate ID tests**

Create `tests/unit/acp/test_request_ids.py`:

```python
import pytest

from optimus.acp.errors import DUPLICATE_REQUEST_ID
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker


def test_tracker_accepts_first_request_id():
    tracker = RequestIdTracker()

    tracker.remember("req-1")

    assert tracker.seen("req-1") is True


def test_tracker_rejects_duplicate_request_id_with_app_code():
    tracker = RequestIdTracker()
    tracker.remember(42)

    with pytest.raises(DuplicateRequestId) as exc_info:
        tracker.remember(42)

    assert exc_info.value.code == DUPLICATE_REQUEST_ID
    assert exc_info.value.request_id == 42
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_request_ids.py -v
```

Expected: FAIL with missing `optimus.acp.request_ids`.

- [ ] **Step 3: Implement the tracker**

Create `src/optimus/acp/request_ids.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from optimus.acp.errors import DUPLICATE_REQUEST_ID


@dataclass(frozen=True)
class DuplicateRequestId(Exception):
    request_id: str | int
    code: int = DUPLICATE_REQUEST_ID

    def __str__(self) -> str:
        return f"duplicate request id: {self.request_id}"


class RequestIdTracker:
    def __init__(self) -> None:
        self._seen: set[str | int] = set()

    def remember(self, request_id: str | int | None) -> None:
        if request_id is None:
            return
        if request_id in self._seen:
            raise DuplicateRequestId(request_id=request_id)
        self._seen.add(request_id)

    def seen(self, request_id: str | int) -> bool:
        return request_id in self._seen
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/acp/test_request_ids.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/acp/request_ids.py tests/unit/acp/test_request_ids.py
git commit -m "Reject duplicate ACP request IDs."
```

## Task 6: Minimal JSON-RPC Dispatcher

**Files:**
- Create: `src/optimus/acp/dispatcher.py`
- Test: `tests/unit/acp/test_dispatcher.py`

- [ ] **Step 1: Write failing dispatcher tests**

Create `tests/unit/acp/test_dispatcher.py`:

```python
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import DUPLICATE_REQUEST_ID, METHOD_NOT_FOUND


def test_dispatcher_handles_ping():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})

    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"message": "pong"}}


def test_dispatcher_rejects_unknown_method():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 2, "method": "unknown"})

    assert response["id"] == 2
    assert response["error"]["code"] == METHOD_NOT_FOUND


def test_dispatcher_rejects_duplicate_id():
    dispatcher = JsonRpcDispatcher()
    dispatcher.dispatch({"jsonrpc": "2.0", "id": "x", "method": "optimus.ping"})

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": "x", "method": "optimus.ping"})

    assert response["id"] == "x"
    assert response["error"]["code"] == DUPLICATE_REQUEST_ID
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py -v
```

Expected: FAIL with missing `optimus.acp.dispatcher`.

- [ ] **Step 3: Implement dispatcher**

Create `src/optimus/acp/dispatcher.py`:

```python
from __future__ import annotations

from typing import Any

from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker


class JsonRpcDispatcher:
    def __init__(self, request_ids: RequestIdTracker | None = None) -> None:
        self._request_ids = request_ids or RequestIdTracker()

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            self._request_ids.remember(request_id)
        except DuplicateRequestId:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(
                    code=DUPLICATE_REQUEST_ID,
                    message="duplicate request id",
                    data={"id": request_id},
                ),
            )

        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
            )

        method = request["method"]
        if method == "optimus.ping":
            return success_response(request_id=request_id, result={"message": "pong"})

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/acp/dispatcher.py tests/unit/acp/test_dispatcher.py
git commit -m "Dispatch minimal JSON-RPC requests."
```

## Task 7: Single-Message Stream Handler Integration

**Files:**
- Create: `src/optimus/acp/server.py`
- Test: `tests/integration/acp/test_server_stream.py`

- [ ] **Step 1: Write failing single-message handler tests**

Create `tests/integration/acp/test_server_stream.py`:

```python
import asyncio
import json

from optimus.acp.errors import PARSE_ERROR
from optimus.acp.framing import encode_message
from optimus.acp.server import AcpStreamServer


class MemoryReader:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, size: int) -> bytes:
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self._chunks.insert(0, chunk[size:])
        return chunk[:size]


class MemoryWriter:
    def __init__(self):
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)


def decode_framed_response(data: bytes) -> dict:
    _, body = data.split(b"\r\n\r\n", 1)
    return json.loads(body.decode("utf-8"))


async def test_stream_handler_handles_fragmented_ping():
    framed = encode_message({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})
    reader = MemoryReader([framed[:2], framed[2:9], framed[9:]])
    writer = MemoryWriter()

    await AcpStreamServer().handle_one(reader, writer)

    assert decode_framed_response(bytes(writer.data)) == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"message": "pong"},
    }


async def test_stream_handler_maps_framing_error_to_json_rpc_error():
    reader = MemoryReader([b"Content-Length: 1\r\n\r\n{"])
    writer = MemoryWriter()

    await AcpStreamServer().handle_one(reader, writer)

    response = decode_framed_response(bytes(writer.data))
    assert response["id"] is None
    assert response["error"]["code"] == PARSE_ERROR
    assert response["error"]["message"] == "invalid JSON body"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/integration/acp/test_server_stream.py -v
```

Expected: FAIL with missing `optimus.acp.server`.

- [ ] **Step 3: Implement single-message stream handler**

Create `src/optimus/acp/server.py`:

```python
from __future__ import annotations

from typing import Protocol

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import JsonRpcError, error_response
from optimus.acp.framing import FramingError, encode_message, read_message


class AsyncByteReader(Protocol):
    async def read(self, size: int) -> bytes:
        ...


class AsyncByteWriter(Protocol):
    def write(self, data: bytes) -> None:
        ...

    async def drain(self) -> None:
        ...


class AcpStreamServer:
    def __init__(self, dispatcher: JsonRpcDispatcher | None = None) -> None:
        self._dispatcher = dispatcher or JsonRpcDispatcher()

    async def handle_one(self, reader: AsyncByteReader, writer: AsyncByteWriter) -> None:
        try:
            request = await read_message(reader)
            response = self._dispatcher.dispatch(request)
        except FramingError as exc:
            response = error_response(
                request_id=None,
                error=JsonRpcError(code=exc.code, message=str(exc)),
            )
        writer.write(encode_message(response))
        await writer.drain()
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
pytest tests/integration/acp/test_server_stream.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/acp/server.py tests/integration/acp/test_server_stream.py
git commit -m "Handle one framed ACP request over streams."
```

## Task 8: Transport Foundation and Coverage Check

**Files:**
- Modify: `README.md`
- Verify: all files from Tasks 1-7

- [ ] **Step 1: Run the narrow ACP suite**

Run:

```bash
pytest tests/unit/acp tests/integration/acp -v
```

Expected: PASS.

- [ ] **Step 2: Run coverage for production package**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing
```

Expected: PASS with aggregate production-code coverage at or above 80%.

- [ ] **Step 3: Add README transport note**

Append this under the README Documentation or Features area:

```markdown
### Phase 1 Transport Foundation

The initial runtime foundation implements ACP-style `Content-Length` framing,
JSON-RPC response helpers, duplicate request ID rejection, and a minimal
`optimus.ping` dispatch path. This is the first transport foundation slice for
the authoritative Phase 1 Test Strategy; later hardening adds the continuous
stdio loop, 50-burst fragmented-header simulation, and full release-gate
transport coverage.
```

- [ ] **Step 4: Run the full test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 5: Check working tree**

Run:

```bash
git status --short
```

Expected: only intentional Plan 1 implementation files are modified or added.

- [ ] **Step 6: Commit**

```bash
git add README.md pyproject.toml src tests
git commit -m "Add ACP transport foundation."
```

## Self-Review

- Spec coverage: Plan 1 covers package scaffold, test harness, ACP message framing, fragmented reads, duplicate request IDs, minimal dispatch, single-message stream integration, selected schema-validation hardening, and coverage checks. Later roadmap plans own modes, gateway, tools, guardrails, usage accounting, continuous stdio serving, 50-burst transport simulation, and release E2E.
- Placeholder scan: no open implementation placeholders are intentional in this plan.
- Type consistency: request IDs are `str | int | None` at JSON-RPC boundaries; duplicate tracking ignores `None`; all response helpers return JSON-serializable dictionaries.
- TDD compliance: every production module has a failing test step before implementation.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-core-runtime-acp-transport.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Per-task commits are optional checkpoints. Do not run `git commit` unless the user explicitly asks for commits.
