"""#681: the Gateway child manifest binds the provider base URL by keyed fingerprint, since it travels on the command line.
Synthetic values only."""

from __future__ import annotations

import json

import pytest

from optimus_security.launch_manifest import (
    LaunchManifestError,
    build_gateway_child_manifest,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)

_KEY = b"k" * 32
_PW = "synthpw" + "q" * 14
_URL = f"https://user:{_PW}@gw-synthetic.example/v1?api_key={_PW}"
_CREDS = {"provider_api_key": "sk-or-v1-" + "c" * 24, "shared_secret": "shared-" + "s" * 24}  # pragma: allowlist secret


def _serialized(base_url: str | None, *, key: bytes = _KEY) -> str:
    return serialize_gateway_child_manifest(build_gateway_child_manifest(
        workspace_digest="a" * 64, security_snapshot_digest="b" * 64, provider="openrouter", base_url=base_url,
        bind_host="127.0.0.1", bind_port=8765, hmac_key=key, policy_version="P9.99-v1", **_CREDS,
    ))


def _verify(serialized: str, base_url: str | None) -> None:
    verify_gateway_child_manifest(serialized, hmac_key=_KEY, provider="openrouter", base_url=base_url,
                                  bind_host="127.0.0.1", bind_port=8765, **_CREDS)


def test_the_serialized_manifest_names_no_part_of_the_url_and_still_verifies() -> None:
    serialized = _serialized(_URL)
    assert "gw-synthetic" not in serialized and _PW not in serialized and "base_url\"" not in serialized
    _verify(serialized, _URL)


def test_the_fingerprint_is_keyed() -> None:
    """A digest anyone could compute would let a guessed host be confirmed from the command line."""
    one, other = (json.loads(_serialized(_URL, key=key))["base_url_fingerprint"] for key in (_KEY, b"o" * 32))
    assert one != other


@pytest.mark.parametrize(("signed", "actual"), [(_URL, _URL + "x"), (_URL, _URL + "/"), (_URL, None), (None, _URL)])
def test_a_different_base_url_refuses_without_either_value(signed: str | None, actual: str | None) -> None:
    with pytest.raises(LaunchManifestError) as caught:
        _verify(_serialized(signed), actual)
    assert caught.value.code == "MANIFEST_BASE_URL_MISMATCH" and str(caught.value) == "MANIFEST_BASE_URL_MISMATCH"


def test_no_base_url_on_either_side_verifies() -> None:
    _verify(_serialized(None), None)


def test_a_manifest_in_the_earlier_plaintext_format_is_refused_as_corrupt() -> None:
    data = json.loads(_serialized(_URL))
    data.pop("base_url_fingerprint")
    data.update(base_url=_URL, schema_version=1)
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _URL)
    assert caught.value.code == "MANIFEST_CORRUPT"
    assert _PW not in str(caught.value)


@pytest.mark.parametrize("extra", [{"base_url": _URL}, {"model_registry": None}, {"unsigned": "x"}])
def test_a_field_the_signature_does_not_cover_is_refused_as_corrupt(extra: dict[str, object]) -> None:
    """Codex round 1: an otherwise valid manifest carrying the old plaintext base_url beside its fingerprint verified."""
    data = {**json.loads(_serialized(_URL)), **extra}
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _URL)
    assert caught.value.code == "MANIFEST_CORRUPT" and _PW not in str(caught.value)


def test_a_non_string_fingerprint_is_refused_as_corrupt() -> None:
    data = json.loads(_serialized(_URL))
    data["base_url_fingerprint"] = 7
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _URL)
    assert caught.value.code == "MANIFEST_CORRUPT"
