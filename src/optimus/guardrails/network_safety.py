from __future__ import annotations

from urllib.parse import urlparse

from optimus.guardrails.validation import ValidationResult, ValidationVerdict


class NetworkSafetyValidator:
    def __init__(self, *, allowed_hosts: tuple[str, ...]) -> None:
        self._allowed_hosts = frozenset(host.lower().rstrip(".") for host in allowed_hosts if host)

    def validate_url(self, url: str) -> ValidationResult:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return ValidationResult(ValidationVerdict.BLOCK, "network.insecure_transport", "network URLs must use HTTPS")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return ValidationResult(ValidationVerdict.BLOCK, "network.missing_host", "network URL missing host")
        if host in self._allowed_hosts or any(host.endswith(f".{allowed}") for allowed in self._allowed_hosts):
            return ValidationResult(ValidationVerdict.ALLOW, "network.host.allowed", "host is allowed")
        return ValidationResult(ValidationVerdict.HOLD, "network.unexpected_egress", "unexpected network egress requires approval")
