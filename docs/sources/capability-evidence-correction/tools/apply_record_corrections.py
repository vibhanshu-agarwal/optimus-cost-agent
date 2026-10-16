"""Three record corrections from Codex's checkpoint 3 WSL-remainder disposition (2026-10-16): the remainder skip
counts (node counts, not summary lines), the node-list hash difference (CRLF versus LF, same order) and the
narrowed statement about prior Linux evidence. Asserted exact replacements in validation-record.md and the
README tools table; the section they correct was written by apply_platform_accounting_update.py, which is left
as it ran so the chain of edits stays visible.

Usage: apply_record_corrections.py REPO_ROOT
"""
from __future__ import annotations

import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
bundle = repo / "docs" / "sources" / "capability-evidence-correction"
record = bundle / "validation-record.md"
readme = bundle / "README.md"
DISPOSITION = "a897e70f955e76d82697f975270a724260c6c7e632bc6148553b711e8af87bf8"  # pragma: allowlist secret


def rep(p: Path, old: str, new: str) -> None:
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (p.name, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")


# 1. skip counts by node, described as platform-specific skips with their exact reasons
rep(record,
    '135 skipped, every skip a Windows-only guard (25 "MAIN-5 guard is Windows-only", 20 "native job ownership is Windows-only", 4 "load-overlap repeats are Windows-only", 3 "job containment is the Windows path", and single-node reasons such as the CP1252 omission needing a real CP1252 Windows process, the Windows snapshot script and the Windows `taskkill` tree-kill path; all 82 nodes of `test_main5_guard.py` skip on Linux)',
    '135 skipped, all platform-specific skips with their reasons recorded, counted per node (81 "MAIN-5 guard is Windows-only: it hooks _winapi and fails closed elsewhere", 38 "native job ownership is Windows-only", 4 "load-overlap repeats are Windows-only", 3 "the load-overlap lane is Windows-only", 3 "job containment is the Windows path", 2 "Task 3\'s exercised tree-kill path is Windows taskkill", and one node each for the Windows snapshot script, the CP1252 omission that needs a real CP1252 Windows process, no separate venv launcher on this platform, and membership in the run\'s job as the native capability; all 82 nodes of `test_main5_guard.py` skip on Linux)')
rep(record,
    "168 skipped by Windows-only guards (33 + 135), 8 passed per pytest",
    "168 platform-specific skips with recorded reasons (33 + 135; skips are not passing native-capability tests), 8 passed per pytest")

# 2. the hash difference is CRLF versus LF over identical ordered lines
rep(record,
    "(Codex's `checkpoint3-platform-missing.txt`, same 659 node ids, hashes as `a19f4c7f167e1f8bd97d4bf1b1302b978f0940d9ffcbe89e2c3b312c7adfd11b` over its own line ordering)",
    "(Codex's `checkpoint3-platform-missing.txt` holds the same 659 node ids in the same order with CRLF line endings and hashes as `a19f4c7f167e1f8bd97d4bf1b1302b978f0940d9ffcbe89e2c3b312c7adfd11b`; converting it to LF reproduces the executed list byte for byte)")

# 3. narrow the claim about prior Linux evidence
rep(record,
    "No existing WSL evidence was eligible for the 659: no Linux run records exist on this host for any clone, and the only full WSL run (`wsl-full-1`) is at cf9bb9d.",
    "No eligible prior evidence was identified for the 659: the WSL clones inspected for reuse (`optimus-cost-agent-main7-linux` at 8177b9b and `p11-fu-17-proof` at 76bbf1e) hold no profile or run records, the only full WSL run (`wsl-full-1`) is at cf9bb9d, and the Linux run records that do exist on this host (the candidate's own 2026-10-16 runs and earlier unrelated work) are not evidence for these nodes at this source.")

# dated note of the corrections at the end of the section they correct
rep(record,
    "Held for the operator: ADR-020 acceptance of the WSL evidence above, the one-commit `check-added-large-files` exception for the four PDFs over 500 KB, the commit itself in a shell with the scoped `PRE_COMMIT_HOME`, and push, PR and merge. Full WSL pre-finalize remains separate.\n",
    "Held for the operator: ADR-020 acceptance of the WSL evidence above, the one-commit `check-added-large-files` exception for the four PDFs over 500 KB, the commit itself in a shell with the scoped `PRE_COMMIT_HOME`, and push, PR and merge. Full WSL pre-finalize remains separate.\n\n"
    "### Record corrections after the WSL-remainder disposition (2026-10-16)\n\n"
    f"Codex's disposition (`checkpoint-3-wsl-remainder-disposition.md`, SHA-256 `{DISPOSITION}`, kept outside the repository) accepted the qualified WSL evidence for the complete 1,629-node set at the frozen candidate `005cdab0...` (1,453 recorded passes, 8 qualified pytest passes, 168 skips, 0 failures or missing nodes) and verified the P2 rebuild outputs, and asked for three corrections to this record, applied by `tools/apply_record_corrections.py`: the remainder skip counts are now per node (81 MAIN-5 and 38 native-job, not 25 and 20, which counted collapsed summary lines); the node-list hash difference is CRLF versus LF over identical ordered lines, not ordering; and the statement about prior Linux evidence is narrowed to what was inspected. The acceptance is Codex's; this record still grants nothing, and full WSL pre-finalize, the file-size exception and the commit remain separate.\n")

# README tools table: name every apply script
rep(readme,
    "| `author_corrections.py`, `apply_review_fixes.py`, `apply_checkpoint3_fixes.py`, `apply_consolidated_update.py` | The asserted `replace` edits that produced the sources from the sealed Plan 12.2 bodies, then the review, checkpoint 3 and post-gate corrections |",
    "| `author_corrections.py`, `apply_review_fixes.py`, `apply_checkpoint3_fixes.py`, `apply_consolidated_update.py`, `apply_platform_accounting_update.py`, `apply_record_corrections.py` | The asserted `replace` edits that produced the sources from the sealed Plan 12.2 bodies, then the review, checkpoint 3, post-gate, platform-accounting and final record corrections |")
print("record corrections applied")
