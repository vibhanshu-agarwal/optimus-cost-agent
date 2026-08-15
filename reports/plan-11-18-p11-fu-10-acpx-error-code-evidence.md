# Plan 11.18 P11-FU-10 acpx error-code evidence

Sanitized observation of an independently authored `acpx` client against a throwaway probe agent. No raw transcript, task prompt, environment, or credentials are recorded.

The application duplicate-ID code changed unconditionally because -32001 is inside JSON-RPC's reserved band (-32768..-32000). This observation is evidence about one real client; it is not permission to retain a protocol-invalid number. DUPLICATE_REQUEST_ID remains -32911.

```json
{
  "acpx_client": "external (independent acpx binary; no project ACP client used)",
  "acpx_path_digest": "9922637b8318da4dfe0207e53bc289245c314895e247ab6b5bfde90d14deb44c",
  "acpx_version": "0.12.0",
  "probed_codes": [
    -32001,
    -32911
  ],
  "probes": [
    {
      "classification": "error_envelope_observed",
      "code": -32001,
      "exit_code": 4
    },
    {
      "classification": "error_envelope_observed",
      "code": -32911,
      "exit_code": 1
    }
  ],
  "unconditional_allocation_reason": "The application duplicate-ID code changed unconditionally because -32001 is inside JSON-RPC's reserved band (-32768..-32000). This observation is evidence about one real client; it is not permission to retain a protocol-invalid number. DUPLICATE_REQUEST_ID remains -32911."
}
```
