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


# #603: each of these makes urllib's parser raise ValueError (an unclosed or invalid bracketed host).
MALFORMED_URLS = ["https://[", "https://[::1", "https://[not-an-address]/x"]


@pytest.mark.parametrize("value", MALFORMED_URLS)
def test_a_malformed_requested_domain_is_rejected_like_any_unlisted_domain(value):
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        policy.effective_allowed_domains((value,))
    assert policy.effective_allowed_domains((value, "example.com")) == ("example.com",)


@pytest.mark.parametrize("value", MALFORMED_URLS)
def test_a_malformed_url_is_not_an_allowed_url(value):
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))

    assert policy.url_allowed(value, ("example.com",)) is False
    with pytest.raises(EvidenceDomainRejected, match="URL host not in effective allowed domains"):
        policy.assert_url_allowed(value, ("example.com",))


def test_a_url_with_an_out_of_range_port_is_not_an_allowed_url():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))

    assert policy.url_allowed("https://example.com:65536/a", ("example.com",)) is False


def test_a_malformed_configured_domain_counts_as_no_domain():
    with pytest.raises(ValueError, match="configured_allowed_domains must not be empty"):
        EvidenceDomainPolicy(configured_allowed_domains=("https://[",))
