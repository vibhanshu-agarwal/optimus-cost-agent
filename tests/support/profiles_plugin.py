"""`--profile` and `--audit-depth` (Plan 11.30).

Registered from the root conftest. Without `--profile` it does nothing. With one, after every other
deselection (`-m`, `-k`, `--deselect`, explicit targets), it classifies the remaining items with
`tests/profiles.toml` and deselects those outside the profile through `pytest_deselected`, so pytest's
own counts and the run context's node stream record them as deselected. The effective `-m` is never
touched, so the run context classifies the session exactly as it would without a profile.

`--audit-depth` (Task 4) defaults to full. A current-audit test asks the `audit_budget` fixture for the
options of an enumerated probe; at quick depth it gets the reduced budget pinned with the Plan 11.26
owner. Every budget a test used, and the session's effective depth, go into the run's terminal record
(through the root conftest) and its terminal summary. A quick run is reduced-depth evidence only: never
a checkpoint, a final gate or a repeat-100 obligation.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tools.testing import test_profiles

_MANIFEST = Path(__file__).resolve().parents[1] / "profiles.toml"
_SUMMARY: pytest.StashKey[str] = pytest.StashKey()
_AUDIT_USED: pytest.StashKey[list[dict[str, object]]] = pytest.StashKey()

AUDIT_DEPTHS = ("full", "quick")
# The only reduced-depth budget, pinned with the Plan 11.26 owner (Task 4): H5 repeats each applicable
# close-path x cause family 100 times at full depth (the sealed count) and once at quick. Every other
# audited probe -- H4's 1,000 seeds and literal corpus, the S1 windows, single executions -- has no
# budget here and always runs full.
AUDIT_BUDGETS: dict[str, dict[str, dict[str, int]]] = {
    "h5.shutdown_schedule": {"full": {"repeats": 100}, "quick": {"repeats": 1}},
}


# Each session's effective depth and every current measurement a test helper reused: pushed at configure and
# popped at unconfigure, so a session started inside another (an in-process pytest.main) never disturbs it.
_SESSIONS: list[dict[str, Any]] = [{"depth": "full", "reused": []}]


def current_audit_session() -> dict[str, Any]:
    """The innermost running session's audit state."""
    return _SESSIONS[-1]


def audit_options(depth: str, entry: str) -> dict[str, int]:
    """The measurement options of an enumerated probe at `depth`. A probe without a budget is refused, never guessed."""
    budget = AUDIT_BUDGETS.get(entry)
    if budget is None:
        raise ValueError(f"{entry}: no reduced-depth budget is enumerated for this probe, so it always runs full")
    return dict(budget[depth])


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--profile",
        dest="test_profile",
        choices=tuple(test_profiles.STATIC_PROFILES),
        default=None,
        help="run one static test profile (tests/profiles.toml) of the selection; absent or 'full' runs it unchanged.",
    )
    parser.addoption(
        "--audit-depth",
        dest="audit_depth",
        choices=AUDIT_DEPTHS,
        default="full",
        help="full (default): every current audit probe at its full count; quick: the enumerated reduced-depth "
        "budgets, labelled in the run's terminal record (never checkpoint, final or repeat-100 evidence).",
    )


def pytest_configure(config: pytest.Config) -> None:
    _SESSIONS.append({"depth": str(config.getoption("audit_depth")), "reused": []})


def pytest_unconfigure(config: pytest.Config) -> None:
    del config
    if len(_SESSIONS) > 1:
        _SESSIONS.pop()


def measure_current_entry(*, source: Any, spec: Any, entry: str, options: Any, repository_root: Any) -> tuple[Any, Any]:
    """A test helper's route to a current measurement. An identical earlier measurement in this session is reused,
    and the run's terminal record names it; it is never counted as a fresh execution. Production never reuses."""
    from tools.plan1126_runtime_audit.measurement import session_measurement_reuse  # noqa: PLC0415 - audit tests only

    nodeid = os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0] or "<outside-a-test>"
    binding, result, earlier = session_measurement_reuse().measure(
        source=source, spec=spec, entry=entry, options=options, repository_root=repository_root,
        depth=current_audit_session()["depth"], requester=nodeid,
    )
    if earlier is not None:
        current_audit_session()["reused"].append({"entry": entry, "nodeid": nodeid, "from_nodeid": earlier})
    return binding, result


@pytest.fixture
def audit_budget(request: pytest.FixtureRequest) -> Callable[[str], dict[str, int]]:
    """The options of an enumerated probe at this session's effective depth; each use is recorded for the run."""
    depth = str(request.config.getoption("audit_depth"))

    def budget(entry: str) -> dict[str, int]:
        options = audit_options(depth, entry)
        request.config.stash.setdefault(_AUDIT_USED, []).append({
            "entry": entry, "depth": depth, "repeats": options["repeats"],
            "full_repeats": AUDIT_BUDGETS[entry]["full"]["repeats"], "nodeid": request.node.nodeid,
        })
        return options

    return budget


def audit_record(config: pytest.Config) -> dict[str, Any] | None:
    """The effective depth, the budgets used and the measurements reused, for the run's terminal record; None
    when this plugin is not loaded."""
    depth = config.getoption("audit_depth", default=None)
    if depth is None:
        return None
    return {"depth": str(depth), "budgets": list(config.stash.get(_AUDIT_USED, [])), "reused": list(current_audit_session()["reused"])}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    profile = config.getoption("test_profile")
    if profile is None:
        return
    try:
        manifest = test_profiles.load_manifest(_MANIFEST.read_text(encoding="utf-8"))
        classification = test_profiles.classify_nodes(tuple(item.nodeid for item in items), manifest)
        members = test_profiles.profile_members(classification, profile)
    except (OSError, test_profiles.ManifestError, test_profiles.ClassificationError) as error:
        raise pytest.UsageError(f"--profile {profile}: {error}") from None
    selected = [item for item in items if item.nodeid in members]
    deselected = [item for item in items if item.nodeid not in members]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
    config.stash[_SUMMARY] = (
        f"test-profiles: profile={profile} selected={len(selected)} deselected={len(deselected)} manifest={manifest.digest[:12]}"
    )


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config) -> None:
    del exitstatus
    line = config.stash.get(_SUMMARY, None)
    if line is not None:
        terminalreporter.write_sep("=", line)
    depth = config.getoption("audit_depth")
    used = config.stash.get(_AUDIT_USED, [])
    reused = current_audit_session()["reused"]
    if depth != "full" or used or reused:  # an ordinary full run without a budget or a reuse prints nothing new
        parts = [f"audit-depth: depth={depth}"]
        if depth != "full":
            parts.append("REDUCED-DEPTH (not checkpoint, final or repeat-100 evidence)")
        budgets = sorted({f"{item['entry']} repeats={item['repeats']}/{item['full_repeats']}" for item in used})
        parts.append("budgets: " + (", ".join(budgets) if budgets else "none used"))
        if reused:
            parts.append(f"reused: {len(reused)} earlier current measurement(s), named in the run record")
        terminalreporter.write_sep("=", " ".join(parts))
