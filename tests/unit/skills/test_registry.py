from pathlib import Path

import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.skills.models import SkillTrustLevel
from optimus.skills.registry import SkillManifestError, SkillRegistry, parse_skill_markdown


SKILL_TEXT = """---
name: pytest-debugging
description: Debug failing pytest tests with a red-green loop.
keywords:
  - pytest
  - debug
  - failing
globs:
  - tests/**/*.py
allowed_tools:
  - shell
  - file_read
owner: maintainer
version: 1.0.0
trust_level: trusted
---

# Pytest Debugging

Run the narrow failing test first, inspect the failure, then patch the smallest code path.
"""


def test_parse_skill_markdown_manifest():
    manifest = parse_skill_markdown(SKILL_TEXT, source_path=Path("skills/pytest/SKILL.md"))

    assert manifest.name == "pytest-debugging"
    assert manifest.description == "Debug failing pytest tests with a red-green loop."
    assert manifest.globs == ("tests/**/*.py",)
    assert manifest.allowed_tools == ("shell", "file_read")
    assert manifest.owner == "maintainer"
    assert manifest.version == "1.0.0"
    assert manifest.trust_level is SkillTrustLevel.TRUSTED
    assert len(manifest.manifest_hash) == 64
    assert manifest.manifest_hash == manifest.content_hash
    assert "Run the narrow failing test first" not in manifest.model_dump_json()


def test_skill_registry_matches_by_description_and_globs(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Please debug the failing pytest test",
        changed_paths=("tests/unit/test_example.py",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert tuple(match.manifest.name for match in matches) == ("pytest-debugging",)
    assert matches[0].matched_reasons == ("description", "glob:tests/**/*.py")


def test_skill_registry_does_not_match_unrelated_task(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Write architecture notes",
        changed_paths=("docs/design.md",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert matches == ()


def test_skill_registry_matches_double_star_zero_directory_path(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Please debug the failing pytest test",
        changed_paths=("tests/test_example.py",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert tuple(match.manifest.name for match in matches) == ("pytest-debugging",)


def test_skill_registry_does_not_read_unmatched_skill_body(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Write architecture notes",
        changed_paths=("docs/design.md",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert matches == ()
    # `from_paths()` reads the full file to hash it; this assertion verifies the body was never surfaced to runtime context.
    assert registry.loaded_body_paths() == ()


def test_skill_registry_loads_body_only_after_match(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))
    match = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Please debug the failing pytest test",
        changed_paths=("tests/unit/test_example.py",),
        execution_mode=ExecutionMode.AGENT,
    )[0]

    body = registry.load_body(match.manifest)

    assert "Run the narrow failing test first" in body
    assert registry.loaded_body_paths() == (path.resolve().as_posix(),)


def test_skill_manifest_rejects_unknown_allowed_tool():
    text = SKILL_TEXT.replace("  - shell", "  - Shell")

    with pytest.raises(SkillManifestError, match="unknown allowed_tools"):
        parse_skill_markdown(text, source_path=Path("skills/pytest/SKILL.md"))
