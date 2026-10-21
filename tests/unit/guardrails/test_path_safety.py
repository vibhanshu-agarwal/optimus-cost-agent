
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


# --- Plan 12.2 READ + W: the reserved runtime tree `.optimus/` (direct calls, without request metadata) ---------


def test_runtime_tree_read_inside_the_workspace_is_blocked(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    for target in (tmp_path / ".optimus" / "telemetry.ndjson", tmp_path / "a" / ".optimus" / "state.json"):
        result = validator.validate_read(target)

        assert result.verdict is ValidationVerdict.BLOCK
        assert result.rule_id == "path.runtime.read"


def test_runtime_tree_read_outside_the_workspace_is_blocked_not_held(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    validator = PathSafetyValidator(workspace_root=workspace)

    result = validator.validate_read(tmp_path / "other-ws" / ".optimus" / "launch-audit.jsonl")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "path.runtime.read"


def test_a_relative_runtime_path_is_anchored_at_the_workspace_not_the_process_cwd(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    validator = PathSafetyValidator(workspace_root=workspace)

    result = validator.validate_read(".optimus/state.json")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "path.runtime.read"


def test_runtime_tree_write_is_blocked(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    result = validator.validate_write(tmp_path / ".optimus" / "new.json")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "path.runtime.write"


def test_runtime_lookalikes_ordinary_dot_directories_and_an_ancestor_named_optimus_stay_allowed(tmp_path):
    workspace = tmp_path / ".optimus" / "ws"
    workspace.mkdir(parents=True)
    validator = PathSafetyValidator(workspace_root=workspace)

    for relative in ("src/a.py", ".optimus-notes/x.md", "optimus/x.py", ".optimus.bak", "x.optimus", ".github/ci.yml", "logs/run.ndjson"):
        assert validator.validate_read(workspace / relative).verdict is ValidationVerdict.ALLOW, relative
        assert validator.validate_write(workspace / relative).verdict is ValidationVerdict.ALLOW, relative


def test_a_secret_name_inside_the_runtime_tree_keeps_the_secret_rule(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    assert validator.validate_read(tmp_path / ".optimus" / ".env").rule_id == "path.secret.read"
    assert validator.validate_write(tmp_path / ".optimus" / ".env").rule_id == "path.secret.write"


def test_ordinary_outside_reads_stay_held_and_outside_writes_stay_blocked(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    validator = PathSafetyValidator(workspace_root=workspace)

    read = validator.validate_read(tmp_path / "notes.txt")
    write = validator.validate_write(tmp_path / "notes.txt")

    assert (read.verdict, read.rule_id) == (ValidationVerdict.HOLD, "path.read.outside_workspace")
    assert (write.verdict, write.rule_id) == (ValidationVerdict.BLOCK, "path.workspace_escape")
