"""Consolidated update of 2026-10-16 after Codex's checkpoint 3 gates-candidate review: the corrected platform
node accounting (1,629 nodes), the bounded WSL remainder run, and the rebuild-procedure correction (P2).
Asserted exact replacements plus one appended record section; the superseded WSL text is kept as dated history.

Usage: apply_platform_accounting_update.py REPO_ROOT WORKSPACE REBUILD_VERIFY_DIR
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
ws = Path(sys.argv[2]).resolve()
verify = Path(sys.argv[3]).resolve()
bundle = repo / "docs" / "sources" / "capability-evidence-correction"
record = bundle / "validation-record.md"
readme = bundle / "README.md"
GATES_REVIEW = "8103ec89c8fb55683fb5878bf73cd6ce2e7b9b0f23299583735f4b6ca10858d8"  # pragma: allowlist secret
FROZEN = "005cdab0941ad3f0f251b9d11e55ef96e0a58b0a0bb53ba6b0c8e14bac3bffa6"  # pragma: allowlist secret
PLATFORM_ALL = "a0bb19ee4613abf3eaa908ec82a6792bcb1bb4eb690abf2f0dea7a06aa3be35e"  # pragma: allowlist secret
PLATFORM_MISSING = "3663505e5258293555cc48420f72a133d1ea8bbe8d964a3ea9c4cfd79ae4a44f"  # pragma: allowlist secret
CODEX_MISSING = "a19f4c7f167e1f8bd97d4bf1b1302b978f0940d9ffcbe89e2c3b312c7adfd11b"  # pragma: allowlist secret


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


acct = (ws / "accounting" / "platform-accounting-005cdab0.md").read_text(encoding="utf-8")
module_table = acct[acct.index("| Module |"):].rstrip("\n")
remainder = ws / "wsl" / "remainder-20261016T051324Z"
receipt_sha = sha(remainder / "09-node-accounting.md")

# ---- validation record: supersede the 56-node text, keep it, append the corrected accounting ----------------
rep(record,
    "Every commit-profile run of this candidate (2026-10-15 and both of 2026-10-16) emitted the obligation; the trigger is `fallback:broad`. The required set is the 56 platform-tagged nodes",
    "**[Superseded 2026-10-16 by the corrected accounting section below, kept as dated history: this paragraph derived the required set from six modules and 56 nodes; the manifest tags 33 modules and the complete set is 1,629 nodes.]** Every commit-profile run of this candidate (2026-10-15 and both of 2026-10-16) emitted the obligation; the trigger is `fallback:broad`. The required set is the 56 platform-tagged nodes")
rep(record,
    "**Disposition.** The evidence above is what ADR-020 asks for at a commit:",
    "**Disposition (superseded; see the corrected accounting section).** The evidence above is what ADR-020 asks for at a commit:")

section = f"""
## Corrected platform accounting, WSL remainder and rebuild-procedure correction (2026-10-16)

Codex's review of the gates candidate (`checkpoint-3-gates-candidate-review.md`, SHA-256 `{GATES_REVIEW}`, kept outside the repository) verified the inventory `3bdf0c19...`, the staged diff `eb79c39b...` and all three seals, and requested two corrections. Both are recorded here. No PDF changed.

### P1: the platform set is 1,629 nodes, not 56

The WSL receipt in the section above was derived from a hand-maintained list of six modules; `tests/profiles.toml` tags **33** modules `platform`. The required set was re-derived from the candidate's complete default collection (7,822 nodes, `pytest --collect-only` on the candidate) with the repository's own `load_manifest` and `classify_nodes`, and every node was then matched to the run records by its digest (`sha256(nodeid)`, the identity the records use; labels are display text and some are sanitized). The result equals Codex's independently derived lists node for node.

| Scope | Nodes | Detail |
|---|---:|---|
| Full platform-tagged set | 1,629 | 918 core, 42 gates, 668 proc, 1 audit-sealed; 33 modules; sorted list SHA-256 `{PLATFORM_ALL}` |
| Present in the WSL commit-profile subrun `20261016T005948-442-35ead5` | 970 | 937 passed, 33 skipped, 0 failed |
| Present in the Windows commit-profile subrun `20261015T190827-42260-d67065` | 970 | 951 passed, 19 skipped, 0 failed |
| Absent from both (the commit profile's broad fallback adds core and gates only) | 659 | 658 proc, 1 audit-sealed; 12 modules; sorted list SHA-256 `{PLATFORM_MISSING}` (Codex's `checkpoint3-platform-missing.txt`, same 659 node ids, hashes as `{CODEX_MISSING}` over its own line ordering) |

Per module (WSL and Windows commit-profile subruns, passed / skipped / failed / absent):

{module_table}

No existing WSL evidence was eligible for the 659: no Linux run records exist on this host for any clone, and the only full WSL run (`wsl-full-1`) is at cf9bb9d. The proc and audit-sealed tiers were not excluded; a bounded real-WSL run of exactly those nodes was made under the operator's go-ahead.

### Bounded WSL run of the 659-node remainder

- **Where**: the same faithful clone `/root/plan12-doccorr-wsl-005cdab0` (WSL Ubuntu-24.04, kernel 6.18.54.1-microsoft-standard-WSL2) at HEAD `91fd64a`, whose `git ls-files --stage` SHA-256 was re-verified equal to `{FROZEN}` before the run; the same independent frozen environment (CPython 3.14.6, pytest 9.1.1, uv 0.11.31; the Windows `.venv` never used).
- **What**: the 659 node ids (`04-nodes.txt`, SHA-256 `{PLATFORM_MISSING}`), collected first (659 collected, exit 0), then run serially, coverage-free, with the repository's run-context recording active: `pytest --no-cov -q -p no:cacheprovider -rsfE @04-nodes.txt`.
- **Result**: pytest `524 passed, 135 skipped in 143.35s (0:02:23)`, exit 0. Run record `20261016T051327-459-82bf7b`: platform `linux`, checkpoint `terminal`, completeness `COMPLETE`, exit 0, selected 659, deselected 0, collection and recording errors 0; 659 node entries and 1,835 phase entries read with zero refused rows. This is a plain pytest run with run-context records, not a profile run: it carries no `test-profile` verdict line and no obligations field.
- **Accounting by digest** (receipt `09-node-accounting.md`, SHA-256 `{receipt_sha}`): 516 passed with all three phases recorded; 135 skipped, every skip a Windows-only guard (25 "MAIN-5 guard is Windows-only", 20 "native job ownership is Windows-only", 4 "load-overlap repeats are Windows-only", 3 "job containment is the Windows path", and single-node reasons such as the CP1252 omission needing a real CP1252 Windows process, the Windows snapshot script and the Windows `taskkill` tree-kill path; all 82 nodes of `test_main5_guard.py` skip on Linux); 0 failed; 0 missing; and 8 nodes passed by pytest's count whose call phase is absent from this run's record. Those eight are all in `tests/unit/tools/test_run_context_lifecycle.py` and exercise the recorder itself: each swaps in a scratch `RunContext` for the duration of its body, so its own call phase is written to the scratch context, not to the run's record; setup and teardown are recorded and passed, and pytest's own count (516 + 8 = 524 passed) reconciles. They are reported as recorded, not reclassified.
- **Combined**: every one of the 1,629 platform-tagged nodes now has a WSL execution record on the exact candidate index: 1,453 passed (937 + 516), 168 skipped by Windows-only guards (33 + 135), 8 passed per pytest with the call phase recorded in a scratch context, 0 failed, 0 missing. The 56-node receipt above stands as dated history of an incomplete derivation.

**Disposition.** The obligation `wsl-platform: next checkpoint` now has evidence for the complete triggered platform set on real WSL in an independent environment against the exact candidate index, with node accounting receipts for both runs. It is recorded for the operator's and Codex's acceptance under ADR-020; this record grants nothing and infers no waiver. The full WSL pre-finalize run remains a separate requirement that these focused receipts do not satisfy.

### P2: the published rebuild sequence validated only Guardrails

Both builders write `build-manifest.json`; the previous README sent them to one output directory and ran the validator once, so a reader following it would validate only the Guardrails manifest. The README now uses separate output directories, validates each, renders each into its own contact-sheet directory and names the renderer's prerequisites (Pillow and Poppler). The corrected procedure was verified on 2026-10-16 outside the candidate and the sealed packets (`C:\\worktrees\\optimus-cost-agent-worktrees\\_rebuild-verify-2026-10-16`, system Python 3.14.4, reportlab 5.0.0, pypdf 6.10.2, Pillow 12.3.0, Poppler 25.07.0): the four-document build validated PASS with `hld`, `lld`, `test` and `roadmap` in both its manifest and its validation report; the Guardrails build validated PASS with `guardrails`; all five output hashes equal the staged PDFs; 17 and 3 contact sheets rendered, pdftoppm exit 0. No filed PDF was replaced. The stale README sentence that said the tools are not in the repository is removed.

### Labels corrected

- The dry-run selection recorded with the previous update (`checks/dry-run-20261016T011326-57148-b2b949`) shows that the staged state after filing the tools selects the same 6,697 nodes as the frozen pass; its binary-diff digest `962d1df6...` is that intermediate state's, and the candidate Codex reviewed is `eb79c39b...`. Identical node sets demonstrate unchanged selection, not execution on changed source; the filing commit's hooks remain the binding run.
- Issue #360's live text (updated 2026-10-16) names the frozen candidate `005cdab0...` and the checkpoint state at that time; it is a dated snapshot, not a completion record for the current inventory.

### Status after this update

This update changes the staged inventory again (this record, the bundle README and the update script `tools/apply_platform_accounting_update.py`), so a new candidate identity is recorded with the fourth evidence packet, outside this file; the three earlier seals are unchanged. Held for the operator: ADR-020 acceptance of the WSL evidence above, the one-commit `check-added-large-files` exception for the four PDFs over 500 KB, the commit itself in a shell with the scoped `PRE_COMMIT_HOME`, and push, PR and merge. Full WSL pre-finalize remains separate.
"""
t = record.read_text(encoding="utf-8")
record.write_text(t.rstrip("\n") + "\n" + section.rstrip("\n") + "\n", encoding="utf-8", newline="\n")

# ---- bundle README --------------------------------------------------------------------------------------------
rep(readme,
    "are kept in the correction packet, not in the repository (see below).",
    "are filed in `tools/` (see below); their sealed-packet copies are identified in the validation record.")
rep(readme,
    "and `2026-10-16-capability-evidence-correction-gates` (`1fdf44bfef3de9501877c24dd5c1e1e4d13df040c0932f78e56aa1297e43a6fc`). The first two are unchanged.",
    "`2026-10-16-capability-evidence-correction-gates` (`1fdf44bfef3de9501877c24dd5c1e1e4d13df040c0932f78e56aa1297e43a6fc`) and `2026-10-16-capability-evidence-correction-platform` (`PLATFORM_SEAL_PENDING`; the corrected platform accounting, the bounded WSL remainder run and the rebuild-procedure verification). The first three are unchanged.")
new_rebuild = """## Rebuilding

Prerequisites: Python 3.14 with reportlab 5.0.0, pypdf 6.10.2 and Pillow (12.3.0 was used); the Windows Arial fonts; Poppler 25.07.0 (`pdftoppm`, `pdftotext`) on `PATH` for rendering and text extraction. Both builders write a `build-manifest.json` and the validator reads the manifest of the directory it is given, so the four-document build and the Guardrails build need **separate output directories**, each validated and rendered on its own. From a checkout of this candidate (or the commit that files it), at the checkout root:

```
python docs/sources/capability-evidence-correction/tools/build_corrections.py . <out-four>
python docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-four>
python docs/sources/capability-evidence-correction/tools/build_guardrails_v15.py . <out-guardrails>
python docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-guardrails>
python docs/sources/capability-evidence-correction/tools/contact_sheets.py <out-four> <sheets-four>
python docs/sources/capability-evidence-correction/tools/contact_sheets.py <out-guardrails> <sheets-guardrails>
```

Expected: `<out-four>/document-validation.json` lists `hld`, `lld`, `test` and `roadmap` with status PASS; `<out-guardrails>/document-validation.json` lists `guardrails` with status PASS; the five PDFs hash equal to the filed editions (the builder fixes the PDF creation date, so the same tools, fonts and sources reproduce the recorded hashes; verified on 2026-10-16, see the validation record). The product code at the inspected pin `91fd64ac78025efe1076bddb106ff89e6adb2030` is read only by the record writer's `git rev-parse` blob checks; the PDFs read no product code. A rebuild with different inputs changes bytes and needs a new validation record and a new rendered review. Never commit a rebuilt PDF over a filed edition.

"""
replace_section(readme, "## Rebuilding", "## Work record", new_rebuild)
rep(readme,
    "and the commit profile passed on real WSL with all 56 platform nodes accounted for;",
    "and on real WSL the commit profile passed and a bounded run covered the remaining platform-tagged nodes, so all 1,629 platform-tagged nodes of the candidate's collection have WSL execution records (validation record, corrected accounting section);")
print("platform accounting update applied")
