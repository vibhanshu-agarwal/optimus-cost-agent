from __future__ import annotations

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.tool_handlers import GatewayToolDependencies
from optimus_gateway.upstream_client import UpstreamClient, UrllibAnthropicClient, UrllibOpenAICompatibleClient


def build_upstream_client(config: GatewayServiceConfig) -> UpstreamClient:
    if config.provider == "anthropic":
        return UrllibAnthropicClient(api_key=config.provider_api_key)
    if config.base_url is None:
        raise ValueError(f"base_url is required for provider {config.provider!r}")
    return UrllibOpenAICompatibleClient(api_key=config.provider_api_key, base_url=config.base_url)


def build_tool_dependencies(config: GatewayServiceConfig) -> GatewayToolDependencies | None:
    """Build the Gateway-side tool provider bundle from config.

    ``GatewayServiceConfig`` carries no Tavily/OSV/package-registry
    credentials or policy configuration yet (a future task adds them), so
    this always returns ``None`` for now. ``serve_gateway`` leaves the four
    ``/v1/tools/*`` routes unserved (404) whenever no dependencies are
    configured here or injected directly by a caller (e.g. tests).
    """
    del config
    return None
