# Evidence and Local Artifact Policy

## Purpose

The repository is the authoritative, contributor-accessible record for product
source, decisions, plans, sanitized evidence summaries, manifests, and hashes.
No build, test, release, or review decision may require an untracked file from
an individual workstation.

Raw evidence can contain private paths, session identifiers, environment
details, or credentials-adjacent material. Keep that material out of Git unless
it has been reviewed and explicitly approved for publication. Its existence
must never turn a private directory into a project dependency.

## Legacy archive record

The legacy material identified during the 2026-09-11 worktree cleanup is held
in one recovery archive. It is archival storage, not a runtime, test, review,
or release input.

| Field | Value |
| --- | --- |
| Archive | `D:\Projects\Development\Python\optimus-cost-agent-backup\optimus-cost-agent-legacy-artifacts-2026-09-11.zip` |
| SHA-256 | `10e36ad0279f9aed1a9dc379dae19f8d4fa25da12eb1da40cc27a444fd1219b7` |
| Size | 59,580,224 bytes |
| Entries | 956 |
| Archived material | `optimus-agent-handoff`; `optimus-ci-production-evidence-slice-b-20260905`; `optimus-evidence-custody`; `optimus-cost-agent-wt-cursor-stray-reports-2026-08-05` |

The unpacked source directories were removed after the archive checksum was
recorded. Before any recovery, verify the archive's SHA-256. Extract only to a
temporary directory outside a Git worktree, inspect the material, create any
needed sanitized repository record, and then remove the temporary extraction.

## Rules for future work

1. Commit the durable claim, a sanitized summary, and the checksum or manifest
   needed to verify it. Use repository-relative paths for all active commands,
   tests, and documentation links.
2. Do not make a task, test, release gate, review, or runtime path depend on a
   workstation-specific directory, an untracked file, or an agent worktree.
3. Keep raw or private evidence in the single legacy archive or in separately
   approved private storage. It is not evidence of a claim until an approved,
   repository-visible summary identifies the relevant command, result, and
   digest.
4. Treat absolute local paths in frozen documents and evidence reports as
   historical provenance only. Do not rewrite frozen records solely to change
   paths. If an active document still needs external raw evidence, publish a
   governed successor that replaces the dependency with a repository-visible
   summary or manifest.
5. Store agent worktrees only under
   `C:\worktrees\optimus-cost-agent-worktrees`. The operator's
   `D:\Projects\Development\Python\optimus-cost-agent-wt-vibhanshu` lane is
   excluded from this agent-worktree rule.

## Review checklist

Before approving a change that refers to evidence or an artifact, reviewers
must confirm:

- the claim can be understood and verified from tracked files;
- any raw external input is identified only as provenance, not a required
  operating dependency;
- private material, local environments, credentials, and agent-session data
  are not staged; and
- new agent worktrees follow the approved `C:\worktrees` location.
