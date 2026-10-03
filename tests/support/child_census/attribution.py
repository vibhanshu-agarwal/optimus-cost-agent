"""Per-site attribution for the child census: which launch sites launched, and what each child did.

Test support only. The census hook records, in the launching process, every `subprocess.Popen`
with the test frame it came from and the identity of the child it started; and, in each child that
inherited the hook, that child's own identity, arming and behaviour. These functions join those
rows to the committed launch-site map, one row per site. A site is credited only by launches
attributed to that site, and a launch only by the child it started: another site's child, a
reused test name, a start-only row or the mere presence of the hook in the environment is never
positive evidence that this child was armed and clean.
"""

from __future__ import annotations

from collections.abc import Iterable

HOOK_FOLDER = "child_census"
# Verdicts for one launch, worst first. A site is `launched_and_clean` only when every launch is clean.
LAUNCH_VERDICTS = (
    "real_adapter_requested", "launched_without_hook", "launch_failed", "launch_identity_unread", "child_unobserved",
    "child_unarmed", "child_incomplete", "pytest_session", "clean",
)


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


def bound_children(launch: dict[str, object], children: list[dict[str, object]]) -> tuple[list[dict[str, object]], str]:
    """The child records a launch started, and how they were bound.

    A launch names the process it created: its PID and, where the launching side could read it,
    creation time. A child record names its own identity and its parent's. The binding is `identity`
    when the launched process is the hooked child itself, and `via_parent` when the launched process
    is the hooked child's parent with the same full identity: on Windows the venv launcher starts
    the interpreter as its child, so the hooked interpreter is one hop below the launched process.
    A launch whose creation time could not be read names no exact process and binds to nothing
    (`none`): a PID alone, with or without a matching parent PID, is reused too often to bind on.
    """
    started = launch.get("child")
    if not isinstance(started, dict) or started.get("pid") is None or started.get("creation_time") is None:
        return [], "none"
    pid, created = started["pid"], started["creation_time"]
    exact = [child for child in children if child.get("pid") == pid and child.get("creation_time") == created]
    if exact:
        return (exact, "identity") if len(exact) == 1 else ([], "none")
    below = [child for child in children if child.get("ppid") == pid and child.get("parent_creation_time") == created]
    return (below, "via_parent") if below else ([], "none")


def child_verdict(child: dict[str, object]) -> str:
    """What one bound child record proves about that child."""
    if int(child.get("calls", 0)):
        return "real_adapter_requested"
    if not child.get("armed"):
        return "child_unarmed"
    if not child.get("ended"):
        return "child_incomplete"
    if child.get("is_pytest") or child.get("imported_unarmed"):
        # A nested pytest session guards its own adapter; that is the nested-session proof, not this census.
        return "pytest_session"
    return "clean"


def launch_verdict(launch: dict[str, object], bound: list[dict[str, object]]) -> str:
    """What one launch proves about the children it started: the worst of their verdicts."""
    if not launch.get("hook_env"):
        return "launched_without_hook"
    started = launch.get("child")
    if not isinstance(started, dict) or started.get("pid") is None:
        return "launch_failed"
    if started.get("creation_time") is None:
        # The launching side could not read the created process's identity: nothing can be bound to it.
        return "launch_identity_unread"
    if not bound:
        return "child_unobserved"
    verdicts = {child_verdict(child) for child in bound}
    return next(verdict for verdict in LAUNCH_VERDICTS if verdict in verdicts)


def per_site_table(
    site_map: dict[str, dict[str, object]], sites: list[dict[str, object]], launches: list[dict[str, object]],
    children: list[dict[str, object]], collected: set[str],
) -> dict[str, dict[str, object]]:
    """One row per mapped site.

    `launches` rows: site (key or None), test, hook_env (bool), launcher_pid, child ({pid, creation_time}
    or None when the launch failed). `children` rows: pid, creation_time, ppid, parent_creation_time,
    armed (bool), ended (bool), calls (int), is_pytest (bool), imported_unarmed (bool). `collected`: node IDs collected
    under the default selection, used to say whether a site's enclosing test function is reachable.
    """
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
        verdicts: dict[str, int] = {}
        bindings: dict[str, int] = {}
        for launch in rows:
            bound, how = bound_children(launch, children)
            verdict = launch_verdict(launch, bound)
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            bindings[how] = bindings.get(how, 0) + 1
        if entry["disposition"] != "census":
            status = "proof_elsewhere"
        elif not rows:
            status = "not_launched"
        else:
            worst = next(verdict for verdict in LAUNCH_VERDICTS if verdict in verdicts)
            status = "launched_and_clean" if worst == "clean" else worst.upper() if worst == "real_adapter_requested" else worst
        table[key] = {
            "disposition": entry["disposition"], "proof": entry["proof"], "reachability": reachable, "launches": len(rows),
            "tests": sorted({str(row.get("test", "")).split(" (")[0] for row in rows}),
            "hook_env_on_every_launch": bool(rows) and all(bool(row.get("hook_env")) for row in rows),
            "children_bound": sum(count for how, count in bindings.items() if how != "none"), "bindings": bindings,
            "verdicts": verdicts, "status": status,
        }
    return table


def unproven(table: dict[str, dict[str, object]]) -> list[str]:
    """Census-disposition sites that this census did not positively prove."""
    return sorted(key for key, row in table.items() if row["disposition"] == "census" and row["status"] != "launched_and_clean")


def child_record(rows: Iterable[dict[str, object]]) -> dict[str, object]:
    """Fold one hooked process's rows (one row file) into the child record the table consumes."""
    state: dict[str, object] = {
        "pid": None, "creation_time": None, "ppid": None, "parent_creation_time": None, "test": "", "armed": False, "ended": False,
        "is_pytest": None, "imported": False, "imported_unarmed": False, "calls": 0, "script": None, "launches": 0,
    }
    for row in rows:
        state["pid"] = state["pid"] if state["pid"] is not None else row.get("pid")
        state["test"] = state["test"] or row.get("test", "")
        event = row.get("event")
        if event == "launch":
            state["launches"] = int(state["launches"]) + 1  # type: ignore[call-overload]
        elif event == "start":
            state.update(armed=bool(row.get("armed")), ppid=row.get("ppid"), creation_time=row.get("creation_time"),
                         parent_creation_time=row.get("parent_creation_time"))
        elif event == "trusted_paths_imported":
            state["imported"] = True
            state["imported_unarmed"] = not bool(row.get("armed"))
        elif event == "real_adapter_call":
            state["calls"] = row.get("count", 0)
        elif event == "end":
            state.update(ended=True, is_pytest=row.get("is_pytest"), script=row.get("script"))
    return state
