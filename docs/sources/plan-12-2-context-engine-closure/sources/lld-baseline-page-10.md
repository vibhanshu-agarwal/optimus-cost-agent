# 4. Behavioral Governance: modes, strategies and scope
The following representative contracts preserve the existing scope and mode vocabulary while retiring the HAIKU/PRO model-tier enum. Executable implementations remain in src/; these type shapes are design contracts.
| Contract | Values / fields |
|---|---|
| ExecutionMode | PLAN; CHAT; AGENT. This existing vocabulary retains the read-only Plan/Chat boundary. |
| CodeGenerationScope | INLINE_SNIPPET; PATCH_PROPOSAL; FILE_MUTATION; MULTI_FILE_CHANGESET |
| ExecutionStrategy | DIRECT; PLAN_AND_EXECUTE; REACT; REFLECTION |
| RigorLevel | LOW; MEDIUM; HIGH |
| Model tier | ultra-cheap; cheap; review. Review role is dormant; use the trusted registry, not HAIKU/PRO aliases. |
| ToolOperationKind | READ; WRITE; EXTERNAL_MUTATION |
| OptimusToolErrorCode | VALIDATION_ERROR; RESOURCE_ERROR; PROVIDER_ERROR; TIMEOUT_ERROR |
| OptimusToolError | code; message; optional context. Exception keeps those fields and its message. |
| AssumptionItem | claim; basis; confidence default medium; requires_verification default true |
| AssumptionLedger | assumptions list, empty by default; no new conversation claim-tracking subsystem |
| ToolResponse | is_success; payload empty dict by default; optional error_code/error_msg |
ToolResponse.to_jsonrpc_error maps VALIDATION_ERROR to -32002, RESOURCE_ERROR to -32004, PROVIDER_ERROR to -32006, TIMEOUT_ERROR to -32005, and unmapped/no typed code to -32603. Return code, Tool Execution Failure message, and data containing typed error_code and context. These fields are retained across the successor.
