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
