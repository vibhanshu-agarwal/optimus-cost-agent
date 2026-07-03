from __future__ import annotations


class GatewayError(Exception):
    """Base class for Optimus Gateway failures."""


class GatewayHttpError(GatewayError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class GatewayResponseError(GatewayError):
    """Raised when a gateway response is malformed or missing required usage."""
