# Fresh Mypy baseline v2 — C1 setup correction

2026-10-16, Asia/Calcutta. Complete successor measurement under the reviewer-settled project configuration; the original measurement and 47-module candidate remain preserved. Product typing implementation has not begun.

| Actual execution platform | Python / Mypy | Errors | Error files | Checked files | Exit |
|---|---|---:|---:|---:|---:|
| Native Windows, windows-c1-01 | 3.14.4 / 2.3.1 | 231 | 46 | 226 | 1 |
| Ubuntu-24.04 WSL2 Linux, wsl-c1-01 | 3.14.4 / 2.3.1 | 222 | 45 | 226 | 1 |

Both stderr files are empty. Before/after source, configuration, lock and status identities matched within each run. The two runs share identical tracked-source/configuration/lock hashes. They ran sequentially after both separate environments completed frozen sync. This is actual Linux execution, not just a target-platform flag.

## Source, setup and authority

The operator approved the main-based lane, Mypy setup and fresh Windows/WSL baselines, with Claude review before implementation. Claude's first review (#329 comment 6220851664) accepted the measurement, independently reproduced the Windows multiset, accepted WSL on retained records (not replayed), and required third-party typing setup before the bootstrap set is finalized.

The C1 setup correction adds two locked dev-only stub packages and the justified exact third-party import exception. It stays within that setup/baseline phase. No source typing, tests, ratchet overrides, hook or CI change has been made. No commit, push, PR, merge, live service, paid call or cleanup has run.

- Lane: `agent/codex/static-typing-port`.
- Source HEAD: `c5ea5a1673b957f1e2dd3a09321c6a34ff293880`.
- `HEAD:src`: `d0d443548d3fc956744efd13764e96aadc0aa02d`.
- Tracked-source SHA-256 manifest: `31c870a54014fc0fbb382d191bf2d84792d34031a6a0e862082c225307781c9c`, unchanged from the original measurement.
- Measured pyproject/config SHA-256: `ab0840ae87dbe9e16311f1ebd0662a78553e8b009e9f65bb5502f57e1b829d91`.
- Lock SHA-256: `b3669ad80c64effed108e0a90a33ba00a92814435153b85059889bae6790eb46`.
- Overall setup diff from HEAD: `pyproject.toml` +14/-0 and `uv.lock` +222/-0. No existing package version changed or was removed. New package records are the original Mypy plus four dependencies and the two stubs below. The original four baseline reports were already untracked before the C1 runs; all before/after statuses match.

Mypy remains declared as `mypy>=2.3,<3`, locked 2.3.1. Added dev stubs: `types-pyyaml==6.0.12.20260906`, `types-defusedxml==0.7.0.20260504`. PyPI/typeshed identify them as stubs for the lane's PyYAML 6.0.* and defusedxml 0.7.* families. The installed confusable_homoglyphs 3.3.1 has no typing marker or stubs. Current typeshed inventory and bounded conventional PyPI stub-name checks found none; the check is not proof against differently named packages. See [PyYAML stubs](https://pypi.org/project/types-PyYAML/6.0.12.20260906/), [defusedxml stubs](https://pypi.org/project/types-defusedxml/0.7.0.20260504/) and [typeshed inventory](https://github.com/python/typeshed/tree/main/stubs).

## Checking policy

Each environment ran its own Python with:

```text
python -m mypy --config-file pyproject.toml --no-incremental --cache-dir <own-fresh-cache> --no-pretty src
```

The actual project Mypy configuration is:

```toml
[tool.mypy]
files = ["src"]
python_version = "3.14"
show_error_codes = true

[[tool.mypy.overrides]]
module = "confusable_homoglyphs"
ignore_missing_imports = true
```

The override names one third-party imported module; it exempts no source module. No source exceptions, global suppressions, source exclusions, wildcard overrides or stricter flags were added. `PYTHONPATH` and `MYPYPATH` are unset for the checker. Default Mypy coverage does not establish strict typing of unannotated bodies. Full absolute argv/interpreter inventories remain private provenance, not required operating dependencies.

## Cleared, new and retained diagnostics

On **each host**, compared with the original measured policy:

- Cleared exactly four `import-untyped` diagnostics: confusable_homoglyphs (`unicode_confusables.py:5`), yaml (`registry.py:27`), defusedxml and defusedxml.common (`tool_providers.py:10,11`). No `import-untyped` diagnostic remains.
- Added exactly two `override` diagnostics at `optimus_model_policy/registry.py:148`: `construct_mapping` declares `dict[str, Any]`, incompatible with the new stubs' `dict[Hashable, Any]` return type in `SafeConstructor` and `BaseConstructor`.
- Retained 229 existing diagnostics on Windows and 220 on WSL. The new stub-exposed source errors are preserved, not repaired or suppressed in this phase.

The successor multisets have 220 diagnostics in common, the same 11 Windows-only diagnostics and the same two WSL-only diagnostics as before. All 13 unmatched observations remain explicit in `baseline-summary.json`: platform account lookup and locking paths in `trusted_paths.py`, `launch_gate.py` and evidence runtime `lifecycle.py`. Their attribution is unchanged; no runtime pass/failure is inferred.

## Successor bootstrap candidate and cohort

The measured candidate is the exact union of **46** failing source modules across the two actual platforms. `optimus.guardrails.unicode_confusables` leaves the original 47-module set; no new module enters. `optimus_model_policy.registry` stays because its missing import was replaced by the two newly visible override diagnostics. This is a frozen review candidate, not installed overrides or operator-approved bootstrap activation.

Telemetry remains exactly **16 missing named `trace_id` call-arg diagnostics on both platforms**, with no other reported error in the module. Claude accepted it as the smallest complete contract in the first review. The new setup leaves this cohort evidence unchanged. Implementation must preserve its existing validator, direct-construction trace IDs, redaction and exact settlement payload contract; the eventual patch requires its all-factory correlation test and fresh static verification.

For the reviewer's C2 point, the implementation plan will propose default-Linux plus `--platform win32` checks in the existing Linux CI job, while retaining real native Windows evidence for platform-sensitive behavior. No CI code or additional target run has been added during preparation.

## Artifact hashes and review

| Artifact | SHA-256 |
|---|---|
| 46-module candidate | `b6a756129365762efe42c77593313507fd1be1a039a85ef4ebc22490194c5bab` |
| Normalized diagnostics | `14e80fb1b37d1581d41866de207bf5ff6e9174d59dd2d9c0fa8f5117e80fd8c0` |
| Platform summaries and multiset differences | `a41130371424c240c6978cd6e812b4621ae07f062c03dbdd73d5c25f6f6a110c` |
| Cleared/new/retained comparison | `90e1707716219a3167f4720015fd0b40cebb232ab14401a3eb6d589f66e473f7` |

Each C1 host was measured exactly once. The original first WSL setup exit-127 failure and all original baseline records remain intact. The C1 WSL sync's hardlink warning fell back to copying and exited 0. No product tests ran. Both sets of baseline records remain failing static-analysis evidence, not clean-head or product acceptance.

Claude is asked to review C1's settled imports/configuration, both successor runs, exact diagnostic deltas and 46-module derivation before the implementation plan is finalized. Product source implementation remains held for the next applicable operator approval.
