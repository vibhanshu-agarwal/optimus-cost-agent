"""Property-based oracle for the shared redactor `sanitize_for_persistence`.

Deterministic per the agreed trial settings. Generators emit only compatibility-v1-covered
credential forms (URI userinfo, Bearer, *_KEY/_SECRET/_TOKEN/_PASSWORD= env assignments, and
generic token/password/secret/credential/api_key assignments).

Oracle soundness (two defects fixed after review):
- Redaction is proven by the SPECIFIC rule firing in `rule_counts` plus the marker's presence --
  not by "secret not in output", which false-positives when the secret value coincides with a
  preserved field name (e.g. `password=password`). The secret is additionally a distinctive
  sentinel that cannot collide with any keyword/host, so the sentinel-absence check is sound too.
- Preservation is expressed as the INVARIANT "text is unchanged UNLESS some rule fired", over
  arbitrary text -- not "a benign-looking string is unchanged", which wrongly rejected a string
  like `bearer abcdefgh` that the policy correctly redacts. This still kills the degenerate
  `return "internal error"` (it changes text with no rule firing).

Target: the SHARED redactor `optimus_security.sanitization.sanitize_for_persistence`, distinct
from the thin ACP wrapper `optimus.acp.errors.sanitize_protocol_error_message`.
"""

from __future__ import annotations

import string

from hypothesis import example, given, settings
from hypothesis import strategies as st

from optimus_security.sanitization import sanitize_for_persistence

REDACTED = "**********"
SPIKE = settings(derandomize=True, database=None, max_examples=300, deadline=None)

# Distinctive sentinel: begins "Zx9" (uppercase-led), >=8 chars, alnum-only. It cannot equal a
# lowercase keyword ("password"/"token"/...), a host, or a scheme, so its absence from the output
# is an unambiguous signal the value was removed.
_secret = st.builds(
    lambda body: "Zx9" + body,
    body=st.text(alphabet=string.ascii_letters + string.digits, min_size=5, max_size=20),
)
_user = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=8)
_envbase = st.text(alphabet=string.ascii_uppercase + "_", min_size=0, max_size=6).map(lambda s: "A" + s)


@st.composite
def _covered_credential(draw):
    """Return (text, sentinel_secret, expected_rule_key) for one policy-covered credential."""
    secret = draw(_secret)
    kind = draw(st.sampled_from(["uri", "bearer", "bearer_hdr", "env", "generic"]))
    if kind == "uri":
        scheme = draw(st.sampled_from(["https", "http", "redis", "postgres"]))
        return f"connecting to {scheme}://{draw(_user)}:{secret}@host.example/db now", secret, "uri_userinfo_masking"
    if kind == "bearer":
        return f"call failed Bearer {secret} end", secret, "bearer_token_redaction"
    if kind == "bearer_hdr":
        return f"headers Authorization: Bearer {secret}", secret, "bearer_token_redaction"
    if kind == "env":
        suffix = draw(st.sampled_from(["_KEY", "_SECRET", "_TOKEN", "_PASSWORD"]))
        return f"env {draw(_envbase)}{suffix}={secret} set", secret, "env_assignment_redaction"
    kw = draw(st.sampled_from(["token", "password", "secret", "credential", "api_key", "api-key"]))
    sep = draw(st.sampled_from(["=", ": ", ":"]))
    return f"config {kw}{sep}{secret} ok", secret, "generic_secret_redaction"


@SPIKE
@given(_covered_credential())
# Fixed synthetic sentinel, never an operational credential; narrow URI scanner allowlist.
@example(("connecting to redis://u:Zx9ABCDEFG@host.example/db now", "Zx9ABCDEFG", "uri_userinfo_masking"))  # pragma: allowlist secret
@example(("env A_SECRET=Zx9TOKENvalue set", "Zx9TOKENvalue", "env_assignment_redaction"))
def test_covered_credential_fires_its_rule_and_removes_the_value(case):
    text, secret, rule = case
    result = sanitize_for_persistence(text)
    assert result.rule_counts.get(rule, 0) >= 1, f"{rule} did not fire on {text!r}: {result.rule_counts}"
    assert REDACTED in result.value, f"marker absent: {result.value!r}"
    assert secret not in result.value, f"sentinel value survived: {result.value!r}"


@SPIKE
@given(st.one_of(_covered_credential().map(lambda c: c[0]), st.text(max_size=200)))
def test_sanitization_is_idempotent(text):
    once = sanitize_for_persistence(text).value
    assert sanitize_for_persistence(once).value == once, "sanitization is not idempotent"


@SPIKE
@given(st.text(max_size=200))
def test_never_raises_on_arbitrary_text(text):
    sanitize_for_persistence(text)  # must not raise for any string


@SPIKE
@given(st.text(max_size=200))
@example("the quick brown fox jumps over the lazy dog")
def test_text_is_unchanged_unless_a_rule_fired(text):
    # Counter-CONSISTENCY: a change must be accompanied by a firing rule. Necessary but not
    # sufficient on its own -- a rule that WRONGLY fires on benign text and bumps its counter would
    # satisfy this. `test_known_benign_is_preserved_exactly` closes that gap, counter-agnostically.
    result = sanitize_for_persistence(text)
    if not result.rule_counts:
        assert result.value == text, "no rule fired, yet the text was altered (over-redaction / collapse)"


# Independently known-benign: a fixed vocabulary of safe words joined by spaces. None is a policy
# keyword (token/password/secret/credential/api/key/bearer), and the alphabet excludes ://, =, :, @,
# so NO compatibility rule can match. Preservation must therefore hold EXACTLY, regardless of any
# rule counter -- this catches an over-redaction that also increments a counter, which the
# counter-consistency check above would miss.
_SAFE_WORDS = [
    "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog", "hello", "world",
    "alpha", "beta", "gamma", "report", "value", "result", "done", "ready", "note", "item",
]
_known_benign = st.lists(st.sampled_from(_SAFE_WORDS), min_size=1, max_size=20).map(" ".join)


@SPIKE
@given(_known_benign)
@example("the quick brown fox jumps over the lazy dog")
def test_known_benign_is_preserved_exactly(text):
    result = sanitize_for_persistence(text)
    assert result.value == text, f"provably-benign text was altered: {result.value!r} (rules={dict(result.rule_counts)})"


def test_documented_counterexamples_behave_correctly():
    # The two review counterexamples, pinned with explicit expected outputs. Both are NON-benign --
    # the policy correctly redacts them -- which is exactly why neither may be used as a preservation
    # case (the original oracle's mistake).
    assert sanitize_for_persistence("bearer abcdefgh").value == "bearer **********"
    assert sanitize_for_persistence("config password=password ok").value == "config password=********** ok"
