# Gateway-MCP authoritative-document reversal publication sources

This sibling package publishes HLD v2.18, LLD v2.41, Guardrails v1.3, and Test Strategy v1.7 without modifying the retired amendment package or its immutable current PDFs.

## Reversion method

For every amendment-affected non-cover page, the assembler restores the exact pre-amendment page body from the named historical predecessor, strips its old running header, and stamps the target document control. New page-one controls and four client-MCP boundary notes are rendered with Pandoc and WeasyPrint. Each changed-page source is a review certificate for a replacement position.

## Boundary

Retired: Gateway profiles, credentials, routes, brokering, binding/admission, MCP accounting, and Context7 probing. Retained: client-supplied ACP mcpServers, local MCPTrustRegistry, validate_tool_call, PreToolGuard.check, untrusted output, and independently authored HTTP/stdio MCP evidence.
