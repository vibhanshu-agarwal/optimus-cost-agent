from __future__ import annotations

from urllib.parse import urlparse


def https_hostname(url: str) -> str | None:
    """Return the lowercased HTTPS hostname, or None when the URL is not HTTPS."""
    try:
        parsed = urlparse(url)
        parsed.port  # noqa: B018
    except ValueError:  # #603: a host or port the parser rejects (an unclosed bracket, port 65536) is no host
        return None
    if parsed.scheme != "https" or parsed.hostname is None:
        return None
    return parsed.hostname.lower().rstrip(".")
