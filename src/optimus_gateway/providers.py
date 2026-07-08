from __future__ import annotations

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.upstream_client import UpstreamClient, UrllibAnthropicClient, UrllibOpenAICompatibleClient


def build_upstream_client(config: GatewayServiceConfig) -> UpstreamClient:
    if config.provider == "anthropic":
        return UrllibAnthropicClient(api_key=config.provider_api_key)
    if config.base_url is None:
        raise ValueError(f"base_url is required for provider {config.provider!r}")
    return UrllibOpenAICompatibleClient(api_key=config.provider_api_key, base_url=config.base_url)
