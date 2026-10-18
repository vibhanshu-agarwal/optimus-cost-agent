"""Faults planted into a nested pytest-xdist run by `tests/unit/tools/test_run_context_xdist.py` (Plan 11.30 Task 5).

Loaded only with `-p tests.support.xdist_faults` in those nested runs; `P1130_XDIST_FAULT` names one fault, and
without it every hook here does nothing. Each fault happens in exactly one place: worker gw1, or the controller.
"""

from __future__ import annotations

import os

import pytest

FAULT = os.environ.get("P1130_XDIST_FAULT", "")
_CONFIGS: list[pytest.Config] = []


def _worker(config: pytest.Config) -> str | None:
    workerinput = getattr(config, "workerinput", None)
    return None if workerinput is None else str(workerinput.get("workerid"))


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    _CONFIGS.append(config)
    if _worker(config) != "gw1":
        return
    if FAULT == "absent_guard":
        from tools.testing import run_context_guard

        run_context_guard.install = lambda: "not_installed"
    if FAULT == "foreign_identity":  # gw1 claims an identity that is not itself: its own PID, another creation time
        from tools.testing import run_context_xdist

        real_identity = run_context_xdist._identity  # noqa: SLF001
        run_context_xdist._identity = lambda: (real_identity()[0], (real_identity()[1] or 0) + 1)  # noqa: SLF001
    if FAULT == "wrong_source":
        from tools.testing import run_context

        real = run_context._session_facts  # noqa: SLF001

        def other_lock(worktree):  # noqa: ANN001, ANN202 - same signature as the real one
            return {**real(worktree), "lock_sha256": "0" * 64}

        run_context._session_facts = other_lock  # noqa: SLF001


@pytest.hookimpl(trylast=True, optionalhook=True)
def pytest_configure_node(node) -> None:  # noqa: ANN001 - xdist's WorkerController
    from tools.testing import run_context_xdist

    if node.gateway.id != "gw1":
        return
    if FAULT == "absent_metadata":
        node.workerinput.pop(run_context_xdist.WORKER_INPUT, None)
    if FAULT == "forged_token":
        node.workerinput[run_context_xdist.WORKER_INPUT] = {**node.workerinput[run_context_xdist.WORKER_INPUT], "token": "0" * 64}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if FAULT == "collection_disagreement" and _worker(config) == "gw1" and items:
        items.pop()


_DUPLICATED: list[str] = []
_SKIPPED_CALL: list[str] = []
_FOREIGN: list[str] = []


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> bool | None:
    """missing_call: gw1 runs its first test through pytest's own protocol with the call left out (pytest's
    setup-only switch, for that one test): setup and teardown pass and are sent, the call never runs, and the
    worker's own count stays equal to what it sent."""
    if FAULT != "missing_call" or _worker(item.config) != "gw1" or _SKIPPED_CALL:
        return None
    from _pytest.runner import runtestprotocol

    _SKIPPED_CALL.append(item.nodeid)
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    before = item.config.option.setuponly
    item.config.option.setuponly = True
    try:
        runtestprotocol(item, nextitem=nextitem, log=True)
    finally:
        item.config.option.setuponly = before
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    config = _CONFIGS[-1] if _CONFIGS else None
    if config is None:
        return
    if FAULT == "duplicate_report" and _worker(config) is None and report.when == "call" and not _DUPLICATED:
        _DUPLICATED.append(report.nodeid)  # the controller sees one forwarded report twice
        config.hook.pytest_runtest_logreport(report=report)
    if FAULT == "foreign_node" and _worker(config) == "gw1" and report.when == "call" and not _FOREIGN:
        # gw1 sends, through xdist's own channel, a report for a test nobody selected, and counts it as sent.
        from tools.testing import run_context_xdist

        interactor = next(plugin for plugin in config.pluginmanager.get_plugins() if type(plugin).__name__ == "WorkerInteractor")
        data = config.hook.pytest_report_to_serializable(config=config, report=report)
        _FOREIGN.append(data["nodeid"] + "_foreign")
        data.update(nodeid=_FOREIGN[0], item_index=interactor.item_index, worker_id=interactor.workerid,
                    testrun_uid=interactor.testrunuid)
        interactor.sendevent("testreport", data=data)
        run_context_xdist.count_phase()
