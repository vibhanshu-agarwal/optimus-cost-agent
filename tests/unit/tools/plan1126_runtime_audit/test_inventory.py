"""Behavior tests for AST/token-derived inventory discovery."""

from __future__ import annotations

from tools.plan1126_runtime_audit.inventory import discover_sites
from tools.plan1126_runtime_audit.model import BaselineScope, Classification, InventoryKind
from tools.plan1126_runtime_audit.source import SourceTree

_SOURCE = '''
import asyncio
import sys

async def audit_fixture(owner, redis_module, telemetry, sink):
    """Ownership invariant: this fixture owns the created work."""
    task = asyncio.create_task(worker())
    task.cancel()
    queue = asyncio.Queue(maxsize=3)
    runtime = RedisRuntime()
    client = redis_module.Redis()
    pool = redis_module.ConnectionPool()
    owner.runtime = runtime
    telemetry.emit("event")
    debug_trace("debug")
    print("bootstrap", file=sys.stderr)
    safe = redact(payload)
    sink.export(safe)
    start_delivery()
    publish_response()
    settle_delivery()
    error_response(INTERNAL_ERROR)
    await runtime.aclose()
    try:
        await worker()
    except Exception:
        sanitize_failure()
'''


def test_discover_sites_derives_all_required_concerns_sorted_and_unique() -> None:
    sites = discover_sites(SourceTree({"fixture.py": _SOURCE}), default_scope=BaselineScope.MERGED)
    kinds = {site.kind for site in sites}
    assert kinds == set(InventoryKind)
    keys = [(site.path, site.symbol, site.line, site.kind.value) for site in sites]
    assert keys == sorted(set(keys))
    assert all(site.evidence_digest.startswith("sha256:") for site in sites)
    assert all(site.baseline_scope is BaselineScope.MERGED for site in sites)
    task_site = next(site for site in sites if site.kind is InventoryKind.TASK_CREATE)
    assert task_site.invariant == "Ownership invariant: this fixture owns the created work."


def test_discover_sites_compares_merged_and_overlay_symbols_without_expected_site_list() -> None:
    merged = SourceTree({"same.py": "def f():\n    publish_response()\n"})
    overlay = SourceTree({"same.py": "def f():\n    publish_response(extra=True)\n"})
    sites = discover_sites(merged, overlay=overlay)
    publication = [site for site in sites if site.kind is InventoryKind.DELIVERY_PUBLICATION]
    assert len(publication) == 2
    assert {site.baseline_scope for site in publication} == {BaselineScope.BOTH_DIVERGENT}


def test_derived_inventory_has_no_unclassified_sites() -> None:
    probe = discover_sites(SourceTree({"fixture.py": _SOURCE}), default_scope=BaselineScope.MERGED)
    classifications = {
        (site.path, site.symbol, site.line, site.kind): Classification.INTENTIONALLY_EXCEPTIONAL
        for site in probe
    }
    classified = discover_sites(
        SourceTree({"fixture.py": _SOURCE}),
        default_scope=BaselineScope.MERGED,
        classifications=classifications,
    )
    assert classified
    assert all(site.classification is not Classification.UNCLASSIFIED for site in classified)


def test_discover_sites_finds_bare_tuple_and_qualified_broad_catches() -> None:
    source = SourceTree({"catches.py": '''
import builtins

def catches():
    try:
        work()
    except:
        recover_bare()
    try:
        work()
    except (ValueError, Exception):
        recover_tuple()
    try:
        work()
    except builtins.BaseException:
        recover_qualified()
'''})
    broad = [site for site in discover_sites(source) if site.kind is InventoryKind.BROAD_CATCH]
    assert len(broad) == 3


def test_reconciliation_ignores_line_only_shifts_for_stable_symbol_site() -> None:
    merged = SourceTree({"same.py": '''
def f():
    """Invariant: publication is owned here."""
    publish_response()
'''})
    overlay = SourceTree({"same.py": '''


def f():
    """Invariant: publication is owned here."""

    publish_response()
'''})
    publication = [site for site in discover_sites(merged, overlay=overlay) if site.kind is InventoryKind.DELIVERY_PUBLICATION]
    assert len(publication) == 1
    assert publication[0].baseline_scope is BaselineScope.BOTH_ALIGNED


def test_reconciliation_marks_invariant_only_change_divergent() -> None:
    merged = SourceTree({"same.py": '''
def f():
    """Invariant: caller owns publication."""
    publish_response()
'''})
    overlay = SourceTree({"same.py": '''
def f():
    """Invariant: writer owns publication."""
    publish_response()
'''})
    publication = [site for site in discover_sites(merged, overlay=overlay) if site.kind is InventoryKind.DELIVERY_PUBLICATION]
    assert len(publication) == 2
    assert {site.baseline_scope for site in publication} == {BaselineScope.BOTH_DIVERGENT}
