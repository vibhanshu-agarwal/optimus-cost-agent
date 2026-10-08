# Trusted Plan 12 test composition — reviewed offline contract

2026-10-04; cf9bb9d. This describes implemented test composition and its evidence boundary, not production activation.

## Entry and trust

Select only --plan12-test-profile qualification or attached. Names map to reviewed repository code/pinned data; no caller file, arbitrary hash, environment toggle or runtime registry override. HMAC launch authorization binds the security snapshot containing the effective profile hash. Host and Gateway independently compose it; authenticated child-manifest verification binds the same hash. Preserve workspace/scope/keyring/credentials. fixture=True, unknown name, mismatched/tampered/stale approval or manifest refuse without upstream attempts.

The host's literal comparison checks that its composition matches the authorized candidate; it is not an independent operator-approval check. The real server passes process-scoped RoutePolicy/attachment/receipt dependencies to ndjson adapters, and the child receives GatewayModelPolicy. Packaged ENFORCEMENT_ACTIVE=False, trusted_snapshot() returning None and shipped defaults stay unchanged.

A profiled host must spawn its own profiled Gateway. Refuse an already-listening/external Gateway or failure to obtain the child with TEST_PROFILE_GATEWAY_NOT_STARTED. Reject --no-auto-start, --framed and --strict at argument parsing. Non-strict --check-config remains non-call inspection; do not claim it proves enforcement. A different explicit --model returns typed AGENT_MODEL_INVALID before Redis/Gateway/server. No standalone run-gateway profile flag is supplied or needed. The operator must deliberately clear a conflicting Gateway before a future profiled run; the host does not take it over.

## Qualification and attached profiles

Qualification targets only openai/gpt-6-luna on openai/fast, reasoning none, literal quantization unknown (distinct from None). Its current estimator is unmeasured and it admits no eligible model, so startup refuses before services. Public route metadata is insufficient tokenizer/finish proof. Qwen has no existing active role that could qualify through this profile; do not add one or substitute a candidate.

Attached maintenance requires verified route/estimator facts and a genuine passing calculator fixture/format/validator receipt. Revised inputs and effective hash require review and matching approval/manifest. No receipt is fabricated. One finite repack shares 18 logical callbacks; StrategyParameters identity is stable and ViewLimits carries remaining allowance.

## Evidence boundary

The offline positive composition uses a SYNTHETIC eligible profile to prove process plumbing, hash binding, provider controls, complete capacity equality/one-over, output/finish behavior and retry propagation. Negative tests prove refusal. Actual HostMaintenance/GatewaySummarizerCall boundary tests are offline and use test estimators. These establish neither Luna eligibility nor real provider quality or Zed behavior. Paid qualification and real Task 13 remain UNRUN/held. The enabled Gateway resends only after definitely NOT_SENT (including proven pre-connection timeout) or rejected 429, at most once on identical route/payload; uncertain delivery, post-connection timeout, 5xx and unknown usage never resend. Each physical attempt is receipted.

Production bootstrap enforcement, attachment and Haiku-default removal remain separately held rollout requirements. This document supplies no paid/live or publication authority.
