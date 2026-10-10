The completion evaluator must be a cheap model routed through the strict-loopback Optimus Gateway,
not the main reasoning model, and uses the same trusted route/capacity and actual-cost accounting contracts. Product evaluators have no dollar stop after migration; independently capped evaluations keep their explicit ceiling. The evaluator uses the developer-owned
aggregator account through the Gateway, has no direct provider credential or provider adapter, and
emits OTel/OTLP telemetry through authenticated Gateway trace ingress with no separate observability
backend or billing path. Missing/malformed reported cost remains explicit unknown with the known subtotal retained. It creates no product goal-loop monetary stop or session latch; an independently capped evaluation can stop its own calls. This evaluator capability is reserved, not currently activated.

# 8. Curated Workflow Skills

Project configuration is for always-on rules; skills are on-demand procedural workflows loaded only
when relevant. A skill is Markdown with YAML frontmatter - a name and description tell the agent when
it applies, and an optional globs field narrows it by file type or path. Keeping procedures out of
the always-on context and loading them only on match keeps the live prompt small while preserving
repeatable execution knowledge.

The evidence is strong that this matters for cost as much as quality. On SkillsBench (86 tasks across
11 domains), a small model given good human-curated skills outperformed a flagship model without
them. When models were allowed to write their own skills the gains disappeared: generic,
self-generated boilerplate makes things worse. Config files therefore hold always-relevant rules,
curated skills hold reusable task-specific procedures, and the live prompt holds what is unique to
the current task.

## 8.1 Skill Rules

- Curated, reviewed, and versioned - skills are managed artifacts, not ad-hoc notes.
- Short and focused - prefer narrow skills over broad documentation dumps.
- Procedures, not advice - a skill encodes a concrete workflow, not vague guidance.
- Support files allowed - scripts, templates, and examples may accompany a skill.
- Metadata required - name, description, applicable file globs, allowed tools, owner, version, and
  trust level.
- Generated skills are draft-only - a model-authored skill is never trusted until reviewed and
  promoted.

## 8.2 Trust & Invocation

Skills are governed by the same permission posture as everything else. A skill's declared
allowed_tools are enforced by the pre-tool guard (§3) - a skill cannot widen the agent's tool
surface - and a skill can never override project or user deny rules (§2.2). The SkillRegistry
resolves a matching SkillManifest only when its description/globs match the task, and
SkillTrustPolicy blocks any untrusted or unreviewed (draft) skill from loading in Agent mode.