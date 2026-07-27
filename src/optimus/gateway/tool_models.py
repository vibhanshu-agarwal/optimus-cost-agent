"""Shared typed-tool contracts for Gateway-backed web, package, and advisory tools.

These frozen Pydantic v2 models are the common wire contract between the local
agent client and the Optimus Gateway (Plan 11.2, ``P11-FEAT-GATEWAY-TOOLS``).
Package/advisory and web-extract text is untrusted data: it is never executed,
followed, or promoted to policy. ``gateway_usage`` is always parsed from the
canonical :class:`~optimus.gateway.models.GatewayUsage` model; this module never
estimates tokens, credits, or dollars.
"""
from __future__ import annotations

from typing import Annotated, Any, Generic, Literal, Mapping, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    model_validator,
)

from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage, parse_gateway_usage
from optimus.tools.policy import ToolClass, ToolPolicySignal

PackageEcosystem = Literal["pypi", "npm", "maven"]


def _require_https(url: HttpUrl) -> HttpUrl:
    if url.scheme != "https":
        raise ValueError("URL must use https")
    return url


HttpsUrl = Annotated[HttpUrl, AfterValidator(_require_https)]


def _reject_duplicate_urls(urls: tuple[HttpsUrl, ...]) -> tuple[HttpsUrl, ...]:
    seen: set[str] = set()
    for url in urls:
        text = str(url)
        if text in seen:
            raise ValueError(f"duplicate URL: {text}")
        seen.add(text)
    return urls


class GatewayToolContext(BaseModel):
    """Typed request-context metadata carried by every Gateway tool call.

    This is transport context, not a caller-supplied authorization decision;
    the Gateway independently resolves the authenticated policy context.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    execution_mode: str = Field(min_length=1)
    org_id: str | None = None
    project_id: str | None = None
    model: str | None = None


class GatewayToolProvenance(BaseModel):
    """Provenance metadata for a tool response. Metadata only, not authorization."""

    model_config = ConfigDict(frozen=True)

    search_id: str | None = None
    source_urls: tuple[HttpsUrl, ...] = ()
    trust: Literal["untrusted"] = "untrusted"


T = TypeVar("T")


class GatewayToolEnvelope(BaseModel, Generic[T]):
    """Common typed-tool response envelope shared by client and Gateway."""

    model_config = ConfigDict(frozen=True)

    tool_class: ToolClass
    policy_signal: ToolPolicySignal
    run_id: str = Field(min_length=1)
    result: T
    provenance: GatewayToolProvenance
    gateway_usage: GatewayUsage


def parse_gateway_tool_envelope(
    body: Mapping[str, Any],
    result_type: type[T],
) -> "GatewayToolEnvelope[T]":
    """Parse a Gateway tool envelope, failing closed on missing/null/malformed usage.

    Reuses :func:`optimus.gateway.models.parse_gateway_usage` as the single
    strict usage parser so audit codes (``GATEWAY_USAGE_MISSING`` /
    ``GATEWAY_COST_MISSING``) stay consistent with the rest of the Gateway
    client. ``Decimal`` cost values are preserved on success.
    """
    if not isinstance(body, Mapping):
        raise GatewayResponseError("tool envelope body missing", audit_code="GATEWAY_USAGE_MISSING")

    usage = parse_gateway_usage(body.get("gateway_usage"))

    try:
        return GatewayToolEnvelope[result_type].model_validate({**body, "gateway_usage": usage})
    except ValidationError as exc:
        raise GatewayResponseError(str(exc), gateway_usage=usage) from exc


# --- Web search / extract contracts -----------------------------------------


class WebSearchRequest(BaseModel):
    """``POST /v1/tools/web/search`` shared request contract."""

    model_config = ConfigDict(frozen=True)

    context: GatewayToolContext
    query: str = Field(min_length=1)
    allowed_domains: tuple[str, ...] = Field(min_length=1)
    result_cap: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"


class WebExtractRequest(BaseModel):
    """``POST /v1/tools/web/extract`` shared request contract.

    Accepts either a legacy single ``url`` (ACP compatibility) or ``urls``, but
    never both. The legacy single form is normalized into a one-element
    ``urls`` tuple before validation.
    """

    model_config = ConfigDict(frozen=True)

    context: GatewayToolContext
    urls: tuple[HttpsUrl, ...] = Field(min_length=1, max_length=10)
    max_chars_per_source: int = Field(default=4000, ge=1, le=20000)

    @model_validator(mode="before")
    @classmethod
    def _normalize_url_forms(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        data = dict(data)
        has_url = data.get("url") is not None
        has_urls = data.get("urls") is not None
        if has_url and has_urls:
            raise ValueError("cannot supply both url and urls")
        if has_url:
            data["urls"] = (data.pop("url"),)
        elif not has_urls:
            raise ValueError("either url or urls is required")
        else:
            data.pop("url", None)
        return data

    @model_validator(mode="after")
    def _reject_duplicates(self) -> "WebExtractRequest":
        _reject_duplicate_urls(self.urls)
        return self


class WebSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = ""
    url: HttpsUrl
    snippet: str = ""


class WebSearchResultSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: tuple[WebSearchResult, ...] = ()


class WebExtractItem(BaseModel):
    """A single extracted page; ``content`` is always untrusted text."""

    model_config = ConfigDict(frozen=True)

    url: HttpsUrl
    title: str = ""
    content: str


class WebExtractResultSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[WebExtractItem, ...] = ()


# --- Package lookup / security advisory contracts (P11-FU-2) ----------------


class PackageLookupRequest(BaseModel):
    """``POST /v1/tools/package/lookup`` shared request contract."""

    model_config = ConfigDict(frozen=True)

    context: GatewayToolContext
    package: str = Field(min_length=1)
    ecosystem: PackageEcosystem
    version: str | None = None


class SecurityAdvisoryRequest(BaseModel):
    """``POST /v1/tools/security/advisory`` shared request contract."""

    model_config = ConfigDict(frozen=True)

    context: GatewayToolContext
    identifier: str = Field(min_length=1)
    ecosystem: PackageEcosystem | None = None
    version: str | None = None


class PackageVersionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    released_at: str | None = None
    source_url: HttpsUrl


class PackageLookupResult(BaseModel):
    """Normalized package lookup result. Provider-specific raw payloads are not returned."""

    model_config = ConfigDict(frozen=True)

    package: str
    ecosystem: PackageEcosystem
    requested_version: str | None = None
    latest_version: str | None = None
    versions: tuple[PackageVersionRecord, ...] = ()
    citations: tuple[HttpsUrl, ...] = ()


class AdvisoryRecord(BaseModel):
    """A single advisory record. All descriptive text is untrusted."""

    model_config = ConfigDict(frozen=True)

    advisory_id: str
    summary: str
    severity: str | None = None
    affected_ranges: tuple[str, ...] = ()
    fixed_versions: tuple[str, ...] = ()
    citations: tuple[HttpsUrl, ...] = ()


class SecurityAdvisoryResult(BaseModel):
    """Normalized security advisory result. Advisory text is untrusted data."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    ecosystem: str | None = None
    version: str | None = None
    advisories: tuple[AdvisoryRecord, ...] = ()
