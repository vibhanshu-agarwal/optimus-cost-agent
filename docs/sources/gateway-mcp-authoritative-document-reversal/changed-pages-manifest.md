# Plan 11.13 changed-page reversion map

Every listed non-cover position restores the matching pre-amendment page body. Page one is a newly rendered target-version control page. The target header is stamped on restored and carried pages.

| Document | Current input | Reversion body | Target | Replacement pages | Client-boundary cover page |
|---|---|---|---|---|---|
| HLD | `docs/Optimus-Cost-Agent-Architecture-v2.17.pdf` | `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf` | `docs/Optimus-Cost-Agent-Architecture-v2.18.pdf` | `1, 3, 4, 7, 9, 10, 11, 12` | 1 |
| LLD | `docs/Optimus-Cost-Agent-LLD-v2.40.pdf` | `docs/Optimus-Cost-Agent-LLD-v2.39.pdf` | `docs/Optimus-Cost-Agent-LLD-v2.41.pdf` | `1, 2, 3, 4, 5, 20, 21, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40` | 1 |
| Guardrails | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.3.pdf` | `1, 4, 6, 8, 10, 11, 12, 14, 16` | 1 |
| Test Strategy | `docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | `docs/Optimus-Cost-Agent-Test-Strategy-v1.7.pdf` | `1, 2, 3, 5, 6, 8, 9, 10, 11, 12, 13, 14` | 1 |

## Fragment mappings

- **HLD:** 1->1, 2->3, 3->4, 4->7, 5->9, 6->10, 7->11, 8->12.
- **LLD:** 1->1, 2->2, 3->3, 4->4, 5->5, 6->20, 7->21, 8->26, 9->27, 10->28, 11->29, 12->30, 13->31, 14->32, 15->33, 16->34, 17->35, 18->36, 19->37, 20->38, 21->39, 22->40.
- **Guardrails:** 1->1, 2->4, 3->6, 4->8, 5->10, 6->11, 7->12, 8->14, 9->16.
- **Test Strategy:** 1->1, 2->2, 3->3, 4->5, 5->6, 6->8, 7->9, 8->10, 9->11, 10->12, 11->13, 12->14.
