from __future__ import annotations

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.tool_handlers import GatewayToolDependencies
from optimus_gateway.tool_policy import GatewayToolPolicy
from optimus_gateway.tool_providers import (
    OsvAdvisoryToolProvider,
    PackageRegistryToolProvider,
    TavilyWebToolProvider,
)
from optimus_gateway.tool_state import RedisGatewayToolStateStore
from optimus_gateway.upstream_client import UpstreamClient, UrllibAnthropicClient, UrllibOpenAICompatibleClient


def build_upstream_client(config: GatewayServiceConfig) -> UpstreamClient:
    if config.provider == "anthropic":
        return UrllibAnthropicClient(api_key=config.provider_api_key)
    if config.base_url is None:
        raise ValueError(f"base_url is required for provider {config.provider!r}")
    return UrllibOpenAICompatibleClient(api_key=config.provider_api_key, base_url=config.base_url)


def build_tool_dependencies(config: GatewayServiceConfig) -> GatewayToolDependencies | None:
    """Build the Gateway-side tool provider bundle from config.

    Incomplete tool configuration fails closed by returning ``None`` so the
    Gateway does not expose a partially configured provider bundle.
    """
    tavily_api_key = (config.tavily_api_key or "").strip()
    tool_redis_url = (config.tool_redis_url or "").strip()
    allowed_domains = tuple(
        domain for domain in (_normalize_domain(value) for value in config.tool_allowed_domains) if domain
    )
    if not tavily_api_key or not tool_redis_url or not allowed_domains:
        return None

    return GatewayToolDependencies(
        web_provider=TavilyWebToolProvider(
            api_key=tavily_api_key,
            base_url=(config.tavily_base_url or "https://api.tavily.com").strip() or "https://api.tavily.com",
        ),
        package_provider=PackageRegistryToolProvider(
            pypi_base_url=(config.pypi_base_url or "https://pypi.org").strip() or "https://pypi.org",
            npm_base_url=(config.npm_base_url or "https://registry.npmjs.org").strip()
            or "https://registry.npmjs.org",
            maven_base_url=(config.maven_base_url or "https://repo1.maven.org/maven2").strip()
            or "https://repo1.maven.org/maven2",
        ),
        advisory_provider=OsvAdvisoryToolProvider(
            base_url=(config.osv_base_url or "https://api.osv.dev").strip() or "https://api.osv.dev",
            api_key=(config.osv_api_key.strip() if config.osv_api_key else None) or None,
        ),
        policy=GatewayToolPolicy(allowed_domains=allowed_domains),
        state_store=RedisGatewayToolStateStore.from_url(tool_redis_url),
        max_calls_per_tool=config.tool_max_calls_per_tool,
    )


def _normalize_domain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().rstrip(".")
