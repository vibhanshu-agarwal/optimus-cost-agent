from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SkillTrustLevel(StrEnum):
    TRUSTED = "trusted"
    DRAFT = "draft"


class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    keywords: tuple[str, ...] = ()
    globs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    owner: str = Field(min_length=1)
    version: str = Field(min_length=1)
    trust_level: SkillTrustLevel = SkillTrustLevel.DRAFT
    source_path: str = Field(min_length=1)
    manifest_hash: str = Field(min_length=64, max_length=64)
    content_hash: str = Field(min_length=64, max_length=64)


class SkillMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: SkillManifest
    matched_reasons: tuple[str, ...]
