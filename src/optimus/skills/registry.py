from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from optimus.guardrails.permissions import ToolSurface
from optimus.runtime.modes import ExecutionMode
from optimus.skills.models import SkillManifest, SkillMatch, SkillTrustLevel
from optimus.telemetry.events import TelemetryEvent


class SkillManifestError(ValueError):
    pass


class SkillRegistry:
    def __init__(
        self,
        manifests: tuple[SkillManifest, ...],
        *,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._manifests = manifests
        self._loaded_body_paths: list[str] = []
        self._event_sink = event_sink
        self._now = now or (lambda: datetime.now(tz=UTC))

    @classmethod
    def from_paths(
        cls,
        paths: tuple[Path, ...],
        *,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> "SkillRegistry":
        return cls(
            tuple(parse_skill_markdown(path.read_text(encoding="utf-8"), source_path=path) for path in paths),
            event_sink=event_sink,
            now=now,
        )

    def match(
        self,
        *,
        run_id: str,
        session_id: str | None,
        task_text: str,
        changed_paths: tuple[str, ...],
        execution_mode: ExecutionMode,
    ) -> tuple[SkillMatch, ...]:
        matches: list[SkillMatch] = []
        for manifest in self._manifests:
            if execution_mode is ExecutionMode.AGENT and manifest.trust_level is SkillTrustLevel.DRAFT:
                continue
            reasons = _match_reasons(manifest, task_text=task_text, changed_paths=changed_paths)
            if reasons:
                match = SkillMatch(manifest=manifest, matched_reasons=reasons)
                matches.append(match)
                self._emit_selection(run_id=run_id, session_id=session_id, match=match)
        return tuple(matches)

    def load_body(self, manifest: SkillManifest) -> str:
        path = Path(manifest.source_path).resolve()
        text = path.read_text(encoding="utf-8")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest.content_hash:
            raise SkillManifestError("skill content hash changed")
        self._loaded_body_paths.append(path.as_posix())
        return _body_without_frontmatter(text)

    def loaded_body_paths(self) -> tuple[str, ...]:
        return tuple(self._loaded_body_paths)

    def _emit_selection(self, *, run_id: str, session_id: str | None, match: SkillMatch) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.skill_selection(
                run_id=run_id,
                session_id=session_id,
                request_id=f"{run_id}:skill-selection:{match.manifest.name}",
                occurred_at=self._now(),
                skill_name=match.manifest.name,
                manifest_hash=match.manifest.manifest_hash,
                matched_reasons=match.matched_reasons,
            )
        )


def parse_skill_markdown(text: str, *, source_path: Path) -> SkillManifest:
    metadata = _frontmatter(text)
    required = ("name", "description", "owner", "version")
    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise SkillManifestError(f"skill manifest missing required fields: {missing}")
    allowed_tools = tuple(metadata.get("allowed_tools", ()))
    unknown_tools = sorted(set(allowed_tools) - {surface.value for surface in ToolSurface})
    if unknown_tools:
        raise SkillManifestError(f"unknown allowed_tools: {unknown_tools}")
    try:
        trust_level = SkillTrustLevel(str(metadata.get("trust_level", "draft")))
    except ValueError as exc:
        raise SkillManifestError(f"unknown trust_level: {metadata.get('trust_level')}") from exc
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SkillManifest(
        name=str(metadata["name"]),
        description=str(metadata["description"]),
        keywords=tuple(metadata.get("keywords", ())),
        globs=tuple(metadata.get("globs", ())),
        allowed_tools=allowed_tools,
        owner=str(metadata["owner"]),
        version=str(metadata["version"]),
        trust_level=trust_level,
        source_path=source_path.as_posix(),
        manifest_hash=content_hash,
        content_hash=content_hash,
    )


def _frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillManifestError("skill markdown must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise SkillManifestError("skill markdown frontmatter must end with ---") from exc
    data: dict[str, object] = {}
    current_list_key: str | None = None
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_list_key is None:
                raise SkillManifestError("list item without key")
            data.setdefault(current_list_key, [])
            if not isinstance(data[current_list_key], list):
                raise SkillManifestError(f"frontmatter key is not a list: {current_list_key}")
            data[current_list_key].append(line[4:].strip())
            continue
        current_list_key = None
        if ":" not in line:
            raise SkillManifestError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        if key in data:
            raise SkillManifestError(f"duplicate frontmatter key: {key}")
        value = value.strip()
        if value == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = value
    return data


def _match_reasons(manifest: SkillManifest, *, task_text: str, changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    task_lower = task_text.lower()
    description_terms = [term for term in (*manifest.keywords, *manifest.description.lower().replace("-", " ").split()) if len(term) >= 5]
    if sum(1 for term in set(description_terms) if term in task_lower) >= 2:
        reasons.append("description")
    for pattern in manifest.globs:
        if any(PurePosixPath(path.replace("\\", "/")).full_match(pattern) for path in changed_paths):
            reasons.append(f"glob:{pattern}")
    return tuple(reasons)


def _body_without_frontmatter(text: str) -> str:
    lines = text.splitlines()
    end = lines.index("---", 1)
    return "\n".join(lines[end + 1 :]).lstrip()
