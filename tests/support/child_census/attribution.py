"""Per-site attribution for the child census: which launch sites actually launched, and with what.

Test support only. The census hook records, in the launching process, every `subprocess.Popen`
with the test frame it came from; and, in each child that inherited the hook, what that child did.
These functions join those rows to the committed launch-site map, one row per site: a site is
credited only by launches attributed to that site, never by another launch in the same file.
"""

from __future__ import annotations

from collections.abc import Iterable

HOOK_FOLDER = "child_census"


def site_for(file: str, function: str, line: int, sites: Iterable[dict[str, object]]) -> str | None:
    """The launch site a frame belongs to: same file and function, nearest site line at or before the frame's line."""
    candidates = [site for site in sites if site["file"] == file and site["function"] == function and int(site["line"]) <= line]  # type: ignore[call-overload]
    if not candidates:
        return None
    return str(max(candidates, key=lambda site: int(site["line"]))["key"])  # type: ignore[call-overload]


def hook_env_present(env: dict[str, str] | None, own_env: dict[str, str]) -> bool:
    """Whether a launch's environment carries the census hook: inherited, or rebuilt with it kept."""
    effective = own_env if env is None else env
    return bool(effective.get("OPTIMUS_TEST_CHILD_CENSUS_DIR")) and HOOK_FOLDER in effective.get("PYTHONPATH", "")


def per_site_table(
    site_map: dict[str, dict[str, object]], sites: list[dict[str, object]], launches: list[dict[str, object]],
    children: list[dict[str, object]], collected: set[str],
) -> dict[str, dict[str, object]]:
    """One row per mapped site.

    `launches` rows: site (key or None), test, hook_env (bool). `children` rows: test, calls (int),
    ended (bool), is_pytest (bool). `collected`: node IDs collected under the default selection,
    used to say whether a site's enclosing test function is reachable at all.
    """
    by_test_children: dict[str, list[dict[str, object]]] = {}
    for child in children:
        by_test_children.setdefault(str(child.get("test", "")).split(" (")[0], []).append(child)
    by_site: dict[str, list[dict[str, object]]] = {}
    for launch in launches:
        if launch.get("site"):
            by_site.setdefault(str(launch["site"]), []).append(launch)
    inventory = {str(site["key"]): site for site in sites}
    table: dict[str, dict[str, object]] = {}
    for key, entry in site_map.items():
        site = inventory.get(key, {})
        file, function = key.split("::")[0], str(site.get("function", ""))
        test_node = f"{file}::{function}"
        reachable = "collected" if any(node == test_node or node.startswith(test_node + "[") for node in collected) \
            else "helper" if not function.startswith("test_") else "not_collected"
        rows = by_site.get(key, [])
        tests = sorted({str(row.get("test", "")).split(" (")[0] for row in rows})
        # Every child attributed to those tests counts; the launching session's own row carries no test.
        observed = [child for test in tests for child in by_test_children.get(test, [])]
        calls = sum(int(child.get("calls", 0)) for child in observed)
        hooked = all(bool(row.get("hook_env")) for row in rows) if rows else False
        if entry["disposition"] != "census":
            status = "proof_elsewhere"
        elif not rows:
            status = "not_launched"
        elif not hooked:
            status = "launched_without_hook"
        elif not observed:
            status = "launched_no_child_seen"
        elif calls:
            status = "REAL_ADAPTER_REQUESTED"
        else:
            status = "launched_and_clean"
        table[key] = {
            "disposition": entry["disposition"], "proof": entry["proof"], "reachability": reachable, "launches": len(rows),
            "tests": tests, "hook_env_on_every_launch": hooked, "children_observed_for_those_tests": len(observed),
            "real_adapter_calls": calls, "status": status,
        }
    return table


def unproven(table: dict[str, dict[str, object]]) -> list[str]:
    """Census-disposition sites that this census did not positively prove."""
    return sorted(key for key, row in table.items() if row["disposition"] == "census" and row["status"] != "launched_and_clean")
