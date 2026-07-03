from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal


class EvidenceRequest(BaseModel):
    """Validated input for a gateway-backed web search evidence call."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    query: str = Field(min_length=1)
    reason: EvidenceReasonCode
    policy_signal: ToolPolicySignal
    allowed_domains: tuple[str, ...] = Field(min_length=1)
    result_cap: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"


class EvidenceExtractRequest(BaseModel):
    """Validated input for extracting page content from an approved search-result URL."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    url: HttpUrl
    reason: EvidenceReasonCode
    policy_signal: ToolPolicySignal
    allowed_domains: tuple[str, ...] = Field(min_length=1)
    max_chars_per_source: int = Field(default=6000, ge=1, le=20000)

    @property
    def url_text(self) -> str:
        return str(self.url)


class EvidenceSearchResult(BaseModel):
    """Single search hit returned by the gateway before provenance tracking."""

    model_config = ConfigDict(frozen=True)

    title: str = ""
    url: HttpUrl
    snippet: str = ""

    @property
    def url_text(self) -> str:
        return str(self.url)


class EvidenceSearchResponse(BaseModel):
    """Parsed gateway search response with normalized results and usage fields."""

    model_config = ConfigDict(frozen=True)

    results: tuple[EvidenceSearchResult, ...]
    gateway_usage: GatewayUsage
    credits_used: int = Field(default=0, ge=0)


class EvidenceExtractResponse(BaseModel):
    """Parsed gateway extract response; content is always treated as untrusted text."""

    model_config = ConfigDict(frozen=True)

    url: HttpUrl
    title: str = ""
    content: str
    trust: Literal["untrusted"] = "untrusted"
    gateway_usage: GatewayUsage
    credits_used: int = Field(default=0, ge=0)

    @property
    def url_text(self) -> str:
        return str(self.url)
