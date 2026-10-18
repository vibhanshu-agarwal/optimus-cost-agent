"""The one consolidated post-gate record update of 2026-10-16 (Codex checkpoint 3 follow-up, items 1-3):
gate-rerun summary, WSL evidence, R2 disposition (tools filed) and the live-issue updates, written into the
validation record, the bundle README, the correction map and the docs index. Every edit is an asserted exact
replacement or a whole-section replacement between known headings. No PDF is rebuilt.

Usage: apply_consolidated_update.py REPO_ROOT WORKSPACE
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
ws = Path(sys.argv[2]).resolve()
bundle = repo / "docs" / "sources" / "capability-evidence-correction"
record = bundle / "validation-record.md"
readme = bundle / "README.md"
FROZEN = "005cdab0941ad3f0f251b9d11e55ef96e0a58b0a0bb53ba6b0c8e14bac3bffa6"  # pragma: allowlist secret
INDEX = "04a2e498305bde854a0f6f281ceb5652bd39d1f0d643fc8557ca750ac90f5ada"  # pragma: allowlist secret
FOLLOWUP = "a17b449be513be55ae5cd24f66b72e60e153ce201d44530b33a869215ccea336"  # pragma: allowlist secret
PLATFORM_NODES = "363bfa3b9fe153418e249867d1e1c7ee4ed03b691d33c99c95b26089af008e2d"  # pragma: allowlist secret
CACHE_DB = "f4001ce92e50304552e665c2e7926d72fef68b7790d16845802fa420233821c1"  # pragma: allowlist secret


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rep(p: Path, old: str, new: str) -> None:
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (p.name, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")


def replace_section(p: Path, start_heading: str, end_heading: str, new: str) -> None:
    t = p.read_text(encoding="utf-8")
    a, b = t.index(start_heading), t.index(end_heading)
    assert a < b
    p.write_text(t[:a] + new + t[b:], encoding="utf-8", newline="\n")


def gate_log(name: str) -> str:
    return sha(ws / "gates-2026-10-16" / name)[:16] + "..."


tools_dir = bundle / "tools"
tool_rows = "\n".join(f"| `{p.name}` | `{sha(p)}` |" for p in sorted(tools_dir.glob("*.py")))
after360 = (ws / "issues" / "applied" / "issue-360-after.txt").read_text(encoding="utf-8").split("|")[1].strip()
after363 = (ws / "issues" / "applied" / "issue-363-after.txt").read_text(encoding="utf-8").split("|")[1].strip()
wsl = ws / "wsl" / "run-20261016T005633Z"
wsl_receipt = sha(wsl / "11-node-accounting.md")

# ---- validation record -------------------------------------------------------------------------------------
rep(record, "# Validation record: capability and evidence correction (2026-10-15, revised 2026-10-16)\n",
    "# Validation record: capability and evidence correction (2026-10-15, revised 2026-10-16; gate rerun, WSL evidence and dispositions appended 2026-10-16)\n")
rep(record, "### Tools (held in the sealed packets, not in the repository)\n",
    "### Tools (identities as sealed in the packets on 2026-10-16; the filed copies are listed in the gate-rerun section)\n")
rep(record, "### Repository checks at the revised filing state (2026-10-16)\n",
    "### Repository checks at the revised filing state (2026-10-16, before the gate rerun; dated history)\n")
rep(record, "Commit readiness is **not** established by these checks: the documentation checks pass, but the policy-required hooks have not passed on this host and the WSL obligation is open.\n",
    "At that time commit readiness was **not** established by these checks: the documentation checks passed, but the policy-required hooks had not passed on this host and the WSL obligation was open. The gate rerun below changed that state; the entries above stand as written.\n")
rep(record, "3. 2026-10-16: R1-R5 applied to the sources, map, bundle README and docs index; HLD v2.20, Test Strategy v1.9 and Roadmap v11 rebuilt; this record rewritten; the supplemental packet sealed.\n",
    "3. 2026-10-16: R1-R5 applied to the sources, map, bundle README and docs index; HLD v2.20, Test Strategy v1.9 and Roadmap v11 rebuilt; this record rewritten; the supplemental packet sealed. Candidate frozen at staged-inventory `" + FROZEN + "` for the Codex follow-up.\n"
    "4. 2026-10-16: scoped pre-commit environment repair and Windows gate rerun; WSL commit-profile run; both bound to the frozen candidate (section below). Nothing in the candidate changed.\n"
    "5. 2026-10-16: the authoring tools filed under `tools/` (R2 disposition), issues #360 and #363 updated under per-issue operator approval, and this section appended; a new candidate identity follows (recorded with the third packet, outside this file).\n")

gate_section = f"""
## Gate rerun, WSL evidence and dispositions (2026-10-16)

Codex's checkpoint 3 follow-up (`checkpoint-3-frozen-candidate-followup.md`, SHA-256 `{FOLLOWUP}`, kept outside the repository) verified the frozen candidate and kept four items open: a repository-visible gate summary, the R2 disposition, the live issues and the WSL evidence. This section records all four. Everything below is bound to the **frozen candidate**: staged-inventory SHA-256 `{FROZEN}` (`git ls-files --stage`), staged binary-diff SHA-256 `{INDEX}` (`git diff --cached --binary 91fd64a`, which is also the `index_sha256` every profile selection below records), HEAD `91fd64ac78025efe1076bddb106ff89e6adb2030`, 23 staged paths. The 2026-10-15 and pre-rerun entries above are dated history and stand as written.

### Windows gates from a scoped pre-commit environment

`PRE_COMMIT_HOME=C:\\worktrees\\optimus-cost-agent-worktrees\\_precommit-home-plan12-doccorr`, provisioned on 2026-10-16 by `pre-commit install-hooks` (`pre-commit-hooks v4.6.0` clone and the `@ast-grep/cli@0.36.2` Node environment; cache `db.db` SHA-256 `{CACHE_DB}`). The shared cache `C:\\Users\\pc\\.cache\\pre-commit` was not modified. Logs are in the gate evidence folder sealed in the third packet (hash prefixes below).

| # | Gate | Shell | Result | Log |
|---|---|---|---|---|
| 1 | `pre-commit install-hooks` | PowerShell | exit 0 | `01-install-hooks.log` ({gate_log("01-install-hooks.log")}) |
| 2 | `pre-commit run --all-files optimus-ast-grep` | PowerShell | Passed | `02-ast-grep-hook.log` ({gate_log("02-ast-grep-hook.log")}) |
| 3 | `pytest --no-cov -q tests/unit/tools/test_debug_trace_message_rule.py` | PowerShell | 39 passed, exit 0 (run `20261015T185559-42060-5aa9b9`); the 2026-10-15 setup error is gone | `03-ast-grep-gate-test.log` ({gate_log("03-ast-grep-gate-test.log")}) |
| 4 | `python -m tools.testing.run_profile --profile commit`, attempt 1 | PowerShell whose PATH lacks `Git\\usr\\bin` | **failed**, exit 1: 6 failed, 6654 passed, 37 skipped; profile `20261015T185623-54604-ec0cdd`, subrun `20261015T185709-62880-107365`. All six failures are `tests/unit/guardrails/test_ci_parity.py`: `shutil.which("bash")` resolved the WSL launcher in that shell (no `uv` inside WSL). An environment artefact, retained as failed, not rerun in that shell | `04-run-profile-commit.log` ({gate_log("04-run-profile-commit.log")}); diagnosis `04a-run-profile-commit-diagnosis.md` ({gate_log("04a-run-profile-commit-diagnosis.md")}) |
| 5 | `pre-commit run --files <23 staged paths>`; the profile's attempt 2 runs inside the `optimus-pytest-coverage` hook | Git Bash | trailing-whitespace Passed; yaml, toml Skipped (no files); **`check-added-large-files` Failed** (four PDFs); ruff, bandit, ast-grep, config-trust-scan, secret-scan Passed; **pytest-coverage Passed**: profile `20261015T190751-54680-5bc4ea`, subrun `20261015T190827-42260-d67065`, 6697 selected, 1125 deselected, 0 failed, 37 skipped, verdict pass, exit 0. Overall `pre-commit` exit 1 from the file-size hook alone | `05-pre-commit-staged.log` ({gate_log("05-pre-commit-staged.log")}) |

Both profile runs selected the same 6697 nodes (`fallback=broad` from the unmapped `sources/page-updates.json`: 235 global gates, 5939 broad fallback, 160 prose gates, 363 folder scans; same `selection.json`). These are staged-candidate, coverage-free Windows results: not committed-HEAD acceptance, not coverage and not WSL evidence. "Commit profile passed" is supported; "all hooks passed" is not. The side session's report said 24 staged paths; the candidate has 23.

File size: HLD 2,880,775 bytes; LLD 14,955,287; Guardrails 2,557,879; Test Strategy 2,139,522 exceed the `check-added-large-files` default of 500 KB (Roadmap 221,473 does not). A one-commit exception limited to that hook and these four files is the operator's decision; no hook configuration is changed.

### WSL evidence for the obligation `wsl-platform: next checkpoint`

Every commit-profile run of this candidate (2026-10-15 and both of 2026-10-16) emitted the obligation; the trigger is `fallback:broad`. The required set is the 56 platform-tagged nodes of the selection (the six modules `tests/profiles.toml` tags `platform`; list `platform-nodes-005cdab0.txt`, SHA-256 `{PLATFORM_NODES}`: 32 in `test_acp_subprocess_env.py`, 9 in `test_launch_trust_flow.py`, 9 in `test_evidence_redaction_adapter.py`, 2 each in `test_private_files_platform.py`, `test_subprocess_truncation.py`, `test_launch_approvals_lock_failures.py`). No existing WSL evidence was eligible for unchanged-input reuse: the sealed `wsl-full-1` is at cf9bb9d (product source differs from `91fd64a`) and the WSL clones on this host (`optimus-cost-agent-main7-linux` at 8177b9b, `p11-fu-17-proof` at 76bbf1e) hold no profile records. Fresh evidence was therefore obtained:

- **Faithful view**: clone of the GitHub repository at the pin `91fd64a` in WSL Ubuntu-24.04 (kernel 6.18.54.1-microsoft-standard-WSL2), index recreated with `git apply --index` from the frozen worktree's `git diff --cached --binary 91fd64a` (SHA-256 `{INDEX}`); the clone's `git ls-files --stage` SHA-256 equals `{FROZEN}` before and after the run. The Windows worktree's `.venv` was never used.
- **Independent frozen environment**: `uv sync --frozen --python 3.14 --extra dev` from `uv.lock`; CPython 3.14.6, pytest 9.1.1, uv 0.11.31, `sys.platform == "linux"`.
- **Selection gate before the run** (dry run): `index_sha256` equal to the Windows pass; 6697 selected, 1125 deselected, 7822 collected; the node digest set identical to the Windows subrun's (6697 of 6697), including all 56 platform nodes.
- **Run**: profile `20261016T005922-418-043002`, subrun `20261016T005948-442-35ead5`, platform `linux`, verdict **pass**, exit 0, 6656 passed, 41 skipped, 0 failed, records COMPLETE, 185.83 s. Qualifications recorded by the runner on Linux: `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported` (the Windows job-object guard has no Linux counterpart); they are qualifications, not failures.
- **Node accounting receipt** (`11-node-accounting.md`, SHA-256 `{wsl_receipt}`): all 56 required nodes ran on WSL; 53 passed; 3 skipped by Windows-only guards (Windows DACL evidence, Windows case folding of the `os.name` default policy, Windows-only explicit unlock); 0 failed; 0 missing. Against the Windows pass (54 passed, 2 skipped), the two POSIX-only nodes skipped on Windows passed on WSL and the three Windows-only nodes that passed on Windows are skipped on WSL: every node of the set executed on at least one platform and none failed anywhere.
- **Preparation defects, corrected and retained**: the first prepared patch was cut against `origin/main` (b27e99a, after PR #359) instead of the pin and did not apply to the clone (aborted attempt in `run-20261016T005423Z`, nothing applied); and the first frozen sync omitted the dev extra, so the first dry run could not collect. Both are in the evidence folder.

**Disposition.** The evidence above is what ADR-020 asks for at a commit: the triggered platform nodes executed on real WSL in an independent environment against the exact candidate index, with a node accounting receipt, and nothing failed. It is recorded here for the operator's and Codex's acceptance; this record does not grant it, and a documentation-only waiver was not inferred. The full WSL pre-finalize run remains a separate, independently applicable requirement that this focused receipt does not satisfy.

### R2 disposition: the authoring tools are filed in this bundle

The operator decided on 2026-10-16 to file the tools under `tools/` in this bundle rather than record an exception. Nine scripts were copied from the sealed packets; the only edits are `# pragma: allowlist secret` on the seventeen lines that hold recorded SHA-256 constants (the secret-scan hook's documented false-positive marker), one ruff E741 rename (`l` to `lld_status` in `apply_review_fixes.py`) and one ruff F401 removal (an unused `PageBreak` import in `build_corrections.py`); `apply_consolidated_update.py` (this update) is new. Ruff passes on the whole repository with them; the secret-scan hook command passes on them. The filed builder reproduced all five editions byte for byte from this bundle and the archived baselines on 2026-10-16 (HLD `52c35442...`, LLD `3fb89935...`, Test Strategy `21ab8cac...`, Roadmap `9d3f858e...`, Guardrails `88f461b6...`), so the recorded hashes are reproducible from the repository alone with the recorded tool versions and fonts. The packet copies keep their sealed identities (table in the revision section); the filed identities are:

| Filed tool | SHA-256 |
|---|---|
{tool_rows}

### Live work record

Issues #360 and #363 were updated on 2026-10-16 under the operator's per-issue approval, each with the exact text drafted and verified equal after the edit (#360 updated {after360}: five-document scope, both 2026-10-16 profile runs with their identities, current sizes, candidate digests, dated history; #363 updated {after363}: title and body consistent with five integrate-or-retire decisions and Tirith as an optional candidate, not adopted). The applied texts are in the third packet.

### Status after this update

The candidate is no longer frozen: this update changes the staged inventory (tools filed; this record, the bundle README, the correction map and the docs index edited), so a new candidate identity is recorded with the third packet, outside this file. The Windows and WSL results above are attributed to `{FROZEN}`; the delta since then adds scripts that no test imports and prose, and its dry-run selection is recorded in the third packet for comparison. The filing commit's own hooks, run from the scoped environment, are the binding run for whatever is committed. Held for the operator: the one-commit `check-added-large-files` exception for the four named PDFs, the commit itself, and the ADR-020 acceptance of the WSL evidence; push, PR and merge follow their own decisions.
"""
t = record.read_text(encoding="utf-8")
record.write_text(t.rstrip("\n") + "\n" + gate_section.rstrip("\n") + "\n", encoding="utf-8", newline="\n")

# ---- bundle README -----------------------------------------------------------------------------------------
new_tools = """## Authoring tools (filed in `tools/`, R2 disposition of 2026-10-16)

The build and validation tools are in [`tools/`](tools/). The checkpoint 3 review (R2) found that a rebuild procedure resting on scripts held only in sealed packets did not meet the evidence policy's contributor-accessibility rule, and the operator chose on 2026-10-16 to file the tools rather than record an exception. They are the packet scripts with `# pragma: allowlist secret` on the lines that hold recorded SHA-256 constants, one ruff rename and one unused-import removal; their filed identities, and the sealed packet identities they derive from, are in the validation record. On 2026-10-16 the filed builder reproduced all five editions byte for byte from this bundle and the archived baselines.

| Tool | Purpose |
|---|---|
| `build_corrections.py` | Assembles HLD, LLD and Test Strategy from the archived baselines and this bundle; renders the Roadmap from Markdown; fixed PDF creation date |
| `build_guardrails_v15.py` | Wrapper over the builder for Guardrails v1.5 (cover only; bodies from the Plan 12.2 bundle) |
| `validate_corrections.py` | Manifest, page-count, carried-text, predecessor-coverage, label/footer and artifact checks |
| `contact_sheets.py` | Renders every page (Poppler) into contact sheets for review |
| `author_corrections.py`, `apply_review_fixes.py`, `apply_checkpoint3_fixes.py`, `apply_consolidated_update.py` | The asserted `replace` edits that produced the sources from the sealed Plan 12.2 bodies, then the review, checkpoint 3 and post-gate corrections |
| `write_validation_record.py`, `compose_validation_record.py` | Generate and compose the mechanical parts of `validation-record.md` |

The build manifests, validation JSON, contact sheets, text extracts, check and gate logs, WSL evidence and the ledger of rulings stay in three sealed packets under `C:\\worktrees\\optimus-cost-agent-worktrees\\_handoff\\` on the operator's workstation: `2026-10-15-capability-evidence-correction` (37 payloads; `SHA256SUMS.txt` SHA-256 `ed690972898d21b48352b8f74b811a2dd4f36423220cda5fd1a91f47cc937996`), `2026-10-16-capability-evidence-correction-supplement` (59 payloads; `fdbf972f35b04901cf6627ce7ccf2d3da2aba776e5f844a5814d3fdf5063637e`) and `2026-10-16-capability-evidence-correction-gates` (`GATES_SEAL_PENDING`). The first two are unchanged. Raw logs and contact sheets stay out of the repository under the evidence policy; the record in this bundle carries the compact summary a reviewer needs, and the tools make the editions reproducible.

## Rebuilding

From a checkout of this candidate (or the commit that files it), with Python 3.14, reportlab 5.0.0, pypdf 6.10.2 and the Windows Arial fonts, run from the checkout root:

```
python docs/sources/capability-evidence-correction/tools/build_corrections.py . <out-dir>
python docs/sources/capability-evidence-correction/tools/build_guardrails_v15.py . <out-dir>
python docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
python docs/sources/capability-evidence-correction/tools/contact_sheets.py <out-dir> <sheets-dir>
```

The product code at the inspected pin `91fd64ac78025efe1076bddb106ff89e6adb2030` is read only by the record writer's `git rev-parse` blob checks; the PDFs read no product code. The builder fixes the PDF creation date, so the same tools, fonts and sources reproduce the recorded hashes. A rebuild with different inputs changes bytes and needs a new validation record and a new rendered review. Never commit a rebuilt PDF over a filed edition.

"""
replace_section(readme, "## Build tools: recorded limitation, not a reproducible build", "## Work record", new_tools)
rep(readme,
    "#360's created text describes a four-document scope, says Guardrails v1.4 is not revised and that only the documentation tests ran; checkpoint 3 (R3) requires the live issue to carry the five-document scope and the actual gate state. The update text is drafted in the supplemental packet (`issues/issue-360-update.md`) and applying it is an operator-approved external write. Issue text as created for #360:",
    f"#360 was updated on 2026-10-16 ({after360}) under the operator's approval to the five-document scope, the actual gate state and the candidate identities (checkpoint 3, R1 and R3); #363 was corrected the same day ({after363}) so that Tirith is an optional candidate, not adopted (R5). The applied texts are in the third packet. Issue text as created for #360 on 2026-10-15:")
rep(readme,
    "Checkpoint 3 (Codex, 2026-10-16) requested changes; this revision answers them and returns to the same checkpoint, not a new one. The pre-commit runner, the ast-grep gate and the commit-profile hook have not passed on this host (validation record); the commit remains held until the environment is repaired under the operator's authority and the gates are rerun against the final candidate.",
    "Checkpoint 3 (Codex, 2026-10-16) requested changes; the revision and this post-gate update answer them and return to the same checkpoint, not a new one. On 2026-10-16, from a scoped pre-commit environment, the ast-grep gate and the commit profile passed on Windows against the frozen candidate `005cdab0...`, and the commit profile passed on real WSL with all 56 platform nodes accounted for; only `check-added-large-files` fails, on the four PDFs over 500 KB (validation record, gate-rerun section). The 2026-10-15 failures stand as dated history. The commit remains held for the operator's file-size decision and ADR-020 acceptance of the WSL evidence.")

# ---- correction map and docs index --------------------------------------------------------------------------
rep(bundle / "correction-map.md",
    "it commissioned no product suite, live run or activation and claims no new full-suite, coverage or live result.",
    "it commissioned no product suite, live run or activation and claims no new full-suite, coverage or live result. The authoring tools are filed in `tools/` (checkpoint 3 R2 disposition, 2026-10-16); the gate rerun and WSL evidence for the frozen candidate are in the validation record.")
rep(repo / "docs" / "README.md",
    "| Sources, correction map and validation record for HLD v2.20, LLD v2.43, Roadmap v11 and Test Strategy v1.9, and the Guardrails v1.5 cover |",
    "| Sources, authoring tools, correction map and validation record for HLD v2.20, LLD v2.43, Roadmap v11 and Test Strategy v1.9, and the Guardrails v1.5 cover |")
print("consolidated update applied")
