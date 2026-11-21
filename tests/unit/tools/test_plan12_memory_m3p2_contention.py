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


def test_the_driver_shows_every_page_before_it_asks_to_apply(tmp_path: Path) -> None:
    """Codex CP2 review 1, finding 5: the 1,000-entry preview's 20 pages are each shown through the production commands, then
    apply asks for the one-shot confirmation."""
    from optimus.acp import memory_commands as mc
    from tests.unit.context.test_authored_memory import _adapter
    from tests.unit.optimus_gateway.test_memory_store_purge import store as purge_store

    store = _adapter(purge_store(tmp_path / "store")[0])
    commands = mc.MemoryCommands(store, trusted=True, sanitize=lambda v: v, scope="project",
                                 imports=mi.ImportLog(tmp_path / "config", store.project))
    c.import_source(tmp_path / "src", store.project)
    asked = c.prepare_import(commands, tmp_path / "src")
    assert asked.confirm is not None and asked.confirm.kind == "import"
    held = commands._importer.held(asked.confirm.meta["preview"])
    assert held.pages == 20 and held.all_shown
