"""Complete-cohort typing refusals and fixed offline authorization vectors."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from optimus.acp.launch_approvals import build_approval_record, serialize_approval_record
from optimus.acp.launch_gate import LaunchGateError
from tests.unit.acp.test_launch_approvals import _sample_workspace_identity


@pytest.mark.parametrize("mode, expected_json", [('durable', '{"approval_id":"appr_000000000000000000000000","ceremony_cli_version":"0.0.test","consumed":false,"created_at":"2026-10-18T00:00:00+00:00","creator_identity":"offline-operator","expires_at":null,"identity_format_version":3,"migration_provenance":null,"mode":"durable","model_observation":"offline-model","monotonic_grants":{"OPTIMUS_LIVE_MAX_COST_USD":"0.25"},"policy_compatibility":"P9.99-v1","record_hmac":"0e758fca18de5a6a380d0e95c046890adb503c07038a4db3fde2b96423112fad","registry_version":"P9.99-v1","schema_version":2,"secret_fingerprints":{"OPTIMUS_API_KEY":"fixture-fingerprint"},"security_literals":{"OPTIMUS_GATEWAY_URL":"http://127.0.0.1:8765"},"security_snapshot_digest":"5c888fbc229c90003c160e55d7e6a3de354cb01f161ba27d6ced98974731cf57","workspace_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'), ('one-shot', '{"approval_id":"appr_000000000000000000000000","ceremony_cli_version":"0.0.test","consumed":false,"created_at":"2026-10-18T00:00:00+00:00","creator_identity":"offline-operator","expires_at":"2026-10-18T00:05:00+00:00","identity_format_version":3,"migration_provenance":null,"mode":"one-shot","model_observation":"offline-model","monotonic_grants":{"OPTIMUS_LIVE_MAX_COST_USD":"0.25"},"policy_compatibility":"P9.99-v1","record_hmac":"cfa7b364b80a931c304d2915c301338c874803a0a2ff9144693ca06de15ab52e","registry_version":"P9.99-v1","schema_version":2,"secret_fingerprints":{"OPTIMUS_API_KEY":"fixture-fingerprint"},"security_literals":{"OPTIMUS_GATEWAY_URL":"http://127.0.0.1:8765"},"security_snapshot_digest":"5c888fbc229c90003c160e55d7e6a3de354cb01f161ba27d6ced98974731cf57","workspace_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')])
def test_fixed_offline_approval_json_and_hmac_vector(monkeypatch, mode, expected_json):
    from optimus.acp import launch_approvals as approvals

    monkeypatch.setattr(approvals.secrets, "token_hex", lambda _length: "0" * 24)
    monkeypatch.setattr(approvals, "_creator_identity", lambda: "offline-operator")
    monkeypatch.setattr(approvals, "_package_version", lambda: "0.0.test")
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


def _typing_dacl_api(monkeypatch, module, *, null):
    """Allocated ACE positive control; NULL is intercepted before any unsafe dereference."""
    import ctypes
    from types import SimpleNamespace

    calls = []
    ace = (ctypes.c_ubyte * 12)()  # ACCESS_ALLOWED_ACE, with allocated SID storage.
    real_cast = ctypes.cast

    def checked_cast(pointer, target):
        if isinstance(pointer, ctypes.c_void_p) and pointer.value is None:
            raise AssertionError("NULL ACE reached dereference")
        return real_cast(pointer, target)

    def security(_path, _flags, _buffer, _size, needed):
        needed._obj.value = 64
        return True

    def dacl(_buffer, present, pointer, _defaulted):
        present._obj.value = True
        pointer._obj.value = ctypes.addressof(ace)
        return True

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

    def free(_pointer):
        calls.append("LocalFree")

    native = SimpleNamespace(GetFileSecurityW=security, GetSecurityDescriptorDacl=dacl,
                             GetAclInformation=information, GetAce=get_ace, ConvertSidToStringSidW=convert)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(advapi32=native, kernel32=SimpleNamespace(LocalFree=free)), raising=False)
    monkeypatch.setattr(ctypes, "cast", checked_cast)
    monkeypatch.setattr(module, "_current_user_sid_string", lambda: "S-1-5-18")
    return calls


@pytest.mark.parametrize("null", [False, True], ids=["allocated-ace", "null-ace"])
def test_typing_dacl_pointer_refusal_precedes_sid_conversion(monkeypatch, tmp_path, null):
    from optimus.acp import launch_gate as gate

    calls = _typing_dacl_api(monkeypatch, gate, null=null)
    if null:
        with pytest.raises(LaunchGateError) as error:
            gate._check_windows_dacl_real(tmp_path / "offline-config")
        assert (error.value.code, error.value.detail) == ("CONFIG_FILE_DACL_UNREADABLE", "cannot read ACE")
        assert calls == ["GetAce"]
    else:
        gate._check_windows_dacl_real(tmp_path / "offline-config")
        assert calls == ["GetAce", "ConvertSid", "LocalFree"]


def test_typing_posix_check_on_windows_has_explicit_refusal(monkeypatch, tmp_path):
    from optimus.acp import launch_gate as gate

    path = tmp_path / "offline-config"
    path.write_text("offline")
    monkeypatch.setattr(gate.sys, "platform", "win32")

    def forbidden_uid():
        pytest.fail("unsupported platform reached UID query")

    monkeypatch.setattr(gate.os, "getuid", forbidden_uid, raising=False)
    with pytest.raises(LaunchGateError) as error:
        gate._validate_posix_permissions(path)
    assert (error.value.code, error.value.detail) == ("CONFIG_FILE_PLATFORM_CHECK_FAILED", "platform cannot verify file permissions")


@pytest.mark.parametrize("parsed", [None, "3", object()], ids=["none", "string", "foreign"])
def test_typing_nonnumeric_monotonic_parser_refuses(monkeypatch, parsed):
    from dataclasses import replace
    from types import SimpleNamespace

    from optimus.acp import launch_gate as gate

    name = "OPTIMUS_MAX_PLANNING_TURNS"
    policies = dict(gate.LAUNCH_VARIABLE_POLICIES)
    policies[name] = replace(policies[name], parser=lambda _raw: parsed)
    monkeypatch.setattr(gate, "LAUNCH_VARIABLE_POLICIES", policies)
    with pytest.raises(LaunchGateError) as error:
        gate._authorize_monotonic_grants(candidate=SimpleNamespace(monotonic_grants={name: "3"}), record_monotonic_grants={})
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
def test_fixed_monotonic_decimal_and_integer_authorization_table(name, raw, grant, allowed):
    from types import SimpleNamespace

    from optimus.acp import launch_gate as gate

    candidate = SimpleNamespace(monotonic_grants={name: raw})
    grants = {} if grant is None else {name: grant}
    if allowed:
        gate._authorize_monotonic_grants(candidate=candidate, record_monotonic_grants=grants)
    else:
        with pytest.raises(LaunchGateError) as error:
            gate._authorize_monotonic_grants(candidate=candidate, record_monotonic_grants=grants)
        assert (error.value.code, error.value.detail) == ("MONOTONIC_LOOSENING_UNAPPROVED", name)
