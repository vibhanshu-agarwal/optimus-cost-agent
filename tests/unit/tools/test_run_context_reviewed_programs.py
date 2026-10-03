"""Executable proofs for launch sites whose child program is assembled at run time.

The child-site map (`run_context_child_sites.json`) accepts a literal `-c` program because the map
test can read it. Three sites build their program instead: `_announcing_child` in the concurrency
diagnostics joins `announce_pid_code` with a sleep tail; `descendant_tree` in the fault-injection
support nests announce-and-sleep members inside `subprocess.Popen` spawns; and one process-tree
test formats a marker path into `open(...).close()`. Their disposition is `reviewed_program`: this
module regenerates each program with synthetic inputs, checks every statement against the reviewed
shapes (publish a pid file at exactly `<directory>/<role>.pid`, sleep, pass, spawn another reviewed
member, create the marker), runs the file-writing part in isolation to show it writes only there,
binds the proof to the helper's source and to every tail the tests reach, and rejects anything
else. `PROVEN_SITES` names the site each proof vouches for; the map test checks the registration.
No general evaluator: a program made of other statements fails, however harmless it looks.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from tests.support import concurrency, fault_injection

_ROOT = Path(__file__).resolve().parents[3]
DIAGNOSTICS = "tests/unit/support/test_concurrency_diagnostics.py"
PROCESS_TREE_TESTS = "tests/unit/tools/test_process_tree.py"

PROVEN_SITES = {
    f"{DIAGNOSTICS}::_announcing_child#1": "test_the_announcing_child_runs_only_the_reviewed_announce_and_sleep",
    f"{PROCESS_TREE_TESTS}::test_kill_tree_kills_every_descendant_including_ones_no_parent_walk_reaches#1":
        "test_descendant_trees_announce_sleep_and_spawn_only_reviewed_programs",
    f"{PROCESS_TREE_TESTS}::test_a_failure_after_the_child_ran_kills_its_whole_tree_and_keeps_the_error#1":
        "test_descendant_trees_announce_sleep_and_spawn_only_reviewed_programs",
    f"{PROCESS_TREE_TESTS}::test_a_child_that_cannot_be_contained_never_runs_and_the_error_is_raised#1":
        "test_the_marker_program_only_creates_its_marker_under_the_synthetic_directory",
}

_ROLE = re.compile(r"^[a-z]+$")


# ---------------------------------------------------------------------------
# Reviewed statement shapes
# ---------------------------------------------------------------------------


def _statements(program: str) -> list[ast.stmt]:
    try:
        return ast.parse(program).body
    except SyntaxError as exc:
        raise AssertionError(f"the program does not parse: {exc}") from exc


def _same(got: ast.stmt, want: ast.stmt) -> bool:
    return ast.dump(got) == ast.dump(want)


def announce_shape(target: str) -> list[ast.stmt]:
    """The four reviewed statements that publish the running process's pid at `target`."""
    return ast.parse(
        f"import os as _o; _t = {target!r}; open(_t + '.tmp', 'w').write(str(_o.getpid())); _o.replace(_t + '.tmp', _t)"
    ).body


def check_announce(statements: list[ast.stmt], directory: Path) -> tuple[str, list[ast.stmt]]:
    """The program starts with the announce prefix for some role, writing only `<directory>/<role>.pid`.

    Returns the role and the statements after the prefix. The target is read from the program and
    then required to be exactly the reviewed path below the synthetic directory, so neither the
    helper nor a caller can redirect the write.
    """
    assert len(statements) >= 4, "program shorter than the announce prefix"
    assignment = statements[1]
    assert isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Constant) and isinstance(assignment.value.value, str), \
        f"second statement is not the target assignment: {ast.unparse(assignment)}"
    target = Path(assignment.value.value)
    assert target.parent == Path(directory) and target.suffix == ".pid" and ".." not in target.parts, \
        f"announce target escapes the synthetic directory: {target}"
    role = target.stem
    assert _ROLE.match(role), f"role is not a plain name: {role!r}"
    for got, want in zip(statements[:4], announce_shape(str(target)), strict=True):
        assert _same(got, want), f"announce statement differs from the reviewed shape: {ast.unparse(got)}"
    return role, statements[4:]


def _is_import_of(statement: ast.stmt, *modules: str) -> bool:
    return isinstance(statement, ast.Import) and [alias.name for alias in statement.names] == list(modules) \
        and all(alias.asname is None for alias in statement.names)


def _sleep_call(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
        and ast.unparse(statement.value.func) == "time.sleep" and len(statement.value.args) == 1 and not statement.value.keywords
        and isinstance(statement.value.args[0], ast.Constant) and isinstance(statement.value.args[0].value, (int, float))
        and not isinstance(statement.value.args[0].value, bool)
    )


def _spawn_program(statement: ast.stmt) -> str:
    """The literal program of `subprocess.Popen([sys.executable, '-c', <literal>])`, else AssertionError."""
    assert isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call), f"not a spawn: {ast.unparse(statement)}"
    call = statement.value
    assert ast.unparse(call.func) == "subprocess.Popen" and not call.keywords and len(call.args) == 1, \
        f"spawn is not a bare subprocess.Popen(command): {ast.unparse(statement)}"
    command = call.args[0]
    assert isinstance(command, ast.List) and len(command.elts) == 3, f"spawn command is not [interpreter, '-c', program]: {ast.unparse(command)}"
    interpreter, flag, program = command.elts
    assert ast.unparse(interpreter) == "sys.executable", f"spawn interpreter is not sys.executable: {ast.unparse(interpreter)}"
    assert isinstance(flag, ast.Constant) and flag.value == "-c", f"spawn flag is not '-c': {ast.unparse(flag)}"
    assert isinstance(program, ast.Constant) and isinstance(program.value, str), f"spawned program is not a literal: {ast.unparse(program)}"
    return program.value


def verify_member(program: str, directory: Path, announced: list[str]) -> None:
    """A tree member: announce, then only sleeps, `pass`, and spawns of further reviewed members.

    Roles are appended to `announced` in announcement order, recursively.
    """
    role, rest = check_announce(_statements(program), directory)
    announced.append(role)
    index = 0
    while index < len(rest):
        statement = rest[index]
        if _is_import_of(statement, "time") and index + 1 < len(rest) and _sleep_call(rest[index + 1]):
            index += 2
        elif isinstance(statement, ast.Pass):
            index += 1
        elif _is_import_of(statement, "subprocess", "sys") and index + 1 < len(rest):
            verify_member(_spawn_program(rest[index + 1]), directory, announced)
            index += 2
        else:
            raise AssertionError(f"statement outside the reviewed shapes: {ast.unparse(statement)}")


def run_announce_prefix(program: str, directory: Path) -> Path:
    """Execute only the announce prefix, in this process, and return the one file it may create."""
    statements = _statements(program)[:4]
    before = set(os.listdir(directory))
    exec(compile(ast.Module(body=statements, type_ignores=[]), "<announce>", "exec"), {"__builtins__": __builtins__})  # noqa: S102 - the four statements were just checked against the reviewed shape
    created = set(os.listdir(directory)) - before
    assert len(created) == 1 and created.pop().endswith(".pid"), f"the announce prefix created {sorted(created)}"
    (target,) = [Path(directory) / name for name in set(os.listdir(directory)) - before]
    assert target.read_text(encoding="utf-8") == str(os.getpid()), "the pid file does not carry this process's pid"
    assert not (Path(directory) / (target.name + ".tmp")).exists(), "the temporary file was not replaced"
    return target


# ---------------------------------------------------------------------------
# Source bindings
# ---------------------------------------------------------------------------


def _module(relative: str) -> ast.Module:
    return ast.parse((_ROOT / relative).read_text(encoding="utf-8"))


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no function {name}")


_ANNOUNCING_CHILD_BODY = ast.parse(
    "code = announce_pid_code(directory, role) + '; ' + then\n"
    "return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
).body


def announcing_child_tails(module: ast.Module) -> list[str]:
    """`_announcing_child` is the reviewed helper and every call hands it a literal role and sleep tail."""
    helper = _function(module, "_announcing_child")
    assert [argument.arg for argument in helper.args.args] == ["directory", "role", "then"], "helper signature changed"
    assert len(helper.body) == 2 and all(_same(got, want) for got, want in zip(helper.body, _ANNOUNCING_CHILD_BODY, strict=True)), \
        "the helper body is not the reviewed construction"
    tails: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_announcing_child":
            assert len(node.args) == 3 and not node.keywords, f"call does not pass (directory, role, then) positionally: {ast.unparse(node)}"
            role, tail = node.args[1], node.args[2]
            assert isinstance(role, ast.Constant) and isinstance(role.value, str) and _ROLE.match(role.value), f"role is not a literal name: {ast.unparse(role)}"
            assert isinstance(tail, ast.Constant) and isinstance(tail.value, str), f"tail is not a literal: {ast.unparse(tail)}"
            statements = _statements(tail.value)
            assert len(statements) == 2 and _is_import_of(statements[0], "time") and _sleep_call(statements[1]), \
                f"tail is not `import time; time.sleep(<number>)`: {tail.value!r}"
            tails.append(tail.value)
    assert tails, "no call reaches the helper"
    return tails


def marker_program_parts(module: ast.Module) -> None:
    """The contained-child test formats exactly `open(<marker>!r, 'w').close()` with `marker = tmp_path / 'ran'`."""
    function = _function(module, "test_a_child_that_cannot_be_contained_never_runs_and_the_error_is_raised")
    assert any(_same(statement, ast.parse("marker = tmp_path / 'ran'").body[0]) for statement in function.body), "marker is not tmp_path / 'ran'"
    launches = [node for node in ast.walk(function) if isinstance(node, ast.Call) and ast.unparse(node.func) == "process_tree.popen"]
    assert len(launches) == 1 and len(launches[0].args) == 1 and not launches[0].keywords, "one bare popen(command) launch expected"
    command = launches[0].args[0]
    assert isinstance(command, ast.List) and len(command.elts) == 3, "command is not [interpreter, '-c', program]"
    interpreter, flag, program = command.elts
    assert ast.unparse(interpreter) == "sys.executable" and isinstance(flag, ast.Constant) and flag.value == "-c"
    assert isinstance(program, ast.JoinedStr) and len(program.values) == 3, f"program is not the reviewed f-string: {ast.unparse(program)}"
    head, value, tail = program.values
    assert isinstance(head, ast.Constant) and head.value == "open(", ast.unparse(program)
    assert isinstance(value, ast.FormattedValue) and value.conversion == ord("r") and value.format_spec is None \
        and ast.unparse(value.value) == "str(marker)", ast.unparse(program)
    assert isinstance(tail, ast.Constant) and tail.value == ", 'w').close()", ast.unparse(program)


def check_marker_program(program: str, directory: Path) -> Path:
    """`open('<directory>/ran', 'w').close()` and nothing else; returns the marker path."""
    statements = _statements(program)
    assert len(statements) == 1, f"{len(statements)} statements, expected one"
    expression = statements[0]
    assert isinstance(expression, ast.Expr) and isinstance(expression.value, ast.Call) and not expression.value.args and not expression.value.keywords
    close = expression.value.func
    assert isinstance(close, ast.Attribute) and close.attr == "close" and isinstance(close.value, ast.Call), ast.unparse(expression)
    opened = close.value
    assert ast.unparse(opened.func) == "open" and len(opened.args) == 2 and not opened.keywords, ast.unparse(expression)
    path, mode = opened.args
    assert isinstance(path, ast.Constant) and isinstance(path.value, str) and isinstance(mode, ast.Constant) and mode.value == "w"
    marker = Path(path.value)
    assert marker == Path(directory) / "ran", f"marker is not <directory>/ran: {marker}"
    return marker


# ---------------------------------------------------------------------------
# The proofs
# ---------------------------------------------------------------------------


def test_the_announcing_child_runs_only_the_reviewed_announce_and_sleep(tmp_path: Path) -> None:
    tails = announcing_child_tails(_module(DIAGNOSTICS))
    for tail in sorted(set(tails)):
        program = concurrency.announce_pid_code(tmp_path, "grandchild") + "; " + tail
        role, rest = check_announce(_statements(program), tmp_path)
        assert role == "grandchild"
        assert len(rest) == 2 and _is_import_of(rest[0], "time") and _sleep_call(rest[1]), f"unexpected tail statements in {program!r}"
    target = run_announce_prefix(concurrency.announce_pid_code(tmp_path, "grandchild"), tmp_path)
    assert target == tmp_path / "grandchild.pid" and os.listdir(tmp_path) == ["grandchild.pid"]


def test_descendant_trees_announce_sleep_and_spawn_only_reviewed_programs(tmp_path: Path) -> None:
    """Every shape the process-tree tests launch: each member announces under the synthetic directory,
    then only sleeps, passes or spawns another reviewed member; the roles come out in announcement order."""
    module = _module(PROCESS_TREE_TESTS)
    calls = [node for node in ast.walk(module) if isinstance(node, ast.Call) and ast.unparse(node.func) == "descendant_tree"]
    assert calls and all(len(call.args) == 2 and not call.keywords for call in calls), "the tests pass only (directory, shape)"
    for shape in fault_injection.TREE_SHAPES:
        program, roles = fault_injection.descendant_tree(tmp_path, shape)
        announced: list[str] = []
        verify_member(program, tmp_path, announced)
        assert announced == list(roles), (shape, announced, roles)
    target = run_announce_prefix(fault_injection.descendant_tree(tmp_path, "parent-alive")[0], tmp_path)
    assert target == tmp_path / "child.pid"


def test_the_marker_program_only_creates_its_marker_under_the_synthetic_directory(tmp_path: Path) -> None:
    """The site's test runs on Windows only; this proof of its program runs on every platform."""
    marker_program_parts(_module(PROCESS_TREE_TESTS))
    marker = tmp_path / "ran"
    program = f"open({str(marker)!r}, 'w').close()"  # the reviewed f-string, rendered with a synthetic marker
    assert check_marker_program(program, tmp_path) == marker
    exec(compile(program, "<marker>", "exec"), {"__builtins__": __builtins__})  # noqa: S102 - just checked to be open(<marker>, 'w').close()
    assert os.listdir(tmp_path) == ["ran"] and marker.read_bytes() == b""


# ---------------------------------------------------------------------------
# Sensitivity: the proofs reject what they are meant to reject
# ---------------------------------------------------------------------------


def _announce(directory: Path, role: str = "grandchild") -> str:
    return concurrency.announce_pid_code(directory, role)


@pytest.mark.parametrize(
    ("name", "build"),
    [
        ("tail-runs-a-command", lambda d: _announce(d) + "; import os; os.system('x')"),
        ("tail-imports-product", lambda d: _announce(d) + "; import optimus"),
        ("tail-sleep-not-a-number", lambda d: _announce(d) + "; import time; time.sleep(n)"),
        ("tail-extra-statement", lambda d: _announce(d) + "; import time; time.sleep(1); print(1)"),
        ("announce-outside-directory", lambda d: concurrency.announce_pid_code(d.parent, "grandchild") + "; import time; time.sleep(1)"),
        ("announce-escaping-directory", lambda d: concurrency.announce_pid_code(d / "..", "grandchild") + "; import time; time.sleep(1)"),
        ("announce-role-with-separator", lambda d: concurrency.announce_pid_code(d, "../x") + "; import time; time.sleep(1)"),
        ("announce-statement-changed", lambda d: _announce(d).replace("_o.getpid()", "_o.getcwd()") + "; import time; time.sleep(1)"),
        ("announce-write-elsewhere", lambda d: _announce(d).replace("_t + '.tmp'", "'/x'", 1) + "; import time; time.sleep(1)"),
        ("spawn-non-literal", lambda d: _announce(d) + "; import subprocess, sys; subprocess.Popen([sys.executable, '-c', code])"),
        ("spawn-other-interpreter", lambda d: _announce(d) + "; import subprocess, sys; subprocess.Popen(['python', '-c', 'pass'])"),
        ("spawn-script", lambda d: _announce(d) + "; import subprocess, sys; subprocess.Popen([sys.executable, 'x.py'])"),
        ("spawn-with-keywords", lambda d: _announce(d) + "; import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'pass'], shell=True)"),
        ("spawned-member-unreviewed", lambda d: _announce(d) + "; import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import optimus'])"),
        ("spawned-member-announces-elsewhere", lambda d: _announce(d) + "; import subprocess, sys; subprocess.Popen([sys.executable, '-c', "
            + repr(concurrency.announce_pid_code(d.parent, "grandchild")) + "])"),
        ("dynamic-import", lambda d: _announce(d) + "; __import__('os').system('x')"),
        ("eval", lambda d: _announce(d) + "; eval('1')"),
        ("not-a-program", lambda d: _announce(d) + "; import ("),
        ("no-announce", lambda d: "import time; time.sleep(1)"),
    ],
)
def test_a_program_outside_the_reviewed_shapes_is_rejected(tmp_path: Path, name: str, build) -> None:
    with pytest.raises(AssertionError):
        verify_member(build(tmp_path), tmp_path, [])


def test_the_reviewed_shapes_are_accepted_as_controls(tmp_path: Path) -> None:
    announced: list[str] = []
    verify_member(_announce(tmp_path, "child") + "; import time; time.sleep(1.5); pass", tmp_path, announced)
    assert announced == ["child"]


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("helper-extra-statement",
         "def _announcing_child(directory, role, then):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    print(code)\n    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
         "def test_x(tmp_path):\n    _announcing_child(tmp_path, 'grandchild', 'import time; time.sleep(1)')\n"),
        ("helper-different-command",
         "def _announcing_child(directory, role, then):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    return subprocess.Popen([sys.executable, code], stdin=subprocess.DEVNULL)\n"
         "def test_x(tmp_path):\n    _announcing_child(tmp_path, 'grandchild', 'import time; time.sleep(1)')\n"),
        ("helper-signature",
         "def _announcing_child(directory, role, then, extra):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
         "def test_x(tmp_path):\n    _announcing_child(tmp_path, 'grandchild', 'import time; time.sleep(1)', 1)\n"),
        ("tail-not-literal",
         "def _announcing_child(directory, role, then):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
         "def test_x(tmp_path):\n    _announcing_child(tmp_path, 'grandchild', then)\n"),
        ("tail-not-a-sleep",
         "def _announcing_child(directory, role, then):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
         "def test_x(tmp_path):\n    _announcing_child(tmp_path, 'grandchild', 'import os; os.system(\"x\")')\n"),
        ("role-not-a-literal",
         "def _announcing_child(directory, role, then):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
         "def test_x(tmp_path):\n    _announcing_child(tmp_path, role, 'import time; time.sleep(1)')\n"),
        ("no-call",
         "def _announcing_child(directory, role, then):\n    code = announce_pid_code(directory, role) + '; ' + then\n"
         "    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"),
    ],
)
def test_a_changed_announcing_helper_or_tail_is_rejected(name: str, source: str) -> None:
    with pytest.raises(AssertionError):
        announcing_child_tails(ast.parse(source))


_MARKER_TEST = (
    "def test_a_child_that_cannot_be_contained_never_runs_and_the_error_is_raised(tmp_path, monkeypatch):\n"
    "    marker = tmp_path / 'ran'\n"
    "    process_tree.popen([sys.executable, '-c', f\"open({str(marker)!r}, 'w').close()\"])\n"
)


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("marker-elsewhere", _MARKER_TEST.replace("tmp_path / 'ran'", "tmp_path.parent / 'ran'")),
        ("program-changed", _MARKER_TEST.replace(".close()", ".write('x')")),
        ("conversion-dropped", _MARKER_TEST.replace("!r", "")),
        ("extra-launch", _MARKER_TEST + "    process_tree.popen([sys.executable, '-c', 'pass'])\n"),
        ("keyword-arguments", _MARKER_TEST.replace("])\n", "], shell=True)\n")),
    ],
)
def test_a_changed_marker_program_is_rejected(name: str, source: str) -> None:
    with pytest.raises(AssertionError):
        marker_program_parts(ast.parse(source))


def test_the_reviewed_marker_test_is_accepted_as_a_control() -> None:
    marker_program_parts(ast.parse(_MARKER_TEST))


@pytest.mark.parametrize(
    ("name", "program"),
    [
        ("elsewhere", "open('/elsewhere/ran', 'w').close()"),
        ("mode", "open('{marker}', 'a').close()"),
        ("write", "open('{marker}', 'w').write('x')"),
        ("two-statements", "open('{marker}', 'w').close(); import os"),
    ],
)
def test_a_rendered_marker_program_outside_the_shape_is_rejected(tmp_path: Path, name: str, program: str) -> None:
    with pytest.raises(AssertionError):
        check_marker_program(program.replace("{marker}", str(tmp_path / "ran").replace("\\", "\\\\")), tmp_path)


def test_an_announce_prefix_that_writes_elsewhere_is_caught_before_it_runs(tmp_path: Path) -> None:
    """The executable step runs only the checked prefix; a program whose prefix fails the check never runs."""
    rogue = concurrency.announce_pid_code(tmp_path.parent, "grandchild")
    with pytest.raises(AssertionError):
        check_announce(_statements(rogue), tmp_path)
    assert os.listdir(tmp_path) == []
