"""Shared fake gateway helper for integration tests. Live Redis fixtures live in tests/conftest.py."""

from tests.conftest import FakeGatewayClient

__all__ = ["FakeGatewayClient"]
