# Plan 11.25 — Multi-turn conversation contract evidence (Task 10)

**Date:** 2026-08-22  
**Implementation HEAD:** recorded at evidence generation time via `git rev-parse HEAD`.  
**Settled contract digest:** `9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38`  
**Primary suite command:**

```powershell
uv run --frozen pytest tests/unit/acp tests/unit/agent tests/unit/telemetry tests/e2e/acp/test_multi_turn_conversation.py -q
```

Node IDs below are pytest node ids. A predicate maps to at least one passing node; compound predicates list the covering set. Retired `5.24` is excluded.

## Predicate → evidence

| Predicate | Test node ID(s) | Notes |
|---|---|---|
| **1** Dependent follow-up | `tests/e2e/acp/test_multi_turn_conversation.py::test_dependent_follow_up_uses_turn1_history` | Real `serve_ndjson` + deterministic runner; turn 2 task requires turn-1 fact; no warning/refusal. |
| **2** Admission/commitment cap | `tests/unit/acp/test_conversation.py::test_admission_cap_refuses_without_history_or_cost`; `tests/unit/acp/test_conversation.py::test_commitment_crossing_commits_then_closes`; `tests/e2e/acp/test_multi_turn_conversation.py::test_cap_closed_refusal_is_explanatory_success`; `tests/e2e/acp/test_multi_turn_conversation.py::test_admission_cap_exact_boundary_still_refuses` | Unit proves latch/no-history; e2e proves explanatory `stopReason: refusal`. |
| **2b** 80% warning first crossing | `tests/unit/acp/test_conversation.py::test_warning_first_crossing_only_confirmed_by_flush`; `tests/unit/acp/test_lifecycle.py::test_warning_sequence_monotonic_ids_retry_and_incremental_retirement`; `tests/unit/acp/test_lifecycle.py::test_warning_abandonment_queued_and_write_started` | Attempt vs flush confirmation; NoticeControl warning lifecycle. |
| **3** Delivery indeterminate dominates | `tests/unit/acp/test_conversation.py::test_delivery_indeterminate_dominates_cap`; `tests/e2e/acp/test_multi_turn_conversation.py::test_delivery_indeterminate_dominates_for_evidence_map` | |
| **4** Concurrent same-session prompt | `tests/e2e/acp/test_multi_turn_conversation.py::test_concurrent_same_session_prompt_rejected`; `tests/unit/acp/test_spec_protocol.py::test_concurrent_same_session_prompt_is_request_cancelled` | `REQUEST_CANCELLED` / `"a turn is already in progress"`. |
| **4b** Unknown session vs terminal refusal | `tests/e2e/acp/test_multi_turn_conversation.py::test_unknown_session_is_jsonrpc_error_not_refusal`; `tests/e2e/acp/test_multi_turn_conversation.py::test_cap_closed_refusal_is_explanatory_success`; `tests/unit/acp/test_spec_protocol.py::test_cap_closed_refusal_is_explanatory_not_jsonrpc_error` | Distinct code paths: JSON-RPC error vs explanatory refusal. |
| **5.1** Atomic execution-start-gate race | `tests/unit/acp/test_lifecycle.py::test_execution_start_versus_cancel_both_lock_orders`; `tests/unit/acp/test_lifecycle.py::test_concurrent_try_start_and_cancel_barrier_invariants`; `tests/unit/acp/test_lifecycle.py::test_try_start_after_cancel_creates_terminal_suppressed_atomically`; `tests/unit/acp/test_lifecycle.py::test_register_operations_when_gate_closed_registers_suppressed` | Barriers; no sleeps. |
| **5.2** Cancel vs teardown / terminal delivery | `tests/unit/acp/test_lifecycle.py::test_cancel_versus_terminal_lane_seal_both_orders`; `tests/unit/acp/test_lifecycle.py::test_cancel_does_not_suppress_terminal_set_messages`; `tests/unit/acp/test_lifecycle.py::test_seal_final_delivery` *via* `test_terminal_decision_type`; `tests/unit/acp/test_spec_protocol.py::test_session_cancel_resolves_prompt_and_pending_permission` | |
| **5.3** Stale planning callback | `tests/unit/acp/test_lifecycle.py::test_late_directive_reports_are_diagnostic_only`; `tests/unit/acp/test_lifecycle.py::test_publish_authoritative_is_idempotent_diagnostic_accepts_late` | |
| **5.4** Required terminal set / plan presence | `tests/unit/acp/test_settlement.py::test_terminal_set_and_fallback_mutate_only_final_delivery`; `tests/unit/agent/test_models.py::test_agent_run_result_accepts_candidate_plan_text`; `tests/unit/acp/test_spec_protocol.py::test_planning_failure_emits_end_turn_without_permission`; `tests/unit/acp/test_spec_protocol.py::test_planning_model_refused_emits_sanitized_text_without_permission`; `tests/unit/acp/test_spec_protocol.py::test_permission_cancel_option_does_not_execute_plan`; `tests/unit/acp/test_spec_protocol.py::test_session_cancel_resolves_prompt_and_pending_permission` | Plan-bearing vs planless exercised through adapter cancel/reject/failure paths; full §2.5 combinatorial matrix remains covered primarily by settlement consequence maps + adapter terminals. |
| **5.5** JSON-RPC response lifetime | `tests/unit/acp/test_lifecycle.py::test_response_start_versus_already_abandoned_transport`; `tests/unit/acp/test_lifecycle.py::test_ordinary_response_capability_and_retirement_orders`; `tests/unit/acp/test_stdio_ndjson.py::test_serve_ndjson_eof_cancels_pending_requests_and_closes_owned_state_once` | TurnControl survives through envelope delivery; EOF teardown. |
| **5.6** Mid-planning / mid-execution teardown | `tests/unit/acp/test_lifecycle.py::test_teardown_freezes_started_directives_exact_vocabularies`; `tests/unit/acp/test_lifecycle.py::test_terminal_message_start_versus_teardown_both_orders` | Gateway `cost_unknown`, WRITE/TEST `failed_effect_unknown`, READ `abandoned_no_effect`, persistence `persistence_partial`. |
| **5.7** Fallback delivery matrix (§2.6a) | `tests/unit/acp/test_settlement.py::test_send_outcome_to_final_delivery_mapping`; `tests/unit/acp/test_settlement.py::test_send_outcome_to_rpc_response_delivery_mapping`; `tests/unit/acp/test_lifecycle.py::test_write_started_freeze_to_ambiguous_and_message_class_consequences` | Pure consequence algebra + freeze consequences; adapter-level six-cell recovery is evidenced by these mappings plus terminal-lane tests. |
| **5.8** Production settlement oracle | `tests/unit/acp/test_spec_protocol.py::test_turn_finalization_emits_content_free_settlement_once`; `tests/unit/telemetry/test_fanout.py::test_emit_acp_turn_settlement_contains_jsonl_redis_and_gateway_failures`; `tests/unit/telemetry/test_fanout.py::test_emit_acp_turn_settlement_does_not_swallow_baseexception_subclass` | Content-free; sink containment. |
| **5.9** Late background completion | `tests/unit/acp/test_lifecycle.py::test_late_directive_reports_are_diagnostic_only`; `tests/unit/acp/test_outbound_writer.py::test_write_started_freeze_plus_late_diagnostic` | |
| **5.10** Runtime lifecycle evidence | `tests/unit/acp/test_outbound_writer.py::test_close_and_join_is_idempotent_and_non_daemon`; `tests/unit/acp/test_outbound_writer.py::test_serve_ndjson_eof_with_dedicated_writer`; `tests/unit/acp/test_stdio_ndjson.py::test_serve_ndjson_eof_cancels_pending_requests_and_closes_owned_state_once` | |
| **5.11** Late registration | `tests/unit/acp/test_lifecycle.py::test_register_operations_when_gate_closed_registers_suppressed` | Gate closed before register → `suppressed`. |
| **5.12** / **5.12a** Terminal-delivery lane race | `tests/unit/acp/test_lifecycle.py::test_cancel_versus_terminal_lane_seal_both_orders`; `tests/unit/acp/test_lifecycle.py::test_terminal_message_start_versus_teardown_both_orders` | Both lock orders. |
| **5.13** Terminal-message start race | `tests/unit/acp/test_lifecycle.py::test_terminal_message_start_versus_teardown_both_orders` | |
| **5.14** Provisional-plan delivery / direct failure | `tests/unit/acp/test_lifecycle.py::test_queued_send_suppressed_on_teardown`; `tests/unit/acp/test_lifecycle.py::test_write_started_freeze_to_ambiguous_and_message_class_consequences`; `tests/unit/acp/test_lifecycle.py::test_permission_allocate_send_outcomes_and_teardown_cancel`; `tests/unit/acp/test_lifecycle.py::test_permission_ambiguous_and_failure_are_not_approved` | Includes owner-scoped permission teardown. |
| **5.15** Repeated teardown idempotent | `tests/unit/acp/test_lifecycle.py::test_frozen_snapshot_immutable_and_repeated_teardown_is_pure_read` | |
| **5.16** Writer serialization | `tests/unit/acp/test_outbound_writer.py::test_fifo_serialization_blocks_second_write_until_first_completes`; `tests/unit/acp/test_outbound_writer.py::test_phase_classification_helpers`; `tests/unit/acp/test_outbound_writer.py::test_token_released_after_flush`; `tests/unit/acp/test_outbound_writer.py::test_no_direct_ndjson_physical_write_outside_writer_and_adapter` | FIFO + no bypass grep. |
| **5.17** Effect-algebra happy path | `tests/unit/acp/test_settlement.py::test_effect_algebra_empty_is_none`; `tests/unit/acp/test_settlement.py::test_effect_algebra_all_succeeded_is_complete`; `tests/unit/acp/test_settlement.py::test_effect_algebra_any_failed_effect_unknown_is_indeterminate`; `tests/unit/acp/test_settlement.py::test_effect_algebra_named_write_succeeded_test_suppressed_is_partial`; `tests/unit/acp/test_settlement.py::test_effect_algebra_failed_no_effect_and_suppressed_only_is_none`; `tests/unit/acp/test_settlement.py::test_read_gateway_and_plan_persistence_never_enter_e` | |
| **5.18** No second write on broken transport | `tests/unit/acp/test_lifecycle.py::test_response_start_versus_already_abandoned_transport`; `tests/unit/acp/test_outbound_writer.py::test_queued_suppression_resolves_without_write`; `tests/unit/acp/test_spec_protocol.py::test_agent_run_denied_after_transport_teardown` | |
| **5.19** `finalize_once` idempotence / exclusivity | `tests/unit/acp/test_lifecycle.py::test_finalize_once_identity_conditional_and_idempotent`; `tests/unit/acp/test_lifecycle.py::test_finalize_once_skips_remover_when_identity_mismatches`; `tests/unit/acp/test_spec_protocol.py::test_turn_finalization_emits_content_free_settlement_once` | |
| **5.20** Plan persistence vocabulary | `tests/unit/acp/test_settlement.py::test_plan_persistence_full_vocabularies`; `tests/unit/agent/test_state_store.py::test_persist_plan_reports_persisted_for_in_memory`; `tests/unit/agent/test_state_store.py::test_persist_plan_partial_when_pointer_write_fails`; `tests/unit/acp/test_lifecycle.py::test_teardown_freezes_started_directives_exact_vocabularies` | |
| **5.21** / **5.21a** Stop-condition precedence | `tests/unit/agent/test_planning_loop.py` halt/precedence selectors; `tests/unit/acp/test_spec_protocol.py::test_session_cancel_resolves_prompt_and_pending_permission`; `tests/unit/acp/test_lifecycle.py::test_post_teardown_fields_expose_transport_abandoned` | Existing halt callback + cancel. |
| **5.22** Typed NoticeControl refusal / warning starts | `tests/unit/acp/test_lifecycle.py::test_refusal_roles_and_finalization_before_writer`; `tests/unit/acp/test_lifecycle.py::test_warning_sequence_monotonic_ids_retry_and_incremental_retirement`; `tests/unit/acp/test_lifecycle.py::test_direct_suppressed_after_abandonment_and_double_start_invariant` | |
| **5.23** Gateway terminal vocabulary | `tests/unit/acp/test_settlement.py::test_gateway_full_vocabularies`; `tests/unit/acp/test_lifecycle.py::test_teardown_freezes_started_directives_exact_vocabularies`; `tests/unit/acp/test_spec_protocol.py::test_unknown_cost_emits_end_turn_without_permission_request` | |
| **5.24** | *(retired)* | Excluded per contract. |
| **5.25** Terminal refusal governed end-to-end | `tests/e2e/acp/test_multi_turn_conversation.py::test_cap_closed_refusal_is_explanatory_success`; `tests/unit/acp/test_spec_protocol.py::test_cap_closed_refusal_is_explanatory_not_jsonrpc_error`; `tests/unit/acp/test_lifecycle.py::test_refusal_roles_and_finalization_before_writer` | |
| **5.26** Send class owner/start exact-set | `tests/unit/acp/test_settlement.py::test_send_owners_gates_and_start_operations`; `tests/unit/acp/test_settlement.py::test_exactly_nine_send_rows`; `tests/unit/acp/test_settlement.py::test_registry_has_exactly_fifteen_rows_with_eight_fields` | |
| **5.27** Non-turn JSON-RPC response ownership | `tests/unit/acp/test_lifecycle.py::test_ordinary_response_capability_and_retirement_orders`; `tests/unit/acp/test_stdio_ndjson.py::test_serve_ndjson_exits_cleanly_on_byte_stream_eof` *(envelope routing covered in Task 8 stdio/server paths)* | Server routes non-turn envelopes through NoticeControl. |
| **5.28** Capability retirement / quiescence | `tests/unit/acp/test_lifecycle.py::test_ordinary_response_capability_and_retirement_orders`; `tests/unit/acp/test_lifecycle.py::test_warning_sequence_monotonic_ids_retry_and_incremental_retirement`; `tests/unit/acp/test_outbound_writer.py::test_token_released_after_flush` | |
| **5.29** Typed send_key / warning-attempt collision-free | `tests/unit/acp/test_lifecycle.py::test_typed_send_keys_do_not_collide_on_equal_scalars`; `tests/unit/acp/test_lifecycle.py::test_warning_sequence_monotonic_ids_retry_and_incremental_retirement` | |
| **5.30** Directive + evidence-append completeness | `tests/unit/acp/test_settlement.py::test_directive_and_evidence_row_counts`; `tests/unit/acp/test_settlement.py::test_settlement_telemetry_has_no_owner_start_lifecycle_or_terminal`; `tests/unit/acp/test_settlement.py::test_planning_iteration_is_halt_only_without_registered_lifecycle`; `tests/unit/acp/test_settlement.py::test_planning_read_full_vocabularies`; `tests/unit/acp/test_settlement.py::test_gateway_full_vocabularies`; `tests/unit/acp/test_settlement.py::test_execution_expands_read_and_write_test_vocabularies`; `tests/unit/acp/test_settlement.py::test_plan_persistence_full_vocabularies` | Same immutable `WORK_CLASS_REGISTRY` object. |
| **5c** Request-id reuse / distinct turns | `tests/e2e/acp/test_multi_turn_conversation.py::test_request_id_reuse_keeps_distinct_turn_seq`; `tests/unit/acp/test_spec_protocol.py::test_sequential_prompts_reuse_wire_id_with_distinct_turn_seq`; `tests/unit/acp/test_conversation.py::test_request_id_reuse_cannot_trip_idempotence_guard` | |
| **5d** Outbound taxonomy / permission ambiguous | `tests/unit/acp/test_lifecycle.py::test_permission_ambiguous_and_failure_are_not_approved`; `tests/unit/acp/test_settlement.py::test_notice_behavior_is_best_effort`; `tests/unit/acp/test_settlement.py::test_permission_eligibility` | Progress/gauge best-effort; permission ambiguity blocks approval. |
| **5e** Canonical adversarial framing | `tests/unit/acp/test_conversation.py::test_canonical_render_is_deterministic_and_keys_by_turn_seq` | Framing + byte length. |
| **5f** Distinct rejection vs cancellation internals | `tests/unit/acp/test_settlement.py` outcome/consequence maps; `tests/unit/acp/test_spec_protocol.py::test_permission_cancel_option_does_not_execute_plan`; `tests/unit/acp/test_spec_protocol.py::test_session_cancel_resolves_prompt_and_pending_permission` | Wire may collapse; internals remain distinct in settlement vocab. |
| **5h** Forced partial-write → indeterminate | `tests/unit/acp/test_settlement.py::test_effect_algebra_any_failed_effect_unknown_is_indeterminate`; `tests/unit/acp/test_lifecycle.py::test_teardown_freezes_started_directives_exact_vocabularies` | WRITE freeze → `failed_effect_unknown`. |
| **5k** Sanitized value across consumers + raw plan boundary | `tests/unit/acp/test_conversation.py::test_sanitization_identical_across_consumers`; `tests/e2e/acp/test_multi_turn_conversation.py::test_sanitized_secret_absent_from_planner_task` | Canary + path aliases; planner receives sanitized task. |
| **5l** `failed_no_effect` → `none` | `tests/unit/acp/test_settlement.py::test_effect_algebra_failed_no_effect_and_suppressed_only_is_none` | |
| **5m** `suppressed` exercised | `tests/unit/acp/test_settlement.py::test_effect_algebra_named_write_succeeded_test_suppressed_is_partial`; `tests/unit/acp/test_lifecycle.py::test_try_start_after_cancel_creates_terminal_suppressed_atomically` | |
| **5n** Empty-effect plan → `none` | `tests/unit/acp/test_settlement.py::test_effect_algebra_empty_is_none` | |
| **5p** Cap constant exact | `tests/unit/acp/test_conversation.py::test_cap_and_warning_constants_are_exact` | `524_288` and `419_431`. |
| **5q** Gauge display-only under refuse | `tests/unit/acp/test_conversation.py::test_gauge_is_floor_division_and_does_not_drive_decisions`; `tests/e2e/acp/test_multi_turn_conversation.py::test_gauge_approximate_and_usage_update_shape` | |
| **5r** Failed refusal delivery preserves disposition | `tests/unit/acp/test_lifecycle.py::test_refusal_roles_and_finalization_before_writer`; `tests/e2e/acp/test_multi_turn_conversation.py::test_cap_closed_refusal_is_explanatory_success` | Disposition latched before delivery; remains closed after. |
| **5s** Planning cost retained | `tests/unit/acp/test_conversation.py::test_planning_cost_once_and_unknown_omits_cumulative`; `tests/unit/agent/test_runner.py::test_approved_agent_run_replays_stored_plan_without_second_gateway_call` | |
| **5u** Password raw+decoded; "default" preserved | `tests/unit/acp/test_conversation.py::test_sanitization_identical_across_consumers` | |
| **6** Session cost never double-counts | `tests/unit/acp/test_conversation.py::test_planning_cost_once_and_unknown_omits_cumulative`; `tests/unit/agent/test_runner.py::test_approved_agent_run_replays_stored_plan_without_second_gateway_call` | Planning cost applied once; approved replay reuses stored cost. |
| **7** 16 KiB workspace assert | `tests/unit/agent/test_planning_loop.py::test_planning_evidence_partition_matches_workspace_context_cap` | |
| **8** Rendered-envelope byte accounting | `tests/unit/acp/test_conversation.py::test_canonical_render_is_deterministic_and_keys_by_turn_seq`; `tests/e2e/acp/test_multi_turn_conversation.py::test_admission_cap_exact_boundary_still_refuses` | Admission uses rendered UTF-8 bytes. |

## Suite commands executed for Task 10

```powershell
uv run --frozen pytest tests/unit/acp tests/unit/agent tests/unit/telemetry tests/e2e/acp/test_multi_turn_conversation.py -q
uv run --frozen coverage run -m pytest
uv run --frozen coverage report --fail-under=80
uv run --frozen ruff check .
git diff --check
```

Results are filled after the commands above pass; HEAD and coverage % are recorded below.

## Results

| Gate | Result |
|---|---|
| Hermetic multi-turn suite | **PASS** — 1013 passed, 19 skipped |
| Coverage ≥ 80% | **PASS** — aggregate **82%** (`coverage report --fail-under=80`) |
| Ruff | **PASS** — `ruff check .` clean |
| `git diff --check` | **PASS** |
| HEAD (pre-Task-10 commit) | `ef7ba40433f149ec4cc671a0e28a8ffbf0b451b6` |

Supporting fixes included in this evidence commit (required for full `coverage run -m pytest` green):

- Plan 11.25 modules added to `ESTABLISHING_EXECUTION_GIT_PATHS`; probe `session/prompt` patch markers updated for `ownership_slot`.
- Plan 9.96 logging-surface manifest entries for conversation envelope, dedicated writer, `write_bytes`, and `persist_plan`.


## Honest residual notes

- Several `5.x` cells are proven by composing pure settlement algebra, `TurnControl` barrier tests, and adapter terminal paths rather than a single mega-scenario that enumerates every §2.6a table cell in one function. Where a cell is only reachable through that composition, the mapping names the composing nodes.
- Dependent follow-up is hermetic in-process NDJSON with a controlled runner (no live Gateway / Zed). Live-provider continuity remains out of Slice 1.
- `MT-FU-1` / `MT-FU-2` remain approval/design-document gates per Task 0; not claimed resolved here.
