"""Immutable source-view tests for the Plan 11.26 audit."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path, PurePosixPath

import pytest

from tools.plan1126_runtime_audit import source as source_module
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


def test_git_commit_source_reads_immutable_blob_not_dirty_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Plan 11.26 Test")
    _git(repo, "config", "user.email", "plan1126@example.invalid")
    tracked = repo / "sample.py"
    tracked.write_text("VALUE = 'committed'\n", encoding="utf-8")
    _git(repo, "add", "sample.py")
    _git(repo, "commit", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    tracked.write_text("VALUE = 'dirty substitution'\n", encoding="utf-8")

    source = GitCommitSource(commit=commit, repository=repo)

    assert source.read_text("sample.py") == "VALUE = 'committed'\n"
    assert source.paths() == ("sample.py",)


def test_git_commit_source_bounds_every_git_subprocess(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def bounded_run(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["timeout"] == 10.0
        return subprocess.CompletedProcess(args[0], 0, stdout="a" * 40, stderr="")

    monkeypatch.setattr(subprocess, "run", bounded_run)

    source = GitCommitSource(commit="HEAD", repository=tmp_path)
    source.paths()

    assert len(calls) == 2


def test_git_commit_source_reads_multiple_blobs_from_one_bounded_archive(
    monkeypatch, tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Plan 11.26 Test")
    _git(repo, "config", "user.email", "plan1126@example.invalid")
    (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("B = 2\n", encoding="utf-8")
    _git(repo, "add", "a.py", "b.py")
    _git(repo, "commit", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    real_run = subprocess.run
    git_commands: list[tuple[str, ...]] = []

    def recording_run(command, **kwargs):
        git_commands.append(tuple(command))
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    source = GitCommitSource(commit=commit, repository=repo)

    assert source.read_text("a.py") == "A = 1\n"
    assert source.read_text("b.py") == "B = 2\n"
    assert sum(command[1:3] == ("archive", "--format=tar") for command in git_commands) == 1
    assert not any(command[1] == "show" for command in git_commands)


# --- Plan 11.30 Task 4: the session export cache. One read-only export of a whole commit serves every
# reader of the same repository, resolved commit and exporting tool/configuration, in one thread of one
# session; nothing else reuses it, only the most recent export is held, and a failed export is never
# cached. ---


def _committed(repo: Path, files: dict[str, str]) -> str:
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", *files)
    _git(repo, "commit", "-m", "fixture")
    return _git(repo, "rev-parse", "HEAD")


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Plan 11.30 Test")
    _git(repo, "config", "user.email", "plan1130@example.invalid")
    return repo, _committed(repo, {"a.py": "A = 1\n", "b.py": "B = 2\n"})


def _export_counter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    real_run = subprocess.run
    exports: list[tuple[str, ...]] = []

    def recording_run(command, **kwargs):
        if tuple(command[1:3]) == ("archive", "--format=tar"):
            exports.append(tuple(command))
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    return exports


def test_a_second_reader_of_the_same_commit_reuses_the_session_export(monkeypatch, tmp_path: Path) -> None:
    repo, commit = _repository(tmp_path)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    first = GitCommitSource(commit=commit, repository=repo)
    second = GitCommitSource(commit=commit, repository=repo)
    assert first.read_text("a.py") == second.read_text("a.py") == "A = 1\n"
    assert second.read_text("b.py") == first.read_text("b.py") == "B = 2\n"
    assert len(exports) == 1
    with pytest.raises(TypeError):  # the shared export is read-only: no reader can change what another reads
        second._load_archive()["a.py"] = b"A = 2\n"  # noqa: SLF001
    assert first.read_text("a.py") == "A = 1\n"


def test_an_export_is_reused_only_for_its_own_repository_commit_tool_thread_and_session(
    monkeypatch, tmp_path: Path,
) -> None:
    repo, commit = _repository(tmp_path)
    later = _committed(repo, {"a.py": "A = 3\n"})
    # A twin repository: the same commit and the same configuration, but its own export rules
    # (.git/info/attributes is not configuration), under which a.py is not exported at all.
    twin = tmp_path / "twin"
    twin.mkdir()
    _git(twin, "init")
    _git(twin, "config", "user.name", "Plan 11.30 Test")
    _git(twin, "config", "user.email", "plan1130@example.invalid")
    _git(twin, "fetch", "-q", str(repo), "HEAD")
    (twin / ".git" / "info").mkdir(exist_ok=True)
    (twin / ".git" / "info" / "attributes").write_text("a.py export-ignore\n", encoding="utf-8")
    assert _git(twin, "config", "--list", "--local") == _git(repo, "config", "--list", "--local")
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read(commit_id: str, repository: Path = repo) -> str:
        return GitCommitSource(commit=commit_id, repository=repository).read_text("a.py")

    # Each step below follows a read whose key differs from it in exactly the one named respect.
    assert read(commit) == "A = 1\n" and len(exports) == 1
    assert read(commit) == "A = 1\n" and len(exports) == 1  # same repository, commit, path and tool: reused
    assert read(later) == "A = 3\n" and len(exports) == 2  # another commit
    assert read(commit) == "A = 1\n" and len(exports) == 3  # bounded: only the most recent export is held
    with pytest.raises(KeyError):  # the same commit in another repository is that repository's own export
        read(commit, twin)
    assert len(exports) == 4
    assert read(commit) == "A = 1\n" and len(exports) == 5
    _git(repo, "config", "core.autocrlf", "true")
    assert read(commit) == "A = 1\n" and len(exports) == 6  # the exporting configuration changed
    monkeypatch.setattr(source_module, "_EXPORT_ARGUMENTS", ("archive", "--format=tar", "--worktree-attributes"))
    assert read(commit) == "A = 1\n" and len(exports) == 7  # the exporting tool's invocation changed
    monkeypatch.setattr(source_module, "_EXPORT_ARGUMENTS", ("archive", "--format=tar"))
    assert read(commit) == "A = 1\n" and len(exports) == 8
    assert read(commit) == "A = 1\n" and len(exports) == 8
    attributes = repo / ".git" / "info" / "attributes"
    attributes.parent.mkdir(exist_ok=True)
    attributes.write_text("a.py export-ignore\n", encoding="utf-8")
    with pytest.raises(KeyError):  # the repository's own export rules changed (not configuration)
        read(commit)
    assert len(exports) == 9
    attributes.unlink()
    assert read(commit) == "A = 1\n" and len(exports) == 10
    seen: list[str] = []
    worker = threading.Thread(target=lambda: seen.append(read(commit)))
    worker.start()
    worker.join()
    assert seen == ["A = 1\n"] and len(exports) == 11  # another thread never reuses this thread's export
    assert read(commit) == "A = 1\n" and len(exports) == 11  # nor replaces it
    source_module.clear_export_cache()  # the session ended
    assert read(commit) == "A = 1\n" and len(exports) == 12


def test_an_export_is_never_reused_after_an_external_attribute_source_changes(monkeypatch, tmp_path: Path) -> None:
    """Codex C-M1: git archive applies attribute files outside the commit and outside configuration -- the
    configured or default global file and the system file. Editing one's CONTENT at an unchanged path (so the
    configuration text is identical) must never serve the earlier export."""
    repo, commit = _repository(tmp_path)
    configured = tmp_path / "configured-attributes"
    configured.write_text("# none\n", encoding="utf-8")
    _git(repo, "config", "core.attributesFile", configured.as_posix())
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    assert read() == "A = 1\n" and len(exports) == 1
    assert read() == "A = 1\n" and len(exports) == 1
    configured.write_text("a.py export-ignore\n", encoding="utf-8")  # same path, same configuration text
    with pytest.raises(KeyError):
        read()
    assert len(exports) == 2

    # The default global location (no core.attributesFile): $XDG_CONFIG_HOME/git/attributes.
    _git(repo, "config", "--unset", "core.attributesFile")
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert read() == "A = 1\n" and len(exports) == 3
    (xdg / "git").mkdir(parents=True)
    (xdg / "git" / "attributes").write_text("a.py export-ignore\n", encoding="utf-8")
    with pytest.raises(KeyError):
        read()
    assert len(exports) == 4
    (xdg / "git" / "attributes").unlink()

    # The system file: only its path lookup is redirected to a scratch file, whose content then changes.
    system = tmp_path / "system-attributes"
    system.write_text("# none\n", encoding="utf-8")
    real_run = GitCommitSource._run

    def redirected(self, *args: str) -> str:
        return f"{system.as_posix()}\n" if args == ("var", "GIT_ATTR_SYSTEM") else real_run(self, *args)

    monkeypatch.setattr(GitCommitSource, "_run", redirected)
    assert read() == "A = 1\n" and len(exports) == 5
    assert read() == "A = 1\n" and len(exports) == 5
    system.write_text("b.py export-ignore\n", encoding="utf-8")
    assert read() == "A = 1\n" and len(exports) == 6  # a changed rule input is a new export, whatever it excludes
    monkeypatch.setenv("GIT_ATTR_NOSYSTEM", "1")  # the system file switched off
    assert read() == "A = 1\n" and len(exports) == 7


@pytest.mark.parametrize(
    "failure",
    [subprocess.CalledProcessError(128, ["git", "var"]), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")],
)
def test_an_export_whose_rule_inputs_cannot_be_established_is_never_reused(monkeypatch, tmp_path: Path, failure: Exception) -> None:
    repo, commit = _repository(tmp_path)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    real_run = GitCommitSource._run

    def unknown_global(self, *args: str) -> str:
        if args == ("var", "GIT_ATTR_GLOBAL"):
            raise failure
        return real_run(self, *args)

    monkeypatch.setattr(GitCommitSource, "_run", unknown_global)
    for count in (1, 2):  # still exported and read correctly, but never served from the cache
        assert GitCommitSource(commit=commit, repository=repo).read_text("a.py") == "A = 1\n"
        assert len(exports) == count


def test_an_export_is_never_reused_after_a_replace_ref_changes(monkeypatch, tmp_path: Path) -> None:
    """Besides attributes, `git archive` of a fixed commit id depends on replace refs (a replaced blob is exported in
    place of the original), which are not configuration text, so they bind the export by content. Mailmap sources
    are read only by export-subst placeholders, whose exports are never reused (C7): they shape no reusable export,
    so changing them keeps reuse."""
    repo, commit = _repository(tmp_path)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    assert read() == "A = 1\n" and len(exports) == 1
    original = _git(repo, "rev-parse", f"{commit}:a.py")
    replacement = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=repo, input="A = 9\n", check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git(repo, "replace", original, replacement)
    assert read() == "A = 9\n" and len(exports) == 2  # the replaced blob, never the earlier export
    assert read() == "A = 9\n" and len(exports) == 2
    monkeypatch.setenv("GIT_NO_REPLACE_OBJECTS", "1")
    assert read() == "A = 1\n" and len(exports) == 3
    monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS")
    assert read() == "A = 9\n" and len(exports) == 4
    (repo / ".mailmap").write_text("Mapped <mapped@example.invalid> <plan1130@example.invalid>\n", encoding="utf-8")
    assert read() == "A = 9\n" and len(exports) == 4
    _committed(repo, {"names.mailmap": "First <first@example.invalid> <plan1130@example.invalid>\n"})
    _git(repo, "config", "mailmap.blob", "HEAD:names.mailmap")  # configuration text changes: one new export
    assert read() == "A = 9\n" and len(exports) == 5
    _committed(repo, {"names.mailmap": "Second <second@example.invalid> <plan1130@example.invalid>\n"})  # the ref moves
    assert read() == "A = 9\n" and len(exports) == 5


def test_a_filter_driver_in_effect_disables_reuse(monkeypatch, tmp_path: Path) -> None:
    """A filter driver's smudge/process output is fixed by no hash, so an export it may shape is never reused."""
    repo, commit = _repository(tmp_path)
    _git(repo, "config", "filter.p1130.smudge", "cat")
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    assert read() == "A = 1\n" and read() == "A = 1\n" and len(exports) == 1  # configured but applied to nothing
    attributes = repo / ".git" / "info" / "attributes"
    attributes.parent.mkdir(exist_ok=True)
    attributes.write_text("a.py filter=p1130\n", encoding="utf-8")
    read()
    read()
    assert len(exports) == 3  # in effect: every reader exports


def test_export_subst_in_effect_disables_reuse(monkeypatch, tmp_path: Path) -> None:
    """Codex C-M3: export-subst placeholders read state outside the commit -- %D where a detached HEAD points, and
    the refs and history near the commit -- so an export they may shape is never reused, wherever the attribute
    is set."""
    repo, _ = _repository(tmp_path)
    commit = _committed(repo, {".gitattributes": "a.py export-subst\n", "a.py": "$Format:%D$\n"})
    later = _committed(repo, {"b.py": "B = 3\n"})
    _git(repo, "checkout", "-q", "--detach", commit)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read(at: str = commit) -> str:
        return GitCommitSource(commit=at, repository=repo).read_text("a.py")

    assert read() == "HEAD\n"
    _git(repo, "checkout", "-q", "--detach", later)  # no ref, configuration or attribute changes
    assert read() == "\n"
    _git(repo, "checkout", "-q", "--detach", commit)  # and back onto the exported commit
    assert read() == "HEAD\n"
    _git(repo, "tag", "p1130-marker", commit)  # a new ref at the commit
    assert read() == "HEAD, tag: p1130-marker\n"
    assert len(exports) == 4
    # Set outside the commit: the repository's info/attributes names export-subst for a commit that does not.
    plain = _committed(repo, {".gitattributes": "", "a.py": "$Format:%D$\n"})
    assert read(plain) == read(plain) == "$Format:%D$\n" and len(exports) == 5  # not in effect: reused
    attributes = repo / ".git" / "info" / "attributes"
    attributes.parent.mkdir(exist_ok=True)
    attributes.write_text("a.py export-subst\n", encoding="utf-8")
    assert read(plain) == read(plain) == "HEAD\n"
    assert len(exports) == 7


@pytest.mark.parametrize("case", ["nested", "nul-byte", "binary-attribute", "literal-pathspecs", "symlink"])
def test_export_subst_is_detected_in_every_gitattributes_the_export_applies(
    monkeypatch, tmp_path: Path, case: str,
) -> None:
    """Fable C7: detection reads every .gitattributes blob of the exported tree -- at any depth, in any mode, with
    any bytes, whatever the environment or other attributes say about it -- not what `git grep` chooses to print.
    `git archive` applies all of these; each must disable reuse."""
    repo, _ = _repository(tmp_path)
    path = "sub/c.py" if case == "nested" else "a.py"
    rules = f"{PurePosixPath(path).name} export-subst\n"
    (repo / "sub").mkdir()
    (repo / path).write_text("$Format:%H$\n", encoding="utf-8")
    _git(repo, "add", path)
    if case == "symlink":  # a symlinked .gitattributes: archive reads the link's blob as rules
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=repo, input=rules, check=True, capture_output=True, text=True,
        ).stdout.strip()
        _git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},.gitattributes")
    else:
        located = (repo / "sub" if case == "nested" else repo) / ".gitattributes"
        located.write_bytes(rules.encode("utf-8") + (b"\0\n" if case == "nul-byte" else b""))
        _git(repo, "add", located.relative_to(repo).as_posix())
    _git(repo, "commit", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    if case == "binary-attribute":  # attributes about .gitattributes itself, from outside the commit
        attributes = repo / ".git" / "info" / "attributes"
        attributes.parent.mkdir(exist_ok=True)
        attributes.write_text(".gitattributes binary\n", encoding="utf-8")
    if case == "literal-pathspecs":
        monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    for count in (1, 2):
        assert GitCommitSource(commit=commit, repository=repo).read_text(path) == f"{commit}\n"
        assert len(exports) == count


def test_an_attribute_blob_that_cannot_be_read_disables_reuse(monkeypatch, tmp_path: Path) -> None:
    """A .gitattributes blob the detection cannot read (a partial clone's absent object, which archive may fetch and
    then apply) leaves export-subst and filters unknown: that export is never reused."""
    repo, _ = _repository(tmp_path)
    commit = _committed(repo, {".gitattributes": "# none\n"})
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    counting_run = subprocess.run

    def absent_blob(command, **kwargs):
        completed = counting_run(command, **kwargs)
        if tuple(command[1:3]) == ("cat-file", "--batch"):
            return subprocess.CompletedProcess(command, 0, stdout=kwargs["input"].replace(b"\n", b" missing\n"), stderr=b"")
        return completed

    monkeypatch.setattr(subprocess, "run", absent_blob)
    for count in (1, 2):
        assert GitCommitSource(commit=commit, repository=repo).read_text("a.py") == "A = 1\n"
        assert len(exports) == count


def test_attribute_detection_reads_object_headers_not_rule_text(monkeypatch, tmp_path: Path) -> None:
    """Fable C7b: only an object header can say an attribute blob is missing; a rule line that happens to end in
    " missing" is ordinary text and keeps reuse."""
    repo, _ = _repository(tmp_path)
    commit = _committed(repo, {".gitattributes": "# nothing is missing\n"})
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    for _ in (1, 2):
        assert GitCommitSource(commit=commit, repository=repo).read_text("a.py") == "A = 1\n"
    assert len(exports) == 1


def test_a_path_that_is_not_utf8_neither_breaks_the_read_nor_the_reuse(monkeypatch, tmp_path: Path) -> None:
    """Fable C7b: a tree path need not be UTF-8 (Git stores bytes). Detection compares path bytes, so such a path
    elsewhere in the exported tree neither crashes the reader nor disables reuse."""
    repo, base = _repository(tmp_path)
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=repo, input=b"latin-1 name\n", check=True, capture_output=True,
    ).stdout.strip()
    entries = subprocess.run(["git", "ls-tree", "-z", base], cwd=repo, check=True, capture_output=True).stdout
    entries += b"100644 blob " + blob + b"\tcaf\xe9.txt\0"
    tree = subprocess.run(["git", "mktree", "-z"], cwd=repo, input=entries, check=True, capture_output=True).stdout
    commit = _git(repo, "commit-tree", tree.decode("ascii").strip(), "-p", base, "-m", "fixture")
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    for _ in (1, 2):
        assert GitCommitSource(commit=commit, repository=repo).read_text("a.py") == "A = 1\n"
    assert len(exports) == 1


def test_a_relative_date_placeholder_is_never_served_from_an_earlier_export(monkeypatch, tmp_path: Path) -> None:
    """Claude, C-M3 class: %cr and %ar are relative to the wall clock, which no key can fix. Git's own test clock
    (GIT_TEST_DATE_NOW) stands in for time passing between two readers."""
    repo, _ = _repository(tmp_path)
    commit = _committed(repo, {".gitattributes": "a.py export-subst\n", "a.py": "$Format:%cr$\n"})
    committed_at = int(_git(repo, "show", "-s", "--format=%ct", commit))
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    monkeypatch.setenv("GIT_TEST_DATE_NOW", str(committed_at + 5))
    assert read() == "5 seconds ago\n"
    monkeypatch.setenv("GIT_TEST_DATE_NOW", str(committed_at + 50))
    assert read() == "50 seconds ago\n"
    assert len(exports) == 2


def test_without_export_subst_head_ref_and_clock_moves_keep_reuse(monkeypatch, tmp_path: Path) -> None:
    """The control for the two above: with no export-subst in effect, nothing they move shapes the export, so one
    export still serves every reader."""
    repo, commit = _repository(tmp_path)
    later = _committed(repo, {"b.py": "B = 3\n"})
    _git(repo, "checkout", "-q", "--detach", commit)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    assert read() == "A = 1\n"
    _git(repo, "checkout", "-q", "--detach", later)
    assert read() == "A = 1\n"
    _git(repo, "tag", "p1130-marker", commit)
    assert read() == "A = 1\n"
    monkeypatch.setenv("GIT_TEST_DATE_NOW", "2000000000")
    assert read() == "A = 1\n"
    assert len(exports) == 1


def test_a_redirected_object_directory_is_part_of_the_repository_identity(monkeypatch, tmp_path: Path) -> None:
    repo, commit = _repository(tmp_path)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    read()
    assert len(exports) == 1
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(repo / ".git" / "objects"))  # same objects, redirected identity
    read()
    assert len(exports) == 2


def test_an_attribute_tree_is_bound_by_the_tree_it_resolves_to(monkeypatch, tmp_path: Path) -> None:
    """attr.tree / GIT_ATTR_SOURCE may name a moving ref. On Git 2.43 and 2.56 neither changed `git archive`
    output (Plan 11.30 Task 4 probe), but the export is bound to the tree the value resolves to, not its text,
    so a moved ref is never served from an earlier export on any Git version."""
    repo, commit = _repository(tmp_path)
    _git(repo, "config", "attr.tree", "HEAD")
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)

    def read() -> str:
        return GitCommitSource(commit=commit, repository=repo).read_text("a.py")

    assert read() == "A = 1\n" and len(exports) == 1
    assert read() == "A = 1\n" and len(exports) == 1
    _committed(repo, {".gitattributes": "a.py export-ignore\n"})  # HEAD moves; the config text does not
    read()
    assert len(exports) == 2
    _git(repo, "config", "--unset", "attr.tree")
    monkeypatch.setenv("GIT_ATTR_SOURCE", "HEAD")
    read()
    assert len(exports) == 3
    assert read() == "A = 1\n" and len(exports) == 3
    _committed(repo, {"b.py": "B = 3\n"})  # the environment value is unchanged; the tree it names is not
    read()
    assert len(exports) == 4


def test_a_failed_export_is_never_cached_and_an_absent_path_fails_for_every_reader(monkeypatch, tmp_path: Path) -> None:
    repo, commit = _repository(tmp_path)
    source_module.clear_export_cache()
    exports = _export_counter(monkeypatch)
    counting_run = subprocess.run
    failures = [subprocess.CalledProcessError(128, ["git", "archive"])]

    def failing_once(command, **kwargs):
        if tuple(command[1:3]) == ("archive", "--format=tar") and failures:
            counting_run(command, **kwargs)  # recorded as an attempted export
            raise failures.pop()
        return counting_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", failing_once)
    with pytest.raises(subprocess.CalledProcessError):
        GitCommitSource(commit=commit, repository=repo).read_text("a.py")
    assert GitCommitSource(commit=commit, repository=repo).read_text("a.py") == "A = 1\n"
    assert len(exports) == 2  # the failed export was attempted again, not reused
    for _ in (1, 2):
        with pytest.raises(KeyError):
            GitCommitSource(commit=commit, repository=repo).read_text("absent.py")
    assert len(exports) == 2


def test_source_tree_is_sorted_and_rejects_path_traversal() -> None:
    source = SourceTree({"z.py": "z = 1\n", "a.py": "a = 1\n"})
    assert source.paths() == ("a.py", "z.py")
    assert source.read_text("a.py") == "a = 1\n"
    try:
        source.read_text("../outside.py")
    except ValueError as exc:
        assert "repository-relative" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")
