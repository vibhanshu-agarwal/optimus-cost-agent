import pytest

from optimus.evidence.domain_policy import EvidenceDomainPolicy, EvidenceDomainRejected


def test_effective_domains_intersect_requested_with_configured_allowlist():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com", "pypi.org"))

    assert policy.effective_allowed_domains(("Example.COM", "evil.com")) == ("example.com",)


def test_effective_domains_reject_when_request_has_no_configured_domain():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        policy.effective_allowed_domains(("evil.com",))


def test_effective_domains_do_not_widen_configured_subdomain():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",))

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        policy.effective_allowed_domains(("example.com",))


def test_domain_policy_allows_subdomains_and_default_https_port():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))
    effective = policy.effective_allowed_domains(("example.com",))

    assert policy.url_allowed("https://docs.example.com/a", effective) is True
    assert policy.url_allowed("https://example.com:443/a", effective) is True


def test_domain_policy_rejects_off_allowlist_urls():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))
    effective = policy.effective_allowed_domains(("example.com",))

    assert policy.url_allowed("https://evil.com/a", effective) is False
    with pytest.raises(EvidenceDomainRejected, match="URL host not in effective allowed domains"):
        policy.assert_url_allowed("https://evil.com/a", effective)
