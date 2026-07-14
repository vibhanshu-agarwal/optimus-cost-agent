from __future__ import annotations

from urllib.parse import urlparse

from optimus.net.https import https_hostname


class EvidenceDomainRejected(ValueError):
    """Raised when caller-requested or gateway-returned domains fail local policy."""


class EvidenceDomainPolicy:
    """
    Manages the policy for allowed evidence domains.

    This class encapsulates the logic for determining which domains are allowed
    based on a configured set of allowed domains and a requested set of domains.
    It is also capable of verifying if a given URL is allowed based on the
    effective allowed domains.

    :ivar configured_domains: A set of pre-configured allowed domains that serve
        as the basis for determining effective allowed domains and validating URL
        access.
    :type configured_domains: frozenset[str]
    """
    def __init__(self, *, configured_allowed_domains: tuple[str, ...]) -> None:
        self._configured_domains = frozenset(
            domain
            for domain in (_normalize_domain(value) for value in configured_allowed_domains)
            if domain
        )
        if not self._configured_domains:
            raise ValueError("configured_allowed_domains must not be empty")

    def effective_allowed_domains(self, requested_domains: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            domain
            for domain in (_normalize_domain(value) for value in requested_domains)
            if domain
        )
        effective = tuple(
            domain
            for domain in normalized
            if any(_domain_matches_configured(domain, configured) for configured in self._configured_domains)
        )
        if not effective:
            raise EvidenceDomainRejected("allowed_domains not in configured evidence allowlist")
        return effective

    def url_allowed(self, url: str, effective_allowed_domains: tuple[str, ...]) -> bool:
        host = https_hostname(url) or ""
        return bool(host) and any(_host_matches_domain(host, domain) for domain in effective_allowed_domains)

    def assert_url_allowed(self, url: str, effective_allowed_domains: tuple[str, ...]) -> None:
        if not self.url_allowed(url, effective_allowed_domains):
            raise EvidenceDomainRejected("URL host not in effective allowed domains")


def _domain_matches_configured(domain: str, configured: str) -> bool:
    return domain == configured or domain.endswith(f".{configured}")


def _host_matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _normalize_domain(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        if parsed.hostname is None:
            return ""
        return parsed.hostname.lower().rstrip(".")
    bare = value.split("/", 1)[0].strip()
    if bare.startswith("["):
        end = bare.find("]")
        if end == -1:
            return ""
        return bare[1:end].lower()
    host = bare.rsplit(":", 1)[0] if ":" in bare else bare
    return host.lower().strip().rstrip(".")
