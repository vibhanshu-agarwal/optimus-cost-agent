"""Apply the Codex checkpoint 3 corrections R1-R5 (review of 2026-10-16, SHA-256 a0811167...29f2) to the
correction bundle sources, the correction map, the bundle README and the docs index.

Every edit is an asserted exact replacement (exactly one match) so the diff is the list below.
Usage: apply_checkpoint3_fixes.py REPO_ROOT
"""
from __future__ import annotations

import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
bundle = repo / "docs" / "sources" / "capability-evidence-correction"
src = bundle / "sources"

COMMIT_PROFILE = (
    "the coverage-free commit-profile hook (`run_profile --profile commit`) selected a broad fallback of 6697 tests "
    "and failed on this host's unprovisioned ast-grep hook environment (6659 passed, 37 skipped, 1 warning, 1 error, exit 1), "
    "and it emitted the platform obligation `wsl-platform: next checkpoint`, which is undischarged"
)


def replace(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    assert n == count, f"{path.name}: expected {count} match(es) for {old[:70]!r}, found {n}"
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


# R1: HLD section 15 evidence anchors
replace(
    src / "hld-15-capability-status.md",
    "Historical passes are not transferred to `91fd64a`: this correction reran only the documentation checks and commissioned no product suite, live run or activation.",
    "Historical passes are not transferred to `91fd64a`. At the filing state this correction's documentation checks passed; "
    + COMMIT_PROFILE
    + ". The exact results are in the validation record filed with the sources. No new full-suite, coverage, live-qualification or activation result is claimed, and no product suite, live run or activation was commissioned.",
)

# R1: Test Strategy section 15.7
replace(
    src / "test-15-context-evidence.md",
    "All of these are historical measurements at their stated pins, not measurements at 91fd64a; this correction reran only the documentation checks.",
    "All of these are historical measurements at their stated pins, not measurements at 91fd64a. At the filing state of this correction the documentation checks passed; "
    + COMMIT_PROFILE
    + " (see §16 and the validation record). No new full-suite, coverage, live-qualification or activation result is claimed.",
)

# R1: Test Strategy section 16 intro, the 111-deselection qualification and a row for the actual run
replace(
    src / "test-16-capability-status.md",
    "this correction ran only the documentation checks (`tests/unit/docs`), so the sealed cf9bb9d runs remain the latest full-suite evidence cited.",
    "this correction's documentation checks (`tests/unit/docs`) passed, and the coverage-free commit-profile hook ran a broad fallback that failed on the host's unprovisioned ast-grep environment (row below, retained as failed). The sealed cf9bb9d runs therefore remain the latest full-suite evidence cited; no new full-suite, coverage, live-qualification or activation result is claimed.",
)
replace(
    src / "test-16-capability-status.md",
    "| Default marker selection excludes the 111 live-tier tests; a clean candidate at that pin only |",
    "| The 111 deselected tests are those the default marker selection excludes (live-dependency and other marked tiers); a clean candidate at that pin only |",
)
replace(
    src / "test-16-capability-status.md",
    "| Retained as failed; its walker violation and two frozen-lane regressions were corrected before `final-gate-2` |\n",
    "| Retained as failed; its walker violation and two frozen-lane regressions were corrected before `final-gate-2` |\n"
    "| Commit-profile hook at the filing state (§8A commit cadence) | `python -m tools.testing.run_profile --profile commit` (coverage-free) | Product source `91fd64a` with the staged documentation candidate; Windows; 2026-10-15 | Selected 6697 (`fallback=broad`: a documentation-only change has no mapped tests), deselected 1125; 6659 passed, 37 skipped, 1 warning, 1 error; exit 1; verdict failed; 9:25 | The error is `test_real_sink_module_passes_the_gate`, which by design fails explicitly when the configured ast-grep hook environment is not provisioned on the host; retained as failed, not reclassified; the run emitted the obligation `wsl-platform: next checkpoint`, undischarged; coverage-free, so no coverage value exists for the pin |\n",
)

# R4: Roadmap v11 - Phase 1 components versus the Phase 1 release gate
replace(
    src / "roadmap-v11.md",
    "| Phase 1: Python local agent and Optimus Gateway | Implemented and offline-verified; several capabilities remain inactive or deferred (HLD v2.20 §15) |",
    "| Phase 1: Python local agent and Optimus Gateway | Components implemented and offline-verified; several capabilities remain inactive or deferred (HLD v2.20 §15); the Phase 1 release gate is not established by this correction (§4) |",
)
replace(
    src / "roadmap-v11.md",
    "This correction schedules or delivers no phase. The HLD's Phase 1 release gate (agent process holds only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`) remains the precondition for any later phase.",
    "This correction schedules or delivers no phase. The HLD's Phase 1 release gate (agent process holds only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`) remains the precondition for any later phase; whether it is satisfied is not established by this correction (§4).",
)
replace(
    src / "roadmap-v11.md",
    "| Phase 1 architecture and release gate | Implemented; verified as stated in HLD v2.20 §15 and Test Strategy v1.9 §16 |\n",
    "| Phase 1 architecture: loopback Gateway, typed tools, usage ledger, guardrails, bounded loops, skills, Context Engine | Implemented components; offline-verified at cf9bb9d and unit-tested at the pin, with the inactive and deferred items stated in HLD v2.20 §15 and Test Strategy v1.9 §16 (Context Engine production attachment and trusted-snapshot enforcement inactive; live and real-client qualification UNRUN) |\n"
    "| Phase 1 release gate (HLD §10.C: mandatory before any later phase) | Approved requirement whose definition exists; its satisfaction is not established by this correction: the live credential-scope, route and real-client qualifications it depends on remain UNRUN (Test Strategy v1.9 §16; issue #237), and no acceptance record names it as passed. This table is not a Phase 1 operational-release approval and grants no permission to start Phase 2 or Phase 3 |\n",
)

# R1: correction map classification note
replace(
    bundle / "correction-map.md",
    "this correction reran only `tests/unit/docs` and commissioned no product suite, live run or activation.",
    "at the filing state this correction's documentation checks (`tests/unit/docs`) passed and the coverage-free commit-profile hook's broad fallback failed on the host's unprovisioned ast-grep environment, emitting the undischarged obligation `wsl-platform: next checkpoint` (validation record); it commissioned no product suite, live run or activation and claims no new full-suite, coverage or live result.",
)

# R3: correction map - pre-expansion position labelled, current scope stated
replace(
    bundle / "correction-map.md",
    "Guardrails v1.4 is not revised (see §5).",
    "Guardrails v1.4 was first held (the pre-expansion position in §5) and is now succeeded by Guardrails v1.5, which replaces only the cover page (§5 and the Guardrails section of `validation-record.md`); v1.4 moves to `docs/archive/` unchanged.",
)
replace(
    bundle / "correction-map.md",
    "## 5. Held scope\n\nGuardrails v1.4 was read for consistency and is not revised in this batch.",
    "## 5. Guardrails scope: pre-expansion position and confirmed expansion\n\n**Pre-expansion position (written 2026-10-15, superseded the same day; retained as written).** Guardrails v1.4 was read for consistency and is not revised in this batch.",
)

# R5: F3 - Tirith is an optional implementation choice, not a missing requirement
replace(
    bundle / "correction-map.md",
    "| F3 | Named evaluation and architecture tooling (PyTestArch, maintainability index, DeepEval, Ragas, PyRIT, Tirith) has no dependency, import or test; the requirements remain intended | None exact; HARDENING-TRACK-ANALYSIS-ORACLE (#316) is the nearest existing track | #363 (created 2026-10-15): integrate or retire each named tool; moving the evaluation tools to #316 stays an operator option recorded in the issue |",
    "| F3 | Named evaluation and architecture tooling (PyTestArch, maintainability index, DeepEval, Ragas, PyRIT) has no dependency, import or test; those requirements remain intended and not established. Tirith is distinct: LLD §12A and Guardrails §4.3 define the contract as `CommandSafetyValidator`, \"satisfiable by Tirith or an equivalent validator\", with no hard dependency on any one implementation, and an in-process `CommandSafetyValidator` with unit tests exists at the pin (`optimus/guardrails/command_safety.py`); the absence of the Tirith package alone is therefore not an unmet requirement | None exact; HARDENING-TRACK-ANALYSIS-ORACLE (#316) is the nearest existing track | #363 (created 2026-10-15): integrate or retire each of the five named tools; moving the evaluation tools to #316 stays an operator option recorded in the issue. Tirith's disposition is \"optional candidate, not adopted\": evaluate the implemented validator against the accepted behavioural contract (LLD §12A, Guardrails §4) and record any demonstrated gap as its own item; nothing requires adding Tirith or removing its labelled illustrative references. #363's created text predates this disposition; correcting it is an operator-approved external write (text drafted in the supplemental packet) |",
)

# R2 and revision provenance: bundle README
readme = bundle / "README.md"
replace(
    readme,
    "Fable 5.1 reviews and a consolidated Codex review are the plan's three checkpoints. The editions are reviewed local filing candidates:",
    "Fable 5.1 reviews and a consolidated Codex review are the plan's three checkpoints. The Codex checkpoint 3 review (`checkpoint-3-documentation-review.md`, 2026-10-16, SHA-256 `a0811167b6b0d4f3e70056a9391618d16355ebbe5a5fce7b70fe7fd195a729f2`, kept outside the repository) requested five corrections, R1-R5; this revision applies them and the HLD, Test Strategy and Roadmap editions were rebuilt (the revision section of [`validation-record.md`](validation-record.md) lists every post-seal change). The editions are reviewed local filing candidates:",
)
text = readme.read_text(encoding="utf-8")
start = text.index("## Kept only in the correction packet")
end = text.index("## Work record")
new_section = """## Build tools: recorded limitation, not a reproducible build

The build and validation tools are not in the repository. The evidence policy (`docs/governance/evidence-and-local-artifact-policy.md`) requires that no build, test, release or review decision depend on an untracked file. This bundle meets that for the **claims**: every edition's identity, page map and check result is recorded here with hashes, and a reviewer needs nothing outside the repository to verify them against the filed PDFs. It does **not** meet it for **rebuilding**: a contributor cannot regenerate the PDFs from the repository alone. That is a recorded limitation of this candidate, following the Plan 12.2 precedent (the operator's 2026-10-05 choice to keep hash-heavy records and authoring scripts outside the secret-scan and lint scope), and not a claim of a repository-reproducible build. Filing the tools under this bundle (`tools/`) would remove the limitation; it is an authoring-tool scope expansion that needs the operator's decision and is not done here.

The tools, each identified by SHA-256 so that a copy obtained from the operator can be verified:

| Tool | Purpose | SHA-256 |
|---|---|---|
| `build_corrections.py` | Assembles HLD, LLD and Test Strategy from the archived baselines and this bundle; renders the Roadmap from Markdown; fixed PDF creation date | `4721ec73e0eacc8d5e45a7b488e39d6aaa9f4c7625c801ac7b4f57d0633340b3` |
| `build_guardrails_v15.py` | Wrapper over the builder for Guardrails v1.5 (cover only) | `654a03c228cfe199587bbe78e217e09933a56c7d92ea59ec4d8d4d41f34e47fd` |
| `validate_corrections.py` | Manifest, page-count, carried-text, predecessor-coverage, label/footer and artifact checks | `5efc7821376c26ad7590cb1be9dddb31aa3c5aad32ef1a5d6bf29b2379df894e` |
| `contact_sheets.py` | Renders every page (Poppler) into contact sheets for review | `078b9cb3c0e68d6f69d99b4f4d5888166e4b06e9199363630e67128808f1e9ae` |
| `author_corrections.py`, `apply_review_fixes.py`, `apply_checkpoint3_fixes.py` | The asserted `replace` edits that produced the sources from the sealed Plan 12.2 bodies, then the review and checkpoint 3 corrections | `e0268c5adc3d26e2a782d3d800fb7b7018396425ea137acf3c4f1d2db6e472eb`, `2fa3cf6c0a5129cd068748a039075af5d7d9f953777f6dfdfc973578cbf70fd1`, recorded in the supplemental packet |
| `write_validation_record.py` | Generates the mechanical part of `validation-record.md` from the build outputs | `cd10853bd2cfad8842cfc53ef362c3fed6a4bbdd8440bea8a3ffa4d3f9387ae8` |

They are held, with the build manifests, validation JSON, contact sheets, text extracts, check logs and the ledger of rulings, in two sealed packets under `C:\\worktrees\\optimus-cost-agent-worktrees\\_handoff\\` on the operator's workstation: the original `2026-10-15-capability-evidence-correction` (37 payloads; `SHA256SUMS.txt` SHA-256 `ed690972898d21b48352b8f74b811a2dd4f36423220cda5fd1a91f47cc937996`, unchanged) and the supplemental `2026-10-16-capability-evidence-correction-supplement` (the Guardrails v1.5 build records, the checkpoint 3 corrections, the rebuilt editions' records and the final checks; its `SHA256SUMS.txt` SHA-256 is `SUPPLEMENT_SEAL_PENDING`). The validation record in this bundle carries the compact summary a reviewer needs.

## Rebuilding

A rebuild needs four inputs, and the first two are different identities:

1. **Product code at the inspected pin** `91fd64ac78025efe1076bddb106ff89e6adb2030`: used only by the record writer's `git rev-parse` blob checks; the PDFs read no product code.
2. **This bundle at the candidate's revision.** The bundle is not at `91fd64a` (that commit predates it); it is the staged candidate on branch `agent/claude/plan12-capability-evidence-correction`, identified by the SHA-256 of each source file in the revision section of `validation-record.md` and, once committed, by that commit.
3. **The archived baselines and predecessors** in `docs/archive/` (v2.18, v2.41, v1.7, v1.3 baselines; v2.19, v2.42, v1.8, v10, v1.4 predecessors), all in the repository.
4. **Tooling**: Python 3.14 with reportlab 5.0.0 and pypdf 6.10.2, the Windows Arial fonts, and the scripts above; Poppler 25.07.0 for review renders.

Then, from a directory holding the scripts (never inside a sealed packet): `python build_corrections.py <checkout-root> <out-dir>`, `python build_guardrails_v15.py <checkout-root> <out-dir>`, `python validate_corrections.py <checkout-root> <out-dir>`, and render the pages for review. The builder fixes the PDF creation date, so the same tools, fonts and sources reproduce the recorded hashes (the 2026-10-16 rebuild reproduced LLD v2.43 `3fb89935...` byte for byte while the HLD, Test Strategy and Roadmap changed as intended). A rebuild with different inputs changes bytes and needs a new validation record and a new rendered review. Never commit a rebuilt PDF over a filed edition.

"""
text = text[:start] + new_section + text[end:]
readme.write_text(text, encoding="utf-8", newline="\n")
replace(
    readme,
    "Filed locally as reviewed candidates in the worktree branch `agent/claude/plan12-capability-evidence-correction`; the plan's authorization covers preparation and local filing readiness.",
    "Filed locally as reviewed candidates in the worktree branch `agent/claude/plan12-capability-evidence-correction`; the plan's authorization covers preparation and local filing readiness. Checkpoint 3 (Codex, 2026-10-16) requested changes; this revision answers them and returns to the same checkpoint, not a new one. The pre-commit runner, the ast-grep gate and the commit-profile hook have not passed on this host (validation record); the commit remains held until the environment is repaired under the operator's authority and the gates are rerun against the final candidate.",
)
# R3: work record paragraph - the live issue must describe the five-document scope
replace(
    readme,
    "Issue text as created for #360:",
    "#360's created text describes a four-document scope, says Guardrails v1.4 is not revised and that only the documentation tests ran; checkpoint 3 (R3) requires the live issue to carry the five-document scope and the actual gate state. The update text is drafted in the supplemental packet (`issues/issue-360-update.md`) and applying it is an operator-approved external write. Issue text as created for #360:",
)

# R3: docs index - merged predecessors versus staged successors
replace(
    repo / "docs" / "README.md",
    "v1.5 replaces only the v1.4 cover, recording the filed D7 provenance (ADR-018) and the merged, corrected companion editions (2026-10-15; local filing candidate); the body is unchanged",
    "v1.5 replaces only the v1.4 cover, recording the filed D7 provenance (ADR-018), the merge of the v2.19/v2.42/v1.8 companions (PR #276) and their corrected successors v2.20/v2.43/v1.9 and Roadmap v11, which are local filing candidates like v1.5 itself (2026-10-15); the body is unchanged",
)

print("checkpoint 3 fixes applied")
