from __future__ import annotations

import ipaddress
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
        literal_ip_result = _literal_ip_target_result(host)
        if literal_ip_result is not None:
            return literal_ip_result
        if host in self._allowed_hosts or any(host.endswith(f".{allowed}") for allowed in self._allowed_hosts):
            return ValidationResult(ValidationVerdict.ALLOW, "network.host.allowed", "host is allowed")
        return ValidationResult(ValidationVerdict.HOLD, "network.unexpected_egress", "unexpected network egress requires approval")


def _literal_ip_target_result(host: str) -> ValidationResult | None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if address.is_loopback:
        return ValidationResult(ValidationVerdict.BLOCK, "network.loopback_target", "loopback IP targets are denied")
    if address.is_private or address.is_link_local or address.is_reserved:
        return ValidationResult(
            ValidationVerdict.BLOCK,
            "network.private_ip_target",
            "private or link-local IP targets are denied",
        )
    return None
