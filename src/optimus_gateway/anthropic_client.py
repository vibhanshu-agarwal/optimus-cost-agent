"""Backward-compatible re-exports; prefer optimus_gateway.upstream_client."""

from optimus_gateway.upstream_client import (
    ProviderMessageResult as AnthropicMessageResult,
)
from optimus_gateway.upstream_client import (
    UpstreamClient as AnthropicClient,
)
from optimus_gateway.upstream_client import (
    UrllibAnthropicClient,
)

__all__ = ["AnthropicClient", "AnthropicMessageResult", "UrllibAnthropicClient"]
