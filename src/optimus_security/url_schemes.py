"""URL admission for the repository's urllib transports."""

from collections.abc import Callable
from functools import cache
from http.client import HTTPMessage
from typing import IO, Any
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPDefaultErrorHandler,
    HTTPErrorProcessor,
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    UnknownHandler,
)

_HTTP_SCHEMES = frozenset({"http", "https"})
_HTTPS_SCHEMES = frozenset({"https"})


class URLPolicyError(ValueError):
    """A destination was refused before its URL could be opened."""


def url_uses_allowed_scheme(value: str, *, allowed_schemes: frozenset[str]) -> bool:
    # urllib strips some raw characters before parsing. Reject ambiguous input
    # and require a complete network URL rather than accepting a scheme alone.
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        return False
    try:
        parts = urlsplit(value)
        return parts.scheme in allowed_schemes and bool(parts.hostname) and (parts.port is None or parts.port > 0)
    except ValueError:
        return False


def http_url_allowed(value: str) -> bool:
    return url_uses_allowed_scheme(value, allowed_schemes=_HTTP_SCHEMES)


def https_url_allowed(value: str) -> bool:
    return url_uses_allowed_scheme(value, allowed_schemes=_HTTPS_SCHEMES)


class _SchemeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allows: Callable[[str], bool]) -> None:
        self._allows = allows

    def http_error_302(self, req: Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> Any:
        # Refuse the destination before urllib can copy an untrusted Location to
        # an exception. urllib still owns URL quoting, method changes and limits.
        location = headers.get("location", headers.get("uri"))
        if location is not None:
            try:
                admitted = self._allows(urljoin(req.full_url, location.replace(" ", "%20")))
            except ValueError:
                admitted = False
            if not admitted:
                fp.close()
                raise URLPolicyError("redirect destination rejected by scheme policy")
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def redirect_request(self, req: Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage, newurl: str) -> Request | None:
        if not self._allows(newurl):
            fp.close()
            raise URLPolicyError("redirect destination rejected by scheme policy")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_http_opener(
    *,
    redirects: Callable[[str], bool] | None,
    http_handler: HTTPHandler | None = None,
    https_handler: HTTPSHandler | None = None,
    proxy_handler: ProxyHandler | None = None,
) -> OpenerDirector:
    """Assemble only HTTP(S) handlers, with the caller's redirect policy."""
    opener = OpenerDirector()
    for handler in (
        proxy_handler if proxy_handler is not None else ProxyHandler(),
        UnknownHandler(),
        http_handler if http_handler is not None else HTTPHandler(),
        https_handler if https_handler is not None else HTTPSHandler(),
        HTTPDefaultErrorHandler(),
        HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    if redirects is not None:
        opener.add_handler(_SchemeRedirectHandler(redirects))
    return opener


@cache
def _http_opener() -> OpenerDirector:
    return build_http_opener(redirects=http_url_allowed)


def open_http_url(request: Request | str, *, timeout: float) -> Any:
    url = request.full_url if isinstance(request, Request) else request
    if not http_url_allowed(url):
        raise URLPolicyError("URL must use HTTP or HTTPS")
    return _http_opener().open(request, timeout=timeout)
