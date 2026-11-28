"""Complete-cohort typing refusals and fixed offline authorization vectors."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest

from optimus.acp.launch_approvals import build_approval_record, serialize_approval_record
from optimus.acp.launch_gate import LaunchGateError
from tests.unit.acp.test_launch_approvals import _sample_workspace_identity


@pytest.mark.parametrize("mode, expected_json", [('durable', '{"approval_id":"appr_000000000000000000000000","ceremony_cli_version":"0.0.test","consumed":false,"created_at":"2026-10-18T00:00:00+00:00","creator_identity":"offline-operator","expires_at":null,"identity_format_version":3,"migration_provenance":null,"mode":"durable","model_observation":"offline-model","monotonic_grants":{"OPTIMUS_LIVE_MAX_COST_USD":"0.25"},"policy_compatibility":"P9.99-v1","record_hmac":"0e758fca18de5a6a380d0e95c046890adb503c07038a4db3fde2b96423112fad","registry_version":"P9.99-v1","schema_version":2,"secret_fingerprints":{"OPTIMUS_API_KEY":"fixture-fingerprint"},"security_literals":{"OPTIMUS_GATEWAY_URL":"http://127.0.0.1:8765"},"security_snapshot_digest":"5c888fbc229c90003c160e55d7e6a3de354cb01f161ba27d6ced98974731cf57","workspace_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'), ('one-shot', '{"approval_id":"appr_000000000000000000000000","ceremony_cli_version":"0.0.test","consumed":false,"created_at":"2026-10-18T00:00:00+00:00","creator_identity":"offline-operator","expires_at":"2026-10-18T00:05:00+00:00","identity_format_version":3,"migration_provenance":null,"mode":"one-shot","model_observation":"offline-model","monotonic_grants":{"OPTIMUS_LIVE_MAX_COST_USD":"0.25"},"policy_compatibility":"P9.99-v1","record_hmac":"cfa7b364b80a931c304d2915c301338c874803a0a2ff9144693ca06de15ab52e","registry_version":"P9.99-v1","schema_version":2,"secret_fingerprints":{"OPTIMUS_API_KEY":"fixture-fingerprint"},"security_literals":{"OPTIMUS_GATEWAY_URL":"http://127.0.0.1:8765"},"security_snapshot_digest":"5c888fbc229c90003c160e55d7e6a3de354cb01f161ba27d6ced98974731cf57","workspace_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')])
def test_fixed_offline_approval_json_and_hmac_vector(monkeypatch, mode, expected_json):
    from optimus.acp import launch_approvals as approvals

    monkeypatch.setattr(approvals.secrets, "token_hex", create_autospec(approvals.secrets.token_hex, return_value="0" * 24))
    monkeypatch.setattr(approvals, "_creator_identity", create_autospec(approvals._creator_identity, return_value="offline-operator"))
    monkeypatch.setattr(approvals, "_package_version", create_autospec(approvals._package_version, return_value="0.0.test"))
    record = build_approval_record(
        mode=mode, workspace_identity=_sample_workspace_identity(),
        security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        secret_fingerprints={"OPTIMUS_API_KEY": "fixture-fingerprint"},  # pragma: allowlist secret - fixed synthetic test fingerprint, not a credential
        monotonic_grants={"OPTIMUS_LIVE_MAX_COST_USD": "0.25"}, model_observation="offline-model",
        hmac_key=b"cohort3-offline-vector-key", override_created_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
    )
    # Constants were derived independently from the signed-field protocol, not this serializer.
    assert serialize_approval_record(record) == expected_json
    assert record.record_hmac == json.loads(expected_json)["record_hmac"]
    assert record.expires_at == (None if mode == "durable" else datetime(2026, 10, 18, 0, 5, tzinfo=timezone.utc))


def _typing_dacl_api(monkeypatch, module, *, null, status=0, null_dacl=False):
    """Allocated ACE positive control; NULL is intercepted before any unsafe dereference. `status` is what
    GetSecurityInfo returns, and `null_dacl` makes a successful call report no DACL (#693)."""
    import ctypes

    calls = []
    ace = (ctypes.c_ubyte * 12)()  # ACCESS_ALLOWED_ACE, with allocated SID storage.
    real_cast = ctypes.cast

    def checked_cast(pointer, target):
        if isinstance(pointer, ctypes.c_void_p) and pointer.value is None:
            raise AssertionError("NULL ACE reached dereference")
        return real_cast(pointer, target)

    descriptor = 0x51D  # a stand-in address for the security descriptor GetSecurityInfo allocates

    def security(handle, kind, flags, _owner, _group, dacl, _sacl, sd):
        calls.append(("GetSecurityInfo", handle, kind, flags))
        if status:
            return status
        dacl._obj.value = None if null_dacl else ctypes.addressof(ace)
        sd._obj.value = descriptor
        return 0  # ERROR_SUCCESS

    def information(_pointer, size, _length, _kind):
        size._obj.AceCount = 1
        return True

    def get_ace(_pointer, _index, pointer):
        calls.append("GetAce")
        pointer._obj.value = None if null else ctypes.addressof(ace)
        return True

    def convert(_pointer, text):
        calls.append("ConvertSid")
        text._obj.value = "S-1-5-18"
        return True

    def free(pointer):
        calls.append("FreeDescriptor" if getattr(pointer, "value", None) == descriptor else "LocalFree")

    native = SimpleNamespace(GetSecurityInfo=security,
                             GetAclInformation=information, GetAce=get_ace, ConvertSidToStringSidW=convert)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(advapi32=native, kernel32=SimpleNamespace(LocalFree=free)), raising=False)
    monkeypatch.setattr(ctypes, "cast", checked_cast)
    monkeypatch.setattr(module, "_current_user_sid_string", lambda: "S-1-5-18")
    return calls


@pytest.mark.parametrize("null", [False, True], ids=["allocated-ace", "null-ace"])
def test_typing_dacl_pointer_refusal_precedes_sid_conversion(monkeypatch, tmp_path, null):
    from optimus.acp import launch_gate as gate

    calls = _typing_dacl_api(monkeypatch, gate, null=null)
    queried = ("GetSecurityInfo", 0x7E57, gate._SE_FILE_OBJECT, gate._DACL_SECURITY_INFORMATION)  # the handle given
    if null:
        with pytest.raises(LaunchGateError) as error:
            gate._check_windows_dacl_real(0x7E57)  # #693: a handle; nothing real is opened
        assert (error.value.code, error.value.detail) == ("CONFIG_FILE_DACL_UNREADABLE", "cannot read ACE")
        assert calls == [queried, "GetAce", "FreeDescriptor"]
    else:
        gate._check_windows_dacl_real(0x7E57)
        assert calls == [queried, "GetAce", "ConvertSid", "LocalFree", "FreeDescriptor"]


@pytest.mark.parametrize(("status", "null_dacl", "detail", "freed"), [
    (5, False, "cannot read security descriptor", False),  # ERROR_ACCESS_DENIED: nothing was allocated
    (0, True, "no DACL present on file", True),
], ids=["failed-call", "null-dacl"])
def test_typing_security_info_refusals_free_only_what_was_allocated(monkeypatch, status, null_dacl, detail, freed):
    from optimus.acp import launch_gate as gate

    calls = _typing_dacl_api(monkeypatch, gate, null=False, status=status, null_dacl=null_dacl)
    with pytest.raises(LaunchGateError) as error:
        gate._check_windows_dacl_real(0x7E57)
    assert (error.value.code, error.value.detail) == ("CONFIG_FILE_DACL_UNREADABLE", detail)
    assert calls[1:] == (["FreeDescriptor"] if freed else [])


def test_typing_posix_check_on_windows_has_explicit_refusal(monkeypatch, tmp_path):
    from optimus.acp import launch_gate as gate

    path = tmp_path / "offline-config"
    path.write_text("offline")
    monkeypatch.setattr(gate.sys, "platform", "win32")

    def forbidden_uid():
        pytest.fail("unsupported platform reached UID query")

    monkeypatch.setattr(gate.os, "getuid", forbidden_uid, raising=False)
    with pytest.raises(LaunchGateError) as error, path.open("rb") as opened:
        gate._validate_posix_permissions(opened.fileno())
    assert (error.value.code, error.value.detail) == ("CONFIG_FILE_PLATFORM_CHECK_FAILED", "platform cannot verify file permissions")


def _monotonic_candidate(tmp_path, grants):
    from dataclasses import replace

    from tests.unit.acp.conftest import FakeKeyring
    from tests.unit.acp.test_launch_gate_model_registry import _candidate

    candidate, _store = _candidate(tmp_path, FakeKeyring())
    return replace(candidate, monotonic_grants=grants)


@pytest.mark.parametrize("parsed", [None, "3", object()], ids=["none", "string", "foreign"])
def test_typing_nonnumeric_monotonic_parser_refuses(monkeypatch, parsed, tmp_path):
    from dataclasses import replace

    from optimus.acp import launch_gate as gate

    name = "OPTIMUS_MAX_PLANNING_TURNS"
    policies = dict(gate.LAUNCH_VARIABLE_POLICIES)
    policies[name] = replace(policies[name], parser=create_autospec(policies[name].parser, return_value=parsed))
    monkeypatch.setattr(gate, "LAUNCH_VARIABLE_POLICIES", policies)
    with pytest.raises(LaunchGateError) as error:
        gate._authorize_monotonic_grants(candidate=_monotonic_candidate(tmp_path, {name: "3"}), record_monotonic_grants={})
    assert (error.value.code, error.value.detail) == ("MONOTONIC_VALUE_INVALID", name)


@pytest.mark.parametrize("name, raw, grant, allowed", [
    ("OPTIMUS_LIVE_MAX_COST_USD", "0.24", None, True),
    ("OPTIMUS_LIVE_MAX_COST_USD", "0.25", None, True),
    ("OPTIMUS_LIVE_MAX_COST_USD", "0.2500000000000000000001", None, False),
    ("OPTIMUS_LIVE_MAX_COST_USD", "0.30", "0.30", True),
    ("OPTIMUS_LIVE_MAX_COST_USD", "0.30", "0.3", False),
    ("OPTIMUS_LIVE_MAX_COST_USD", "0.31", "0.30", False),
    ("OPTIMUS_MAX_PLANNING_TURNS", "2", None, True),
    ("OPTIMUS_MAX_PLANNING_TURNS", "3", None, True),
    ("OPTIMUS_MAX_PLANNING_TURNS", "4", None, False),
    ("OPTIMUS_MAX_PLANNING_TURNS", "4", "4", True),
    ("OPTIMUS_MAX_PLANNING_TURNS", "4", "04", False),
    ("OPTIMUS_MAX_PLANNING_TURNS", "5", "4", False),
])
def test_fixed_monotonic_decimal_and_integer_authorization_table(name, raw, grant, allowed, tmp_path):

    from optimus.acp import launch_gate as gate

    candidate = _monotonic_candidate(tmp_path, {name: raw})
    grants = {} if grant is None else {name: grant}
    if allowed:
        gate._authorize_monotonic_grants(candidate=candidate, record_monotonic_grants=grants)
    else:
        with pytest.raises(LaunchGateError) as error:
            gate._authorize_monotonic_grants(candidate=candidate, record_monotonic_grants=grants)
        assert (error.value.code, error.value.detail) == ("MONOTONIC_LOOSENING_UNAPPROVED", name)
