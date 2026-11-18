from collections.abc import Callable
from http.client import HTTPMessage
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import HTTPHandler, HTTPSHandler, ProxyHandler, Request
from urllib.response import addinfourl

import pytest

from optimus_gateway.upstream_client import _model_url_allowed
from optimus_security.url_schemes import URLPolicyError, build_http_opener, http_url_allowed, https_url_allowed, url_uses_allowed_scheme


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("HTTPS://fixture.invalid:443/a%20b", True),
        ("http://127.0.0.1/a", True),
        ("https://[::1]", True),
        ("policy-test://fixture.invalid", False),
        ("//fixture.invalid", False),
        ("https:///missing-authority", False),
        ("https://[malformed", False),
        ("https://fixture.invalid:bad-port", False),
        ("https://fixture.invalid:65536", False),
        ("ht\ttps://fixture.invalid", False),
        (" https://fixture.invalid", False),
        ("", False),
    ],
)
def test_allowed_scheme_parses_a_complete_url(value: str, accepted: bool) -> None:
    assert url_uses_allowed_scheme(value, allowed_schemes=frozenset({"http", "https"})) is accepted


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("http://127.0.0.2", True),
        ("http://LOCALHOST:8080", True),
        ("http://[::1]:8080", True),
        ("http://localhost.fixture.invalid", False),
        ("http://127.0.0.1.fixture.invalid", False),
        ("http://127.1", False),
        ("http://[2001:db8::1]", False),
        ("https://fixture.invalid", True),
    ],
)
def test_plain_http_model_upstreams_require_an_explicit_loopback(value: str, accepted: bool) -> None:
    assert _model_url_allowed(value) is accepted


class _ScriptedResponse:
    def __init__(self, location: str) -> None:
        self.location = location
        self.calls: list[tuple[str, str]] = []

    def open(self, request: Request) -> addinfourl:
        self.calls.append((request.full_url, request.get_method()))
        headers = HTTPMessage()
        status = 200
        if len(self.calls) == 1:
            status = 302
            headers["Location"] = self.location
        response = addinfourl(BytesIO(b"ok"), headers, request.full_url, status)
        response.msg = "fixture"
        return response


class _ScriptedHTTPHandler(HTTPHandler):
    def __init__(self, script: _ScriptedResponse) -> None:
        self.http_open = script.open


class _ScriptedHTTPSHandler(HTTPSHandler):
    def __init__(self, script: _ScriptedResponse) -> None:
        self.https_open = script.open


def _opener(script, redirects):
    return build_http_opener(
        redirects=redirects,
        http_handler=_ScriptedHTTPHandler(script),
        https_handler=_ScriptedHTTPSHandler(script),
        proxy_handler=ProxyHandler({}),
    )


@pytest.mark.parametrize(
    ("allows", "origin", "redirect"),
    [
        (http_url_allowed, "http://fixture.invalid/start", "/next"),
        (http_url_allowed, "http://fixture.invalid/start", "https://fixture.invalid/next"),
        (_model_url_allowed, "http://127.0.0.1/start", "/next"),
        (https_url_allowed, "https://fixture.invalid/start", "/next"),
    ],
)
def test_allowed_redirect_preserves_urllib_method_rules(allows: Callable[[str], bool], origin: str, redirect: str) -> None:
    script = _ScriptedResponse(redirect)
    with _opener(script, allows).open(Request(origin, data=b"{}", method="POST"), timeout=1) as response:
        assert response.read() == b"ok"
    assert script.calls[0] == (origin, "POST")
    assert script.calls[1][0].endswith("/next")
    assert script.calls[1][1] == "GET"


@pytest.mark.parametrize(
    ("allows", "origin", "redirect"),
    [
        (http_url_allowed, "http://fixture.invalid/start", "policy-test://fixture.invalid/not-disclosed"),
        (_model_url_allowed, "https://fixture.invalid/start", "http://fixture.invalid/not-disclosed"),
        (https_url_allowed, "https://fixture.invalid/start", "http://127.0.0.1/not-disclosed"),
        (https_url_allowed, "https://fixture.invalid/start", "https://[not-disclosed"),
    ],
)
def test_rejected_redirect_does_not_invoke_the_next_handler(allows: Callable[[str], bool], origin: str, redirect: str) -> None:
    script = _ScriptedResponse(redirect)
    with pytest.raises(URLPolicyError, match=r"^redirect destination rejected by scheme policy$"):
        _opener(script, allows).open(Request(origin), timeout=1)
    assert script.calls == [(origin, "GET")]


def test_one_shot_opener_surfaces_redirect_without_dispatching_it() -> None:
    script = _ScriptedResponse("/next")
    with pytest.raises(HTTPError) as raised:
        _opener(script, None).open(Request("https://fixture.invalid/start"), timeout=1)
    assert raised.value.code == 302
    raised.value.close()
    assert script.calls == [("https://fixture.invalid/start", "GET")]
