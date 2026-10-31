from __future__ import annotations

from types import MappingProxyType

import pytest

from optimus.acp.e2e_transcript import _looks_like_process_env
from optimus.acp.spec import _permission_approved
from optimus.context.adapter import ApprovalDecision, approval_fact_from_permission


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ((), False),
        (("PATH",), False),
        (("HOME",), False),
        (("USERPROFILE",), False),
        (("SystemRoot",), False),
        (("HOME", "USERPROFILE", "SystemRoot"), False),
        (("PATH", "HOME"), True),
        (("PATH", "USERPROFILE"), True),
        (("PATH", "SystemRoot"), True),
        (("Path", "HOME"), False),
        (("PATH", "systemroot"), False),
        (("OPTIMUS_API_KEY",), True),
        (("PATH", "HOME", "OPTIMUS_API_KEY"), True),
    ],
)
def test_process_environment_key_characterization(keys, expected):
    assert _looks_like_process_env(dict.fromkeys(keys)) is expected


def test_process_environment_converts_non_string_keys():
    class PathKey:
        def __str__(self):
            return "PATH"

    assert _looks_like_process_env({PathKey(): None, "HOME": None}) is True


@pytest.mark.parametrize(
    ("result", "halted", "expected"),
    [
        ({"outcome": {"outcome": "selected", "optionId": "approve"}}, False, ApprovalDecision.GRANTED),
        ({"outcome": {"outcome": "selected", "optionId": "approve"}}, True, ApprovalDecision.CANCELLED),
        ({"outcome": {"outcome": "selected", "optionId": "reject"}}, False, ApprovalDecision.DENIED),
        ({"outcome": {"outcome": "selected", "optionId": "reject"}}, True, ApprovalDecision.CANCELLED),
        ({"outcome": {"outcome": "cancelled"}}, False, ApprovalDecision.CANCELLED),
        ({"outcome": "cancelled"}, False, ApprovalDecision.DENIED),
        ({"outcome": "cancelled"}, True, ApprovalDecision.CANCELLED),
        ({}, False, ApprovalDecision.DENIED),
        ({}, True, ApprovalDecision.CANCELLED),
    ],
)
def test_permission_fact_characterization(result, halted, expected):
    fact = approval_fact_from_permission(turn_seq=7, artifact_hash="hash", permission_result=result, halted=halted, scope=("x",))
    assert (fact.turn_seq, fact.artifact_hash, fact.decision, fact.scope) == (7, "hash", expected, ("x",))
    assert (fact.decision is ApprovalDecision.GRANTED) == (_permission_approved(result) and not halted)


def test_nested_mapping_proxy_preserves_existing_spec_disagreement():
    result = {"outcome": MappingProxyType({"outcome": "selected", "optionId": "approve"})}
    fact = approval_fact_from_permission(turn_seq=1, artifact_hash="hash", permission_result=result, halted=False)
    assert fact.decision is ApprovalDecision.GRANTED
    assert _permission_approved(result) is False


def test_default_approval_scope_is_empty():
    fact = approval_fact_from_permission(turn_seq=1, artifact_hash="hash", permission_result={}, halted=False)
    assert fact.scope == ()


def test_halt_suppresses_outcome_lookup_failure():
    class FailingDict(dict):
        def get(self, key, default=None):
            raise LookupError(key)

    result = {"outcome": FailingDict()}
    assert (
        approval_fact_from_permission(turn_seq=1, artifact_hash="hash", permission_result=result, halted=True).decision
        is ApprovalDecision.CANCELLED
    )
    with pytest.raises(LookupError, match="outcome"):
        approval_fact_from_permission(turn_seq=1, artifact_hash="hash", permission_result=result, halted=False)


@pytest.mark.parametrize(
    ("outcome", "halted", "calls"),
    [
        ({"outcome": "selected", "optionId": "approve"}, True, []),
        ({"outcome": "cancelled"}, False, ["outcome"]),
        ({"outcome": "selected", "optionId": "approve"}, False, ["outcome", "outcome", "optionId"]),
        ({"outcome": "other"}, False, ["outcome", "outcome"]),
    ],
)
def test_permission_outcome_lookup_order_is_preserved(outcome, halted, calls):
    seen = []

    class ObservedDict(dict):
        def get(self, key, default=None):
            seen.append(key)
            return super().get(key, default)

    approval_fact_from_permission(turn_seq=1, artifact_hash="hash", permission_result={"outcome": ObservedDict(outcome)}, halted=halted)
    assert seen == calls
