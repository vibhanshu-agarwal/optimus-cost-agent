import os
import sys
from pathlib import Path

import pytest

from optimus.acp.debug_trace import DEFAULT_DEBUG_LOG_RELATIVE_PATH
from optimus.acp.operator_paths import resolve_operator_paths
from optimus.agent import workspace_context
from optimus.agent.workspace_context import (
    WorkspaceReferenceDiagnostic,
    WorkspaceReferenceStatus,
    assemble_workspace_context_for_prompt,
    gather_workspace_context_for_prompt,
)
from optimus.telemetry.jsonl import DEFAULT_TELEMETRY_DIRNAME


def test_task_aware_context_includes_explicit_path_ahead_of_alphabetical_filler(tmp_path):
    filler = tmp_path / "a-filler.txt"
    filler.write_text("x" * 900, encoding="utf-8")
    target = tmp_path / "reports" / "fixture" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("def answer():\n    return 42\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Add a docstring to reports/fixture/example.py",
        max_total_bytes=600,
    )

    assert "--- reports/fixture/example.py ---" in result.text
    assert "def answer():" in result.text
    assert result.prioritized_paths == ("reports/fixture/example.py",)


def test_unique_basename_is_resolved(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("ok\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Update example.py")

    diagnostic = result.diagnostics[0]
    assert diagnostic.status is WorkspaceReferenceStatus.RESOLVED
    assert diagnostic.candidates == ("src/example.py",)
    assert result.prioritized_paths == ("src/example.py",)


def test_ambiguous_basename_returns_sorted_candidates_and_blocking_reason(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "example.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b" / "example.py").write_text("b\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Update example.py")

    assert result.blocking_stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"
    assert result.diagnostics == (
        WorkspaceReferenceDiagnostic(
            reference="example.py",
            status=WorkspaceReferenceStatus.AMBIGUOUS,
            candidates=("a/example.py", "b/example.py"),
        ),
    )
    assert "Retry with one exact workspace-relative path" in result.blocking_message


def test_missing_explicit_path_is_non_blocking_for_file_creation(tmp_path):
    result = assemble_workspace_context_for_prompt(tmp_path, task="Create new/module.py")

    diagnostic = result.diagnostics[0]
    assert diagnostic.status is WorkspaceReferenceStatus.NOT_FOUND
    assert diagnostic.candidates == ()
    assert result.blocking_stop_reason is None


def test_reference_followed_by_sentence_period_is_extracted(tmp_path):
    target = tmp_path / "reports" / "x" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("ok\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Please edit reports/x/example.py.",
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.reference == "reports/x/example.py"
    assert result.prioritized_paths == ("reports/x/example.py",)


def test_dot_prefixed_relative_reference_is_normalized(tmp_path):
    (tmp_path / "example.py").write_text("ok\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Edit ./example.py")

    assert result.prioritized_paths == ("example.py",)


def test_nonexistent_path_inside_skip_directory_is_not_readable(tmp_path):
    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Create .venv/new.py and node_modules/new.js",
    )

    assert {item.reference for item in result.diagnostics} == {".venv/new.py", "node_modules/new.js"}
    assert all(item.status is WorkspaceReferenceStatus.NOT_READABLE for item in result.diagnostics)
    assert result.blocking_stop_reason == "WORKSPACE_REFERENCE_NOT_READABLE"
    assert ".venv/new.py" in result.blocking_message
    assert "node_modules/new.js" not in result.blocking_message


def test_mixed_ambiguous_and_not_readable_resolves_all_diagnostics(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "example.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b" / "example.py").write_text("b\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Update example.py and create .venv/new.py",
    )

    assert len(result.diagnostics) == 2
    assert result.diagnostics[0].reference == "example.py"
    assert result.diagnostics[0].status is WorkspaceReferenceStatus.AMBIGUOUS
    assert result.diagnostics[1].reference == ".venv/new.py"
    assert result.diagnostics[1].status is WorkspaceReferenceStatus.NOT_READABLE
    assert result.blocking_stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"
    assert "example.py" in result.blocking_message
    assert ".venv/new.py" not in result.blocking_message


def test_absolute_and_parent_traversal_tokens_are_not_prioritized(tmp_path):
    (tmp_path / "inside.py").write_text("ok\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task=r"Edit C:\temp\outside.py and ../outside.py",
    )

    assert result.prioritized_paths == ()
    assert all("outside.py" not in candidate for item in result.diagnostics for candidate in item.candidates)


def test_explicit_binary_or_directory_reference_is_not_readable(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    package_dir = tmp_path / "package.py"
    package_dir.mkdir()

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Inspect image.png and package.py",
    )

    assert {item.reference for item in result.diagnostics} == {"image.png", "package.py"}
    assert all(item.status is WorkspaceReferenceStatus.NOT_READABLE for item in result.diagnostics)
    assert result.blocking_stop_reason == "WORKSPACE_REFERENCE_NOT_READABLE"


def test_repeated_reference_is_deduplicated_in_first_mention_order(tmp_path):
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Edit b.py then a.py and b.py again")

    assert result.prioritized_paths == ("b.py", "a.py")


def test_priority_file_is_complete_and_precedes_filler(tmp_path):
    (tmp_path / "filler.txt").write_text("FILLER_SENTINEL\n" + "y" * 400, encoding="utf-8")
    (tmp_path / "target.py").write_text("PRIORITY_SENTINEL_COMPLETE\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Edit target.py",
        max_total_bytes=600,
    )

    target_index = result.text.index("--- target.py ---")
    filler_index = result.text.index("--- filler.txt ---")
    assert target_index < filler_index
    assert "PRIORITY_SENTINEL_COMPLETE" in result.text


def test_two_referenced_files_follow_task_mention_order(tmp_path):
    (tmp_path / "a.py").write_text("CONTENT_A\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("CONTENT_B\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Edit b.py then a.py")

    b_index = result.text.index("--- b.py ---")
    a_index = result.text.index("--- a.py ---")
    assert b_index < a_index
    assert "CONTENT_B" in result.text
    assert "CONTENT_A" in result.text


def test_oversized_priority_file_blocks_without_partial_content(tmp_path):
    (tmp_path / "large.py").write_text("x" * 700, encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Edit large.py",
        max_total_bytes=600,
    )

    assert result.text == ""
    assert result.blocking_stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
    assert result.diagnostics[0].status is WorkspaceReferenceStatus.TOO_LARGE
    assert "partial" not in result.blocking_message.lower()


def test_combined_priority_files_over_budget_blocks_instead_of_partial_pack(tmp_path):
    (tmp_path / "a.py").write_text("a" * 200, encoding="utf-8")
    (tmp_path / "b.py").write_text("b" * 200, encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Edit a.py and b.py",
        max_total_bytes=350,
    )

    assert result.text == ""
    assert result.blocking_stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
    assert result.diagnostics[0].status is WorkspaceReferenceStatus.TOO_LARGE


def test_filler_remains_alphabetical_after_priority_files(tmp_path):
    (tmp_path / "z-priority.py").write_text("priority\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("aaa\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("bbb\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Edit z-priority.py")

    priority_index = result.text.index("--- z-priority.py ---")
    a_index = result.text.index("--- a.txt ---")
    b_index = result.text.index("--- b.txt ---")
    assert priority_index < a_index < b_index


def test_result_never_exceeds_max_total_bytes_in_utf8(tmp_path):
    (tmp_path / "emoji.py").write_text("☺" * 300, encoding="utf-8")
    (tmp_path / "ascii.py").write_text("a" * 300, encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Edit emoji.py",
        max_total_bytes=400,
    )

    assert result.used_bytes == len(result.text.encode("utf-8"))
    assert result.used_bytes <= 400


def test_legacy_gather_wrapper_preserves_string_api(tmp_path):
    large = "x" * 500
    (tmp_path / "a.py").write_text(large, encoding="utf-8")
    (tmp_path / "b.py").write_text(large, encoding="utf-8")
    (tmp_path / "c.py").write_text(large, encoding="utf-8")

    context = gather_workspace_context_for_prompt(tmp_path, max_total_bytes=600)

    assert isinstance(context, str)
    assert "--- a.py ---" in context
    assert "--- omitted (size cap):" in context
    assert "b.py" in context
    assert "c.py" in context
    assert "--- c.py ---" not in context


def test_filler_only_path_returns_content_without_silent_empty_result(tmp_path):
    (tmp_path / "a.py").write_text("aa\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("bb\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(tmp_path, task="", max_total_bytes=92)

    assert result.text != ""
    assert result.used_bytes > 0
    assert result.blocking_stop_reason is None
    assert result.used_bytes <= 92


def test_small_priority_file_not_blamed_when_filler_names_dominate_budget(tmp_path):
    (tmp_path / "target.py").write_text("ok\n", encoding="utf-8")
    for index in range(15):
        (tmp_path / f"filler-{index:02d}.txt").write_text("x\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Edit target.py",
        max_total_bytes=120,
    )

    assert result.blocking_stop_reason is None
    assert "--- target.py ---" in result.text
    assert result.used_bytes <= 120


def test_gather_workspace_context_includes_text_files(tmp_path):
    (tmp_path / "example.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")

    context = gather_workspace_context_for_prompt(tmp_path)

    assert "--- example.py ---" in context
    assert "def greet():" in context
    assert "--- notes.txt ---" in context
    assert "--- end of workspace files ---" not in context


def test_gather_workspace_context_skips_git_and_binary_files(tmp_path):
    (tmp_path / "example.py").write_text("ok\n", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("secret\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    context = gather_workspace_context_for_prompt(tmp_path)

    assert "--- example.py ---" in context
    assert ".git" not in context
    assert "image.png" not in context


def test_gather_workspace_context_respects_total_byte_cap_with_truncation_marker(tmp_path):
    large = "x" * 500
    (tmp_path / "a.py").write_text(large, encoding="utf-8")
    (tmp_path / "b.py").write_text(large, encoding="utf-8")
    (tmp_path / "c.py").write_text(large, encoding="utf-8")

    context = gather_workspace_context_for_prompt(tmp_path, max_total_bytes=600)

    assert "--- a.py ---" in context
    assert "--- omitted (size cap):" in context
    assert "b.py" in context
    assert "c.py" in context
    assert "--- c.py ---" not in context


# --- Plan 12.2: the reserved .optimus runtime tree is never workspace context (runtime-context exclusion plan v2) ---

RUNTIME_SENTINEL = "RUNTIME_SENTINEL_7F3A"
SOURCE_SENTINEL = "SOURCE_SENTINEL_2C9E"
RUNTIME_FILES = ("debug-acp.ndjson", "launch-audit.ndjson", "local-gateway.log", "telemetry.jsonl")
WINDOWS = sys.platform == "win32"


def _runtime_tree(parent: Path, name: str = ".optimus") -> Path:
    """The files a launch writes under its runtime tree, each carrying the runtime sentinel."""
    runtime = parent / name
    runtime.mkdir(parents=True)
    for file_name in RUNTIME_FILES:
        (runtime / file_name).write_text(f'{{"event": "{RUNTIME_SENTINEL} {file_name}"}}\n', encoding="utf-8")
    return runtime


def _source(root: Path, relative: str = "src/app.py") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {SOURCE_SENTINEL}\n", encoding="utf-8")
    return path


def _assert_runtime_absent(result) -> None:
    assert RUNTIME_SENTINEL not in result.text
    assert ".optimus" not in result.text.casefold()
    assert not any(".optimus" in path.casefold() for path in (*result.prioritized_paths, *result.omitted_paths))


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:  # Windows without the symlink privilege: WinError 1314
        pytest.skip(f"symlink creation is unavailable on this platform account: {exc}")


def test_runtime_tree_is_excluded_before_any_of_its_content_is_read(tmp_path, monkeypatch):
    _runtime_tree(tmp_path)
    _source(tmp_path)
    read: list[Path] = []
    original = Path.read_bytes

    def recording_read_bytes(self: Path) -> bytes:
        read.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", recording_read_bytes)
    result = assemble_workspace_context_for_prompt(tmp_path, task="Explain src/app.py")

    assert SOURCE_SENTINEL in result.text and result.prioritized_paths == ("src/app.py",)
    _assert_runtime_absent(result)
    assert not [path for path in read if ".optimus" in path.parts], "no runtime file is opened to decide eligibility"


def test_a_runtime_only_workspace_contributes_no_blocks_candidates_or_omitted_names(tmp_path):
    _runtime_tree(tmp_path)

    result = assemble_workspace_context_for_prompt(tmp_path, task="", max_total_bytes=96)

    assert (result.text, result.used_bytes, result.omitted_paths, result.prioritized_paths) == ("", 0, (), ())


def test_a_nested_runtime_tree_is_excluded_and_its_sibling_source_is_kept(tmp_path):
    _runtime_tree(tmp_path / "sub")
    _source(tmp_path, "sub/app.py")

    result = assemble_workspace_context_for_prompt(tmp_path, task="")

    assert "--- sub/app.py ---" in result.text and SOURCE_SENTINEL in result.text
    _assert_runtime_absent(result)


@pytest.mark.parametrize("reference", [".optimus/debug-acp.ndjson", ".optimus/new-file.ndjson", "sub/.optimus/telemetry.jsonl"])
def test_an_explicit_runtime_reference_is_not_readable(tmp_path, reference):
    _runtime_tree(tmp_path)
    _runtime_tree(tmp_path / "sub")
    _source(tmp_path)

    result = assemble_workspace_context_for_prompt(tmp_path, task=f"Show me {reference}")

    assert result.diagnostics[0].reference == reference
    assert result.diagnostics[0].status is WorkspaceReferenceStatus.NOT_READABLE
    assert result.blocking_stop_reason == "WORKSPACE_REFERENCE_NOT_READABLE"
    assert result.text == ""


def test_a_runtime_only_basename_is_not_found_and_never_packed(tmp_path):
    _runtime_tree(tmp_path)
    _source(tmp_path)

    result = assemble_workspace_context_for_prompt(tmp_path, task="What is in debug-acp.ndjson?")

    assert result.diagnostics[0].status is WorkspaceReferenceStatus.NOT_FOUND
    assert result.blocking_stop_reason is None and SOURCE_SENTINEL in result.text
    _assert_runtime_absent(result)


def test_a_normal_source_sharing_a_runtime_basename_resolves_instead_of_being_ambiguous(tmp_path):
    _runtime_tree(tmp_path)
    _source(tmp_path, "logs/telemetry.jsonl")

    result = assemble_workspace_context_for_prompt(tmp_path, task="Summarise telemetry.jsonl")

    assert result.diagnostics[0].status is WorkspaceReferenceStatus.RESOLVED
    assert result.diagnostics[0].candidates == ("logs/telemetry.jsonl",)
    assert result.blocking_stop_reason is None and "--- logs/telemetry.jsonl ---" in result.text
    _assert_runtime_absent(result)


@pytest.mark.parametrize("relative", ["my.optimus/notes.md", ".optimus-notes/notes.md", "optimus/notes.md", "docs/.optimusrc.md"])
def test_names_that_only_resemble_the_runtime_tree_stay_eligible(tmp_path, relative):
    _source(tmp_path, relative)

    result = assemble_workspace_context_for_prompt(tmp_path, task="")

    assert f"--- {relative} ---" in result.text and SOURCE_SENTINEL in result.text


def test_ordinary_logs_json_and_other_dot_directories_stay_eligible(tmp_path):
    for relative in ("logs/app.log", "data/events.ndjson", ".config/settings.json"):
        _source(tmp_path, relative)

    result = assemble_workspace_context_for_prompt(tmp_path, task="")

    for relative in ("logs/app.log", "data/events.ndjson", ".config/settings.json"):
        assert f"--- {relative} ---" in result.text


def test_the_reserved_name_follows_the_platform_case_rule(tmp_path):
    _runtime_tree(tmp_path, ".Optimus")
    _source(tmp_path)

    result = assemble_workspace_context_for_prompt(tmp_path, task="")
    reference = assemble_workspace_context_for_prompt(tmp_path, task="Show .Optimus/debug-acp.ndjson")

    if WINDOWS:  # NTFS is case-insensitive: <workspace>/.optimus is this very directory
        assert RUNTIME_SENTINEL not in result.text
        assert reference.diagnostics[0].status is WorkspaceReferenceStatus.NOT_READABLE
    else:  # a distinct, ordinary directory on a case-sensitive filesystem
        assert RUNTIME_SENTINEL in result.text
        assert reference.diagnostics[0].status is WorkspaceReferenceStatus.RESOLVED
    assert SOURCE_SENTINEL in result.text


def test_a_workspace_under_an_ancestor_named_like_the_runtime_tree_keeps_its_files(tmp_path):
    root = tmp_path / ".optimus" / "project"
    _source(root)

    result = assemble_workspace_context_for_prompt(root, task="Explain src/app.py")

    assert SOURCE_SENTINEL in result.text and result.prioritized_paths == ("src/app.py",)


def test_the_omitted_files_marker_never_names_a_runtime_path(tmp_path):
    _runtime_tree(tmp_path)
    for index in range(6):
        _source(tmp_path, f"src/module_{index}.py")

    result = assemble_workspace_context_for_prompt(tmp_path, task="", max_total_bytes=200)

    assert result.omitted_paths and "--- omitted (size cap):" in result.text
    _assert_runtime_absent(result)


def test_a_candidate_whose_target_cannot_be_resolved_is_not_read(tmp_path, monkeypatch):
    _source(tmp_path, "src/app.py")
    _source(tmp_path, "src/unresolvable.py")
    original = Path.resolve

    def failing_resolve(self: Path, strict: bool = False) -> Path:
        if self.name == "unresolvable.py":
            raise OSError("simulated resolution failure")
        return original(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", failing_resolve)
    result = assemble_workspace_context_for_prompt(tmp_path, task="")

    assert "--- src/app.py ---" in result.text
    assert "unresolvable.py" not in result.text


@pytest.mark.skipif(not WINDOWS, reason="NTFS directory junctions are a Windows mechanism")
def test_a_junction_into_the_runtime_tree_is_excluded_and_an_ordinary_junction_is_kept(tmp_path):
    import _winapi  # CreateJunction needs no privilege, unlike a symlink

    runtime = _runtime_tree(tmp_path)
    _source(tmp_path)
    runtime_alias, source_alias = tmp_path / "logs", tmp_path / "src-alias"
    _winapi.CreateJunction(str(runtime), str(runtime_alias))
    _winapi.CreateJunction(str(tmp_path / "src"), str(source_alias))
    try:
        result = assemble_workspace_context_for_prompt(tmp_path, task="")
        reference = assemble_workspace_context_for_prompt(tmp_path, task="Show logs/debug-acp.ndjson")

        assert "--- src-alias/app.py ---" in result.text, "an ordinary junction stays eligible"
        assert RUNTIME_SENTINEL not in result.text and "logs/" not in result.text
        assert reference.diagnostics[0].status is WorkspaceReferenceStatus.NOT_READABLE
    finally:
        os.rmdir(runtime_alias)  # remove the junctions themselves, never through them
        os.rmdir(source_alias)


def test_a_file_symlink_into_the_runtime_tree_is_excluded_and_an_ordinary_one_is_kept(tmp_path):
    runtime = _runtime_tree(tmp_path)
    source = _source(tmp_path)
    _symlink_or_skip(tmp_path / "notes.ndjson", runtime / "debug-acp.ndjson")
    _symlink_or_skip(tmp_path / "alias.py", source)

    result = assemble_workspace_context_for_prompt(tmp_path, task="")
    reference = assemble_workspace_context_for_prompt(tmp_path, task="Show notes.ndjson")

    assert "--- alias.py ---" in result.text, "an ordinary file alias stays eligible"
    assert RUNTIME_SENTINEL not in result.text and "notes.ndjson" not in result.text
    assert reference.diagnostics[0].status is WorkspaceReferenceStatus.NOT_READABLE


def test_a_file_symlink_to_a_runtime_tree_outside_the_workspace_is_excluded(tmp_path):
    other = _runtime_tree(tmp_path / "other-workspace")
    root = tmp_path / "workspace"
    _source(root)
    _symlink_or_skip(root / "borrowed.ndjson", other / "telemetry.jsonl")

    result = assemble_workspace_context_for_prompt(root, task="")

    assert SOURCE_SENTINEL in result.text and RUNTIME_SENTINEL not in result.text


def test_a_symlink_loop_and_a_directory_symlink_into_the_runtime_tree_are_never_read(tmp_path):
    runtime = _runtime_tree(tmp_path)
    _source(tmp_path)
    _symlink_or_skip(tmp_path / "loop.txt", tmp_path / "loop.txt")
    _symlink_or_skip(tmp_path / "runtime-dir", runtime, directory=True)

    result = assemble_workspace_context_for_prompt(tmp_path, task="")

    assert SOURCE_SENTINEL in result.text
    assert "loop.txt" not in result.text and "runtime-dir/" not in result.text
    _assert_runtime_absent(result)


def test_the_reserved_name_matches_every_runtime_writer(tmp_path):
    reserved = getattr(workspace_context, "RUNTIME_DIR_NAME", None)
    config = tmp_path / "config"
    paths = resolve_operator_paths(workspace_root=tmp_path / "ws", environ={"APPDATA": str(config), "XDG_CONFIG_HOME": str(config)})

    assert reserved == paths.runtime_root.name == DEFAULT_TELEMETRY_DIRNAME == DEFAULT_DEBUG_LOG_RELATIVE_PATH.parts[0]
    assert paths.debug_log_path.parent == paths.gateway_log_path.parent == paths.runtime_root
