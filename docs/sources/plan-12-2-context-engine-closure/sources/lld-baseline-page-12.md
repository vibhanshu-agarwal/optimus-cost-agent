# 4. Mutation assertion and path containment (retained prototype)
The full assertion is shown here so the raise statement is not orphaned after the preceding page replacement. ExecutionMode is the retained PLAN/CHAT/AGENT vocabulary. These illustrative contracts preserve the original containment checks; executable implementation remains authoritative.
```python
def assert_mutation_allowed(mode: ExecutionMode,
                            operation: ToolOperationKind, tool_name: str):
    if mode != ExecutionMode.AGENT and operation in {
        ToolOperationKind.WRITE, ToolOperationKind.EXTERNAL_MUTATION
    }:
        raise OptimusToolError(
            OptimusToolErrorCode.VALIDATION_ERROR,
            f"Access security violation error: "
            f"Mutation blocked in Plan/Chat mode: {operation}",
        )
class MutationGuard:
    def __init__(self, mode: ExecutionMode):
        self.mode = mode
    def enforce_gate(self, op_kind: ToolOperationKind, tool_name: str):
        assert_mutation_allowed(self.mode, op_kind, tool_name)
class ASTOptimizationInput(BaseModel):
    project_path: DirectoryPath = Field(
        ..., description="Absolute path to the project root."
    )
    target_file: str = Field(..., description="Relative file path string.")
    adl_rules: list[str] = Field(default_factory=list)
    execution_mode: ExecutionMode = Field(default=ExecutionMode.PLAN)
    generation_scope: CodeGenerationScope = Field(
        default=CodeGenerationScope.INLINE_SNIPPET
    )
    rigor_budget: RigorLevel = Field(default=RigorLevel.LOW)
    assumption_ledger: AssumptionLedger = Field(
        default_factory=AssumptionLedger
    )
    @model_validator(mode="after")
    def validate_paths_and_safeguards(self) -> "ASTOptimizationInput":
        if Path(self.target_file).is_absolute():
            raise ValueError("Target file must be a relative path configuration.")
        try:
            resolved_base = Path(os.path.abspath(self.project_path)).resolve(
                strict=True
            )
            candidate_path = Path(os.path.abspath(
                os.path.join(str(resolved_base), self.target_file)
            ))
        except (ValueError, FileNotFoundError, RuntimeError):
            raise ValueError("Malformed or invalid project root directory specification.")
        try:
            if candidate_path.exists() or candidate_path.is_symlink():
                resolved_target = candidate_path.resolve(strict=False)
                if os.path.commonpath([
                    str(resolved_base), str(resolved_target)
                ]) != str(resolved_base):
                    raise ValueError(
                        "Breakout attempt detected via target file path alignment."
                    )
            else:
                parent_path = candidate_path.parent
                resolved_parent = parent_path.resolve(strict=True)
                if os.path.commonpath([
                    str(resolved_base), str(resolved_parent)
                ]) != str(resolved_base):
                    raise ValueError(
                        "Symlink ancestry breakout via target parent folder."
                    )
        except ValueError as ve:
            raise ValueError(
                f"Cross-drive partition boundary constraint or layout failure: {ve}"
            )
        except (FileNotFoundError, RuntimeError):
            raise ValueError(
                "Missing or invalid ancestral directory infrastructure mapping."
            )
        return self
```
