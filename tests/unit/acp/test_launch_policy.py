"""Tests for the canonical launch-variable policy registry.

Task 1 of Plan 9.96: every source-referenced OPTIMUS_* name, the OPTIMUS_LOCAL_GATEWAY_
prefix, and every provider-key name must have exactly one classified policy entry.
Unknown and internal-only names must fail closed before resolution.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

# The module under test — expected to fail on import until Task 1 Step 2 creates it.
from optimus.acp.launch_policy import (
    DEFAULT_LIVE_MAX_COST_USD,
    DEFAULT_MAX_PLANNING_TURNS,
    LAUNCH_VARIABLE_POLICIES,
    LOCAL_GATEWAY_PREFIX,
    LaunchEnvironmentSnapshot,
    LaunchPolicyError,
    LaunchVariableTier,
    PropagationTarget,
    classify_variable,
)
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"

# --- AST inventory helpers ---


def _extract_optimus_string_literals(source_root: Path) -> set[str]:
    """Walk all .py files under source_root and extract string literals matching OPTIMUS_*."""
    pattern = re.compile(r"^OPTIMUS_[A-Z][A-Z0-9_]*$")
    found: set[str] = set()
    for py_file in source_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if pattern.match(node.value):
                    found.add(node.value)
    return found


def _extract_provider_key_literals(source_root: Path) -> set[str]:
    """Extract provider-key name literals from LOCAL_PROVIDER_KEY_NAMES in gateway.py."""
    # Use the runtime set directly rather than AST to avoid drift.
    return set(LOCAL_PROVIDER_KEY_NAMES)


# --- Task 1 Step 1: Registry-inventory tests ---


class TestRegistryInventory:
    """Prove exhaustive, non-duplicate coverage of all source-referenced names."""

    def test_every_literal_optimus_source_name_has_one_policy(self) -> None:
        """Every OPTIMUS_* string literal in src/**/*.py is either:
        - a concrete key in LAUNCH_VARIABLE_POLICIES, OR
        - covered by the prefix rule (starts with OPTIMUS_LOCAL_GATEWAY_ and is not
          separately enumerated).

        A literal ending in _ is a prefix rule token, not a variable name.
        """
        all_literals = _extract_optimus_string_literals(_SRC_ROOT)
        # Exclude prefix tokens (ending in _) — they represent prefix rules, not variables.
        concrete_names = {name for name in all_literals if not name.endswith("_")}

        prefix = LOCAL_GATEWAY_PREFIX  # "OPTIMUS_LOCAL_GATEWAY_"
        missing: set[str] = set()
        for name in concrete_names:
            if name in LAUNCH_VARIABLE_POLICIES:
                continue
            # If it starts with the prefix and is NOT separately enumerated, the prefix
            # rule covers it — but only if the prefix rule itself exists.
            if name.startswith(prefix):
                continue
            missing.add(name)

        assert not missing, (
            f"Source-referenced OPTIMUS_* names with no policy entry: {sorted(missing)}"
        )

    def test_local_gateway_prefix_literal_has_one_fail_closed_prefix_rule(self) -> None:
        """The literal 'OPTIMUS_LOCAL_GATEWAY_' prefix exists in source and the registry
        has a prefix-rule entry that rejects any non-enumerated member."""
        all_literals = _extract_optimus_string_literals(_SRC_ROOT)
        # The prefix literal itself (ending in _) should appear in source.
        assert LOCAL_GATEWAY_PREFIX in all_literals or any(
            lit.endswith("_") and lit.startswith("OPTIMUS_LOCAL_GATEWAY") for lit in all_literals
        ), "Expected OPTIMUS_LOCAL_GATEWAY_ prefix literal in source"

        # The prefix rule must classify unknown members as failing closed.
        unknown_under_prefix = "OPTIMUS_LOCAL_GATEWAY_SOMETHING_UNKNOWN"
        with pytest.raises(LaunchPolicyError) as exc_info:
            classify_variable(unknown_under_prefix)
        assert exc_info.value.code == "LAUNCH_VARIABLE_UNCLASSIFIED"
        assert exc_info.value.variable_name == unknown_under_prefix

    def test_provider_key_registry_equals_local_provider_key_names(self) -> None:
        """Every name in LOCAL_PROVIDER_KEY_NAMES has a Secret-tier policy."""
        provider_keys_in_registry = {
            name
            for name, policy in LAUNCH_VARIABLE_POLICIES.items()
            if policy.tier == LaunchVariableTier.SECRET
            and name in LOCAL_PROVIDER_KEY_NAMES
        }
        assert provider_keys_in_registry == LOCAL_PROVIDER_KEY_NAMES

    def test_every_policy_has_parser_display_approval_and_propagation(self) -> None:
        """No policy entry has None/empty for required fields."""
        for name, policy in LAUNCH_VARIABLE_POLICIES.items():
            assert policy.name == name, f"Policy name mismatch for {name}"
            assert policy.tier in LaunchVariableTier, f"Invalid tier for {name}"
            assert policy.propagation, f"Empty propagation for {name}"
            assert all(
                t in PropagationTarget for t in policy.propagation
            ), f"Invalid propagation target in {name}"
            assert callable(policy.parser), f"Non-callable parser for {name}"
            assert callable(policy.display), f"Non-callable display for {name}"
            assert policy.approval, f"Empty approval rule for {name}"
            assert isinstance(policy.uri_userinfo, bool), f"Missing uri_userinfo for {name}"


def test_every_url_named_security_variable_declares_uri_userinfo() -> None:
    for name, policy in LAUNCH_VARIABLE_POLICIES.items():
        if policy.tier == LaunchVariableTier.SECURITY and (name.endswith("_URL") or name.endswith("_URI")):
            assert policy.uri_userinfo is True, f"URI policy metadata missing for {name}"


class TestFailClosedBehavior:
    """Unknown and internal-only names must fail before resolution."""

    def test_unknown_optimus_name_fails_closed_by_name_only(self) -> None:
        """An unrecognized OPTIMUS_* name raises LaunchPolicyError without
        requiring or revealing a value."""
        with pytest.raises(LaunchPolicyError) as exc_info:
            classify_variable("OPTIMUS_COMPLETELY_UNKNOWN_SETTING")
        assert exc_info.value.code == "LAUNCH_VARIABLE_UNCLASSIFIED"
        assert exc_info.value.variable_name == "OPTIMUS_COMPLETELY_UNKNOWN_SETTING"

    def test_inherited_bind_and_acp_debug_names_fail_before_resolution(self) -> None:
        """Internal-only names in the inherited environment must be rejected
        before any downstream resolution or propagation."""
        internal_names = [
            "OPTIMUS_LOCAL_GATEWAY_BIND_HOST",
            "OPTIMUS_LOCAL_GATEWAY_PORT",
            "OPTIMUS_ACP_DEBUG_TRACE",
            "OPTIMUS_ACP_DEBUG_LOG",
            "OPTIMUS_ACP_PROVENANCE_ROOT",
        ]
        for name in internal_names:
            policy = LAUNCH_VARIABLE_POLICIES[name]
            assert policy.tier == LaunchVariableTier.INTERNAL_ONLY, (
                f"{name} must be classified as INTERNAL_ONLY"
            )
            assert PropagationTarget.NEVER in policy.propagation, (
                f"{name} must have NEVER propagation"
            )


class TestMonotonicAndModelDecisions:
    """Boundary tests for monotonic limits and bounded model exception."""

    def test_default_live_max_cost_usd_is_quarter(self) -> None:
        assert DEFAULT_LIVE_MAX_COST_USD == Decimal("0.25")

    def test_default_max_planning_turns_is_three(self) -> None:
        assert DEFAULT_MAX_PLANNING_TURNS == 3

    def test_monotonic_cost_parser_accepts_valid_below_default(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LIVE_MAX_COST_USD"]
        result = policy.parser("0.10")
        assert result == Decimal("0.10")

    def test_monotonic_cost_parser_accepts_equal_to_default(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LIVE_MAX_COST_USD"]
        result = policy.parser("0.25")
        assert result == Decimal("0.25")

    def test_monotonic_cost_parser_rejects_zero(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LIVE_MAX_COST_USD"]
        with pytest.raises((ValueError, InvalidOperation)):
            policy.parser("0")

    def test_monotonic_cost_parser_rejects_negative(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LIVE_MAX_COST_USD"]
        with pytest.raises((ValueError, InvalidOperation)):
            policy.parser("-0.10")

    def test_monotonic_cost_parser_rejects_non_finite(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LIVE_MAX_COST_USD"]
        for bad in ("inf", "Infinity", "NaN", "nan"):
            with pytest.raises((ValueError, InvalidOperation)):
                policy.parser(bad)

    def test_monotonic_cost_parser_rejects_malformed(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LIVE_MAX_COST_USD"]
        with pytest.raises((ValueError, InvalidOperation)):
            policy.parser("not-a-number")

    def test_monotonic_turns_parser_accepts_valid_below_default(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_MAX_PLANNING_TURNS"]
        result = policy.parser("2")
        assert result == 2

    def test_monotonic_turns_parser_accepts_equal_to_default(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_MAX_PLANNING_TURNS"]
        result = policy.parser("3")
        assert result == 3

    def test_monotonic_turns_parser_rejects_zero(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_MAX_PLANNING_TURNS"]
        with pytest.raises(ValueError):
            policy.parser("0")

    def test_monotonic_turns_parser_rejects_negative(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_MAX_PLANNING_TURNS"]
        with pytest.raises(ValueError):
            policy.parser("-1")

    def test_monotonic_turns_parser_rejects_non_integer(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_MAX_PLANNING_TURNS"]
        with pytest.raises(ValueError):
            policy.parser("2.5")

    def test_model_is_operational_tier(self) -> None:
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_AGENT_MODEL"]
        assert policy.tier == LaunchVariableTier.OPERATIONAL

    @pytest.mark.parametrize(
        "credential_shaped_value",
        [
            "user:token@evil.example",
            "user:s3cr3t-token@evil.example/model",
            "redis://u:p@h",
            "http://user:pass@host/path",
            "x:y@z/model",
            "admin:hunter2@internal-gateway.example.com",
        ],
    )
    def test_model_parser_rejects_credential_shaped_values(self, credential_shaped_value: str) -> None:
        """Frozen contract, Tier 4 condition 4 (bounded-model exception):
        'The model value is logged only as non-secret configuration and
        cannot contain URI user information or credentials.' _parse_model
        must fail closed on a userinfo-shaped model string BEFORE it is
        ever displayed (_display_literal echoes it verbatim) or stored in
        model_observation/the approval record/the audit event — a value
        rejected at parse time never reaches those sinks. Covers both the
        schemed form (scheme://user:pass@host) AND the schemeless form
        (user:pass@host) deliberately: the sanitizer's existing
        _URL_USERINFO_RE requires a `\\w+://` scheme prefix and would MISS
        the schemeless case entirely, so this parser cannot simply reuse
        that regex as-is."""
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_AGENT_MODEL"]
        with pytest.raises(ValueError):
            policy.parser(credential_shaped_value)

    @pytest.mark.parametrize(
        "legitimate_model_value",
        [
            "claude-haiku-4-5",
            "claude-haiku",
            "anthropic/claude-3.5-sonnet",
            "openrouter/meta-llama/llama-3.1-70b",
            "gpt-4o",
            "gpt-4o-mini",
            "z-ai/glm-5.2",
            "ft:gpt-4o-mini:acme::abc123",
        ],
    )
    def test_model_parser_accepts_legitimate_model_names(self, legitimate_model_value: str) -> None:
        """Companion accept-matrix to the reject test above: the credential
        detection must not false-positive on real model identifiers,
        including slash-namespaced (provider/model), versioned
        (claude-3.5-sonnet), and fine-tune-suffixed (ft:...) forms — all of
        which contain '/' or ':' but no userinfo-shaped '<user>:<pass>@'
        segment."""
        policy = LAUNCH_VARIABLE_POLICIES["OPTIMUS_AGENT_MODEL"]
        result = policy.parser(legitimate_model_value)
        assert result == legitimate_model_value


class TestImmutableSnapshot:
    """LaunchEnvironmentSnapshot captures once and is immutable."""

    def test_capture_freezes_values(self) -> None:
        env = {"OPTIMUS_API_KEY": "secret", "PATH": "/usr/bin", "OTHER": "val"}
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        # The captured values are immutable — modifying the source dict has no effect.
        env["OPTIMUS_API_KEY"] = "changed"
        assert snapshot.values["OPTIMUS_API_KEY"] == "secret"

    def test_snapshot_values_are_readonly(self) -> None:
        env = {"OPTIMUS_API_KEY": "secret"}
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        with pytest.raises(TypeError):
            snapshot.values["new_key"] = "value"  # type: ignore[index]
