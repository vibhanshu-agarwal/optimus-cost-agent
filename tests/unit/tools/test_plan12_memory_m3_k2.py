"""Plan 12.11 K2 measurement tool: the parts that run without the released store. The measurement itself needs the release."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from tools.plan12_memory import m3_k2


def test_without_the_release_nothing_runs(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("P1211_MEMORY_DOCKER_RELEASED", raising=False)
    monkeypatch.setattr(m3_k2, "run", lambda *_a, **_k: pytest.fail("ran without the release"))
    assert m3_k2.main(["--output", "unused.json"]) == 2
    assert capsys.readouterr().out.startswith("UNRUN")


def test_summaries_report_the_tail_not_only_the_middle() -> None:
    values = [0.01] * 95 + [2.0] * 5
    assert m3_k2._summary(values, 1000) == {"count": 100, "p50": 10.0, "p95": 2000.0, "max": 2000.0}
    assert m3_k2._summary([]) == {"count": 0}


@pytest.mark.parametrize(("shown", "mib"), [("62.9MiB / 1GiB", 62.9), ("1.5GiB / 2GiB", 1536.0), ("512KiB / 1GiB", 0.5), ("", None)])
def test_container_memory_is_read_in_mib(monkeypatch: pytest.MonkeyPatch, shown: str, mib: float | None) -> None:
    monkeypatch.setattr(m3_k2, "docker", lambda *_a: subprocess.CompletedProcess([], 0, stdout=shown, stderr=""))
    assert m3_k2._container_ram_mib("c") == mib


def test_the_throttle_reaches_only_the_released_store_s_own_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(argv: Any, *_args: Any, **_kwargs: Any) -> Any:
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(m3_k2.local_infra.subprocess, "run", run)
    with m3_k2._throttled(["--device-write-bps", "/dev/sdd:256kb"]):
        m3_k2.local_infra.subprocess.run(["docker", "run", "-d", "--name", m3_k2.CONTAINER, "image"])
        m3_k2.local_infra.subprocess.run(["docker", "run", "-d", "--name", "other", "image"])
    assert seen == [["docker", "run", "-d", "--device-write-bps", "/dev/sdd:256kb", "--name", m3_k2.CONTAINER, "image"],
                    ["docker", "run", "-d", "--name", "other", "image"]]


def test_the_expected_inventory_comes_from_the_schedule_alone() -> None:
    """Codex CP2 review 1, finding 10: the frozen population is 10,000 live items, each at the version the schedule gives it."""
    expected = m3_k2.schedule(events=100_000, items=10_000)
    assert sum(len(per_client) for per_client in expected) == 10_000
    assert {version for per_client in expected for _status, version, _content in per_client.values()} == {10}
    small = m3_k2.schedule(events=12, items=8)  # 3 writes over 2 slots per client: one item twice, one once
    assert small[0] == {m3_k2._item(0, 0): ("active", 2, m3_k2._digest(m3_k2._statement(0, 0, 2))),
                        m3_k2._item(0, 1): ("active", 1, m3_k2._digest(m3_k2._statement(0, 1, 1)))}


def test_an_unintended_purge_or_a_short_population_fails_the_identity_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    expected = m3_k2.schedule(events=8, items=8)
    items = []
    for n, per_client in enumerate(expected):
        for item, (status, version, _content) in per_client.items():
            slot = int(item[-12:], 16)
            purged = n == 0 and slot == 0  # the store returns client 0's item as purged although nothing purged it
            items.append((n, {"item": item, "status": "purged" if purged else status, "version": version + purged,
                              "statement": "" if purged else m3_k2._statement(n, slot, version)}))
    replies = {f"p-{n}": [record for owner, record in items if owner == n] for n in range(m3_k2.CLIENTS)}
    monkeypatch.setattr(m3_k2, "_service", lambda *_a: None)
    monkeypatch.setattr(m3_k2, "_call", lambda _s, body: (200, {"items": replies[body["project"]], "cursor": None}))
    check = m3_k2._identity_check(None, tmp_path, list(replies), expected, "t")  # type: ignore[arg-type]
    assert (check["wrong"], check["live_items"], check["missing"], check["unexpected"]) == (1, 7, 0, 0)
