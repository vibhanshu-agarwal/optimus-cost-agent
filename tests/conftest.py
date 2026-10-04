from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp.debug_trace import reset_debug_trace_context
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.agent.state_store import RedisAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.redis.async_bridge import shutdown_background_loop
from optimus.redis.runtime import RedisRuntime
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter
from tools.plan1126_unrun_binding import (
    binding_commit_available,
    format_terminal_summary,
    load_scopeout_manifest,
    scopeout_nodeids,
    scopeout_reason,
)
from tools.testing import run_context, run_context_guard

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLAN1126_UNRUN_COUNT: pytest.StashKey[int] = pytest.StashKey()
_RUN_CONTEXT: pytest.StashKey[run_context.RunContext] = pytest.StashKey()
_RUN_CONTEXT_FINAL: pytest.StashKey[dict[str, object]] = pytest.StashKey()
_RUN_CONTEXT_DESELECTED: list[str] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--test-run-context",
        dest=run_context.OPTION_DEST,
        choices=("auto", "passive"),
        default="auto",
        help="auto: own a job and guard real folders for the default selection; passive: record only.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_PLAN1126_UNRUN_COUNT] = 0
    # Before collection: an active default-selection session owns its processes and is guarded
    # against the real application folders from here on. Any other selection is only recorded.
    config.stash[_RUN_CONTEXT] = run_context.start_run(config)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    manifest = load_scopeout_manifest(_REPO_ROOT)
    selected = scopeout_nodeids(
        manifest,
        tuple(item.nodeid for item in items),
        binding_available=binding_commit_available(_REPO_ROOT, manifest.binding_commit),
    )
    selected_set = set(selected)
    marker = pytest.mark.skip(reason=scopeout_reason())
    for item in items:
        if item.nodeid in selected_set:
            item.add_marker(marker)
    config.stash[_PLAN1126_UNRUN_COUNT] = len(selected)


def pytest_deselected(items: list[pytest.Item]) -> None:
    _RUN_CONTEXT_DESELECTED.extend(item.nodeid for item in items)


def pytest_collection_finish(session: pytest.Session) -> None:
    context = session.config.stash.get(_RUN_CONTEXT, None)
    if context is not None:
        run_context.record_collection(context, [item.nodeid for item in session.items], list(_RUN_CONTEXT_DESELECTED))
    _RUN_CONTEXT_DESELECTED.clear()


def pytest_collectreport(report: pytest.CollectReport) -> None:
    context = run_context.current()
    if context is not None and report.failed:
        run_context.record_collection_error(context)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    context = run_context.current()
    if context is not None:
        run_context.record_phase(context, report)


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    del exitstatus
    skipped_count = config.stash[_PLAN1126_UNRUN_COUNT]
    if skipped_count:
        terminalreporter.write_sep("=", format_terminal_summary(skipped_count))
    context = config.stash.get(_RUN_CONTEXT, None)
    if context is not None:
        terminalreporter.write_sep("=", run_context.summary_line(context, config.stash.get(_RUN_CONTEXT_FINAL, None)))

_INHERITED_GIT_ENV: dict[str, str] = {}


def pytest_sessionstart(session: pytest.Session) -> None:
    """Neutralise hook-inherited `GIT_*` for the whole session, before collection.

    Git exports `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_WORK_TREE` and friends to the hooks it
    runs. Any test or helper that shells out to git then operates on the SURROUNDING
    repository no matter what `cwd` says -- on 2026-09-02 that marked the real repository
    bare and wrote a fixture identity into its shared config, breaking `git status` in the
    main checkout and every worktree.

    This is deliberately a session hook rather than a fixture: a fixture only runs once a
    test asks for it, which is after collection, and conftest/collection-time code can
    shell out to git too. Restored in `pytest_sessionfinish` so the calling process is
    left exactly as it was found. See HARDENING-ITEM-GIT-ENV-TEST-IMMUNITY.
    """
    for key in [name for name in os.environ if name.startswith("GIT_")]:
        _INHERITED_GIT_ENV[key] = os.environ.pop(key)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Restore whatever `pytest_sessionstart` removed; leave no trace in the parent."""
    os.environ.update(_INHERITED_GIT_ENV)
    _INHERITED_GIT_ENV.clear()
    context = session.config.stash.get(_RUN_CONTEXT, None)
    if context is not None:
        session.config.stash[_RUN_CONTEXT_FINAL] = run_context.finish_run(context, int(exitstatus))


@pytest.fixture(autouse=True)
def _default_trusted_root_isolation(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """In an active run, a test that passes no folders gets its own synthetic ones, never real roots."""
    context = request.config.stash.get(_RUN_CONTEXT, None)
    if context is None or context.guard_mode != "pytest_process_guard":
        return
    session_root = request.getfixturevalue("tmp_path_factory").getbasetemp() / "known-folders"
    run_context_guard.redirect_for_test(monkeypatch, session_root, request.node.nodeid)


@pytest.fixture(scope="session", autouse=True)
def _shutdown_redis_bridge_after_session() -> None:
    yield
    shutdown_background_loop()


@pytest.fixture(autouse=True)
def _reset_debug_trace_context_between_tests() -> Iterator[None]:
    """Plan 9.96, Task 5: DebugTraceContext is process-local module state (it
    replaced os.environ mutation, which pytest's monkeypatch used to undo
    automatically). Without this reset, a context set by one test would leak
    into every subsequent test in the same process."""
    reset_debug_trace_context()
    yield
    reset_debug_trace_context()


@pytest.fixture
def isolated_windows_known_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give launch/path tests explicit temporary OS folder inputs, never real roots.

    Product entry points import the resolver in several modules. Patch those
    aliases to the same wrapper so authoring and launching see identical roots.
    The guarded real adapter itself remains untouched and fail-closed.
    """
    import sys

    from optimus.acp import __main__ as acp_main
    from optimus.acp import launch_approval_cli, operator_paths, trusted_paths

    if sys.platform != "win32":
        return
    # Test workspaces often use tmp_path itself. Keep OS roots in a sibling,
    # preserving the production rule that config/approval roots are external.
    known_root = tmp_path.parent / f"{tmp_path.name}-known-folders"
    roaming = known_root / "Roaming"
    local = known_root / "Local"
    roaming.mkdir(parents=True)
    local.mkdir()
    folders = SimpleNamespace(roaming_appdata=roaming, local_appdata=local)
    original = trusted_paths.resolve_trusted_operator_roots

    def resolve_with_test_folders(*, platform_name: str, windows_known_folders=None, posix_home=None):
        selected_folders = windows_known_folders
        if platform_name == "win32" and selected_folders is None:
            selected_folders = folders
        return original(
            platform_name=platform_name,
            windows_known_folders=selected_folders,
            posix_home=posix_home,
        )

    imported_capture_tool = sys.modules.get("tools.run_plan996_acpx_security_evidence")
    modules = [trusted_paths, operator_paths, acp_main, launch_approval_cli]
    if imported_capture_tool is not None:
        modules.append(imported_capture_tool)
    for module in modules:
        monkeypatch.setattr(module, "resolve_trusted_operator_roots", resolve_with_test_folders)


@pytest.fixture
def redis_key_namespace() -> Iterator[str]:
    run_id = f"live-{uuid.uuid4().hex}"
    yield run_id


@pytest.fixture
def live_redis_store(redis_key_namespace: str) -> Iterator[tuple[RedisAgentStateStore, str]]:
    try:
        redis_url = run_preflight(os.environ, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)
    runtime = RedisRuntime.from_url(redis_url)
    store = runtime.sync_state_store()
    try:
        yield store, redis_key_namespace
    finally:
        runtime.close()


@pytest.fixture
async def live_redis_telemetry(redis_key_namespace: str):
    try:
        redis_url = run_preflight(os.environ, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)

    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
    adapter = RedisTelemetryAdapter(client=client)
    run_id = redis_key_namespace
    try:
        yield adapter, run_id, client
    finally:
        for pattern in (f"telemetry:run:{run_id}*", f"run:{run_id}:*"):
            async for key in client.scan_iter(match=pattern):
                await client.delete(key)
        await client.aclose()


class FakeGatewayClient:
    def __init__(self, output_text: str = "Plan text") -> None:
        self.calls: list[dict[str, object]] = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-1"},
        )
