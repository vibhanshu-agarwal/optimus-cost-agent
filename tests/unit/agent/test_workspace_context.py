from optimus.agent.workspace_context import (
    WorkspaceReferenceDiagnostic,
    WorkspaceReferenceStatus,
    assemble_workspace_context_for_prompt,
    gather_workspace_context_for_prompt,
)


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
