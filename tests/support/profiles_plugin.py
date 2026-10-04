"""`--profile`: run one static test profile of the selection (Plan 11.30).

Registered from the root conftest. Without `--profile` it does nothing. With one, after every other
deselection (`-m`, `-k`, `--deselect`, explicit targets), it classifies the remaining items with
`tests/profiles.toml` and deselects those outside the profile through `pytest_deselected`, so pytest's
own counts and the run context's node stream record them as deselected. The effective `-m` is never
touched, so the run context classifies the session exactly as it would without a profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.testing import test_profiles

_MANIFEST = Path(__file__).resolve().parents[1] / "profiles.toml"
_SUMMARY: pytest.StashKey[str] = pytest.StashKey()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--profile",
        dest="test_profile",
        choices=tuple(test_profiles.STATIC_PROFILES),
        default=None,
        help="run one static test profile (tests/profiles.toml) of the selection; absent or 'full' runs it unchanged.",
    )


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
