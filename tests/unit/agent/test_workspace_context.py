from optimus.agent.workspace_context import gather_workspace_context_for_prompt


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
