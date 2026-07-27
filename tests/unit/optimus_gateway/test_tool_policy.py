from __future__ import annotations

import pytest

from optimus_gateway.models import GatewayToolContext, ToolClass, ToolPolicySignal
from optimus_gateway.tool_policy import GatewayToolPolicy, GatewayToolPolicyError


def _policy(*, allowed_domains: tuple[str, ...] = ("python.org", "pypi.org")) -> GatewayToolPolicy:
    return GatewayToolPolicy(allowed_domains=allowed_domains)


def _body(**overrides: object) -> dict[str, object]:
    context = {
        "run_id": "run-1",
        "execution_mode": "agent",
        "session_id": "session-1",
        "org_id": "org-1",
        "project_id": "project-1",
        "model": "glm-5.2",
    }
    context.update(overrides.pop("context_overrides", {}))
    body: dict[str, object] = {"context": context}
    body.update(overrides)
    return body


# --- resolve_context ---------------------------------------------------------


def test_resolve_context_succeeds_for_well_formed_request():
    policy = _policy()

    context = policy.resolve_context(request_body=_body(), authenticated_subject="subject-1")

    assert isinstance(context, GatewayToolContext)
    assert context.run_id == "run-1"
    assert context.execution_mode == "agent"
    assert context.session_id == "session-1"
    assert context.org_id == "org-1"
    assert context.project_id == "project-1"
    assert context.model == "glm-5.2"
    assert context.authenticated_subject == "subject-1"


def test_resolve_context_rejects_missing_run_id():
    policy = _policy()
    body = _body(context_overrides={"run_id": ""})

    with pytest.raises(GatewayToolPolicyError) as excinfo:
        policy.resolve_context(request_body=body, authenticated_subject="subject-1")

    assert excinfo.value.rule_id == "MISSING_RUN_ID"


def test_resolve_context_rejects_missing_run_id_key_entirely():
    policy = _policy()
    body = {"context": {"execution_mode": "agent"}}

    with pytest.raises(GatewayToolPolicyError) as excinfo:
        policy.resolve_context(request_body=body, authenticated_subject="subject-1")

    assert excinfo.value.rule_id == "MISSING_RUN_ID"


@pytest.mark.parametrize(
    "malformed_body",
    (
        {},
        {"context": "not-a-mapping"},
        {"context": ["also", "not", "a", "mapping"]},
        {"context": {"run_id": "run-1", "execution_mode": "agent", "session_id": 123}},
    ),
)
def test_resolve_context_rejects_malformed_metadata(malformed_body: dict[str, object]):
    policy = _policy()

    with pytest.raises(GatewayToolPolicyError) as excinfo:
        policy.resolve_context(request_body=malformed_body, authenticated_subject="subject-1")

    assert excinfo.value.rule_id == "MALFORMED_METADATA"


@pytest.mark.parametrize("execution_mode", ("", "unknown", "PLAN_MODE", None))
def test_resolve_context_rejects_unsupported_execution_mode(execution_mode: object):
    policy = _policy()
    body = _body(context_overrides={"execution_mode": execution_mode})

    with pytest.raises(GatewayToolPolicyError) as excinfo:
        policy.resolve_context(request_body=body, authenticated_subject="subject-1")

    assert excinfo.value.rule_id == "UNSUPPORTED_EXECUTION_MODE"


@pytest.mark.parametrize("subject", ("", "   ", None))
def test_resolve_context_rejects_missing_authenticated_subject(subject: object):
    policy = _policy()

    with pytest.raises(GatewayToolPolicyError) as excinfo:
        policy.resolve_context(request_body=_body(), authenticated_subject=subject)

    assert excinfo.value.rule_id == "MISSING_IDENTITY"


def test_resolve_context_allows_optional_fields_to_be_absent():
    policy = _policy()
    body = {"context": {"run_id": "run-2", "execution_mode": "chat"}}

    context = policy.resolve_context(request_body=body, authenticated_subject="subject-1")

    assert context.run_id == "run-2"
    assert context.session_id is None
    assert context.org_id is None
    assert context.project_id is None
    assert context.model is None


# --- authorize: domain intersection -----------------------------------------


def _context(**overrides: object) -> GatewayToolContext:
    defaults: dict[str, object] = {
        "run_id": "run-1",
        "authenticated_subject": "subject-1",
        "session_id": None,
        "execution_mode": "agent",
        "org_id": None,
        "project_id": None,
        "model": None,
    }
    defaults.update(overrides)
    return GatewayToolContext(**defaults)


def test_authorize_rejects_empty_effective_domain_intersection():
    policy = _policy(allowed_domains=("python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("attacker.example",),
        resolved_urls=(),
    )

    assert decision.allowed is False
    assert decision.rule_id == "EMPTY_DOMAIN_INTERSECTION"


def test_authorize_allows_exact_configured_domain():
    policy = _policy(allowed_domains=("python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("python.org",),
        resolved_urls=("https://python.org/downloads",),
    )

    assert decision.allowed is True
    assert decision.effective_domains == ("python.org",)


def test_authorize_allows_subdomain_of_configured_domain():
    policy = _policy(allowed_domains=("python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("docs.python.org",),
        resolved_urls=("https://docs.python.org/3/",),
    )

    assert decision.allowed is True


def test_authorize_rejects_requested_domain_that_is_a_superdomain_of_configured():
    # configured "docs.python.org" must not authorize a bare "python.org" request.
    policy = _policy(allowed_domains=("docs.python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("python.org",),
        resolved_urls=(),
    )

    assert decision.allowed is False
    assert decision.rule_id == "EMPTY_DOMAIN_INTERSECTION"


# --- authorize: HTTPS enforcement --------------------------------------------


def test_authorize_rejects_non_https_resolved_url():
    policy = _policy(allowed_domains=("python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("python.org",),
        resolved_urls=("http://python.org/insecure",),
    )

    assert decision.allowed is False
    assert decision.rule_id == "NON_HTTPS_URL"


def test_authorize_rejects_resolved_url_outside_effective_domains():
    policy = _policy(allowed_domains=("python.org", "pypi.org"))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("python.org",),
        resolved_urls=("https://pypi.org/project/x",),
    )

    assert decision.allowed is False
    assert decision.rule_id == "URL_DOMAIN_NOT_ALLOWED"


# --- authorize: tool-class / policy-signal routing ---------------------------


def test_authorize_rejects_web_search_with_wrong_signal():
    policy = _policy(allowed_domains=("python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        requested_domains=("python.org",),
        resolved_urls=(),
    )

    assert decision.allowed is False
    assert decision.rule_id == "POLICY_SIGNAL_MISMATCH"


def test_authorize_rejects_web_extract_without_provenance_signal():
    policy = _policy(allowed_domains=("python.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.WEB_EXTRACT,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=("python.org",),
        resolved_urls=("https://python.org/a",),
    )

    assert decision.allowed is False
    assert decision.rule_id == "POLICY_SIGNAL_MISMATCH"


def test_authorize_allows_package_and_advisory_with_dependency_signal():
    policy = _policy(allowed_domains=("pypi.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        requested_domains=(),
        resolved_urls=("https://pypi.org/project/x",),
    )

    assert decision.allowed is True


def test_authorize_rejects_package_and_advisory_with_wrong_signal():
    policy = _policy(allowed_domains=("pypi.org",))

    decision = policy.authorize(
        context=_context(),
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        requested_domains=(),
        resolved_urls=(),
    )

    assert decision.allowed is False
    assert decision.rule_id == "POLICY_SIGNAL_MISMATCH"
