Reviewed contract after Task 11 at cf9bb9d: product LoopBudgetPolicy uses optional max_budget_usd=None; an explicit independently capped evaluation may supply a positive ceiling.

```python
class PermissionDecision(BaseModel):
    verdict: Literal["ALLOW", "DENY", "HOLD"]
    layer: Literal["mode", "user_deny", "project_allow", "impact", "classifier"]
    rule_id: str | None = None
    reason: str
    requires_human_approval: bool = False
class PreToolResult(BaseModel):
    verdict: Literal["ALLOW", "BLOCK", "HOLD"]
    tool_class: ToolClass            # bash | file_edit | mcp_call | web
    checks_failed: list[str] = Field(default_factory=list)
    audit: ToolInvocationAuditEvent
class MCPTrustEntry(BaseModel):
    server_id: str
    manifest_hash: str               # change forces re-approval
    allowed_tools: list[str] = Field(default_factory=list)
    permission_scope: list[str] = Field(default_factory=list)
    approved: bool = False
class GoalLoopController(BaseModel):
    completion: CompletionEvaluator
    budget: LoopBudgetPolicy          # max_iterations, repeated_failure_limit,
                                      # max_wall_clock_minutes
    state: IterationState
    ledger: ProgressLedger
    def stop_reason(self) -> LoopStopReason | None: ...
    # COMPLETED | MAX_ITERATIONS
    # | WALL_CLOCK | REPEATED_FAILURE | HUMAN_HALT
    # independent evaluation may add a scoped monetary exhaustion reason
class SkillManifest(BaseModel):
    name: str
    description: str
    globs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    owner: str
    version: str
    trust_level: Literal["trusted", "draft"] = "draft"
```

# 11. Test Coverage Mapping (Test Strategy Anchor)

Every control in this document must trace to at least one executable test category, consistent with the Test Strategy's first objective (no design claim ships without a test). These categories are specified in Test Strategy §14 and added as rows to the §4 Requirements-to-Test Traceability Matrix.