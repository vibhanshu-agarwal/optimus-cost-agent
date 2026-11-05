"""Plan 12.6 Task 1: the one includable-files policy. Real files in temporary workspaces, a real Git for the ignore
semantics comparison, and the real reader; denied content must never be opened."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from optimus.guardrails import file_policy
from optimus.guardrails.file_policy import FilePolicy, FilePurpose

SENTINEL = "DUMMY_PROOF_TOKEN=not-a-real-secret-0000"  # pragma: allowlist secret - a fake sentinel
WINDOWS = sys.platform == "win32"
AUTO = FilePurpose.AUTOMATIC


def _write(root: Path, relative: str, text: str = "ordinary\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _reasons(policy: FilePolicy) -> dict[str, str]:
    return {decision.relative_path: decision.reason for decision in policy.walk(purpose=AUTO)}


@pytest.mark.parametrize(
    ("relative", "reason"),
    [
        (".env", "deny.secret"),
        ("config/.env.local", "deny.secret"),
        (".ENV.Production", "deny.secret"),
        ("certs/server.pem", "deny.secret"),
        (".optimus/debug-acp.ndjson", "deny.runtime_tree"),
        ("node_modules/pkg/index.js", "deny.skipped_dir"),
        ("src/app.py", "allowed"),
    ],
)
def test_security_denials_and_an_ordinary_control(tmp_path, relative, reason):
    _write(tmp_path, relative, SENTINEL)

    decision = FilePolicy(tmp_path).decide(relative, purpose=AUTO)

    assert decision.reason == reason and decision.allowed is (reason == "allowed")
    assert SENTINEL not in repr(decision), "a decision never carries file content"


def test_an_ignore_file_can_never_negate_a_denial(tmp_path):
    for relative in (".env", "config/.env.local", ".optimus/trace.ndjson", "src/app.py"):
        _write(tmp_path, relative, SENTINEL)
    _write(tmp_path, ".gitignore", "!.env\n!.optimus/\n")
    _write(tmp_path, ".optimusignore", "!.env*\n!config/.env.local\n!**/.optimus/**\n")

    reasons = _reasons(FilePolicy(tmp_path))

    assert reasons[".env"] == reasons["config/.env.local"] == "deny.secret"
    assert reasons[".optimus/trace.ndjson"] == "deny.runtime_tree"
    assert reasons["src/app.py"] == "allowed"


def test_gitignore_and_optimusignore_rules_with_negation_and_nesting(tmp_path):
    for relative in ("a.log", "keep.log", "sub/b.log", "build/out.txt", "build/keep.txt", "private/notes.md",
                     "docs/guide.md", "docs/keep.md", "src/app.py"):
        _write(tmp_path, relative)
    _write(tmp_path, ".gitignore", "*.log\n!keep.log\nbuild/\n!build/keep.txt\n")
    _write(tmp_path, "sub/.gitignore", "!*.log\n")
    _write(tmp_path, ".optimusignore", "private/\ndocs/*.md\n!docs/keep.md\n")

    reasons = _reasons(FilePolicy(tmp_path))

    assert reasons["a.log"] == "ignored.gitignore"
    assert reasons["keep.log"] == "allowed", "a later negation re-includes"
    assert reasons["sub/b.log"] == "allowed", "a deeper ignore file overrides a shallower one"
    assert reasons["build/out.txt"] == reasons["build/keep.txt"] == "ignored.gitignore", "no re-include under an excluded folder"
    assert reasons["private/notes.md"] == reasons["docs/guide.md"] == "ignored.optimusignore"
    assert reasons["docs/keep.md"] == reasons["src/app.py"] == reasons[".gitignore"] == "allowed"


def test_optimusignore_is_read_after_gitignore_so_it_can_re_include(tmp_path):
    _write(tmp_path, "generated/api.md")
    _write(tmp_path, ".gitignore", "generated/*\n")
    _write(tmp_path, ".optimusignore", "!generated/api.md\n")

    assert FilePolicy(tmp_path).decide("generated/api.md", purpose=AUTO).allowed


@pytest.mark.skipif(not WINDOWS, reason="NTFS compares names case-insensitively, as Git's core.ignorecase there")
def test_ignore_patterns_follow_the_platform_case_rule(tmp_path):
    _write(tmp_path, "Private/Notes.md")
    _write(tmp_path, ".optimusignore", "private/\n")

    assert FilePolicy(tmp_path).decide("Private/Notes.md", purpose=AUTO).reason == "ignored.optimusignore"


def test_empty_binary_and_oversized_files(tmp_path):
    _write(tmp_path, "empty.txt", "")
    (tmp_path / "image.bin").write_bytes(b"\x89PNG\x00\x01")
    (tmp_path / "latin1.txt").write_bytes("caf\xe9".encode("latin-1"))
    _write(tmp_path, "big.txt", "x" * 200)
    policy = FilePolicy(tmp_path, max_index_file_bytes=100)

    assert policy.decide("empty.txt", purpose=AUTO).reason == "excluded.empty"
    assert policy.decide("image.bin", purpose=AUTO).reason == "excluded.binary"
    assert policy.decide("latin1.txt", purpose=AUTO).reason == "excluded.binary"
    assert policy.decide("big.txt", purpose=FilePurpose.INDEX).reason == "excluded.too_large"
    assert policy.decide("big.txt", purpose=AUTO).allowed, "the indexing limit is not the automatic-context budget"
    assert file_policy.DEFAULT_MAX_INDEX_FILE_BYTES == 1024 * 1024


def test_denied_and_ignored_content_is_never_opened(tmp_path, monkeypatch):
    for relative in (".env", "secrets/db.txt", ".optimus/trace.ndjson", "private/notes.md", "src/app.py"):
        _write(tmp_path, relative, SENTINEL)
    _write(tmp_path, ".optimusignore", "private/\n")
    opened: list[Path] = []

    def recording(file, *args, **kwargs):  # the policy opens content only through this name
        opened.append(Path(file))
        return open(file, *args, **kwargs)

    monkeypatch.setattr(file_policy, "open", recording, raising=False)
    reasons = _reasons(FilePolicy(tmp_path))

    assert reasons["src/app.py"] == "allowed"
    assert {path.relative_to(tmp_path).as_posix() for path in opened} == {"src/app.py", ".optimusignore"}


def test_policy_revision_binds_the_ignore_files_that_judged_a_decision(tmp_path):
    _write(tmp_path, "docs/a.md")
    _write(tmp_path, "src/app.py")
    _write(tmp_path, "docs/.optimusignore", "draft.md\n")
    before = FilePolicy(tmp_path)
    docs, src = before.decide("docs/a.md", purpose=AUTO), before.decide("src/app.py", purpose=AUTO)
    _write(tmp_path, "docs/.optimusignore", "draft.md\nold.md\n")
    after = FilePolicy(tmp_path).decide("docs/a.md", purpose=AUTO)

    assert docs.policy_revision.startswith(file_policy.POLICY_VERSION + ":")
    assert docs.policy_revision != src.policy_revision, "only docs/a.md is judged by docs/.optimusignore"
    assert after.policy_revision != docs.policy_revision


def test_read_rechecks_the_target_identity_after_reading(tmp_path, monkeypatch):
    _write(tmp_path, "src/app.py")
    _write(tmp_path, "src/other.py")
    policy = FilePolicy(tmp_path)
    original = file_policy.resolve_target
    calls = {"count": 0}

    def swapped(path: Path) -> Path | None:
        calls["count"] += 1
        return original(path) if calls["count"] == 1 else original(tmp_path / "src" / "other.py")

    monkeypatch.setattr(file_policy, "resolve_target", swapped)
    decision, data = policy.read("src/app.py", purpose=AUTO)

    assert data is None and decision.reason == "deny.identity_changed"


@pytest.mark.skipif(not WINDOWS, reason="NTFS directory junctions are a Windows mechanism")
def test_junction_aliases_to_secret_or_outside_targets_are_denied(tmp_path):
    import _winapi  # CreateJunction needs no privilege, unlike a symlink

    root, outside = tmp_path / "ws", tmp_path / "outside"
    _write(root, "secrets/db.txt", SENTINEL)
    _write(root, "src/app.py")
    _write(outside, "shared.txt")
    links = {root / "notes": root / "secrets", root / "shared": outside, root / "src-alias": root / "src"}
    for link, target in links.items():
        _winapi.CreateJunction(str(target), str(link))
    try:
        reasons = _reasons(FilePolicy(root))
    finally:
        for link in links:
            os.rmdir(link)  # remove the junction itself, never through it

    assert reasons["notes/db.txt"] == "deny.secret"
    assert reasons["shared/shared.txt"] == "deny.outside_workspace"
    assert reasons["src-alias/app.py"] == "allowed"


def _deep(root: Path) -> str:
    """A folder whose full path is well past Windows' limit."""
    return "/".join(["a_folder_named_long_enough_to_add_up"] * 10)


def _long_write(root: Path, relative: str, text: str) -> None:
    path = file_policy._extended(str(root.joinpath(*relative.split("/"))))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


@pytest.mark.skipif(not WINDOWS, reason="the path length limit is a Windows mechanism")
def test_a_file_past_the_windows_path_limit_is_walked_read_and_judged_like_any_other(tmp_path):
    import _winapi

    root, outside = tmp_path / "ws", tmp_path / "outside"
    deep = _deep(root)
    assert len(str(root)) + len(deep) > 300
    _long_write(root, f"{deep}/App.java", "class App {}\n")
    _long_write(root, f"{deep}/.env", SENTINEL)
    _long_write(root, f"{deep}/.gitignore", "skipped.txt\n")
    _long_write(root, f"{deep}/skipped.txt", SENTINEL)
    _write(outside, "shared.txt", SENTINEL)
    link = file_policy._extended(str(root.joinpath(*deep.split("/"), "away")))
    _winapi.CreateJunction(str(outside), link)
    try:
        policy = FilePolicy(root)
        reasons = _reasons(policy)
        decision, data = policy.read(f"{deep}/App.java", purpose=AUTO)
    finally:
        os.rmdir(link)
        shutil.rmtree(file_policy._extended(str(root)))
    assert reasons[f"{deep}/App.java"] == "allowed"
    assert reasons[f"{deep}/.env"] == "deny.secret"
    assert reasons[f"{deep}/skipped.txt"] == "ignored.gitignore"
    assert reasons[f"{deep}/away/shared.txt"] == "deny.outside_workspace"
    assert decision.allowed and data == b"class App {}\n" and decision.resolved_identity == f"{deep}/App.java"


@pytest.mark.skipif(not WINDOWS, reason="NTFS directory junctions are a Windows mechanism")
def test_a_junction_back_to_its_own_ancestor_ends_the_walk_there(tmp_path):
    import _winapi

    root = tmp_path / "ws"
    _write(root, "src/app.py")
    _winapi.CreateJunction(str(root), str(root / "src" / "loop"))
    try:
        reasons = _reasons(FilePolicy(root))
    finally:
        os.rmdir(root / "src" / "loop")
    assert reasons == {"src/app.py": "allowed"}


def test_a_folder_that_cannot_be_listed_is_reported_and_not_skipped_in_silence(tmp_path, monkeypatch):
    _write(tmp_path, "open/a.py")
    _write(tmp_path, "locked/b.py")
    real = os.scandir

    def scandir(path):
        if os.path.basename(path) == "locked":
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(file_policy.os, "scandir", scandir)
    reasons = _reasons(FilePolicy(tmp_path))
    assert reasons == {"locked": "excluded.unreadable", "open/a.py": "allowed"}
    assert file_policy.describe("excluded.unreadable") == "a folder that cannot be listed"


@pytest.mark.parametrize(
    ("name", "special"),
    [(".env ", True), (".env.", True), ("private.key ", True), ("a.txt...", True), ("CON", True), ("nul.txt", True), ("Com1.log", True), ("LPT9", True), ("conin$", True), ("aux .txt", True),
     (".env", False), ("console.log", False), ("nullable.java", False), ("com10.txt", False), ("a b.txt", False), (".hidden", False)],
)
def test_the_names_windows_would_change_or_read_as_a_device(name, special):
    assert file_policy.windows_special_name(name) is special


@pytest.mark.skipif(not WINDOWS, reason="only the Windows extended path form takes these names literally")
@pytest.mark.parametrize("name", [".env ", "private.key ", ".env.", "CON", "NUL.txt", "notes. "])
def test_a_name_only_the_extended_form_reaches_is_denied_unopened(tmp_path, monkeypatch, name):
    root = tmp_path / "ws"
    deep = _deep(root)
    _long_write(root, f"{deep}/{name}", SENTINEL)
    _long_write(root, f"{deep}/control.txt", "ordinary\n")
    opened = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda path, *a, **k: opened.append(os.fspath(path)) or real_open(path, *a, **k))
    try:
        policy = FilePolicy(root)
        reasons = _reasons(policy)
        decision, data = policy.read(f"{deep}/{name}", purpose=AUTO)
    finally:
        monkeypatch.undo()
        shutil.rmtree(file_policy._extended(str(root)))
    assert reasons[f"{deep}/{name}"] == decision.reason == "deny.windows_name" and data is None
    assert reasons[f"{deep}/control.txt"] == "allowed"
    assert not [path for path in opened if path.endswith(name)], "denied before anything opened it"


def test_a_workspace_root_that_cannot_be_listed_is_reported(tmp_path, monkeypatch):
    _write(tmp_path, "a.py")

    def scandir(path):
        raise PermissionError(path)

    monkeypatch.setattr(file_policy.os, "scandir", scandir)
    assert _reasons(FilePolicy(tmp_path)) == {".": "excluded.unreadable"}


def test_a_link_that_loops_is_left_out_and_the_walk_goes_on(tmp_path, monkeypatch):
    """A real loop needs a symlink privilege Windows accounts often lack, so this one stands in; test_workspace_context has the real one."""
    _write(tmp_path, "a.py")
    real_scandir = os.scandir

    class _Loop:
        name = "loop.txt"
        path = str(tmp_path / "loop.txt")

        def is_symlink(self):
            return True

        def is_junction(self):
            return False

        def is_dir(self, *, follow_symlinks=True):
            return False

        def is_file(self):
            raise OSError(40, "Too many levels of symbolic links")

    monkeypatch.setattr(file_policy.os, "scandir", lambda path: [_Loop(), *real_scandir(path)])
    assert set(_reasons(FilePolicy(tmp_path))) == {"a.py"}


def test_a_path_keeps_its_spelling_until_it_nears_the_limit():
    short = str(Path("C:/short/file.txt"))
    assert file_policy.reachable_path(short) == short
    long = "C:\\" + "x" * 300
    assert file_policy.reachable_path(long) == (f"\\\\?\\{long}" if WINDOWS else long)
    assert file_policy._plain("\\\\?\\C:\\x") == "C:\\x" and file_policy._plain("\\\\?\\UNC\\host\\share") == "\\\\host\\share"


def test_invalid_paths_are_denied_without_touching_the_filesystem(tmp_path):
    policy = FilePolicy(tmp_path)

    for relative in ("", "/etc/passwd", "../escape.txt", "C:/Windows/win.ini", "a/../../b.txt"):
        assert policy.path_denial(relative) == "deny.invalid_path"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs a real Git to compare ignore semantics")
def test_gitignore_semantics_match_native_git(tmp_path):
    files = (
        "a.log", "keep.log", "sub/b.log", "sub/deep/c.log", "build/out.txt", "build/keep.txt", "src/app.py",
        "src/gen/x.py", "docs/a.md", "docs/sub/b.md", "notes/todo.txt", "root.tmp", "nested/root.tmp", "data/raw.csv",
    )
    for relative in files:
        _write(tmp_path, relative)
    _write(tmp_path, ".gitignore", "*.log\n!keep.log\nbuild/\n!build/keep.txt\n/root.tmp\nsrc/**/gen/\ndocs/*.md\ndata/\n")
    _write(tmp_path, "sub/.gitignore", "!*.log\ndeep/\n")
    _write(tmp_path, "notes/.gitignore", "*\n!.gitignore\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    listed = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files", "--others", "--ignored", "--exclude-standard"],
        check=True, capture_output=True, text=True,
    ).stdout.split()

    decided = {path for path, reason in _reasons(FilePolicy(tmp_path)).items() if reason == "ignored.gitignore"}

    assert decided == set(listed)
    assert {"a.log", "build/keep.txt", "root.tmp", "src/gen/x.py", "docs/a.md", "notes/todo.txt"} <= decided
    assert not {"keep.log", "sub/b.log", "nested/root.tmp", "docs/sub/b.md"} & decided


# --- Codex round 82: identity-bound reads, alias targets, ignore-file safety, case negation ---


def _recording_open(monkeypatch, before=None) -> list[Path]:
    """Record every file the policy opens; ``before`` runs a real filesystem change just before the first open."""
    opened: list[Path] = []

    def recording(file, *args, **kwargs):
        if before is not None and not opened:
            before()
        opened.append(Path(file))
        return open(file, *args, **kwargs)

    monkeypatch.setattr(file_policy, "open", recording, raising=False)
    return opened


def test_a_file_replaced_at_the_same_path_after_validation_is_refused_unread(tmp_path, monkeypatch):
    target = _write(tmp_path, "src/app.py")
    replacement = _write(tmp_path, "staging/app.py", SENTINEL)
    _recording_open(monkeypatch, before=lambda: os.replace(replacement, target))

    decision, data = FilePolicy(tmp_path).read("src/app.py", purpose=AUTO)

    assert data is None and decision.reason == "deny.identity_changed"


def test_an_unchanged_file_reads_through_the_validated_handle(tmp_path, monkeypatch):
    source = _write(tmp_path, "src/app.py")
    opened = _recording_open(monkeypatch)

    decision, data = FilePolicy(tmp_path).read("src/app.py", purpose=AUTO)

    assert decision.allowed and data == source.read_bytes()
    assert [path.name for path in opened] == ["app.py"]


@pytest.mark.skipif(not WINDOWS, reason="NTFS directory junctions are a Windows mechanism")
def test_a_junction_swapped_to_a_secret_folder_during_the_read_is_refused(tmp_path, monkeypatch):
    import _winapi

    _write(tmp_path, "docs/a.md")
    _write(tmp_path, "secrets/a.md", SENTINEL)
    alias = tmp_path / "notes"
    _winapi.CreateJunction(str(tmp_path / "docs"), str(alias))

    def swap():
        os.rmdir(alias)
        _winapi.CreateJunction(str(tmp_path / "secrets"), str(alias))

    opened = _recording_open(monkeypatch, before=swap)
    try:
        decision, data = FilePolicy(tmp_path).read("notes/a.md", purpose=AUTO)
    finally:
        os.rmdir(alias)

    assert data is None and decision.reason == "deny.identity_changed"
    assert all("secrets" not in path.parts for path in opened), "the secret folder's file is never opened"


@pytest.mark.skipif(not WINDOWS, reason="NTFS directory junctions are a Windows mechanism")
def test_aliases_into_skipped_folders_are_denied_unopened(tmp_path, monkeypatch):
    import _winapi

    _write(tmp_path, "node_modules/pkg/private.txt", SENTINEL)
    _write(tmp_path, ".venv/lib/site.py", SENTINEL)
    links = {tmp_path / "vendor": tmp_path / "node_modules" / "pkg", tmp_path / "env": tmp_path / ".venv" / "lib"}
    for link, target in links.items():
        _winapi.CreateJunction(str(target), str(link))
    opened = _recording_open(monkeypatch)
    try:
        reasons = _reasons(FilePolicy(tmp_path))
    finally:
        for link in links:
            os.rmdir(link)

    assert reasons["vendor/private.txt"] == reasons["env/site.py"] == "deny.skipped_dir"
    assert not opened


@pytest.mark.skipif(not WINDOWS, reason="the casefolded compare is the Windows rule")
def test_skipped_folder_names_follow_the_platform_case_rule(tmp_path):
    _write(tmp_path, "Node_Modules/pkg/index.js")

    assert FilePolicy(tmp_path).decide("Node_Modules/pkg/index.js", purpose=AUTO).reason == "deny.skipped_dir"


def test_an_oversized_ignore_file_makes_what_it_judges_unavailable(tmp_path):
    _write(tmp_path, "private/notes.md", SENTINEL)
    _write(tmp_path, "src/app.py")
    _write(tmp_path, "other/.gitignore", "*.tmp\n")
    _write(tmp_path, "other/b.txt")
    padding = "# padding\n" * (file_policy._MAX_IGNORE_FILE_BYTES // 10 + 1)
    _write(tmp_path, "private/.optimusignore", "notes.md\n" + padding)

    reasons = _reasons(FilePolicy(tmp_path))

    assert reasons["private/notes.md"] == "deny.ignore_unavailable", "never more permissive than the lost rules"
    assert reasons["src/app.py"] == reasons["other/b.txt"] == "allowed", "folders it does not judge are unaffected"


def test_an_ignore_file_that_is_not_a_regular_file_is_unavailable(tmp_path):
    _write(tmp_path, "src/app.py")
    (tmp_path / "src" / ".gitignore").mkdir()

    assert FilePolicy(tmp_path).decide("src/app.py", purpose=AUTO).reason == "deny.ignore_unavailable"


def test_a_symlinked_ignore_file_is_never_followed(tmp_path, monkeypatch):
    _write(tmp_path, "secrets/rules.txt", "app.py\n")
    _write(tmp_path, "src/app.py")
    try:
        (tmp_path / "src" / ".gitignore").symlink_to(tmp_path / "secrets" / "rules.txt")
    except OSError as exc:  # Windows without the symlink privilege: WinError 1314
        pytest.skip(f"symlink creation is unavailable on this platform account: {exc}")
    opened = _recording_open(monkeypatch)

    assert FilePolicy(tmp_path).decide("src/app.py", purpose=AUTO).reason == "deny.ignore_unavailable"
    assert not [path for path in opened if "secrets" in path.parts]


def test_a_case_variant_negation_never_re_includes(tmp_path):
    _write(tmp_path, "public.txt")
    _write(tmp_path, ".gitignore", "*.txt\n!PUBLIC.TXT\n")

    assert FilePolicy(tmp_path).decide("public.txt", purpose=AUTO).reason == "ignored.gitignore"


# --- Codex round 82 follow-up 1: content is never consumed from a swapped folder; excluded folders stay closed ---


class _ReadRecorder:
    """Wraps a handle the policy opened and records every read of its content."""

    def __init__(self, handle, path: Path, reads: list[Path]) -> None:
        self._handle, self._path, self._reads = handle, path, reads

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self._handle.__exit__(*exc_info)

    def fileno(self) -> int:
        return self._handle.fileno()

    def read(self, *args):
        self._reads.append(self._path)
        return self._handle.read(*args)


def _recording_reads(monkeypatch, before_open=None, after_open=None) -> list[Path]:
    reads: list[Path] = []

    def recording(file, *args, **kwargs):
        if before_open is not None:
            before_open()
        handle = open(file, *args, **kwargs)
        if after_open is not None:
            after_open()
        return _ReadRecorder(handle, Path(file), reads)

    monkeypatch.setattr(file_policy, "open", recording, raising=False)
    return reads


def _link_folder(link: Path, target: Path) -> None:
    if WINDOWS:
        import _winapi  # CreateJunction needs no privilege, unlike a symlink

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def _unlink_folder(link: Path) -> None:
    os.rmdir(link) if WINDOWS else os.unlink(link)  # the link itself, never through it


def test_the_read_observer_sees_an_ordinary_read(tmp_path, monkeypatch):
    _write(tmp_path, "docs/a.md")
    reads = _recording_reads(monkeypatch)

    decision, data = FilePolicy(tmp_path).read("docs/a.md", purpose=AUTO)

    assert decision.allowed and data is not None and [path.name for path in reads] == ["a.md"]


@pytest.mark.parametrize(
    ("handle_path_available", "reason"), [(True, "deny.identity_changed"), (False, "deny.unverifiable")]
)
def test_a_folder_swapped_after_validation_is_caught_before_any_byte_is_read(
    tmp_path, monkeypatch, handle_path_available, reason
):
    if not handle_path_available:  # e.g. a filesystem without final-path support: never the weaker read
        monkeypatch.setattr(file_policy, "_handle_path", lambda fd: None)
    _write(tmp_path, "docs/a.md")
    _write(tmp_path, "secrets/a.md", SENTINEL)
    docs, parked, secrets = tmp_path / "docs", tmp_path / "docs-parked", tmp_path / "secrets"
    validated_read = file_policy._read_validated

    def swap_then_read(path, target, limit):  # after the policy validated docs/a.md, before its first stat
        os.rename(docs, parked)
        _link_folder(docs, secrets)
        return validated_read(path, target, limit)

    def restore():  # right after the open, so every later pathname check sees docs again
        _unlink_folder(docs)
        os.rename(parked, docs)

    reads = _recording_reads(monkeypatch, after_open=restore)
    monkeypatch.setattr(file_policy, "_read_validated", swap_then_read)

    decision, data = FilePolicy(tmp_path).read("docs/a.md", purpose=AUTO)

    assert data is None and decision.reason == reason
    assert reads == [], "no byte of the swapped-in secret file is consumed"


def test_an_unverifiable_handle_is_never_read_even_for_an_ordinary_file(tmp_path, monkeypatch):
    _write(tmp_path, "docs/a.md")
    reads = _recording_reads(monkeypatch)
    monkeypatch.setattr(file_policy, "_handle_path", lambda fd: None)

    decision, data = FilePolicy(tmp_path).read("docs/a.md", purpose=AUTO)

    assert data is None and decision.reason == "deny.unverifiable" and reads == []


def test_a_file_replaced_after_validation_is_never_consumed(tmp_path, monkeypatch):
    target = _write(tmp_path, "src/app.py")
    replacement = _write(tmp_path, "staging/app.py", SENTINEL)
    # between the identity baseline (stat) and the open: the handle then reaches a different file
    reads = _recording_reads(monkeypatch, before_open=lambda: os.replace(replacement, target))

    decision, data = FilePolicy(tmp_path).read("src/app.py", purpose=AUTO)

    assert data is None and decision.reason == "deny.identity_changed" and reads == []


def test_an_excluded_folders_ignore_file_is_never_opened(tmp_path, monkeypatch):
    _write(tmp_path, ".gitignore", "private/\n")
    _write(tmp_path, "private/.gitignore", "!notes.md\n")
    _write(tmp_path, "private/notes.md", SENTINEL)
    _write(tmp_path, "sub/.gitignore", "*.tmp\n")
    _write(tmp_path, "sub/x.txt")
    opened = _recording_open(monkeypatch)
    policy = FilePolicy(tmp_path)

    assert policy.decide("private/notes.md", purpose=AUTO).reason == "ignored.gitignore"
    assert policy.decide("sub/x.txt", purpose=AUTO).allowed
    names = {path.relative_to(tmp_path).as_posix() for path in opened}
    assert "private/.gitignore" not in names and "private/notes.md" not in names
    assert {".gitignore", "sub/.gitignore", "sub/x.txt"} <= names, "an eligible folder's ignore file is read"


def test_names_judges_by_name_and_opens_nothing(tmp_path, monkeypatch):
    _write(tmp_path, "keep.py", SENTINEL)
    _write(tmp_path, ".env", SENTINEL)
    _write(tmp_path, "ignored.py", SENTINEL)
    _write(tmp_path, ".gitignore", "ignored.py\n")
    (tmp_path / "huge.txt").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")

    real = file_policy._read_validated

    def only_ignore_files(path, target, limit):
        assert path.name in file_policy.IGNORE_FILE_NAMES, f"{path} was opened"
        return real(path, target, limit)

    monkeypatch.setattr(file_policy, "_read_validated", only_ignore_files)
    policy = FilePolicy(tmp_path)
    names, unlisted = policy.names()
    assert set(names) == {".gitignore", "huge.txt", "keep.py"} and unlisted == 0
    admits = policy.admitter()
    assert admits("keep.py") and not admits(".env") and not admits("ignored.py") and not admits("gone.py")


def test_ignore_files_are_read_again_only_when_asked(tmp_path):
    _write(tmp_path, "keep.py", SENTINEL)
    policy = FilePolicy(tmp_path)
    assert policy.decide("keep.py", purpose=AUTO).allowed
    _write(tmp_path, ".optimusignore", "keep.py\n")
    assert policy.decide("keep.py", purpose=AUTO).allowed
    policy.forget_ignore_files()
    assert policy.decide("keep.py", purpose=AUTO).reason == "ignored.optimusignore"


def test_one_folders_verdict_is_shared_within_a_walk_and_its_answers_do_not_change(tmp_path):
    for name in ("build/a.py", "build/b.py", "src/nested/c.py", "src/nested/d.py"):
        _write(tmp_path, name, SENTINEL)
    _write(tmp_path, ".gitignore", "build/\n")
    policy = FilePolicy(tmp_path)
    calls = []
    real = policy._match

    def counting(parts, *, is_dir, folded):
        calls.append(is_dir)
        return real(parts, is_dir=is_dir, folded=folded)

    policy._match = counting
    names = policy.names()[0]
    assert set(names) == {".gitignore", "src/nested/c.py", "src/nested/d.py"}
    assert calls.count(True) <= 8, "each folder is judged once in each case mode"


def test_names_counts_a_folder_it_cannot_list(tmp_path, monkeypatch):
    _write(tmp_path, "keep.py", SENTINEL)
    _write(tmp_path, "locked/hidden.py", SENTINEL)
    real = os.scandir

    def scandir(path):
        if str(path).endswith("locked"):
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(file_policy.os, "scandir", scandir)
    assert FilePolicy(tmp_path).names() == (("keep.py",), 1)


def test_names_and_a_full_walk_agree_on_ordinary_text(tmp_path):
    for name in ("a.py", "pkg/b.py", "docs/c.md", ".env", ".git/config"):
        _write(tmp_path, name, SENTINEL)
    policy = FilePolicy(tmp_path)
    assert set(policy.names()[0]) == {decision.relative_path for decision in policy.walk(purpose=AUTO) if decision.allowed}


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows mechanism")
def test_names_judges_a_junction_out_of_the_workspace_by_its_target(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    _write(root, "keep.py", SENTINEL)
    _write(outside, "secret.py", SENTINEL)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "linked"), str(outside)], check=True, capture_output=True)
    names = FilePolicy(root).names()[0]
    assert "keep.py" in names and "linked/secret.py" not in names


def test_names_judges_a_symlink_by_its_target(tmp_path):
    root = tmp_path / "root"
    _write(root, "keep.py", SENTINEL)
    _write(root, ".env", SENTINEL)
    _write(tmp_path, "outside.py", SENTINEL)
    try:
        (root / "out.py").symlink_to(tmp_path / "outside.py")
        (root / "alias.py").symlink_to(root / ".env")
    except OSError:
        pytest.skip("this host cannot create symbolic links")
    names = FilePolicy(root).names()[0]
    assert names == ("keep.py",)


def test_names_refuses_what_a_read_would_refuse_for_its_spelling(tmp_path, monkeypatch):
    _write(tmp_path, "keep.py", SENTINEL)
    policy = FilePolicy(tmp_path)
    monkeypatch.setattr(policy, "_listing", lambda *_args: iter([(("keep.py",), True), (("a:b.py",), True), (("c\\d.py",), True)]))
    assert policy.names()[0] == ("keep.py",)
    assert not policy.admitter()("a:b.py")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot create this name")
def test_names_and_a_read_agree_on_a_real_file_with_a_colon(tmp_path):
    _write(tmp_path, "keep.py", SENTINEL)
    (tmp_path / "a:b.py").write_text(SENTINEL, encoding="utf-8")
    policy = FilePolicy(tmp_path)
    assert policy.names()[0] == ("keep.py",)
    assert not policy.read("a:b.py", purpose=AUTO)[0].allowed
