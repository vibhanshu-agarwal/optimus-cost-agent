"""Plan 12.12 K2 contention driver: the frozen import leg's source (targets.json k2_contention import_leg), read by the import."""

from __future__ import annotations

from pathlib import Path

from optimus.context import memory_import as mi
from tools.plan12_memory import m3p2_contention as c


def test_the_import_leg_is_the_frozen_seeded_source_and_reads_whole(tmp_path: Path) -> None:
    leg = c._workload()["import_leg"]
    first = c.import_source(tmp_path / "a", "p-bi-0")
    assert first == c.import_source(tmp_path / "b", "p-bi-0"), "seeded: the same source every run"
    assert len(first) == leg["entries"] == 1000 and all(200 <= len(s) <= 2000 for s in first)
    assert all(s.startswith(f"p1212 import entry {i}: ") for i, s in enumerate(first))
    assert sorted(p.name for p in (tmp_path / "a").iterdir()) == sorted(["MEMORY.md", *(f"topic-{t}.md" for t in range(10))])
    source = mi.Reader(tmp_path / "a", project="p-bi-0", mapped=None, sanitize=lambda v: v, workspace=None).read()
    assert [e.disposition for e in source.entries] == ["import"] * 1000 and len(source.files) == 11 and not source.gaps
