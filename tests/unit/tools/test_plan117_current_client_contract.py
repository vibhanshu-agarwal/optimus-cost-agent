"""Plan 11.7 v5 E1: pure current-client gate contracts and two-layer derivation.

Every document here is synthetic (tests/support/plan117_v5_evidence.py); none is live or accepted evidence.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from tests.support import plan117_v5_evidence as ev
from tools.evidence_gather_support import plan117_current_client_contract as c

D = c.GateDisposition
R = c.GateReason


def _reduce(document, layer="raw"):
    return c.reduce_document(document, layer=layer)


def _codes(result):
    return [hit.reason for hit in (result.primary, *result.secondary) if hit is not None]


# --------------------------------------------------------------------------- baseline


def test_valid_raw_document_is_accepted_with_derived_unreachability():
    result = _reduce(ev.valid_raw_document())
    assert result.disposition is D.ACCEPTED
    assert result.primary is None and result.secondary == ()
    assert result.derived_reachability == "ZERO_ENTRY_UNREACHABLE"


def test_unbound_classification_remains_invalid_without_a_reopen_signal():
    raw = ev.valid_raw_document()
    raw["provisional_classification_sha256"] = None

    with pytest.raises(c.ContractError):
        c.parse_raw_manifest(raw)
    result = _reduce(raw)
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert result.reason_codes() == ("schema_invalid",)


def test_only_accepted_carries_the_unreachable_label():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "a_prime", "after_first").update(session_binding="session-" + "b" * 32)))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.derived_reachability is None


def test_typed_reduce_gate_matches_tolerant_entry_point():
    manifest = c.parse_raw_manifest(ev.valid_raw_document())
    assert c.reduce_gate(manifest).disposition is D.ACCEPTED


# --------------------------------------------------------------------------- strict JSON


def test_strict_json_rejects_duplicate_keys_non_finite_and_invalid_utf8():
    with pytest.raises(c.ContractError) as duplicate:
        c.strict_json_loads(b'{"a":1,"a":2}')
    assert duplicate.value.code == "duplicate_key"
    for payload in (b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'):
        with pytest.raises(c.ContractError):
            c.strict_json_loads(payload)
    with pytest.raises(c.ContractError):
        c.strict_json_loads(b'{"a":"\xff"}')


def test_canonical_json_is_sorted_compact_and_rejects_non_finite():
    assert c.canonical_json_bytes({"b": 1, "a": [True, None]}) == b'{"a":[true,null],"b":1}'
    with pytest.raises(ValueError):
        c.canonical_json_bytes({"a": float("nan")})


# --------------------------------------------------------------------------- schema strictness


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda d: d.update(extra=1), id="top-level-unknown"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first").update(extra=1), id="launch-unknown"),
        pytest.param(lambda d: ev.launch(d, "r_refusal", "first")["wire"][0].update(extra=1), id="wire-unknown"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["module_closure"]["entries"][0].update(x=1), id="module-entry-unknown"),
        pytest.param(lambda d: ev.checkpoint(d, "prompted", "after_lifecycle_a")["files"][0].update(x=1), id="db-file-unknown"),
        pytest.param(lambda d: d["source"].update(x=1), id="source-unknown"),
        pytest.param(lambda d: d["custody"]["cleanup"]["targets"][0].update(x=1), id="cleanup-unknown"),
        pytest.param(lambda d: d["path_identities"][0].update(x=1), id="path-identity-unknown"),
        pytest.param(lambda d: d.pop("client"), id="missing-client"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "reopen").pop("counts"), id="missing-counts"),
    ],
)
def test_recursive_unknown_or_missing_fields_are_schema_invalid(mutation):
    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert result.primary.reason is R.SCHEMA_INVALID


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["counts"].update(initialize=True), id="bool-count"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first").update(monotonic_started_ns=True), id="bool-monotonic"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["counts"].update(initialize=1.0), id="float-count"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["counts"].update(initialize="1"), id="string-count"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["wire"][0].update(request_id=True), id="bool-request-id"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["initialize"].update(load_session=1), id="int-as-bool"),
        pytest.param(lambda d: d.update(scenario_sha256="A" * 64), id="uppercase-digest"),
        pytest.param(lambda d: d.update(run_id="../escape"), id="run-id-grammar"),
        pytest.param(lambda d: d["run_window"].update(wall_started_at="2026-11-20 10:00:00"), id="timestamp-grammar"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["wire"][1].update(direction="sideways"), id="enum-direction"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["wire"][1].update(index=7), id="wire-index-gap"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["module_closure"]["entries"][0].update(source_relative_path="..\\x.py"), id="unsafe-locator"),
    ],
)
def test_type_coercion_and_grammar_violations_are_schema_invalid(mutation):
    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.SCHEMA_INVALID in _codes(result)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda d: d["arms"].append(copy.deepcopy(d["arms"][0])), id="duplicate-arm"),
        pytest.param(lambda d: d["path_identities"].append(copy.deepcopy(d["path_identities"][0])), id="duplicate-path-role"),
        pytest.param(lambda d: ev.arm(d, "a_prime")["launches"].append(copy.deepcopy(ev.launch(d, "a_prime", "first"))), id="duplicate-launch"),
        pytest.param(lambda d: d["isolated_sources"].append(copy.deepcopy(d["isolated_sources"][0])), id="duplicate-source-kind"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["module_closure"]["entries"].append(copy.deepcopy(ev.launch(d, "a_prime", "first")["module_closure"]["entries"][0])), id="duplicate-module"),
        pytest.param(lambda d: ev.arm(d, "a_prime").update(profile_role="profile:missing"), id="dangling-role"),
        pytest.param(lambda d: ev.arm(d, "a_prime").update(arm_id="r_unregistered"), id="unregistered-arm"),
    ],
)
def test_duplicate_or_dangling_semantic_identities_are_schema_invalid(mutation):
    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.SCHEMA_INVALID in _codes(result)


def test_missing_registered_case_invalidates_coverage():
    result = _reduce(ev.mutated(lambda d: d["arms"].remove(ev.arm(d, "r_internal_error"))))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.ARM_SET_INVALID in _codes(result)


# --------------------------------------------------------------------------- custody / identity closure


def test_counts_inconsistent_with_wire_list_are_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "first")["counts"].update(session_prompt=1)))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.COUNTS_INCONSISTENT in _codes(result)


def test_unpaired_response_is_invalid():
    def mutation(d):
        ev.launch(d, "a_prime", "first")["wire"][1]["request_id"] = 77

    result = _reduce(ev.mutated(mutation))
    assert R.WIRE_INCONSISTENT in _codes(result)


def test_initialize_result_must_match_its_wire_response():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "reopen")["initialize"].update(result_sha256="0" * 64)))
    assert R.WIRE_INCONSISTENT in _codes(result)


def test_omitted_required_module_is_invalid():
    def mutation(d):
        entries = ev.launch(d, "r_cancelled", "reopen")["module_closure"]["entries"]
        entries[:] = [e for e in entries if e["module_name"] != "optimus.acp.server"]

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.MODULE_CLOSURE_INCOMPLETE in _codes(result)


def test_missing_module_closure_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "first").update(module_closure=None)))
    assert R.MODULE_CLOSURE_INCOMPLETE in _codes(result)


def test_module_closure_reported_outside_its_launch_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "first")["module_closure"].update(report_monotonic_ns=1)))
    assert R.MODULE_CLOSURE_CHRONOLOGY in _codes(result)


def test_patched_spec_bytes_substitution_is_invalid():
    def mutation(d):
        for entry in ev.launch(d, "r_refusal", "first")["module_closure"]["entries"]:
            if entry["module_name"] == "optimus.acp.spec":
                entry["sha256"] = ev.spec_sha(c.LOAD_ONLY_STUB)

    result = _reduce(ev.mutated(mutation))
    assert R.PATCH_IDENTITY_MISMATCH in _codes(result)


def test_launch_from_the_wrong_isolated_source_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "r_refusal", "first").update(source_kind=c.LOAD_ONLY_STUB)))
    assert R.PATCH_IDENTITY_MISMATCH in _codes(result)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda d: ev.launch(d, "a_prime", "first").update(monotonic_started_ns=1), id="launch-before-window"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "reopen").update(monotonic_started_ns=ev.launch(d, "a_prime", "first")["monotonic_started_ns"]), id="overlapping-launches"),
        pytest.param(lambda d: ev.checkpoint(d, "a_prime", "after_first").update(copied_monotonic_ns=ev.launch(d, "a_prime", "first")["monotonic_started_ns"]), id="copy-before-stop"),
        pytest.param(lambda d: d["run_window"].update(wall_ended_at="2026-11-20T09:00:00Z"), id="wall-regression"),
        pytest.param(lambda d: d["custody"].update(path_custody_monotonic_ns=ev.launch(d, "prompted", "lifecycle_b")["monotonic_started_ns"]), id="custody-before-last-copy"),
    ],
)
def test_impossible_chronology_is_invalid(mutation):
    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.CHRONOLOGY_INVALID in _codes(result)


def test_cross_arm_profile_reuse_is_invalid():
    def mutation(d):
        ev.arm(d, "r_end_turn")["profile_role"] = "profile:a_prime"

    result = _reduce(ev.mutated(mutation))
    assert R.CROSS_ARM_IDENTITY_REUSE in _codes(result)


def test_cross_arm_reuse_through_distinct_roles_with_the_same_location_is_invalid():
    def mutation(d):
        roles = {p["role"]: p for p in d["path_identities"]}
        roles["workspace:prompted"]["canonical_path"] = roles["workspace:a_prime"]["canonical_path"]
        roles["workspace:prompted"]["raw_path"] = roles["workspace:a_prime"]["raw_path"]

    result = _reduce(ev.mutated(mutation))
    assert R.CROSS_ARM_IDENTITY_REUSE in _codes(result)


def test_database_checkpoint_substitution_is_invalid():
    def mutation(d):
        ev.checkpoint(d, "a_prime", "after_reopen")["files"][0]["path_role"] = "database:r_refusal:after_first"

    result = _reduce(ev.mutated(mutation))
    assert R.DATABASE_IDENTITY_DISAGREEMENT in _codes(result)


def test_thread_identity_change_between_checkpoints_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "r_cancelled", "after_reopen").update(thread_id="0" * 32)))
    assert R.DATABASE_IDENTITY_DISAGREEMENT in _codes(result)


def test_live_database_inspection_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "a_prime", "after_reopen").update(closed_copy=False)))
    assert R.LIVE_DATABASE_INSPECTED in _codes(result)


def test_unreadable_database_copy_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "a_prime", "after_reopen").update(readable=False, thread_id=None)))
    assert R.DATABASE_UNREADABLE in _codes(result)


def test_custody_failures_recorded_by_derivation_are_invalid():
    result = _reduce(ev.mutated(lambda d: d.update(custody_failures=["artifact_digest_mismatch"])))
    assert result.primary.reason is R.CUSTODY_ARTIFACT_FAILURE


def test_undecodable_wire_bytes_are_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "reopen").update(undecodable_bytes=True)))
    assert R.WIRE_INCONSISTENT in _codes(result)


# --------------------------------------------------------------------------- non-waivable STOP latch


@pytest.mark.parametrize("arm_id", c.REOPEN_ARM_IDS)
def test_reopen_load_in_every_reopen_arm_latches_stop(arm_id):
    result = _reduce(ev.mutated(lambda d: ev.add_reopen_load(d, arm_id)))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.primary.reason is R.REOPEN_LOAD_OBSERVED
    assert result.primary.subject == arm_id


@pytest.mark.parametrize("arm_id", c.REOPEN_ARM_IDS)
def test_pre_reopen_binding_in_every_reopen_arm_latches_stop(arm_id):
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, arm_id, "after_first").update(session_binding="session-" + "c" * 32)))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.primary.reason is R.REOPEN_PRE_BINDING_NON_NULL


def test_load_hidden_by_zero_count_still_latches_stop():
    result = _reduce(ev.mutated(lambda d: ev.add_reopen_load(d, "a_prime", recount_after=False)))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert R.COUNTS_INCONSISTENT in _codes(result)


def test_positive_count_with_empty_wire_list_still_latches_stop():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "r_refusal", "reopen")["counts"].update(session_load=1)))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert R.COUNTS_INCONSISTENT in _codes(result)


def test_load_request_id_without_method_count_still_latches_stop():
    def mutation(d):
        ev.add_reopen_load(d, "r_end_turn", recount_after=False)
        ev.launch(d, "r_end_turn", "reopen")["wire"][-2]["kind"] = "notification"

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP


@pytest.mark.parametrize(
    "masking",
    [
        pytest.param(lambda d: d.update(extra=1), id="schema-invalid"),
        pytest.param(lambda d: d.pop("client"), id="missing-field"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "reopen").update(launch_id="reopen-renamed"), id="renamed-launch"),
        pytest.param(lambda d: ev.arm(d, "a_prime").update(arm_id="garbled"), id="garbled-arm"),
        pytest.param(lambda d: ev.launch(d, "a_prime", "first")["initialize"].update(load_session=False), id="capability-invalid"),
        pytest.param(lambda d: d.update(aborted={"reason_code": "zed_launch_failed", "stage": "launch"}), id="aborted"),
        pytest.param(lambda d: d.update(custody_failures=["artifact_digest_mismatch"]), id="custody-failure"),
        pytest.param(lambda d: d["custody"]["cleanup"]["targets"][0].update(absent_after=False), id="cleanup-failure"),
        pytest.param(lambda d: d["source"].update(actual_source_commit="f" * 40), id="source-drift"),
    ],
)
def test_no_invalidity_masks_a_positive_reopen_signal(masking):
    def mutation(d):
        ev.add_reopen_load(d, "a_prime")
        masking(d)

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.primary.reason in (R.REOPEN_LOAD_OBSERVED, R.REOPEN_LOAD_ID_OBSERVED)
    assert len(result.secondary) >= 1


def test_positive_signal_in_a_non_dict_document_shape_is_still_scanned():
    document = ev.mutated(lambda d: ev.add_reopen_load(d, "r_cancelled"))
    document["arms"].append("not-an-arm")
    result = _reduce(document)
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP


def test_garbage_document_without_signal_is_invalid_not_accepted():
    for document in (None, [], "x", {"arms": "x"}):
        assert _reduce(document).disposition is D.INVALID_CURRENT_CLIENT_GATE


def test_first_launch_load_is_invalid_choreography_not_reachability():
    def mutation(d):
        record = ev.launch(d, "a_prime", "first")
        wire = record["wire"]
        wire.append(dict(wire[2], index=len(wire), method="session/load", request_id=5))
        wire.append(dict(wire[3], index=len(wire), request_id=5, result_session_id=None))
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.FIRST_LAUNCH_LOAD_OBSERVED in _codes(result)


def test_prompted_lifecycle_b_load_is_not_a_reachability_signal():
    assert c.scan_positive_signals(ev.valid_raw_document()) == ()


# --------------------------------------------------------------------------- capability


@pytest.mark.parametrize("launch_id", ["first", "reopen"])
@pytest.mark.parametrize("value", [False, None])
def test_a_prime_launch_without_load_session_is_invalid_never_unreachability(launch_id, value):
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", launch_id)["initialize"].update(load_session=value)))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.CAPABILITY_LOAD_SESSION_MISSING in _codes(result)
    assert result.derived_reachability is None


@pytest.mark.parametrize("arm_id", c.ARM_IDS)
def test_resume_advertisement_is_invalid_on_every_arm(arm_id):
    launch_id = "lifecycle_b" if arm_id == "prompted" else "reopen"
    result = _reduce(ev.mutated(lambda d: ev.launch(d, arm_id, launch_id)["initialize"].update(has_resume=True)))
    assert R.CAPABILITY_RESUME_ADVERTISED in _codes(result)


def test_missing_initialize_capture_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "reopen").update(initialize=None)))
    assert R.INITIALIZE_MISSING in _codes(result)


def test_capability_invalidity_with_positive_signal_is_stop_with_secondary():
    def mutation(d):
        ev.launch(d, "a_prime", "first")["initialize"]["has_resume"] = True
        ev.checkpoint(d, "a_prime", "after_first")["session_binding"] = "session-" + "d" * 32

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert R.CAPABILITY_RESUME_ADVERTISED in _codes(result)


# --------------------------------------------------------------------------- choreography


def test_a_prime_prompt_is_invalid():
    def mutation(d):
        record = ev.launch(d, "a_prime", "first")
        record["wire"].append(dict(ev.launch(d, "r_cancelled", "first")["wire"][5], index=len(record["wire"])))
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.FIRST_LAUNCH_SEQUENCE_INVALID in _codes(result)


@pytest.mark.parametrize("arm_id", c.R_DESCRIPTOR_IDS)
def test_r_case_without_its_one_valid_prompt_is_invalid(arm_id):
    def mutation(d):
        record = ev.launch(d, arm_id, "first")
        record["wire"] = [e for e in record["wire"] if e["index"] < 5]
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.FIRST_LAUNCH_SEQUENCE_INVALID in _codes(result)


def test_reopen_without_fresh_session_new_is_invalid():
    def mutation(d):
        record = ev.launch(d, "r_refusal", "reopen")
        record["wire"] = record["wire"][:2]
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.REOPEN_SEQUENCE_INVALID in _codes(result)


def test_post_reopen_binding_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "a_prime", "after_reopen").update(session_binding="session-" + "e" * 32)))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.BINDING_AFTER_REOPEN_NOT_NULL in _codes(result)


@pytest.mark.parametrize(
    "arm_id,replacement",
    [
        ("r_refusal", {"stopReason": "end_turn"}),
        ("r_end_turn", {"stopReason": "refusal"}),
        ("r_cancelled", {"stopReason": "end_turn"}),
    ],
)
def test_r_case_with_wrong_stop_reason_is_invalid(arm_id, replacement):
    def mutation(d):
        response = ev.launch(d, arm_id, "first")["wire"][-1]
        response["stop_reason"] = replacement["stopReason"]
        response["response_sha256"] = ev.sha(c.canonical_json_bytes(replacement))
        response["result_bytes_sha256"] = response["response_sha256"]

    result = _reduce(ev.mutated(mutation))
    assert R.R_PROMPT_RESPONSE_MISMATCH in _codes(result)


@pytest.mark.parametrize("arm_id", ["r_invalid_request", "r_request_cancelled", "r_internal_error"])
def test_r_case_with_wrong_error_payload_is_invalid(arm_id):
    def mutation(d):
        response = ev.launch(d, arm_id, "first")["wire"][-1]
        response["response_sha256"] = ev.sha(c.canonical_json_bytes({"code": response["error_code"], "message": "other"}))

    result = _reduce(ev.mutated(mutation))
    assert R.R_PROMPT_RESPONSE_MISMATCH in _codes(result)


def test_r_case_that_answers_with_an_error_class_instead_of_a_stop_reason_is_invalid():
    def mutation(d):
        response = ev.launch(d, "r_refusal", "first")["wire"][-1]
        response.update(stop_reason=None, result_bytes_sha256=None, error_code=-32600,
                        response_sha256=ev.sha(c.canonical_json_bytes({"code": -32600, "message": "empty prompt"})))

    result = _reduce(ev.mutated(mutation))
    assert R.R_PROMPT_RESPONSE_MISMATCH in _codes(result)


def test_r_case_stored_class_update_inside_prompt_window_is_invalid():
    def mutation(d):
        record = ev.launch(d, "r_cancelled", "first")
        notice = dict(record["wire"][4], update_kind="plan")
        record["wire"].insert(6, notice)
        ev.reindex(record)
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.R_NOTICE_MISMATCH in _codes(result)


def test_r_case_missing_declared_notice_is_invalid():
    def mutation(d):
        record = ev.launch(d, "r_refusal", "first")
        del record["wire"][6]
        ev.reindex(record)
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.R_NOTICE_MISMATCH in _codes(result)


def test_stored_class_update_outside_any_prompt_is_invalid():
    def mutation(d):
        record = ev.launch(d, "a_prime", "reopen")
        record["wire"].append(dict(record["wire"][4], index=len(record["wire"]), update_kind="agent_message_chunk"))
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.STORED_CLASS_UPDATE_OBSERVED in _codes(result)


def test_forced_kill_is_invalid_and_unknown_shutdown_is_indeterminate():
    forced = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "first")["shutdown"].update(mechanism="forced_kill", agent_stdin_eof=False, child_exit_code=None)))
    assert forced.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.SHUTDOWN_FORCED_KILL in _codes(forced)
    unknown = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "first")["shutdown"].update(mechanism="unknown")))
    assert unknown.disposition is D.INDETERMINATE_CURRENT_CLIENT_GATE
    assert unknown.primary.reason is R.SHUTDOWN_UNKNOWN


def test_clean_eof_claim_without_stdin_eof_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "a_prime", "first")["shutdown"].update(agent_stdin_eof=False)))
    assert R.SHUTDOWN_INCONSISTENT in _codes(result)


# --------------------------------------------------------------------------- prompted arm


def test_prompted_load_for_a_different_session_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "prompted", "lifecycle_b")["wire"][2].update(session_id="session-" + "f" * 32)))
    assert R.PROMPTED_LOAD_INVALID in _codes(result)


def test_prompted_two_loads_are_invalid():
    def mutation(d):
        record = ev.launch(d, "prompted", "lifecycle_b")
        record["wire"].append(dict(record["wire"][2], index=4, request_id=3))
        record["wire"].append(dict(record["wire"][3], index=5, request_id=3))
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.PROMPTED_LOAD_INVALID in _codes(result)


def test_prompted_load_response_must_be_exact_empty_object():
    result = _reduce(ev.mutated(lambda d: ev.launch(d, "prompted", "lifecycle_b")["wire"][3].update(result_bytes_sha256=ev.sha(b"{ }"))))
    assert R.PROMPTED_LOAD_RESPONSE_NOT_EMPTY in _codes(result)


def test_prompted_replay_during_load_is_spurious_activity():
    def mutation(d):
        record = ev.launch(d, "prompted", "lifecycle_b")
        record["wire"].append(dict(ev.launch(d, "prompted", "lifecycle_a")["wire"][4], index=len(record["wire"]), session_id=ev.PROMPTED_SESSION))
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.PROMPTED_SPURIOUS_ACTIVITY in _codes(result)


def test_prompted_binding_before_b_must_equal_lifecycle_a_session():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "prompted", "after_lifecycle_a").update(session_binding=None)))
    assert R.PROMPTED_BINDING_BEFORE_B_MISMATCH in _codes(result)


def test_prompted_binding_retained_after_b_is_invalid():
    result = _reduce(ev.mutated(lambda d: ev.checkpoint(d, "prompted", "after_lifecycle_b").update(session_binding=ev.PROMPTED_SESSION)))
    assert R.PROMPTED_BINDING_RETAINED in _codes(result)


def test_prompted_lifecycle_a_without_prompt_is_invalid():
    def mutation(d):
        record = ev.launch(d, "prompted", "lifecycle_a")
        record["wire"] = record["wire"][:5]
        ev.recount(record)

    result = _reduce(ev.mutated(mutation))
    assert R.PROMPTED_LIFECYCLE_A_INVALID in _codes(result)


# --------------------------------------------------------------------------- source / cleanup tier


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda d: d["source"].update(actual_source_commit="f" * 40), R.SOURCE_COMMIT_MISMATCH),
        (lambda d: d["source"].update(tracked_diff_sha256="0" * 64), R.SOURCE_DIRTY),
        (lambda d: d["source"].update(untracked_digest_sha256="0" * 64), R.SOURCE_DIRTY),
        (lambda d: d["source"].update(normal_source_sha256_after="0" * 64), R.NORMAL_SOURCE_NOT_RESTORED),
        (lambda d: d["source"]["historical_pins"].update(candidate_v3="0" * 40), R.HISTORICAL_PINS_MISMATCH),
        (lambda d: d["custody"]["cleanup"]["targets"][0].update(absent_after=False), R.CLEANUP_UNVERIFIED),
        (lambda d: d["custody"]["cleanup"].update(targets=[]), R.CLEANUP_UNVERIFIED),
    ],
)
def test_source_and_cleanup_invalidity(mutation, reason):
    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert reason in _codes(result)


def test_cleanup_before_path_custody_capture_is_invalid():
    def mutation(d):
        d["custody"]["cleanup"]["started_monotonic_ns"] = d["custody"]["path_custody_monotonic_ns"] - 1

    result = _reduce(ev.mutated(mutation))
    assert R.CLEANUP_BEFORE_CUSTODY in _codes(result)


def test_aborted_run_without_signal_is_indeterminate():
    def mutation(d):
        d["aborted"] = {"reason_code": "zed_launch_failed", "stage": "launch"}
        d["arms"] = d["arms"][:3]

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INDETERMINATE_CURRENT_CLIENT_GATE
    assert result.primary.reason is R.RUN_ABORTED


def test_precedence_orders_hits_by_tier():
    def mutation(d):
        d["source"]["tracked_diff_sha256"] = "0" * 64
        ev.checkpoint(d, "prompted", "after_lifecycle_b")["session_binding"] = ev.PROMPTED_SESSION
        ev.launch(d, "a_prime", "first")["initialize"]["load_session"] = False
        ev.launch(d, "a_prime", "first")["counts"]["session_prompt"] = 3

    result = _reduce(ev.mutated(mutation))
    assert _codes(result) == [
        R.COUNTS_INCONSISTENT,
        R.CAPABILITY_LOAD_SESSION_MISSING,
        R.PROMPTED_BINDING_RETAINED,
        R.SOURCE_DIRTY,
    ]


def test_reason_tier_declaration_order_is_the_plan_precedence():
    tiers = [c.reason_tier(reason) for reason in c.GateReason]
    assert tiers == sorted(tiers)
    assert c.reason_tier(R.REOPEN_LOAD_OBSERVED) < c.reason_tier(R.SCHEMA_INVALID)
    assert c.reason_tier(R.SCHEMA_INVALID) < c.reason_tier(R.FIRST_LAUNCH_SEQUENCE_INVALID)
    assert c.reason_tier(R.FIRST_LAUNCH_SEQUENCE_INVALID) < c.reason_tier(R.PROMPTED_LOAD_INVALID)
    assert c.reason_tier(R.PROMPTED_LOAD_INVALID) < c.reason_tier(R.SOURCE_DIRTY)
    assert c.reason_tier(R.SOURCE_DIRTY) < c.reason_tier(R.RUN_ABORTED)


# --------------------------------------------------------------------------- windows-path-v1 and commitments


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("c:\\Users\\Op\\Work", "C:\\Users\\Op\\Work"),
        ("C:/Users/Op/Work", "C:\\Users\\Op\\Work"),
        ("C:\\Users\\.\\Op\\.\\Work", "C:\\Users\\Op\\Work"),
        ("C:\\MiXeD\\Case", "C:\\MiXeD\\Case"),
        ("C:\\cafe\u0301", "C:\\caf\u00e9"),
        ("d:\\", "D:\\"),
    ],
)
def test_windows_path_v1_canonicalization(raw, canonical):
    assert c.canonicalize_windows_path(raw) == canonical
    assert c.path_identity_bytes(canonical) == b"windows-path-v1\x00" + canonical.encode("utf-8")


@pytest.mark.parametrize("raw", ["", "relative\\x", "\\no-drive", "\\\\server\\share\\x", "C:relative", "C:\\a\\..\\b", "C:\\a\x00b"])
def test_windows_path_v1_rejects_non_canonicalizable_inputs(raw):
    with pytest.raises(c.ContractError):
        c.canonicalize_windows_path(raw)


def test_commitment_uses_the_v5_domain_and_a_per_run_key():
    canonical = "C:\\p117v5\\run"
    expected = hmac.new(ev.RUN_KEY, b"plan-11-7-v5:path:v1\x00" + c.path_identity_bytes(canonical), hashlib.sha256).hexdigest()
    assert c.commit_path(canonical, ev.RUN_KEY) == expected
    v3_domain = hmac.new(ev.RUN_KEY, b"plan-11-7-v3:path:v1\x00" + c.path_identity_bytes(canonical), hashlib.sha256).hexdigest()
    assert c.commit_path(canonical, ev.RUN_KEY) != v3_domain
    assert c.commit_path(canonical, bytes(32)) != expected
    with pytest.raises(c.ContractError):
        c.commit_path(canonical, b"short")


# --------------------------------------------------------------------------- two-layer derivation and privacy


def _sanitize(document=None):
    raw = c.parse_raw_manifest(document or ev.valid_raw_document())
    return c.derive_sanitized_manifest(raw)


def test_sanitized_manifest_carries_no_raw_path_or_key_and_reduces_identically():
    raw_document = ev.valid_raw_document()
    sanitized, mapping = _sanitize(raw_document)
    encoded = c.canonical_json_bytes(sanitized).decode("utf-8")
    for identity in raw_document["path_identities"]:
        assert identity["raw_path"] not in encoded
        assert identity["canonical_path"] not in encoded
    assert ev.RUN_KEY.hex() not in encoded
    assert "\\" not in encoded
    assert c.find_privacy_violations(sanitized, forbidden_strings=()) == ()
    assert c.reduce_document(sanitized, layer="sanitized").disposition is D.ACCEPTED
    assert mapping["schema"] == c.PRIVATE_MAPPING_SCHEMA
    assert {item["canonical_path"] for item in mapping["entries"]} == {p["canonical_path"] for p in raw_document["path_identities"]}


def test_sanitized_identities_are_opaque_aliases_with_keyed_commitments():
    raw_document = ev.valid_raw_document()
    sanitized, mapping = _sanitize(raw_document)
    by_role = {p["role"]: p for p in raw_document["path_identities"]}
    for public, private in zip(sanitized["path_identities"], mapping["entries"], strict=True):
        assert set(public) == {"role", "alias", "commitment", "kind", "sha256", "size_bytes"}
        assert public["alias"].startswith("path-")
        assert public["commitment"] == c.commit_path(by_role[public["role"]]["canonical_path"], ev.RUN_KEY)
        assert (private["role"], private["alias"], private["commitment"]) == (public["role"], public["alias"], public["commitment"])


def test_sanitized_reduction_matches_raw_for_stop_and_invalid_runs():
    for mutation in (lambda d: ev.add_reopen_load(d, "r_internal_error"), lambda d: ev.arm(d, "r_end_turn").update(profile_role="profile:a_prime")):
        raw_document = ev.mutated(mutation)
        sanitized, _ = _sanitize(raw_document)
        assert c.reduce_document(sanitized, layer="sanitized") == c.reduce_document(raw_document, layer="raw")


def test_sanitized_layer_refuses_raw_path_fields():
    sanitized, _ = _sanitize()
    sanitized["path_identities"][0]["raw_path"] = "C:\\x"
    assert c.reduce_document(sanitized, layer="sanitized").primary.reason is R.SCHEMA_INVALID


def test_raw_layer_requires_key_and_sanitized_layer_forbids_it():
    raw_document = ev.mutated(lambda d: d.pop("path_commitment_key_hex"))
    assert _reduce(raw_document).primary.reason is R.SCHEMA_INVALID
    sanitized, _ = _sanitize()
    sanitized["path_commitment_key_hex"] = ev.RUN_KEY.hex()
    assert c.reduce_document(sanitized, layer="sanitized").primary.reason is R.SCHEMA_INVALID


@pytest.mark.parametrize(
    "value,code",
    [
        ("C:\\Users\\Op", "windows_path_material"),
        ("see c:/users/op", "windows_path_material"),
        ("a\\b", "backslash"),
        ("\\\\host\\share", "backslash"),
        ("/home/op/x", "posix_home_path"),
        ("/Users/op/x", "posix_home_path"),
        ("/mnt/c/x", "posix_home_path"),
    ],
)
def test_privacy_scanner_flags_path_material(value, code):
    assert code in c.find_privacy_violations({"field": [value]}, forbidden_strings=())


def test_privacy_scanner_flags_forbidden_values_and_identity_tokens():
    violations = c.find_privacy_violations(
        {"a": "x-plan-OpUser-y", "b": "deadbeef" * 8},
        forbidden_strings=("deadbeef" * 8,),
        identity_tokens=("opuser",),
    )
    assert "forbidden_value" in violations
    assert "operator_identity" in violations
    assert c.find_privacy_violations({"a": "plan117-run"}, forbidden_strings=(), identity_tokens=("pc",)) == ()


# --------------------------------------------------------------------------- private review receipt


def _receipt(**overrides):
    receipt = {
        "schema": c.RECEIPT_SCHEMA,
        "verdict": "accepting",
        "reviewer_identity": "reviewer@example",
        "reviewer_session": "session-review-1",
        "reviewer_model": "human-private-review",
        "reviewed_at": "2026-11-21T09:00:00Z",
        "run_id": ev.RUN_ID,
        "scenario_id": c.SCENARIO_ID,
        "scenario_sha256": ev.sha(b"scenario"),
        "source_commit": ev.SOURCE_COMMIT,
        "raw_manifest_sha256": ev.sha(b"raw"),
        "raw_bundle_sha256": ev.sha(b"bundle"),
        "sanitized_manifest_sha256": ev.sha(b"sanitized"),
        "mapping_sha256": ev.sha(b"mapping"),
        "derivatives": [{"locator": "manifest.json", "sha256": ev.sha(b"sanitized")}],
        "redaction_report_sha256": ev.sha(b"report"),
    }
    receipt.update(overrides)
    return receipt


def _expectation(**overrides):
    expected = {key: value for key, value in _receipt().items() if key not in {"schema", "verdict", "reviewer_identity", "reviewer_session", "reviewer_model", "reviewed_at"}}
    expected["not_before"] = "2026-11-20T11:00:00Z"
    expected.update(overrides)
    return c.ReceiptExpectation(**expected)


def test_accepting_receipt_binds_every_hash():
    receipt = c.parse_private_review_receipt(_receipt())
    c.verify_receipt_binding(receipt, _expectation())


@pytest.mark.parametrize("verdict", ["rejecting", "conditional", "", "ACCEPTING"])
def test_non_accepting_verdict_cannot_promote(verdict):
    with pytest.raises(c.ContractError) as excinfo:
        c.verify_receipt_binding(c.parse_private_review_receipt(_receipt(verdict=verdict)), _expectation())
    assert excinfo.value.code in {"receipt_not_accepting", "schema_invalid"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "p117v5-run-0002"),
        ("scenario_sha256", "0" * 64),
        ("source_commit", "f" * 40),
        ("raw_manifest_sha256", "0" * 64),
        ("raw_bundle_sha256", "0" * 64),
        ("sanitized_manifest_sha256", "0" * 64),
        ("mapping_sha256", "0" * 64),
        ("redaction_report_sha256", "0" * 64),
        ("derivatives", [{"locator": "manifest.json", "sha256": "0" * 64}]),
        ("derivatives", []),
    ],
)
def test_receipt_hash_mismatch_cannot_promote(field, value):
    with pytest.raises(c.ContractError) as excinfo:
        c.verify_receipt_binding(c.parse_private_review_receipt(_receipt(**{field: value})), _expectation())
    assert excinfo.value.code == "receipt_binding_mismatch"


def test_receipt_reviewed_before_the_run_ended_is_refused():
    with pytest.raises(c.ContractError) as excinfo:
        c.verify_receipt_binding(c.parse_private_review_receipt(_receipt(reviewed_at="2026-11-20T10:30:00Z")), _expectation())
    assert excinfo.value.code == "receipt_chronology_invalid"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(observation_counts={"session_load": 0}),
        lambda r: r.pop("reviewer_identity"),
        lambda r: r.update(reviewer_identity="C:\\Users\\x"),
        lambda r: r.update(schema="other"),
        lambda r: r.update(derivatives=[{"locator": "../escape", "sha256": "0" * 64}]),
    ],
)
def test_receipt_is_closed_and_cannot_carry_observations(mutation):
    receipt = _receipt()
    mutation(receipt)
    with pytest.raises(c.ContractError):
        c.parse_private_review_receipt(receipt)


# --------------------------------------------------------------------------- trusted approved-run registry


def _run_spec(**overrides):
    spec = {
        "run_id": ev.RUN_ID,
        "evidence_kind": c.EVIDENCE_KIND_GATE,
        "scenario_id": c.SCENARIO_ID,
        "scenario_source_sha256": ev.sha(b"scenario-source"),
        "scenario_sha256": ev.sha(b"scenario"),
        "descriptor_fixture_sha256": ev.descriptor_fixture_sha256(),
        "patch_sha256s": {kind: ev.patch_sha(kind) for kind in c.SOURCE_KINDS},
        "source_commit": ev.SOURCE_COMMIT,
        "source_tree": ev.SOURCE_TREE,
        "required_modules": sorted(c.REQUIRED_MODULE_PATHS),
        "client": {"executable_sha256": ev.sha(b"zed-binary"), "app_version": "1.27.0", "source_revision": "c84af5b99cbc366d675064e52b23664a015b6e35"},
        "launch_config_sha256": ev.sha(b"launch-config"),
        "arm_ids": list(c.ARM_IDS),
        "approval_id": ev.APPROVAL_ID,
        "approval_not_before": "2026-11-20T09:00:00Z",
        "approval_not_after": "2026-11-20T18:00:00Z",
        "budget_policy_sha256": ev.sha(b"budget-policy"),
        "private_root_commitments": {"capture_root": c.commit_path(c.canonicalize_windows_path("C:\\p117v5\\capture"), ev.RUN_KEY)},
    }
    spec.update(overrides)
    return spec


def _registry(*specs):
    return {
        "schema": c.RUN_REGISTRY_SCHEMA,
        "runs": [{"run_spec": spec, "run_spec_sha256": ev.sha(c.canonical_json_bytes(spec))} for spec in specs],
    }


def test_empty_registry_parses_and_has_no_approved_run():
    registry = c.parse_approved_runs(_registry())
    assert registry.runs == ()
    with pytest.raises(c.ContractError) as excinfo:
        registry.lookup(ev.RUN_ID)
    assert excinfo.value.code == "run_not_registered"


def test_registry_lookup_returns_the_hash_bound_run_spec():
    registry = c.parse_approved_runs(_registry(_run_spec()))
    assert registry.lookup(ev.RUN_ID).run_id == ev.RUN_ID


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda r: r["runs"].append(copy.deepcopy(r["runs"][0])), "duplicate_run_id"),
        (lambda r: r["runs"][0].update(run_spec_sha256="0" * 64), "run_spec_digest_mismatch"),
        (lambda r: r["runs"][0]["run_spec"].update(observations={}), "schema_invalid"),
        (lambda r: r.update(extra=1), "schema_invalid"),
        (lambda r: r["runs"][0]["run_spec"].update(arm_ids=list(c.ARM_IDS)[:-1]), "schema_invalid"),
    ],
)
def test_registry_is_strict(mutation, code):
    registry = _registry(_run_spec())
    mutation(registry)
    with pytest.raises(c.ContractError) as excinfo:
        c.parse_approved_runs(registry)
    assert excinfo.value.code == code


def test_manifest_matching_its_run_spec_has_no_mismatch():
    manifest = c.parse_raw_manifest(ev.valid_raw_document())
    spec = c.parse_approved_runs(_registry(_run_spec())).lookup(ev.RUN_ID)
    assert c.run_spec_mismatches(manifest, spec) == ()


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"approval_id": "approval-other"}, "approval_id"),
        ({"scenario_sha256": "0" * 64}, "scenario_sha256"),
        ({"descriptor_fixture_sha256": "0" * 64}, "descriptor_fixture_sha256"),
        ({"source_commit": "f" * 40}, "source_commit"),
        ({"source_tree": "f" * 40}, "source_tree"),
        ({"launch_config_sha256": "0" * 64}, "launch_config_sha256"),
        ({"budget_policy_sha256": "0" * 64}, "budget_policy_sha256"),
        ({"approval_not_after": "2026-11-20T10:30:00Z"}, "approval_window"),
        ({"client": {"executable_sha256": "0" * 64, "app_version": "1.27.0", "source_revision": "c84af5b99cbc366d675064e52b23664a015b6e35"}}, "client"),  # pragma: allowlist secret - fake Zed source-revision fixture, not authentication material
        ({"private_root_commitments": {"capture_root": "0" * 64}}, "private_root_commitments"),
        ({"required_modules": sorted([*c.REQUIRED_MODULE_PATHS, "optimus.acp.extra"])}, "required_modules"),
    ],
)
def test_manifest_run_spec_mismatch_is_reported(overrides, field):
    manifest = c.parse_raw_manifest(ev.valid_raw_document())
    spec = c.parse_approved_runs(_registry(_run_spec(**overrides))).lookup(ev.RUN_ID)
    assert field in c.run_spec_mismatches(manifest, spec)


def test_patch_identity_mismatch_against_run_spec_is_reported():
    patches = {kind: ev.patch_sha(kind) for kind in c.SOURCE_KINDS}
    patches[c.LOAD_ONLY_STUB] = "0" * 64
    manifest = c.parse_raw_manifest(ev.valid_raw_document())
    spec = c.parse_approved_runs(_registry(_run_spec(patch_sha256s=patches))).lookup(ev.RUN_ID)
    assert "patch_sha256s" in c.run_spec_mismatches(manifest, spec)


def test_sanitized_manifest_is_checked_against_run_spec_commitments():
    sanitized, _ = _sanitize()
    manifest = c.parse_sanitized_manifest(sanitized)
    spec = c.parse_approved_runs(_registry(_run_spec())).lookup(ev.RUN_ID)
    assert c.run_spec_mismatches(manifest, spec) == ()
    other = c.parse_approved_runs(_registry(_run_spec(private_root_commitments={"capture_root": "1" * 64}))).lookup(ev.RUN_ID)
    assert "private_root_commitments" in c.run_spec_mismatches(manifest, other)


# --------------------------------------------------------------------------- descriptor fixture


def test_descriptor_fixture_registers_exactly_the_six_classes():
    fixture = c.parse_descriptor_fixture(ev.descriptor_fixture())
    assert tuple(d.descriptor_id for d in fixture.descriptors) == c.R_DESCRIPTOR_IDS
    covered = {entry.descriptor_id for entry in fixture.census if entry.disposition == "descriptor"}
    assert covered == set(c.R_DESCRIPTOR_IDS)


def test_descriptor_codes_and_notices_are_the_current_source_values():
    from optimus.acp import errors, spec

    fixture = c.parse_descriptor_fixture(ev.descriptor_fixture())
    for descriptor in fixture.descriptors:
        if descriptor.error_code_name is not None:
            assert getattr(errors, descriptor.error_code_name) == descriptor.error_code
        if descriptor.notice_source is not None and descriptor.notice_source.startswith("optimus.acp.spec:"):
            assert getattr(spec, descriptor.notice_source.split(":", 1)[1]) == descriptor.notice_text
    excluded = fixture.excluded_classes[0]
    assert getattr(errors, excluded["error_code_name"]) == excluded["error_code"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda f: f["descriptors"].pop(),
        lambda f: f["descriptors"][0].update(stop_reason="refusal"),
        lambda f: f["descriptors"].append(copy.deepcopy(f["descriptors"][0])),
        lambda f: f["census"][1].update(descriptor_id="r_unknown"),
        lambda f: f["census"][1].update(disposition="covered"),
        lambda f: f.update(extra=1),
        lambda f: [e.update(disposition="negative_control", descriptor_id=None) for e in f["census"] if e["descriptor_id"] == "r_internal_error"],
    ],
)
def test_descriptor_fixture_is_strict_and_complete(mutation):
    fixture = ev.descriptor_fixture()
    mutation(fixture)
    with pytest.raises(c.ContractError):
        c.parse_descriptor_fixture(fixture)


def test_expected_prompt_response_hash_follows_descriptor():
    fixture = c.parse_descriptor_fixture(ev.descriptor_fixture())
    by_id = {d.descriptor_id: d for d in fixture.descriptors}
    assert c.expected_response_sha256(by_id["r_refusal"]) == ev.sha(b'{"stopReason":"refusal"}')
    assert c.expected_response_sha256(by_id["r_invalid_request"]) == ev.sha(b'{"code":-32600,"message":"empty prompt"}')
    assert c.expected_notices(by_id["r_cancelled"]) == ()
    # production appends AGENT_MESSAGE_BLOCK_SEPARATOR to every agent chunk (optimus.acp.shapes)
    assert c.expected_notices(by_id["r_refusal"]) == (("agent_message_chunk", ev.sha(b"This prompt was refused.\n\n")),)


def test_json_round_trip_of_valid_document_is_stable():
    document = ev.valid_raw_document()
    encoded = c.canonical_json_bytes(document)
    assert c.strict_json_loads(encoded) == json.loads(encoded)


def test_unsalted_path_digests_are_forbidden_in_promotable_bytes():
    raw = c.parse_raw_manifest(ev.valid_raw_document())
    forbidden = c.private_forbidden_strings(raw)
    identity = next(item for item in raw.path_identities if item.role == "run_root")
    unsalted = (
        hashlib.sha256(c.path_identity_bytes(identity.canonical_path)).hexdigest(),
        hashlib.sha256(identity.canonical_path.encode("utf-8")).hexdigest(),
        hashlib.sha256(identity.canonical_path.casefold().encode("utf-8")).hexdigest(),
    )
    for digest in unsalted:
        assert digest in forbidden
        sanitized, _ = c.derive_sanitized_manifest(raw)
        sanitized["client"]["cli_version"] = "Zed 1.27.0"
        sanitized["approval_id"] = digest
        assert "forbidden_value" in c.find_privacy_violations(sanitized, forbidden_strings=forbidden)
    clean, _ = c.derive_sanitized_manifest(raw)
    assert c.find_privacy_violations(clean, forbidden_strings=forbidden) == ()


def test_cross_run_aliases_do_not_carry_over_another_runs_commitments():
    raw = c.parse_raw_manifest(ev.valid_raw_document())
    other_key = bytes(reversed(ev.RUN_KEY))
    other = c.parse_raw_manifest(ev.mutated(lambda d: d.update(path_commitment_key_hex=other_key.hex())))
    mine, _ = c.derive_sanitized_manifest(raw)
    theirs, _ = c.derive_sanitized_manifest(other)
    assert [p["alias"] for p in mine["path_identities"]] == [p["alias"] for p in theirs["path_identities"]]
    assert not {p["commitment"] for p in mine["path_identities"]} & {p["commitment"] for p in theirs["path_identities"]}


# --------------------------------------------------------------------------- post-full-run self-review fixes


def test_a_reopen_arm_renamed_prompted_cannot_mask_stop():
    def mutation(d):
        ev.add_reopen_load(d, "a_prime")
        ev.arm(d, "a_prime")["arm_id"] = "prompted"

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP


def test_a_load_in_a_non_lifecycle_launch_of_the_prompted_arm_is_scanned():
    def mutation(d):
        record = ev.launch(d, "prompted", "lifecycle_b")
        record["launch_id"] = "reopen"

    assert c.scan_positive_signals(ev.mutated(mutation)) != ()


def test_the_genuine_prompted_lifecycle_b_load_is_still_not_a_signal():
    assert c.scan_positive_signals(ev.valid_raw_document()) == ()


# --------------------------------------------------------------------------- CP1 Fable findings (S1, M5)


@pytest.mark.parametrize("arm_id", ["a_prime", "r_internal_error"])
def test_reopen_launch_relabelled_first_cannot_mask_stop(arm_id):
    def mutation(d):
        ev.add_reopen_load(d, arm_id)
        ev.launch(d, arm_id, "reopen")["launch_id"] = "first"

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP


@pytest.mark.parametrize("arm_id", ["a_prime", "r_cancelled"])
def test_pre_reopen_checkpoint_relabelled_after_reopen_cannot_mask_stop(arm_id):
    def mutation(d):
        checkpoint = ev.checkpoint(d, arm_id, "after_first")
        checkpoint["session_binding"] = "session-" + "9" * 32
        checkpoint["label"] = "after_reopen"

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP


def test_the_genuine_first_launch_and_post_reopen_checkpoint_stay_exempt():
    assert c.scan_positive_signals(ev.valid_raw_document()) == ()


def test_isolated_launcher_hash_must_match_its_captured_launcher_identity():
    def mutation(d):
        next(s for s in d["isolated_sources"] if s["source_kind"] == "refusal_stub:r_refusal")["launcher_sha256"] = "0" * 64

    result = _reduce(ev.mutated(mutation))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.PATCH_IDENTITY_MISMATCH in _codes(result)


# --------------------------------------------------------------------------- CP1 coordinator controls: scan totality


_SHAPES = ({}, [], None, 0, True, "x", 1.5, {"launch_id": "first"}, ["first"])


def _positive():
    return ev.mutated(lambda d: ev.add_reopen_load(d, "a_prime"))


def _leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield (*prefix, key)
            yield from _leaf_paths(item, (*prefix, key))
    elif isinstance(value, list):
        for position, item in enumerate(value):
            yield (*prefix, position)
            yield from _leaf_paths(item, (*prefix, position))


def _set(document, path, replacement):
    target = document
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = replacement


def _get(document, path):
    for step in path:
        document = document[step]
    return document


@pytest.mark.parametrize("layer", ["raw", "sanitized"])
def test_unhashable_prompted_launch_id_cannot_erase_a_known_stop(layer):
    document = _positive()
    if layer == "sanitized":
        document, _ = c.derive_sanitized_manifest(c.parse_raw_manifest(document))
    next(a for a in document["arms"] if a["arm_id"] == "prompted")["launches"][0]["launch_id"] = {}
    assert c.reduce_document(document, layer=layer).disposition is D.ZERO_ENTRY_REACHABLE_STOP


@pytest.mark.parametrize("layer", ["raw", "sanitized"])
def test_a_positive_launch_without_an_id_is_scanned_not_exempt(layer):
    document = _positive()
    if layer == "sanitized":
        document, _ = c.derive_sanitized_manifest(c.parse_raw_manifest(document))
    arm = next(a for a in document["arms"] if a["arm_id"] == "a_prime")
    arm["launches"] = [arm["launches"][1]]
    del arm["launches"][0]["launch_id"]
    assert c.reduce_document(document, layer=layer).disposition is D.ZERO_ENTRY_REACHABLE_STOP


@pytest.mark.parametrize("layer", ["raw", "sanitized"])
def test_a_bound_checkpoint_without_a_label_is_scanned_not_exempt(layer):
    document = ev.mutated(lambda d: ev.checkpoint(d, "r_refusal", "after_first").update(session_binding="session-" + "8" * 32))
    if layer == "sanitized":
        document, _ = c.derive_sanitized_manifest(c.parse_raw_manifest(document))
    arm = next(a for a in document["arms"] if a["arm_id"] == "r_refusal")
    arm["checkpoints"] = [arm["checkpoints"][0]]
    del arm["checkpoints"][0]["label"]
    assert c.reduce_document(document, layer=layer).disposition is D.ZERO_ENTRY_REACHABLE_STOP


def _non_signal_paths(document):
    positive = ("arms", 0, "launches", 1)
    for path in _leaf_paths(document):
        if path[: len(positive)] == positive or path == ("arms",) or path == ("arms", 0):
            continue
        yield path


def test_scan_and_reducer_are_total_and_keep_stop_under_arbitrary_field_shapes():
    base = _positive()
    paths = list(_non_signal_paths(base))
    assert len(paths) > 1000
    for path in paths[::7]:
        for shape in _SHAPES:
            document = copy.deepcopy(base)
            _set(document, path, copy.deepcopy(shape))
            result = c.reduce_document(document, layer="raw")
            assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, (path, shape)


def test_malformed_shapes_without_a_positive_are_invalid_never_an_exception():
    base = ev.valid_raw_document()
    for path in list(_leaf_paths(base))[::5]:
        for shape in ({}, [], 1.5, "x"):
            if _get(base, path) == shape:
                continue
            document = copy.deepcopy(base)
            _set(document, path, copy.deepcopy(shape))
            result = c.reduce_document(document, layer="raw")  # never raises, whatever the shape
            if shape != "x":  # a short token can be a legitimately valid value; containers and floats never are
                assert result.disposition is not D.ACCEPTED_CURRENT_CLIENT_GATE, (path, shape)
    for document in ({}, {"arms": [None, 1, "x", [], {"arm_id": {}}]}, {"arms": [{"launches": {}, "checkpoints": "x"}]}):
        assert c.reduce_document(document, layer="raw").disposition is D.INVALID_CURRENT_CLIENT_GATE
        assert c.reduce_document(document, layer="sanitized").disposition is D.INVALID_CURRENT_CLIENT_GATE


def test_real_first_launch_load_stays_invalid_and_prompted_b_stays_exempt_after_totality_fix():
    def first_load(d):
        record = ev.launch(d, "r_end_turn", "first")
        record["wire"].append(dict(record["wire"][2], index=len(record["wire"]), method="session/load", request_id=5))
        record["wire"].append(dict(record["wire"][3], index=len(record["wire"]), request_id=5, result_session_id=None))
        ev.recount(record)

    result = _reduce(ev.mutated(first_load))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE and R.FIRST_LAUNCH_LOAD_OBSERVED in _codes(result)
    assert c.scan_positive_signals(ev.valid_raw_document()) == ()


# --------------------------------------------------------------------------- consolidated Codex CP1 review (Serious 3, Serious 4, Minor 6)


def _prompt_event(document, arm_id, launch_id):
    return next(e for e in ev.launch(document, arm_id, launch_id)["wire"] if e["method"] == "session/prompt")


@pytest.mark.parametrize("arm_id", c.R_DESCRIPTOR_IDS)
def test_r_first_prompt_must_be_a_valid_prompt_not_an_empty_or_invalid_request(arm_id):
    result = _reduce(ev.mutated(lambda d: _prompt_event(d, arm_id, "first").update(prompt_valid=False)))
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.R_PROMPT_INVALID in _codes(result)


def test_prompted_lifecycle_a_prompt_must_be_valid():
    result = _reduce(ev.mutated(lambda d: _prompt_event(d, "prompted", "lifecycle_a").update(prompt_valid=False)))
    assert R.PROMPTED_LIFECYCLE_A_INVALID in _codes(result)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: _prompt_event(d, "r_refusal", "first").update(prompt_valid=None),
        lambda d: _prompt_event(d, "r_refusal", "first").update(prompt_valid=1),
        lambda d: ev.launch(d, "a_prime", "first")["wire"][0].update(prompt_valid=True),
        lambda d: ev.launch(d, "a_prime", "first")["wire"][0].pop("prompt_valid"),
    ],
)
def test_prompt_validity_is_a_closed_boolean_only_on_prompt_requests(mutation):
    assert R.SCHEMA_INVALID in _codes(_reduce(ev.mutated(mutation)))


def test_valid_prompt_validity_facts_reduce_to_accepted_and_survive_sanitization():
    raw = ev.valid_raw_document()
    assert _reduce(raw).disposition is D.ACCEPTED_CURRENT_CLIENT_GATE
    sanitized, _ = c.derive_sanitized_manifest(c.parse_raw_manifest(raw))
    assert _prompt_event(sanitized, "r_end_turn", "first")["prompt_valid"] is True
    assert c.reduce_document(sanitized, layer="sanitized").disposition is D.ACCEPTED_CURRENT_CLIENT_GATE


@pytest.mark.parametrize("payload", [b'{"a":1e400}', b'{"a":-1e400}', b'[1e999]'])
def test_strict_json_rejects_numeric_overflow_to_infinity(payload):
    with pytest.raises(c.ContractError) as excinfo:
        c.strict_json_loads(payload)
    assert excinfo.value.code == "non_finite_number"


@pytest.mark.parametrize("error", [RecursionError, ValueError])
def test_strict_json_maps_decoder_failure_to_invalid_json(monkeypatch, error):
    def reject(*_args, **_kwargs):
        raise error("simulated JSON decoder refusal")

    monkeypatch.setattr(c, "json", SimpleNamespace(JSONDecodeError=json.JSONDecodeError, loads=reject))
    with pytest.raises(c.ContractError) as excinfo:
        c.strict_json_loads(b"[]")
    assert excinfo.value.code == "invalid_json"


def test_privacy_scan_finds_private_keys_and_values_at_any_parseable_depth():
    # F1: the iterative scan must retain private keys and values in a deeply nested parsed document.
    leaf = b'{"/home/alice/notes":["D:/data","secret-token"]}'
    shallow = c.find_privacy_violations(c.strict_json_loads(leaf), forbidden_strings=("secret-token",))
    assert set(shallow) == {"posix_home_path", "windows_path_material", "forbidden_value"}
    deep = c.strict_json_loads(b"[" * 3_000 + leaf + b"]" * 3_000)
    assert c.find_privacy_violations(deep, forbidden_strings=("secret-token",)) == shallow


@pytest.mark.parametrize(
    "field,value",
    [
        ("error_code", True),
        ("error_code", "-32912"),
        ("error_code", [-32912]),
        ("error_code_name", ["MCP_REOPEN_REFUSED"]),
        ("error_code_name", "mcp_reopen_refused"),
        ("requires", {"x": 1}),
        ("requires", ""),
        ("owner", {"issue": 230}),
        ("owner", ""),
    ],
)
def test_descriptor_exclusions_are_recursively_typed(field, value):
    fixture = ev.descriptor_fixture()
    fixture["excluded_classes"][0][field] = value
    with pytest.raises(c.ContractError):
        c.parse_descriptor_fixture(fixture)


def test_the_source_proven_prior_idle_exclusion_is_retained():
    excluded = c.parse_descriptor_fixture(ev.descriptor_fixture()).excluded_classes
    assert [(e["error_code_name"], e["error_code"], e["requires"]) for e in excluded] == [("MCP_REOPEN_REFUSED", -32912, "prior_idle_suspension")]
