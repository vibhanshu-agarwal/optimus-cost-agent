from __future__ import annotations

from urllib.parse import urlparse


def https_hostname(url: str) -> str | None:
    """Return the lowercased HTTPS hostname, or None when the URL is not HTTPS."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname is None:
        return None
    return parsed.hostname.lower().rstrip(".")
