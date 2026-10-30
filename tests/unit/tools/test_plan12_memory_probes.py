"""Plan 12.7 Task 1: the probe runner's safety controls, offline.

Doubles stand in only for parsing and containment: docker inspection output, a client factory that
must never be called, and command runners. No test here can produce a native-service or client PASS;
those come from the released live runs. Each refusal sits next to an accepted control on the same path.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import time
from compression import zstd
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark.expression import Expression

from tests.support import child_launch_inventory
from tools.plan12_memory import client_probe, probe_child, probes, redis_probe
from tools.testing import run_context

_ROOT = Path(__file__).resolve().parents[3]
_LIVE = _ROOT / "tests/integration/tools/test_plan12_memory_redis_probe.py"
_IMAGE = "sha256:" + "a" * 64


def _config(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1, "run_label": "p127-test", "authorization": "unit test",
        "limits": {"timeout_seconds": 5, "max_download_bytes": 1000},
        "allowed_hosts": ["pypi.org"],
        "redis": {"endpoint": "redis://127.0.0.1:6390/0", "container": "p127-probe-redis", "image": "redis:8",
                  "image_id": _IMAGE, "volume": "p127-probe-redis-data"},
        "targets": {"redis": dict.fromkeys(probes.REDIS_TARGETS, 1)},
    }
    data.update(overrides)
    return data


def _parsed(**overrides: Any) -> probes.ProbeConfig:
    return probes.parse_config(json.dumps(_config(**overrides)).encode())


def _container(**overrides: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "Id": "c" * 64, "Name": "/p127-probe-redis", "Image": _IMAGE, "State": {"Running": True},
        "HostConfig": {"PortBindings": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6390"}]}},
        "Mounts": [{"Type": "volume", "Name": "p127-probe-redis-data", "Destination": "/data"}],
    }
    info.update(overrides)
    return info


# --- config ---

def test_a_valid_config_parses_and_is_bound_to_its_bytes() -> None:
    raw = json.dumps(_config()).encode()
    config = probes.parse_config(raw)
    assert config.redis is not None and config.redis.container == "p127-probe-redis"
    assert config.redis_targets_complete()
    assert config.sha256 == __import__("hashlib").sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(extra=1),
        lambda c: c.update(schema_version=2),
        lambda c: c["limits"].update(timeout_seconds=0),
        lambda c: c["limits"].update(timeout_seconds=True),
        lambda c: c["redis"].pop("volume"),
        lambda c: c["redis"].update(password="literal"),
        lambda c: c.update(targets={"redis": {"items": "many"}}),
        lambda c: c.update(postgres={"host": "127.0.0.1", "container": "x", "image_id": "i", "volume": "v",
                                     "user": "u", "database": "d"}),
    ],
)
def test_malformed_configs_are_refused(mutate: Any) -> None:
    data = _config()
    mutate(data)
    with pytest.raises(probes.ConfigError):
        probes.parse_config(json.dumps(data).encode())


def test_non_json_config_is_refused() -> None:
    with pytest.raises(probes.ConfigError):
        probes.parse_config(b"{not json")


def test_incomplete_redis_targets_are_detected() -> None:
    targets = dict.fromkeys(probes.REDIS_TARGETS, 1)
    targets.pop("physical_erasure_seconds")
    assert not _parsed(targets={"redis": targets}).redis_targets_complete()


def test_generic_redis_variables_never_supply_a_config(tmp_path: Path) -> None:
    shared = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6390/0", "REDIS_URL": "redis://127.0.0.1:6390/0"}
    assert probes.config_from_environment(shared) is None
    path = tmp_path / "probe-config.json"
    path.write_text(json.dumps(_config()), encoding="utf-8")
    assert probes.config_from_environment({**shared, probes.CONFIG_ENV: str(path)}).run_label == "p127-test"


def test_downloads_are_limited_to_allowed_https_hosts() -> None:
    config = _parsed()
    assert probes.allowed_url("https://pypi.org/simple", config)
    assert not probes.allowed_url("http://pypi.org/simple", config)
    assert not probes.allowed_url("https://evil.example/simple", config)


# --- dedicated Redis admission (R-2) ---

def _resource(endpoint: str) -> probes.RedisResource:
    return probes.RedisResource(endpoint=endpoint, container="p127-probe-redis", image="redis:8", image_id=_IMAGE,
                                volume="p127-probe-redis-data")


def test_the_released_dedicated_endpoint_is_admitted() -> None:
    assert probes.admit_redis_endpoint(_resource("redis://127.0.0.1:6390/0"), environ={}) == ("127.0.0.1", 6390, 0)


@pytest.mark.parametrize(
    "endpoint",
    [
        "redis://127.0.0.1:6379/0",
        "redis://127.0.0.1:6379/7",
        "redis://localhost:6379/3",
        "redis://[::1]:6379/0",
        "redis://127.0.0.2:6379/0",
        "redis://0.0.0.0:6390/0",
        "redis://192.168.1.10:6390/0",
        "rediss://127.0.0.1:6390/0",
        "redis://user:pw@127.0.0.1:6390/0",  # pragma: allowlist secret - synthetic refused endpoint
        "redis://127.0.0.1:6390/0?db=1",
        "redis://127.0.0.1:99999/0",
        "redis://127.0.0.1:6390/abc",
        "redis://127.0.0.1/0",
    ],
)
def test_shared_aliased_or_malformed_endpoints_are_refused(endpoint: str) -> None:
    with pytest.raises(probes.AdmissionError):
        probes.admit_redis_endpoint(_resource(endpoint), environ={})


def test_a_port_named_by_a_shared_redis_variable_becomes_protected() -> None:
    resource = _resource("redis://127.0.0.1:6391/0")
    assert probes.admit_redis_endpoint(resource, environ={})[1] == 6391
    with pytest.raises(probes.AdmissionError):
        probes.admit_redis_endpoint(resource, environ={"OPTIMUS_REDIS_URL": "redis://localhost:6391/2"})


def test_the_released_container_binding_is_admitted() -> None:
    admitted = probes.admit_redis_resource(_resource("redis://127.0.0.1:6390/0"), lambda name: _container(), environ={})
    assert admitted["volume"] == "p127-probe-redis-data" and admitted["host_port"] == 6390


@pytest.mark.parametrize(
    "overrides",
    [
        {"Name": "/optimus-redis"},
        {"Image": "sha256:" + "b" * 64},
        {"State": {"Running": False}},
        {"HostConfig": {"PortBindings": {"6379/tcp": [{"HostIp": "0.0.0.0", "HostPort": "6390"}]}}},
        {"HostConfig": {"PortBindings": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6379"}]}}},
        {"HostConfig": {"PortBindings": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6390"}],
                                         "6380/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6391"}]}}},
        {"Mounts": []},
        {"Mounts": [{"Type": "bind", "Name": "", "Destination": "/data"}]},
        {"Mounts": [{"Type": "volume", "Name": "shared-data", "Destination": "/data"}]},
        {"Mounts": [{"Type": "volume", "Name": "p127-probe-redis-data", "Destination": "/data"},
                    {"Type": "volume", "Name": "other", "Destination": "/other"}]},
    ],
)
def test_unsafe_resource_mappings_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(probes.AdmissionError):
        probes.admit_redis_resource(_resource("redis://127.0.0.1:6390/0"), lambda name: _container(**overrides), environ={})


def _inspect_runner(info: dict[str, Any]) -> Any:
    calls: list[list[str]] = []

    def runner(argv: list[str], timeout: float, env: Any = None, stdin: Any = None) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        assert argv[:2] == ["docker", "inspect"], argv
        return subprocess.CompletedProcess(argv, 0, json.dumps([info]), "")

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def _forbidden_client() -> Any:
    raise AssertionError("a client was constructed")


def test_a_refused_resource_never_constructs_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPTIMUS_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    runner = _inspect_runner(_container(Name="/optimus-redis"))
    result, _ = probes.run_probe("redis", _parsed(), bodies={
        "redis": lambda ctx, res: redis_probe.run_redis(ctx, res, runner=runner, client_factory=_forbidden_client)})
    assert result.outcome == "ERROR" and "AdmissionError" in result.limitations[0]
    assert runner.calls == [["docker", "inspect", "--type", "container", "p127-probe-redis"]]


def test_a_shared_endpoint_is_refused_before_inspection_or_client() -> None:
    runner = _inspect_runner(_container())
    config = _parsed(redis={**_config()["redis"], "endpoint": "redis://localhost:6379/9"})
    result, _ = probes.run_probe("redis", config, bodies={
        "redis": lambda ctx, res: redis_probe.run_redis(ctx, res, runner=runner, client_factory=_forbidden_client)})
    assert result.outcome == "ERROR" and runner.calls == []


def test_incomplete_targets_leave_redis_unrun_without_any_call() -> None:
    runner = _inspect_runner(_container())
    result, _ = probes.run_probe("redis", _parsed(targets={}), bodies={
        "redis": lambda ctx, res: redis_probe.run_redis(ctx, res, runner=runner, client_factory=_forbidden_client)})
    assert (result.outcome, result.disposition) == ("UNRUN", "open") and runner.calls == []


def test_missing_redis_section_is_unrun() -> None:
    data = _config()
    data.pop("redis")
    result, _ = probes.run_probe("redis", probes.parse_config(json.dumps(data).encode()), bodies={
        "redis": lambda ctx, res: redis_probe.run_redis(ctx, res, runner=_inspect_runner({}), client_factory=_forbidden_client)})
    assert result.outcome == "UNRUN"


def test_postgres_admission_refuses_the_default_port_and_admits_the_released_one() -> None:
    section = {"host": "127.0.0.1", "port": 5440, "container": "p127-probe-pg", "image_id": _IMAGE, "volume": "pgv"}
    info = _container(Name="/p127-probe-pg",
                      HostConfig={"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5440"}]}},
                      Mounts=[{"Type": "volume", "Name": "pgv", "Destination": "/var/lib/postgresql/data"}])
    assert probes.admit_postgres_resource(section, lambda name: info)["host_port"] == 5440
    with pytest.raises(probes.AdmissionError):
        probes.admit_postgres_resource({**section, "port": 5432}, lambda name: info)


# --- sanitized, write-once records ---

@pytest.mark.parametrize(
    "secret",
    [
        "sk-test1234567890abcdef",  # pragma: allowlist secret - synthetic redaction input
        "AKIAABCDEFGHIJKLMNOP",  # pragma: allowlist secret - synthetic redaction input
        "-----BEGIN RSA PRIVATE KEY-----",  # pragma: allowlist secret - synthetic redaction input
        "password=hunter2xyz",  # pragma: allowlist secret - synthetic redaction input
        "redis://probe:s3cret@127.0.0.1:6390/0",  # pragma: allowlist secret - synthetic redaction input
    ],
)
def test_secrets_in_any_field_are_redacted(secret: str, tmp_path: Path) -> None:
    result = probes.ProbeResult(kind="packages", run_label="r", config_sha256="c", started_utc="2026-10-30T00:00:00")
    result.observations = {"stdout": f"line {secret} end", "nested": [{"k": secret}]}
    text = probes.write_attempt(result, tmp_path).read_text(encoding="ascii")
    assert secret not in text and "[REDACTED:" in text
    assert json.loads(text)["redactions"] == 2


def test_clean_observations_are_kept_verbatim(tmp_path: Path) -> None:
    result = probes.ProbeResult(kind="packages", run_label="r", config_sha256="c", outcome="PASS", disposition="concluded",
                                started_utc="2026-10-30T00:00:00")
    result.observations = {"pins": ["pathspec==1.1.1"], "big": "y" * 5000, "set": {"b", "a"}}
    data = json.loads(probes.write_attempt(result, tmp_path).read_text(encoding="ascii"))
    assert data["observations"]["pins"] == ["pathspec==1.1.1"] and data["redactions"] == 0
    assert data["observations"]["set"] == ["a", "b"] and data["observations"]["big"].endswith("...[truncated]")


def test_a_record_holding_a_ram_only_body_is_refused_and_replaced_by_an_error_record(tmp_path: Path) -> None:
    body = "synthetic-source-body-" + "z" * 40
    result = probes.ProbeResult(kind="embedding", run_label="r", config_sha256="c", outcome="PASS", disposition="concluded",
                                started_utc="2026-10-30T00:00:00")
    result.observations = {"leaked": f"prefix {body} suffix"}
    text = probes.write_attempt(result, tmp_path, {body}).read_text(encoding="ascii")
    data = json.loads(text)
    assert body not in text and data["outcome"] == "ERROR" and data["observations"] == {}
    assert "RAM-only" in data["limitations"][0]


def test_an_attempt_is_never_overwritten_and_leaves_no_partial(tmp_path: Path) -> None:
    result = probes.ProbeResult(kind="redis", run_label="r", config_sha256="c", outcome="FAIL", disposition="concluded",
                                started_utc="2026-10-30T00:00:00")
    first = probes.write_attempt(result, tmp_path)
    original = first.read_bytes()
    result.outcome = "PASS"
    with pytest.raises(FileExistsError):
        probes.write_attempt(result, tmp_path)
    assert first.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == [first.name]


# --- bounded dispatch ---

def _run(body: Any, **config: Any) -> probes.ProbeResult:
    return probes.run_probe("packages", _parsed(**config), bodies={"packages": body}, grace_seconds=2)[0]


def test_a_well_formed_body_keeps_its_outcome() -> None:
    def body(ctx: probes.ProbeContext, res: probes.ProbeResult) -> None:
        res.outcome, res.disposition = "FAIL", "concluded"

    result = _run(body)
    assert (result.outcome, result.disposition) == ("FAIL", "concluded") and result.ended_utc


def test_a_body_past_its_deadline_is_cancelled_and_inconclusive() -> None:
    def body(ctx: probes.ProbeContext, res: probes.ProbeResult) -> None:
        while True:
            ctx.check()
            time.sleep(0.01)

    result = _run(body, limits={"timeout_seconds": 0.2, "max_download_bytes": 0})
    assert result.outcome == "INCONCLUSIVE" and "stopped after cancel: True" in result.limitations[0]


def test_an_exception_becomes_an_error_record() -> None:
    def body(ctx: probes.ProbeContext, res: probes.ProbeResult) -> None:
        raise RuntimeError("native client exploded")

    result = _run(body)
    assert result.outcome == "ERROR" and result.limitations == ["RuntimeError: native client exploded"]


@pytest.mark.parametrize(("outcome", "disposition"), [("GREEN", "concluded"), ("PASS", "closed"), ("PASS", "handoff")])
def test_malformed_or_handed_off_passes_are_inconclusive(outcome: str, disposition: str) -> None:
    def body(ctx: probes.ProbeContext, res: probes.ProbeResult) -> None:
        res.outcome, res.disposition = outcome, disposition

    assert _run(body).outcome == "INCONCLUSIVE"


def test_cleanups_run_in_reverse_and_failures_are_journaled() -> None:
    order: list[str] = []

    def body(ctx: probes.ProbeContext, res: probes.ProbeResult) -> None:
        ctx.on_cleanup("first", lambda: order.append("first"))
        ctx.on_cleanup("broken", lambda: (_ for _ in ()).throw(OSError("busy")))
        res.outcome, res.disposition = "PASS", "concluded"

    result = _run(body)
    assert order == ["first"] and result.outcome == "PASS"
    assert [row["action"] for row in result.cleanup] == ["broken", "first"]
    assert result.cleanup[0]["status"].startswith("failed: OSError")


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(probes.ConfigError):
        probes.run_probe("graph", _parsed())


def test_importing_the_probe_modules_does_no_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("work at import time")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    for name in ("probes", "redis_probe", "client_probe", "probe_child"):
        spec = importlib.util.spec_from_file_location(f"_p127_copy_{name}", _ROOT / f"tools/plan12_memory/{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)


# --- P1 package body with a scripted runner ---

def test_packages_needs_an_allowed_index_and_runs_nothing_otherwise() -> None:
    calls: list[Any] = []
    config = _parsed(packages={"index_url": "https://evil.example/simple", "candidates": ["rustworkx"]})
    result, _ = probes.run_probe("packages", config, bodies={
        "packages": lambda ctx, res: probes.run_packages(ctx, res, runner=lambda *a, **k: calls.append(a))})
    assert result.outcome == "UNRUN" and calls == []


def test_an_unresolvable_candidate_is_kept_in_a_partial_matrix() -> None:
    def runner(argv: list[str], timeout: float, env: Any = None, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        if stdin == "graspologic-native\n":
            return subprocess.CompletedProcess(argv, 1, "", "error: no wheels for cp314")
        return subprocess.CompletedProcess(argv, 1, "", "stop after resolution")

    config = _parsed(packages={"index_url": "https://pypi.org/simple", "candidates": ["graspologic-native"]})
    result, _ = probes.run_probe("packages", config, bodies={
        "packages": lambda ctx, res: probes.run_packages(ctx, res, runner=runner)})
    assert result.outcome == "FAIL" and result.observations["resolution"]["graspologic-native"]["resolved"] is False


# --- P1/P2 child helpers ---

def test_child_smoke_reports_each_distribution_without_crashing() -> None:
    rows = probe_child.smoke(["pathspec", "p127-no-such-distribution"])["packages"]
    assert rows["pathspec"]["ok"] and rows["pathspec"]["version"] == "1.1.1"
    assert "MPL" in rows["pathspec"]["license"]
    assert rows["p127-no-such-distribution"]["ok"] is False


def test_the_synthetic_corpus_is_deterministic() -> None:
    assert probe_child._corpus(5) == probe_child._corpus(5) and len(set(probe_child._corpus(50))) == 50


def test_the_cursor_is_replaced_atomically_and_holds_no_corpus_text(tmp_path: Path) -> None:
    cursor = tmp_path / "cursor.json"
    state = {"model": "m", "items": 5, "batch": 2, "next_batch": 1, "chain": "00"}
    probe_child._write_cursor(cursor, state)
    probe_child._write_cursor(cursor, {**state, "next_batch": 2})
    assert json.loads(cursor.read_text(encoding="utf-8"))["next_batch"] == 2
    assert sorted(path.name for path in tmp_path.iterdir()) == ["cursor.json"]
    assert not any(text in cursor.read_text(encoding="utf-8") for text in probe_child._corpus(5))


def test_main_refuses_a_bad_config_and_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "probe-config.json"
    bad.write_text(json.dumps(_config(extra=True)), encoding="utf-8")
    assert probes.main(["--kind", "redis", "--config", str(bad), "--out", str(tmp_path / "out")]) == 2
    assert "unknown config keys" in capsys.readouterr().err and not (tmp_path / "out").exists()


# --- P5 stub agent and sink scan ---

def test_the_stub_agent_reads_the_buffer_only_when_advertised(tmp_path: Path) -> None:
    buffer = tmp_path / "buffer.txt"
    buffer.write_text("disk text", encoding="utf-8")
    agent = client_probe.StubAgent("seed", str(buffer))
    out, rows = agent.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": True}}}})
    assert out[0]["result"]["protocolVersion"] == 1 and rows[0]["clientCapabilities"]["fs"]["readTextFile"]
    out, _ = agent.handle({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path)}})
    session = out[0]["result"]["sessionId"]
    assert [m["params"]["update"]["sessionUpdate"] for m in out[1:]] == ["agent_message_chunk", "tool_call"]
    assert agent.canary["message"] in json.dumps(out[1]) and agent.canary["card"] in json.dumps(out[2])
    out, _ = agent.handle({"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": session}})
    read = out[0]
    assert read["method"] == "fs/read_text_file" and out[-1] == {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}}
    _, rows = agent.handle({"jsonrpc": "2.0", "id": read["id"], "result": {"content": "unsaved buffer text"}})
    assert rows[0]["event"] == "fs_read_result" and rows[0]["matches_disk"] is False

    plain = client_probe.StubAgent("seed", str(buffer))
    plain.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientCapabilities": {}}})
    out, rows = plain.handle({"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": "s"}})
    assert all(m.get("method") != "fs/read_text_file" for m in out) and rows[0]["fs_read_requested"] is False
    out, _ = plain.handle({"jsonrpc": "2.0", "id": 9, "method": "authenticate", "params": {}})
    assert out[0]["error"]["code"] == -32601


def test_the_stub_serves_newline_delimited_json_and_journals(tmp_path: Path) -> None:
    log = tmp_path / "stub.jsonl"
    stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\nnot json\n')
    stdout = io.StringIO()
    client_probe.serve(client_probe.StubAgent("seed", str(tmp_path / "b.txt")), log, stdin, stdout)
    assert json.loads(stdout.getvalue().splitlines()[0])["id"] == 1
    assert [json.loads(line)["event"] for line in log.read_text(encoding="utf-8").splitlines()] == ["initialize", "malformed_input"]


def test_the_sink_scan_finds_canaries_in_plain_utf16_sqlite_and_zstd_cells(tmp_path: Path) -> None:
    needles = client_probe.canaries("seed")
    (tmp_path / "log.txt").write_text(f"x {needles['message']} y", encoding="utf-8")
    (tmp_path / "wide.bin").write_bytes(needles["card"].encode("utf-16-le"))
    with sqlite3.connect(tmp_path / "threads.db") as db:
        db.execute("CREATE TABLE threads (id TEXT, data BLOB)")
        db.execute("INSERT INTO threads VALUES (?, ?)", ("t1", zstd.compress(needles["card"].encode())))
    db.close()
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "other.txt").write_text("nothing here", encoding="utf-8")
    scan = client_probe.scan_sinks([tmp_path, tmp_path / "absent"], needles)
    assert any(path.endswith("log.txt") for path in scan["found"]["message"])
    assert {Path(p).name for p in scan["found"]["card"]} == {"wide.bin", "threads.db"}
    assert scan["unreadable"] == [f"{(tmp_path / 'absent').as_posix()} (absent)"]
    assert client_probe.scan_sinks([clean], needles)["found"] == {"message": [], "card": []}


def test_run_zed_keeps_canaries_out_of_the_record_and_hands_off_unrun_rows(tmp_path: Path) -> None:
    needles = client_probe.canaries("seed")
    log = tmp_path / "stub.jsonl"
    log.write_text(json.dumps({"event": "initialize", "clientCapabilities": {"fs": {"readTextFile": False}}}) + "\n"
                   + json.dumps({"event": "session_new"}) + "\n", encoding="utf-8")
    sinks = tmp_path / "zed-state"
    sinks.mkdir()
    (sinks / "Zed.log").write_text(f"rendered {needles['message']}", encoding="utf-8")
    config = _parsed(zed={"canary_seed": "seed", "stub_log": str(log), "sink_roots": [str(sinks)]})

    def runner(argv: list[str], timeout: float, env: Any = None, stdin: Any = None) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, f"{Path(argv[0]).name} 9.9.9 deadbeef extra", "")

    result, context = probes.run_probe("zed", config, bodies={"zed": lambda ctx, res: client_probe.run_zed(ctx, res, runner)})
    p5 = result.observations["P5"]
    assert p5["P5-a"]["status"] == "UNSUPPORTED" and p5["P5-d"]["status"] == "FAIL"
    assert p5["P5-b"]["status"] == "UNRUN" and p5["P5-c"]["optimus_path"]["owner"] == "M3"
    assert result.outcome == "FAIL" and result.disposition == "handoff"
    text = probes.write_attempt(result, tmp_path / "out", context.ram_only).read_text(encoding="ascii")
    assert needles["message"] not in text and json.loads(text)["outcome"] == "FAIL"


# --- dedicated marker: registered, excluded by default, never the shared tier ---

def test_the_probe_marker_is_excluded_by_the_approved_default_selection() -> None:
    assert "requires_plan12_probe_redis" in run_context.EXCLUDED_BY_DEFAULT
    expression = Expression.compile(run_context.APPROVED_DEFAULT_MARKER_EXPRESSION)
    assert not expression.evaluate(lambda name: name == "requires_plan12_probe_redis")
    assert expression.evaluate(lambda name: False)
    assert child_launch_inventory._EXCLUDED_MARKERS == set(run_context.EXCLUDED_BY_DEFAULT)


def test_the_live_file_carries_only_the_dedicated_marker() -> None:
    spec = importlib.util.spec_from_file_location("_p127_live", _LIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [mark.name for mark in module.pytestmark] == ["requires_plan12_probe_redis"]
    source = _LIVE.read_text(encoding="utf-8")
    for shared in ("live_redis_store", "live_redis_telemetry", "run_preflight", "OPTIMUS_REDIS_URL", "redis_support"):
        assert shared not in source
