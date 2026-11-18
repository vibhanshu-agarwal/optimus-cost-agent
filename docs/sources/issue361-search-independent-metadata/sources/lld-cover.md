# Optimus - Low-Level Design

**Version 2.48 — #361 search-independent metadata, 2026-11-17.**

Predecessor: Optimus-Cost-Agent-LLD-v2.47.pdf; SHA-256 e8e42bb59dcdcfe17f297ad968854950e8bca3babfaad440221ef1a649ba0d51. Retain the predecessor byte-for-byte in `docs/archive/`.

**Edition scope.** Package/OSV construction and serving no longer require Tavily configuration; Redis URL and normalized domain policy remain required. Search and extract remain Tavily-backed and fail closed without its key. Separate extract independence and the search decision remain specified, not implemented, with accepted custody in #362. This edition updates only those capability/verification claims and retains the predecessor's later accounting, Auto, timing, memory and decision qualifications at their own stated pins.

**Evidence boundary.** Named unit and real-loopback HTTP fixtures exercise actual construction, policy and dispatch with controlled external boundaries. No live Gateway/provider/Redis or GUI proof was run for #361; the real release gate remains UNRUN. Source, review and final CI identities are retained in #361 and this bundle's validation record. Historical failed/skip/UNRUN/reused/warning qualifications are not relabelled.

**Authority.** The operator adopted the #361 bounded plan and authorized Codex implementation, Claude review and end-to-end delivery on 2026-11-17, with live probes and cleanup prohibited. This publication changes no unrelated target or historical evidence.
