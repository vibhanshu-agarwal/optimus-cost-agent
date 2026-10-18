"""Compose the revised validation record (2026-10-16): the generated mechanical record for the rebuilt
editions, the preserved Guardrails v1.5 section, and the checkpoint 3 revision section.

Usage: compose_validation_record.py REPO_ROOT WORKSPACE PACKET_TEXT_DIR G15_TOOLS_DIR
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
ws = Path(sys.argv[2]).resolve()
packet_text = Path(sys.argv[3]).resolve()
g15_tools = Path(sys.argv[4]).resolve()
bundle = repo / "docs" / "sources" / "capability-evidence-correction"
record = bundle / "validation-record.md"
tools = ws / "tools"
REVIEW_SHA = "a0811167b6b0d4f3e70056a9391618d16355ebbe5a5fce7b70fe7fd195a729f2"  # pragma: allowlist secret


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# 1. the Guardrails section of the current record, preserved with one custody sentence updated
current = record.read_text(encoding="utf-8")
g_start = current.index("## Guardrails v1.5: cover alignment")
guardrails = current[g_start:].rstrip("\n") + "\n"
old = (
    "They were produced after the correction packet was sealed and were handed to the operator (session notes folder "
    "`guardrails-v1.5/`) rather than written into the sealed packet; adding them to the packet with a new seal is the operator's call."
)
assert current.count(old) == 1
guardrails = guardrails.replace(
    old,
    "They were produced after the original correction packet was sealed and are held in the supplemental packet "
    "`2026-10-16-capability-evidence-correction-supplement` (revision section below); the original seal is unchanged.",
)

# 2. the generated mechanical record for the 2026-10-16 build, with the 2026-10-15 checks appended
tmp = ws / "validation-record.generated.md"
subprocess.run(
    [sys.executable, str(tools / "write_validation_record.py"), str(repo), str(ws / "build3"), str(ws / "sheets3"), str(tmp), str(ws / "checks.md")],
    check=True,
)
generated = tmp.read_text(encoding="utf-8")
generated = generated.replace(
    "# Validation record: capability and evidence correction (2026-10-15)\n",
    "# Validation record: capability and evidence correction (2026-10-15, revised 2026-10-16)\n\n"
    "This record was first written on 2026-10-15 and rewritten on 2026-10-16 after the Codex checkpoint 3 review; the successor table below is the "
    "current candidate (HLD, Test Strategy and Roadmap rebuilt on 2026-10-16; LLD unchanged). The 2026-10-15 identities that the review verified are "
    "listed in the revision section at the end, together with every change made after the original packet was sealed.\n",
    1,
)
generated = generated.replace(
    "This is an author review of all pages, not an independent external review.\n",
    "This is an author review of all pages, not an independent external review. The all-page review was performed on the 2026-10-15 editions; on 2026-10-16 "
    "the three rebuilt editions were rendered again and the pages whose text changed (revision section) were inspected; text-identical pages carry the 2026-10-15 review.\n",
    1,
)

# 3. changed pages: text of the rebuilt editions versus the sealed 2026-10-15 extracts
def pages(path: Path) -> list[str]:
    return path.read_text(encoding="latin-1").split("\f")


changed_rows = []
for stem, label in [
    ("Optimus-Cost-Agent-Architecture-v2.20", "HLD v2.20"),
    ("Optimus-Cost-Agent-Test-Strategy-v1.9", "Test Strategy v1.9"),
    ("Optimus-Architecture-Roadmap-v11", "Roadmap v11"),
    ("Optimus-Cost-Agent-LLD-v2.43", "LLD v2.43"),
]:
    before = pages(packet_text / f"{stem}.txt")
    after = pages(ws / "text3" / f"{stem}.txt")
    n = max(len(before), len(after))
    diff = [str(i + 1) for i in range(n) if (before[i] if i < len(before) else None) != (after[i] if i < len(after) else None)]
    changed_rows.append(f"| {label} | {len(before) - 1 if before and before[-1] == '' else len(before)} -> {len(after) - 1 if after and after[-1] == '' else len(after)} | {', '.join(diff) if diff else 'none'} |")

# 4. identities
succ = [
    ("Architecture (HLD) v2.20", "Optimus-Cost-Agent-Architecture-v2.20.pdf", "rebuilt (R1)", "6f2540cfce5e4f6363135a2fcb3b5f3671ef0de42332e3ee268a63e9174ebaf3"),  # pragma: allowlist secret
    ("LLD v2.43", "Optimus-Cost-Agent-LLD-v2.43.pdf", "unchanged; rebuilt byte-identical", "3fb89935201eb5947eff666a97431653d264ee482b8a5a8a6a4d229d4c8b7c27"),  # pragma: allowlist secret
    ("Architecture Roadmap v11", "Optimus-Architecture-Roadmap-v11.pdf", "rebuilt (R4)", "bcae299aa35e31cbf406e8e068b91d9fcf12ad2a88eefade8534edaddcba27ee"),  # pragma: allowlist secret
    ("Test Strategy v1.9", "Optimus-Cost-Agent-Test-Strategy-v1.9.pdf", "rebuilt (R1)", "758b0bf3199324b5f7bce3d4af7e7bb7ef5fa172effb1845e87ec19b2fa83360"),  # pragma: allowlist secret
    ("Guardrails v1.5", "Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.5.pdf", "unchanged; not rebuilt", "88f461b6e63c61f4677a80ac67e1f660422406a4bb6ebe8f9c84796ddca6b943"),  # pragma: allowlist secret
]
succ_rows = []
for name, fn, state, before in succ:
    p = repo / "docs" / fn
    import logging

    logging.disable(logging.CRITICAL)
    from pypdf import PdfReader

    succ_rows.append(f"| {name} | `{fn}` | {len(PdfReader(str(p)).pages)} | {p.stat().st_size:,} | `{sha(p)}` | `{before[:12]}...` | {state} |")

src_rows = []
for p in sorted(bundle.rglob("*")):
    if p.is_file() and p.name not in {"validation-record.md", "README.md"}:
        src_rows.append(f"| `{p.relative_to(bundle).as_posix()}` | `{sha(p)}` |")

tool_rows = []
for name in ["build_corrections.py", "validate_corrections.py", "contact_sheets.py", "author_corrections.py", "apply_review_fixes.py", "apply_checkpoint3_fixes.py", "write_validation_record.py", "compose_validation_record.py"]:
    tool_rows.append(f"| `{name}` | `{sha(tools / name)}` |")
tool_rows.append(f"| `build_guardrails_v15.py` | `{sha(g15_tools / 'build_guardrails_v15.py')}` |")

checks_rev = (ws / "checks-rev.md").read_text(encoding="utf-8").rstrip("\n")

revision = f"""## Revision after checkpoint 3 (2026-10-16)

The Codex checkpoint 3 review (`checkpoint-3-documentation-review.md`, SHA-256 `{REVIEW_SHA}`, kept outside the repository) returned **changes requested** on the 2026-10-15 candidate and verified its preservation facts: all five predecessors byte-identical, all five successor hashes as recorded, the original packet 37/37. It required five corrections, applied here as asserted exact replacements by `apply_checkpoint3_fixes.py`:

| Requirement | Where applied |
|---|---|
| R1 Execution claims agree with the retained failed commit-profile run; WSL obligation preserved; 111-deselection wording consistent | HLD §15 evidence anchors (`sources/hld-15-capability-status.md`); Test Strategy §15.7 and §16 intro, the full-suite row's limit and a new row for the commit-profile run (`sources/test-15-context-evidence.md`, `sources/test-16-capability-status.md`); `correction-map.md` §1; the 2026-10-15 checks table above (commit-profile row now names the obligation); this section. The issue #360 update is drafted, not applied (operator-approved external write) |
| R2 Rebuild procedure no longer depends silently on private files | `README.md` "Build tools: recorded limitation" and "Rebuilding": the limitation is stated as such, every tool is identified by SHA-256 (table below), and the candidate's source identity is distinguished from the product pin. Filing the tools in the repository is identified as an authoring-tool scope expansion for the operator's decision; not done |
| R3 Live work record and mutable wording agree with the five-document scope | `correction-map.md` §3 and §5 (pre-expansion position labelled; current scope stated); `docs/README.md` Guardrails row (merged predecessors distinguished from staged successors); `README.md` work record. The issue #360 scope/completion update is drafted, not applied |
| R4 Phase 1 components separated from the Phase 1 release gate | `sources/roadmap-v11.md` §1 and §4: implemented components with their bounded offline evidence in one row; the release gate as an approved requirement whose satisfaction is not established, with no later-phase permission |
| R5 Tirith is an optional implementation choice | `correction-map.md` §4 F3: Tirith given the disposition "optional candidate, not adopted"; the five other tools keep integrate-or-retire. The issue #363 correction is drafted, not applied |

Two inherited statements were deliberately left as they are, and are recorded here so the reviewer can object: the shared cover sentence "it was produced without running any product suite" (true of the editions' production; the commit-profile hook ran afterwards as a check on the filing state, and its result is now stated in §15/§16 and here), kept so that the LLD and Guardrails covers did not need a rebuild; and the Guardrails v1.5 cover's "have since been succeeded by" the corrected editions, which the version line on the same cover qualifies as a local filing candidate.

### Integrated candidate

| Document | File | Pages | Bytes | SHA-256 (2026-10-16) | SHA-256 before (2026-10-15) | State |
|---|---|---|---|---|---|---|
{chr(10).join(succ_rows)}

Predecessors: the five files in `docs/archive/` listed in this record (v2.19, v2.42, v10, v1.8 above; v1.4 in the Guardrails section) are byte-identical to origin/main and staged as `R100` moves. The original packet `2026-10-15-capability-evidence-correction` (`SHA256SUMS.txt` SHA-256 `ed690972898d21b48352b8f74b811a2dd4f36423220cda5fd1a91f47cc937996`) is unchanged.

Pages whose extracted text differs from the 2026-10-15 edition (pdftotext, page by page), and the page counts:

| Document | Pages before -> after | Changed pages |
|---|---|---|
{chr(10).join(changed_rows)}

### Candidate source identity

The bundle is not at the product pin `91fd64a` (that commit predates it). Until the filing commit exists, the sources are identified by these hashes; `README.md` is excluded because it carries the supplemental packet's seal hash, which in turn covers a copy of this record.

| Source file | SHA-256 |
|---|---|
{chr(10).join(src_rows)}

### Tools (held in the sealed packets, not in the repository)

| Tool | SHA-256 |
|---|---|
{chr(10).join(tool_rows)}

### Changes made after the original seal, in order

1. 2026-10-15: Guardrails v1.5 built and staged with v1.4 archived (operator-confirmed scope expansion); `sources/guardrails-v15-cover.md`, the Guardrails section of this record, `docs/README.md` and `README.md` updated.
2. 2026-10-15: issues #360-#363 created under per-issue operator approval; their numbers inserted in `README.md` (work record) and `correction-map.md` §4.
3. 2026-10-16: R1-R5 applied to the sources, map, bundle README and docs index; HLD v2.20, Test Strategy v1.9 and Roadmap v11 rebuilt; this record rewritten; the supplemental packet sealed.

### Evidence packaging

Supplemental packet `2026-10-16-capability-evidence-correction-supplement` under `C:\\worktrees\\optimus-cost-agent-worktrees\\_handoff\\`: the checkpoint 3 review copy, the tools above, the 2026-10-16 build manifest and validation JSON, the Guardrails v1.5 build manifest, validation JSON and contact sheets, the 2026-10-16 contact sheets and text extracts, the check outputs, the issue-update drafts, the environment-repair proposal, the ledger and a copy of this record. Its `SHA256SUMS.txt` SHA-256 is recorded in `README.md`. The staged-inventory identity (SHA-256 of `git ls-files --stage`) is reported with the packet, outside the repository, because this record is part of that inventory.

{checks_rev}
"""

final = generated.rstrip("\n") + "\n\n" + guardrails + "\n" + revision
record.write_text(final.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
tmp.unlink()
print("validation record composed:", record)
