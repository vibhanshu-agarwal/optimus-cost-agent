from __future__ import annotations

import ast
import inspect

import pytest

import optimus_gateway.providers as providers
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.providers import build_tool_dependencies, build_upstream_client
from optimus_gateway.tool_policy import GatewayToolPolicy
from optimus_gateway.upstream_client import UrllibOpenAICompatibleClient


def _openrouter_config(**overrides: object) -> GatewayServiceConfig:
    fields: dict[str, object] = {
        "bind_host": "127.0.0.1",
        "bind_port": 8765,
        "shared_secret": "secret",
        "provider": "openrouter",
        "provider_api_key": "provider-key",
        "base_url": "https://openrouter.ai/api/v1",
        "tavily_api_key": "tavily-key",
        "tool_allowed_domains": ("python.org",),
        "tool_redis_url": "redis://localhost/0",
    }
    fields.update(overrides)
    return GatewayServiceConfig(**fields)


def test_build_upstream_client_uses_openai_compatible_client_for_openrouter() -> None:
    client = build_upstream_client(_openrouter_config())

    assert isinstance(client, UrllibOpenAICompatibleClient)


def test_build_upstream_client_constructs_only_openai_compatible_upstream_class() -> None:
    source = inspect.getsource(providers.build_upstream_client)
    tree = ast.parse(source)
    constructed_clients: set[str] = set()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name) and call.func.id.endswith("Client"):
            constructed_clients.add(call.func.id)
        elif isinstance(call.func, ast.Attribute) and call.func.attr.endswith("Client"):
            constructed_clients.add(call.func.attr)

    assert constructed_clients == {"UrllibOpenAICompatibleClient"}


@pytest.mark.parametrize(
    "missing_field",
    ("tavily_api_key", "tool_allowed_domains", "tool_redis_url"),
)
def test_build_tool_dependencies_fails_closed_when_required_field_missing(
    missing_field: str,
) -> None:
    config = _openrouter_config(**{missing_field: None if missing_field != "tool_allowed_domains" else ()})

    assert build_tool_dependencies(config) is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("tavily_api_key", "   "),
        ("tool_redis_url", " \t "),
        ("tool_allowed_domains", ("  ",)),
        ("tool_allowed_domains", ("", "   ")),
    ),
)
def test_build_tool_dependencies_fails_closed_on_whitespace_required_fields(
    field: str,
    value: object,
) -> None:
    assert build_tool_dependencies(_openrouter_config(**{field: value})) is None


def test_build_tool_dependencies_wires_all_providers_and_gateway_controls(monkeypatch) -> None:
    sentinel_store = object()
    monkeypatch.setattr(
        "optimus_gateway.providers.RedisGatewayToolStateStore.from_url",
        lambda url: sentinel_store,
    )

    dependencies = build_tool_dependencies(
        _openrouter_config(
            tavily_base_url="https://tavily.example",
            osv_base_url="https://osv.example",
            osv_api_key="osv-key",
            pypi_base_url="https://pypi.example",
            npm_base_url="https://npm.example",
            maven_base_url="https://maven.example",
            tool_max_calls_per_tool=3,
        )
    )

    assert dependencies is not None
    assert type(dependencies.web_provider).__name__ == "TavilyWebToolProvider"
    assert type(dependencies.package_provider).__name__ == "PackageRegistryToolProvider"
    assert type(dependencies.advisory_provider).__name__ == "OsvAdvisoryToolProvider"
    assert isinstance(dependencies.policy, GatewayToolPolicy)
    assert dependencies.state_store is sentinel_store
    assert dependencies.max_calls_per_tool == 3


def test_build_tool_dependencies_uses_gateway_provider_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        "optimus_gateway.providers.RedisGatewayToolStateStore.from_url",
        lambda url: object(),
    )

    dependencies = build_tool_dependencies(_openrouter_config())

    assert dependencies is not None
    assert dependencies.web_provider.base_url == "https://api.tavily.com"
    assert dependencies.package_provider.pypi_base_url == "https://pypi.org"
    assert dependencies.package_provider.npm_base_url == "https://registry.npmjs.org"
    assert dependencies.package_provider.maven_base_url == "https://repo1.maven.org/maven2"
    assert dependencies.advisory_provider.base_url == "https://api.osv.dev"


def test_from_env_loads_gateway_tool_fields() -> None:
    config = GatewayServiceConfig.from_env(
        {
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "secret",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "provider-key",
            "TAVILY_API_KEY": "tavily-key",
            "OPTIMUS_GATEWAY_TAVILY_BASE_URL": "https://tavily.example",
            "OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS": "python.org, pypi.org ",
            "OPTIMUS_GATEWAY_TOOL_REDIS_URL": "redis://localhost/1",
            "OPTIMUS_GATEWAY_OSV_BASE_URL": "https://osv.example",
            "OPTIMUS_GATEWAY_OSV_API_KEY": "osv-key",
            "OPTIMUS_GATEWAY_PYPI_BASE_URL": "https://pypi.example",
            "OPTIMUS_GATEWAY_NPM_BASE_URL": "https://npm.example",
            "OPTIMUS_GATEWAY_MAVEN_BASE_URL": "https://maven.example",
            "OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL": "7",
        },
        bind_host="127.0.0.1",
        bind_port=8765,
    )

    assert config.tavily_api_key == "tavily-key"
    assert config.tavily_base_url == "https://tavily.example"
    assert config.tool_allowed_domains == ("python.org", "pypi.org")
    assert config.tool_redis_url == "redis://localhost/1"
    assert config.osv_base_url == "https://osv.example"
    assert config.osv_api_key == "osv-key"
    assert config.pypi_base_url == "https://pypi.example"
    assert config.npm_base_url == "https://npm.example"
    assert config.maven_base_url == "https://maven.example"
    assert config.tool_max_calls_per_tool == 7


def test_from_env_uses_tool_defaults_when_optional_fields_are_omitted() -> None:
    config = GatewayServiceConfig.from_env(
        {
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "secret",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "provider-key",
        },
        bind_host="127.0.0.1",
        bind_port=8765,
    )

    assert config.tavily_api_key is None
    assert config.tavily_base_url is None
    assert config.tool_allowed_domains == ()
    assert config.tool_redis_url is None
    assert config.osv_base_url is None
    assert config.osv_api_key is None
    assert config.pypi_base_url is None
    assert config.npm_base_url is None
    assert config.maven_base_url is None
    assert config.tool_max_calls_per_tool == 5
