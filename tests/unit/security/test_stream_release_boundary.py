"""A stream release never separates a pattern rule's label from its value (#622).

Before #622, ``StreamingTextSanitizer.feed()`` cut the pending text only so that it never split
an exact known secret. A cut between a label and its value released the label with nothing to
mask and the value with no label in front of it, so the value went out in clear while the
one-shot ``sanitize_for_persistence`` masked it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evidence_handoff.redaction import text as text_mod
from evidence_handoff.redaction.models import Disposition
from optimus_security.sanitization import (
    COMPATIBILITY_SANITIZATION_POLICY,
    EVIDENCE_REDACTION_POLICY,
    MAX_STREAM_HOLD_CHARS,
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


def test_a_match_longer_than_the_hold_back_limit_refuses_the_stream() -> None:
    stream = StreamingTextSanitizer(policy=EVIDENCE_REDACTION_POLICY, max_secret_chars=8, max_hold_chars=64)
    assert stream.feed("note token=" + "a" * 40) == "note "
    with pytest.raises(StreamHoldBackExceededError):
        stream.feed("a" * 40)


def test_a_text_artifact_with_a_match_past_the_hold_back_limit_is_quarantined(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_bytes(("note token=" + "a" * (MAX_STREAM_HOLD_CHARS + 2 * 65_536)).encode("utf-8"))
    staging = tmp_path / "staging"
    staging.mkdir()
    result = text_mod.sanitize_text_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "text_match_too_long"
    assert list(staging.iterdir()) == []


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
_PIECES = st.one_of(st.sampled_from(_WORDS), st.sampled_from(_LABELS))
# The overlap below is at least as long as any label plus value here; the long run is longer than the overlap,
# so a label followed by it reaches the end of the buffer before its value arrives.
_MIN_OVERLAP = 32
_SEPARATORS = st.sampled_from((" ", "  ", "\n", "\t", " " * (_MIN_OVERLAP + 9)))


@st.composite
def _label_value_texts(draw) -> str:
    parts = draw(st.lists(st.tuples(_PIECES, _SEPARATORS), min_size=1, max_size=12))
    return "".join(piece + sep for piece, sep in parts)


@settings(derandomize=True, database=None, max_examples=300, deadline=None)
@given(
    text=_label_value_texts(),
    overlap=st.integers(min_value=_MIN_OVERLAP, max_value=_MIN_OVERLAP + 8),
    policy=st.sampled_from((EVIDENCE_REDACTION_POLICY, COMPATIBILITY_SANITIZATION_POLICY)),
)
def test_streaming_equals_one_shot_at_every_cut_position(text: str, overlap: int, policy) -> None:
    expected = _one_shot(text, policy)
    # One character per feed: every position in the text is offered as a release cut.
    stream = StreamingTextSanitizer(policy=policy, max_secret_chars=overlap + 1)
    assert "".join(stream.feed(ch) for ch in text) + stream.finalize() == expected
    # Two feeds: the cut is offered at each position in turn.
    for cut in range(len(text) + 1):
        stream = StreamingTextSanitizer(policy=policy, max_secret_chars=overlap + 1)
        assert stream.feed(text[:cut]) + stream.feed(text[cut:]) + stream.finalize() == expected
