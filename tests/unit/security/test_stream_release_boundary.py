"""A stream release never separates a pattern rule's label from its value (#622).

Before #622, ``StreamingTextSanitizer.feed()`` cut the pending text only so that it never split
an exact known secret. A cut between a label and its value released the label with nothing to
mask and the value with no label in front of it, so the value went out in clear while the
one-shot ``sanitize_for_persistence`` masked it.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evidence_handoff.redaction import text as text_mod
from evidence_handoff.redaction.models import Disposition
from optimus_security import sanitization
from optimus_security.sanitization import (
    COMPATIBILITY_SANITIZATION_POLICY,
    EVIDENCE_REDACTION_POLICY,
    MAX_STREAM_HOLD_CHARS,
    PathAliasRule,
    StreamHoldBackExceededError,
    StreamingTextSanitizer,
    sanitize_for_persistence,
)

_VALUE = "abc123x"

# One label per label-then-value rule: whitespace assignment (with and without copula or
# separator), generic assignment, bearer, env assignment, api-key header, x-api-key header.
_LABELS = (
    "password : ",
    "token is ",
    "token ",
    "password=",
    "Authorization: Bearer ",
    "Bearer ",
    "OPTIMUS_API_KEY=",
    "api_key: ",
    "x-api-key: ",
)


def _one_shot(text: str, policy) -> str:
    return sanitize_for_persistence(text, policy=policy).value


@pytest.mark.parametrize("label", _LABELS)
def test_a_default_overlap_cut_after_the_label_keeps_the_value_masked(label: str) -> None:
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY)
    head = "note " + label
    # The tentative cut lands exactly after ``head``: between the label and its value.
    text = head + _VALUE + " " * (stream.overlap_chars - len(_VALUE))
    out = stream.feed(text) + stream.finalize()
    assert _VALUE not in out
    assert out == _one_shot(text, EVIDENCE_REDACTION_POLICY)


@pytest.mark.parametrize("label", _LABELS)
def test_a_cut_inside_the_label_keeps_the_value_masked(label: str) -> None:
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY)
    head = "note " + label[: len(label) // 2]
    text = head + label[len(label) // 2 :] + _VALUE + " " * stream.overlap_chars
    text = text[: len(head) + stream.overlap_chars]
    out = stream.feed(text) + stream.finalize()
    assert _VALUE not in out
    assert out == _one_shot(text, EVIDENCE_REDACTION_POLICY)


def test_a_label_followed_by_whitespace_longer_than_the_overlap_waits_for_its_value() -> None:
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY)
    text = "note password" + " " * (stream.overlap_chars + 10)
    out = stream.feed(text)
    out += stream.feed(_VALUE + " tail") + stream.finalize()
    assert _VALUE not in out
    assert out == _one_shot(text + _VALUE + " tail", EVIDENCE_REDACTION_POLICY)


def test_a_value_that_is_also_a_label_does_not_hide_the_next_label() -> None:
    # Matched without overlaps, "password :  password" hides the second label from the boundary.
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY)
    head = "password= password :  password :  "
    text = head + _VALUE + " " * (stream.overlap_chars - len(_VALUE))
    out = stream.feed(text) + stream.finalize()
    assert _VALUE not in out
    assert out == _one_shot(text, EVIDENCE_REDACTION_POLICY)


def _cut_between(head: str, tail: str, **kwargs) -> tuple[str, str]:
    """Stream ``head + tail`` with the default overlap and the tentative cut exactly after ``head``."""
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY, **kwargs)
    text = head + tail + " " * (stream.overlap_chars - len(tail))
    oneshot_kwargs = {k: v for k, v in kwargs.items() if k in ("known_secrets", "known_pii", "path_aliases")}
    expected = sanitize_for_persistence(text, policy=EVIDENCE_REDACTION_POLICY, **oneshot_kwargs).value
    return stream.feed(text) + stream.finalize(), expected


_BACKSLASH = chr(92)
# Codex round 1 (#622): an earlier rule changes what a later rule matches, or the cut loses left context.
_RULE_ORDER_CASES = (
    pytest.param("note fixturepassword=", _VALUE, {"known_secrets": ["fixture"]}, id="secret-makes-a-word-boundary"),
    pytest.param("note fixturepassword=", _VALUE, {"known_pii": ["fixture"]}, id="pii-makes-a-word-boundary"),
    pytest.param("Bearer A_KEY= " + "A" * 2048 + "_KEY = ", _VALUE, {}, id="earlier-mask-exposes-a-long-label"),
    pytest.param(
        "note https:" + _BACKSLASH * 2 + "user:",
        _VALUE + "@host",
        {"path_aliases": [PathAliasRule(source_root="C:/no/such/root", alias="<root>")]},
        id="alias-normalizes-backslashes-into-a-uri",
    ),
    pytest.param(
        "note " + "m" * 244 + "AbCdEfGhIjK8",
        "LmNoPqRsT0Uv",
        {"known_secrets": ["m" * 244]},
        id="secret-removal-realigns-an-entropy-token",
    ),
    pytest.param("note " + chr(233), "%+@a.io", {}, id="cut-after-a-letter-before-an-email"),
    pytest.param("note model=", "sk-" + "a" * 16, {}, id="preserved-model-value"),
)


@pytest.mark.parametrize(("head", "tail", "kwargs"), _RULE_ORDER_CASES)
def test_a_cut_where_rule_order_or_left_context_matters_matches_one_shot(head: str, tail: str, kwargs) -> None:
    out, expected = _cut_between(head, tail, **kwargs)
    assert out == expected


def test_a_uri_whose_user_part_outlasts_the_overlap_keeps_its_password_masked() -> None:
    text = " https://" + "u" * 131_072 + ":" + _VALUE + "@host" + chr(10)
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY)
    out = "".join(stream.feed(text[i : i + 65_536]) for i in range(0, len(text), 65_536)) + stream.finalize()
    assert _VALUE not in out
    assert out == _one_shot(text, EVIDENCE_REDACTION_POLICY)


def test_a_match_longer_than_the_hold_back_limit_refuses_the_stream() -> None:
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY, max_secret_chars=8, max_hold_chars=64)
    assert stream.feed("note token=" + "a" * 40) == "note "
    with pytest.raises(StreamHoldBackExceededError):
        stream.feed("a" * 40)


def _artifact(tmp_path: Path, body: str, **kwargs) -> str:
    source = tmp_path / "note.txt"
    source.write_bytes(body.encode("utf-8"))
    staging = tmp_path / "staging"
    staging.mkdir()
    context = {"known_secrets": (), "known_pii": (), "path_aliases": (), **kwargs}
    result = text_mod.sanitize_text_artifact(
        source_path=source, staging_root=staging, artifact_role="session_note", **context
    )
    assert result.disposition is Disposition.PROMOTED
    assert result.staging_path is not None
    return result.staging_path.read_text(encoding="utf-8")


def test_a_text_artifact_with_a_match_past_the_hold_back_limit_is_sanitized_whole(tmp_path: Path) -> None:
    # A stream refuses this; an artifact is sanitized in one pass, so it is masked instead.
    body = "note token=" + "a" * (MAX_STREAM_HOLD_CHARS + 2 * 65_536)
    out = _artifact(tmp_path, body)
    assert out == _one_shot(body, EVIDENCE_REDACTION_POLICY)
    assert "a" * 16 not in out


def _at_default_cut(head: str, tail: str) -> str:
    """``head + tail`` placed so the cut between them falls at character 65,537, padded to 131,072 characters."""
    body = " " * (65_537 - len(head)) + head + tail
    return body + " " * max(0, 131_072 - len(body))


@pytest.mark.parametrize(
    ("head", "tail"),
    (
        # Codex round 2 (#622): a rule chain longer than any trial window, cut on either side of the run.
        ("Bearer A_KEY= B_KEY = " + " " * 9000, "abc123x"),
        ("Bearer A_KEY= B_KEY = ", " " * 9000 + "abc123x"),
        # An email whose start a stream would already have released.
        ("note a@", "b" * 131_072 + ".io"),
    ),
    ids=("chain-cut-after-run", "chain-cut-before-run", "long-email-domain"),
)
def test_a_text_artifact_equals_one_shot_where_a_stream_cut_cannot(tmp_path: Path, head: str, tail: str) -> None:
    body = _at_default_cut(head, tail)
    out = _artifact(tmp_path, body)
    assert "abc123x" not in out
    assert "b" * 64 not in out
    assert out == _one_shot(body, EVIDENCE_REDACTION_POLICY)


def test_a_text_artifact_with_secrets_pii_and_aliases_equals_one_shot(tmp_path: Path) -> None:
    context = {
        "known_secrets": ("fixture",),
        "known_pii": ("Zq9value",),
        "path_aliases": (PathAliasRule(source_root="C:/repo", alias="<repo>"),),
    }
    body = _at_default_cut("fixturepassword : Zq9value C:" + _BACKSLASH + "repo" + _BACKSLASH + "f ", "token is abc123x")
    out = _artifact(tmp_path, body, **context)
    assert out == sanitize_for_persistence(body, policy=EVIDENCE_REDACTION_POLICY, **context).value


@settings(derandomize=True, database=None, max_examples=2000, deadline=None)
@given(st.lists(st.sampled_from(("a", "b", ".", "_", "%", "+", "-", "9", "@", " ", chr(233), "co", "io", "x.y")), max_size=40))
def test_linear_email_masking_equals_the_email_regex(parts: list[str]) -> None:
    text = "".join(parts)
    masked = sanitization._mask_emails(text)
    assert (text if masked is None else masked) == sanitization._EMAIL_RE.sub(sanitization._REDACTED, text)
    assert (masked is not None) == bool(sanitization._EMAIL_RE.search(text))


def test_email_masking_is_linear_on_a_dotted_run() -> None:
    # The email regex alone retries every word boundary of the run: about three minutes here on the old rule.
    text = "a." * 2**18 + "@x"
    started = time.perf_counter()
    assert sanitization._mask_emails(text) is None
    assert time.perf_counter() - started < 10.0


@settings(derandomize=True, database=None, max_examples=2000, deadline=None)
@given(needle=st.text(alphabet="ab", min_size=1, max_size=6), text=st.text(alphabet="ab", max_size=40))
def test_occurrence_runs_equal_the_search_from_each_occurrence(needle: str, text: str) -> None:
    # The pre-#622 loop: search again from each occurrence plus one, merging overlapping (not touching) ones.
    expected: list[tuple[int, int]] = []
    idx = text.find(needle)
    while idx != -1:
        if expected and idx < expected[-1][1]:
            expected[-1] = (expected[-1][0], idx + len(needle))
        else:
            expected.append((idx, idx + len(needle)))
        idx = text.find(needle, idx + 1)
    assert sanitization._occurrence_runs(text, needle, sanitization._smallest_period(needle)) == expected


@pytest.mark.parametrize("label", ("password : ", "token is ", "password=", "OPTIMUS_API_KEY="))
def test_a_text_artifact_cut_after_the_label_keeps_the_value_masked(tmp_path: Path, label: str) -> None:
    overlap = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY).overlap_chars
    head = "note " + label
    body = head + _VALUE + " " * (overlap - len(_VALUE)) + "\ntrailer\n"
    source = tmp_path / "note.txt"
    source.write_bytes(body.encode("utf-8"))
    staging = tmp_path / "staging"
    staging.mkdir()
    result = text_mod.sanitize_text_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        # The first read's tentative cut lands exactly after ``head``.
        read_size=len(head) + overlap,
    )
    assert result.disposition is Disposition.PROMOTED
    assert result.staging_path is not None
    out = result.staging_path.read_text(encoding="utf-8")
    assert _VALUE not in out
    assert out == _one_shot(body, EVIDENCE_REDACTION_POLICY)


def test_an_exact_secret_after_a_label_still_holds_back() -> None:
    secret = "Zq7-known-value-Zq7"  # pragma: allowlist secret
    stream = StreamingTextSanitizer(known_secrets=[secret], max_secret_chars=len(secret))
    text = "password=" + secret + " tail"
    out = "".join(stream.feed(ch) for ch in text) + stream.finalize()
    assert secret not in out
    assert out == sanitize_for_persistence(text, known_secrets=[secret]).value


_WORDS = ("note", "the", "run", "ok", "done", "abc123x", "Zq9value", "42", "a.b", ":", "=", "is")
# Pieces where one-shot rule order or left context matters (Codex round 1, #622).
_ORDER_PIECES = (
    "fixture",
    "https:" + _BACKSLASH * 2 + "u:",
    "@host",
    "C:" + _BACKSLASH + "repo" + _BACKSLASH + "f",
    chr(233),
    "%+@a.io",
    "model=",
    "sk-" + "a" * 16,
    "AbCdEfGhIjK8LmNoPqRsT0Uv",  # pragma: allowlist secret
)
_PIECES = st.one_of(st.sampled_from(_WORDS), st.sampled_from(_LABELS), st.sampled_from(_ORDER_PIECES))
# The overlap below is at least as long as any label plus value here; the long run is longer than the overlap,
# so a label followed by it reaches the end of the buffer before its value arrives. The empty separator glues
# pieces, so a replaced secret or an alias can change what the next piece matches.
_MIN_OVERLAP = 32
_SEPARATORS = st.sampled_from(("", " ", "  ", chr(10), chr(9), " " * (_MIN_OVERLAP + 9)))
_CONTEXTS = (
    {},
    {
        "known_secrets": ["fixture"],
        "known_pii": ["Zq9value"],
        "path_aliases": [PathAliasRule(source_root="C:/repo", alias="<repo>")],
    },
)


@st.composite
def _label_value_texts(draw) -> str:
    parts = draw(st.lists(st.tuples(_PIECES, _SEPARATORS), min_size=1, max_size=12))
    return "".join(piece + sep for piece, sep in parts)


@settings(derandomize=True, database=None, max_examples=400, deadline=None)
@given(
    text=_label_value_texts(),
    overlap=st.integers(min_value=_MIN_OVERLAP, max_value=_MIN_OVERLAP + 8),
    policy=st.sampled_from((EVIDENCE_REDACTION_POLICY, COMPATIBILITY_SANITIZATION_POLICY)),
    context=st.sampled_from(_CONTEXTS),
)
def test_streaming_equals_one_shot_at_every_cut_position(text: str, overlap: int, policy, context) -> None:
    expected = sanitize_for_persistence(text, policy=policy, **context).value

    def stream() -> StreamingTextSanitizer:
        return StreamingTextSanitizer(policy=policy, max_secret_chars=overlap + 1, **context)

    # One character per feed: every position in the text is offered as a release cut.
    one_by_one = stream()
    assert "".join(one_by_one.feed(ch) for ch in text) + one_by_one.finalize() == expected
    # Two feeds: the cut is offered at each position in turn.
    for cut in range(len(text) + 1):
        two = stream()
        assert two.feed(text[:cut]) + two.feed(text[cut:]) + two.finalize() == expected
