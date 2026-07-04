from pathlib import Path

from optimus.guardrails.path_safety import PathSafetyValidator, ValidationVerdict


def test_secret_file_read_is_blocked(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    result = validator.validate_read(tmp_path / ".env")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "path.secret.read"


def test_write_outside_workspace_is_blocked(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    result = validator.validate_write(tmp_path.parent / "outside.txt")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "path.workspace_escape"


def test_recursive_glob_delete_is_held(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    result = validator.validate_delete_pattern(str(tmp_path / "**" / "*"))

    assert result.verdict is ValidationVerdict.HOLD
    assert result.rule_id == "path.recursive_glob_delete"


def test_normal_workspace_write_allows(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    result = validator.validate_write(tmp_path / "src" / "optimus" / "ok.py")

    assert result.verdict is ValidationVerdict.ALLOW
