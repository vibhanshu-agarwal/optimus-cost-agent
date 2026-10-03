"""Executable proofs for launch sites whose child program is assembled at run time.

The child-site map (`run_context_child_sites.json`) accepts a literal `-c` program because the map
test can read it. Three sites build their program instead: `_announcing_child` in the concurrency
diagnostics joins `announce_pid_code` with a sleep tail; `descendant_tree` in the fault-injection
support nests announce-and-sleep members inside `subprocess.Popen` spawns; and one process-tree
test formats a marker path into `open(...).close()`. Their disposition is `reviewed_program`: this
module binds each site end to end (Codex correction review, 2026-10-04): the helper's source, the
values the calling test actually passes (its own `tmp_path` fixture, a literal role or shape, a
literal sleep tail), the single assignment that produces the launched value, and the launch
command itself; then it regenerates the program with a synthetic directory, checks every statement
against the reviewed shapes (publish a pid file at exactly `<directory>/<role>.pid`, sleep, pass,
spawn another reviewed member, create the marker), and runs the file-writing part in isolation,
validating the very statements it executes first. `PROVEN_SITES` names the site each proof vouches
for; the map test checks the registration. No general evaluator or dataflow engine: a caller that
passes anything else, rebinds the value, or launches a different command fails the proof.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from tests.support import concurrency, fault_injection
from tests.unit.tools.test_run_context_child_sites import binds, function_binds

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
_LAUNCH_KEYWORDS = {"stdin", "stdout", "stderr"}  # launch keywords that cannot change what runs


# ---------------------------------------------------------------------------
# Reviewed statement shapes
# ---------------------------------------------------------------------------


def _statements(program: str) -> list[ast.stmt]:
    try:
        return ast.parse(program).body
    except SyntaxError as exc:
        raise AssertionError(f"the program does not parse: {exc}") from exc


def _same(got: ast.AST, want: ast.AST) -> bool:
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


def _is_sleep_tail(program: str) -> bool:
    statements = _statements(program)
    return len(statements) == 2 and _is_import_of(statements[0], "time") and _sleep_call(statements[1])


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
    """Check the program's announce prefix against `directory`, execute exactly those checked statements, and
    return the one file they created. The statements executed are the parsed objects that passed the check."""
    statements = _statements(program)
    role, _ = check_announce(statements, directory)
    prefix = statements[:4]
    before = set(os.listdir(directory))
    exec(compile(ast.Module(body=prefix, type_ignores=[]), "<announce>", "exec"), {"__builtins__": __builtins__})  # noqa: S102 - the four statements were just checked against the reviewed shape
    created = set(os.listdir(directory)) - before
    assert created == {f"{role}.pid"}, f"the announce prefix created {sorted(created)}"
    target = Path(directory) / f"{role}.pid"
    assert target.read_text(encoding="utf-8") == str(os.getpid()), "the pid file does not carry this process's pid"
    return target


# ---------------------------------------------------------------------------
# Source bindings: the helper, the calling tests' actual inputs, and the launch
# ---------------------------------------------------------------------------


def _module(relative: str) -> ast.Module:
    return ast.parse((_ROOT / relative).read_text(encoding="utf-8"))


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    found = [node for node in ast.walk(module) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    assert len(found) == 1, f"{len(found)} definitions of {name}"
    return found[0]


def _functions(module: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [node for node in ast.walk(module) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _imports_name(module: ast.Module, source: str, name: str) -> None:
    """The module imports `name` from `source` once, at the top level, unaliased, and never rebinds it."""
    imports = [node for node in module.body if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == source
               and any(alias.name == name and alias.asname is None for alias in node.names)]
    assert len(imports) == 1, f"{name} is not imported once from {source}"
    others = [statement for statement in module.body if statement not in imports and binds(statement, name)]
    assert not others, f"{name} is rebound at module level: {ast.unparse(others[0])[:80]}"


def _fixture_parameter(function: ast.FunctionDef | ast.AsyncFunctionDef, name: str = "tmp_path") -> None:
    assert any(parameter.arg == name for parameter in function.args.args), f"{function.name} has no {name} parameter"
    assert not any(binds(statement, name) for statement in function.body), f"{function.name} rebinds {name}"


def _single_assignment(function: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> ast.Assign:
    """The one statement in the function that binds `name`; it must be a plain assignment."""
    bindings = [statement for statement in ast.walk(function) if isinstance(statement, ast.stmt) and binds(statement, name)
                and not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    # ast.walk yields a compound statement and its nested statements; keep the innermost binding ones.
    innermost = [statement for statement in bindings if not any(other is not statement and other in ast.walk(statement) for other in bindings)]
    assert len(innermost) == 1, f"{function.name} binds {name} {len(innermost)} times, expected exactly once"
    assignment = innermost[0]
    assert isinstance(assignment, ast.Assign), f"{function.name} binds {name} by {type(assignment).__name__}, not a plain assignment"
    assert not any(parameter.arg == name for parameter in function.args.args), f"{name} is also a parameter of {function.name}"
    return assignment


def _launch_command(call: ast.Call, program: ast.expr, keywords: set[str]) -> None:
    """`popen([sys.executable, '-c', <program>], **keywords)` with exactly that program expression."""
    assert len(call.args) == 1, f"launch does not pass exactly one positional command: {ast.unparse(call)}"
    command = call.args[0]
    assert isinstance(command, ast.List) and len(command.elts) == 3, f"command is not [interpreter, '-c', program]: {ast.unparse(command)}"
    interpreter, flag, launched = command.elts
    assert ast.unparse(interpreter) == "sys.executable", f"interpreter is not sys.executable: {ast.unparse(interpreter)}"
    assert isinstance(flag, ast.Constant) and flag.value == "-c", f"flag is not '-c': {ast.unparse(flag)}"
    assert _same(launched, program), f"launched program is {ast.unparse(launched)}, expected {ast.unparse(program)}"
    assert {keyword.arg for keyword in call.keywords} <= keywords, f"launch keywords outside {sorted(keywords)}: {ast.unparse(call)}"


_ANNOUNCING_CHILD_BODY = ast.parse(
    "code = announce_pid_code(directory, role) + '; ' + then\n"
    "return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
).body


def announcing_child_tails(module: ast.Module) -> list[str]:
    """`_announcing_child` is the reviewed helper and every call hands it the test's own `tmp_path`, a literal role and a literal sleep tail."""
    _imports_name(module, "tests.support.concurrency", "announce_pid_code")
    helper = _function(module, "_announcing_child")
    assert not any(binds(statement, "_announcing_child") for statement in module.body if statement is not helper), "the helper is rebound"
    assert [argument.arg for argument in helper.args.args] == ["directory", "role", "then"] and not (
        helper.args.vararg or helper.args.kwarg or helper.args.kwonlyargs or helper.args.defaults
    ), "helper signature changed"
    assert len(helper.body) == 2 and all(_same(got, want) for got, want in zip(helper.body, _ANNOUNCING_CHILD_BODY, strict=True)), \
        "the helper body is not the reviewed construction"
    tails: list[str] = []
    for function in _functions(module):
        if function is helper:
            continue
        for node in ast.walk(function):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_announcing_child"):
                continue
            assert len(node.args) == 3 and not node.keywords, f"call does not pass (directory, role, then) positionally: {ast.unparse(node)}"
            directory, role, tail = node.args
            assert isinstance(directory, ast.Name) and directory.id == "tmp_path", f"directory is not the test's tmp_path: {ast.unparse(node)}"
            _fixture_parameter(function)
            assert isinstance(role, ast.Constant) and isinstance(role.value, str) and _ROLE.match(role.value), f"role is not a literal name: {ast.unparse(role)}"
            assert isinstance(tail, ast.Constant) and isinstance(tail.value, str) and _is_sleep_tail(tail.value), \
                f"tail is not a literal `import time; time.sleep(<number>)`: {ast.unparse(tail)}"
            tails.append(tail.value)
    assert tails, "no call reaches the helper"
    return tails


_MARKER_TEST = "test_a_child_that_cannot_be_contained_never_runs_and_the_error_is_raised"
_MARKER_PROGRAM = ast.parse("f\"open({str(marker)!r}, 'w').close()\"", mode="eval").body


def marker_program_parts(module: ast.Module) -> None:
    """The contained-child test launches exactly `[sys.executable, '-c', f"open({str(marker)!r}, 'w').close()"]`,
    and `marker` is bound once in that test, to `tmp_path / 'ran'`, before the launch."""
    _imports_name(module, "tools", "process_tree")
    function = _function(module, _MARKER_TEST)
    _fixture_parameter(function)
    assignment = _single_assignment(function, "marker")
    assert _same(assignment, ast.parse("marker = tmp_path / 'ran'").body[0]), f"marker is not tmp_path / 'ran': {ast.unparse(assignment)}"
    assert not function_binds(function, "process_tree"), f"{function.name} rebinds process_tree"
    launches = [node for node in ast.walk(function) if isinstance(node, ast.Call) and ast.unparse(node.func) == "process_tree.popen"]
    assert len(launches) == 1, f"{len(launches)} launches in {function.name}, expected one"
    assert assignment.lineno < launches[0].lineno, "marker is assigned after the launch"
    _launch_command(launches[0], _MARKER_PROGRAM, set())


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


def _parametrized_over_tree_shapes(function: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """`@pytest.mark.parametrize("<name>", TREE_SHAPES)` on the function, and `name` is its parameter."""
    for decorator in function.decorator_list:
        if (isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "pytest.mark.parametrize" and len(decorator.args) == 2
                and not decorator.keywords and isinstance(decorator.args[0], ast.Constant) and decorator.args[0].value == name
                and isinstance(decorator.args[1], ast.Name) and decorator.args[1].id == "TREE_SHAPES"):
            return any(parameter.arg == name for parameter in function.args.args) and not any(binds(s, name) for s in function.body)
    return False


def descendant_tree_launches(module: ast.Module) -> dict[str, set[str]]:
    """Every test that launches a `descendant_tree` program: the shapes it launches, bound end to end.

    In each such test `code` is bound exactly once, by `code, roles = descendant_tree(tmp_path, <shape>)`
    where `tmp_path` is the test's fixture and `<shape>` is a literal in TREE_SHAPES or the test's
    `shape` parameter parametrized over TREE_SHAPES; and every `process_tree.popen` in the test launches
    exactly `[sys.executable, '-c', code]` after that binding, with only stdio keywords.
    """
    _imports_name(module, "tests.support.fault_injection", "descendant_tree")
    _imports_name(module, "tests.support.fault_injection", "TREE_SHAPES")
    _imports_name(module, "tools", "process_tree")
    shapes_by_test: dict[str, set[str]] = {}
    for function in _functions(module):
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "descendant_tree"]
        if not calls:
            continue
        assert not function_binds(function, "descendant_tree") and not function_binds(function, "process_tree"), f"{function.name} rebinds a helper"
        _fixture_parameter(function)
        assignment = _single_assignment(function, "code")
        assert len(assignment.targets) == 1 and isinstance(assignment.targets[0], ast.Tuple) and [ast.unparse(e) for e in assignment.targets[0].elts] == ["code", "roles"], \
            f"{function.name}: code is not bound by `code, roles = descendant_tree(...)`"
        assert len(calls) == 1 and assignment.value is calls[0], f"{function.name}: descendant_tree is called other than in that binding"
        call = calls[0]
        assert len(call.args) == 2 and not call.keywords, f"{function.name}: descendant_tree is not called as (directory, shape)"
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == "tmp_path", f"{function.name}: directory is not tmp_path"
        shape = call.args[1]
        if isinstance(shape, ast.Constant) and isinstance(shape.value, str):
            assert shape.value in fault_injection.TREE_SHAPES, f"{function.name}: unknown shape {shape.value!r}"
            shapes = {shape.value}
        elif isinstance(shape, ast.Name) and _parametrized_over_tree_shapes(function, shape.id):
            shapes = set(fault_injection.TREE_SHAPES)
        else:
            raise AssertionError(f"{function.name}: shape is neither a literal nor a parameter parametrized over TREE_SHAPES: {ast.unparse(shape)}")
        launches = [node for node in ast.walk(function) if isinstance(node, ast.Call) and ast.unparse(node.func) == "process_tree.popen"]
        assert launches, f"{function.name} never launches"
        for launch in launches:
            assert launch.lineno > assignment.lineno, f"{function.name}: launch precedes the binding of code"
            _launch_command(launch, ast.Name(id="code", ctx=ast.Load()), _LAUNCH_KEYWORDS)
        shapes_by_test[function.name] = shapes
    assert shapes_by_test, "no test launches a descendant tree"
    return shapes_by_test


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
    target = run_announce_prefix(concurrency.announce_pid_code(tmp_path, "grandchild") + "; " + tails[0], tmp_path)
    assert target == tmp_path / "grandchild.pid" and os.listdir(tmp_path) == ["grandchild.pid"]


def test_descendant_trees_announce_sleep_and_spawn_only_reviewed_programs(tmp_path: Path) -> None:
    """Every shape the process-tree tests actually launch: each member announces under the synthetic directory,
    then only sleeps, passes or spawns another reviewed member; the roles come out in announcement order."""
    shapes_by_test = descendant_tree_launches(_module(PROCESS_TREE_TESTS))
    launched = set().union(*shapes_by_test.values())
    assert launched == set(fault_injection.TREE_SHAPES), launched
    for shape in sorted(launched):
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
    program = f"open({str(marker)!r}, 'w').close()"  # the bound f-string, rendered with a synthetic marker
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


_DIAGNOSTICS_CONTROL = (
    "from tests.support.concurrency import announce_pid_code\n"
    "import subprocess, sys\n"
    "def _announcing_child(directory, role: str, then: str):\n"
    "    code = announce_pid_code(directory, role) + '; ' + then\n"
    "    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)\n"
    "def test_x(tmp_path):\n"
    "    _announcing_child(tmp_path, 'grandchild', 'import time; time.sleep(1)')\n"
)


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("caller-directory-outside-tmp-path", _DIAGNOSTICS_CONTROL.replace("_announcing_child(tmp_path,", "_announcing_child(tmp_path.parent,")),
        ("caller-directory-other-name", _DIAGNOSTICS_CONTROL.replace("_announcing_child(tmp_path,", "_announcing_child(directory,")),
        ("caller-rebinds-tmp-path", _DIAGNOSTICS_CONTROL.replace("def test_x(tmp_path):\n", "def test_x(tmp_path):\n    tmp_path = tmp_path.parent\n")),
        ("caller-without-fixture", _DIAGNOSTICS_CONTROL.replace("def test_x(tmp_path):\n", "def test_x():\n    tmp_path = None\n")),
        ("helper-extra-statement", _DIAGNOSTICS_CONTROL.replace("    return subprocess.Popen", "    print(code)\n    return subprocess.Popen")),
        ("helper-different-command", _DIAGNOSTICS_CONTROL.replace("[sys.executable, '-c', code]", "[sys.executable, code]")),
        ("helper-signature", _DIAGNOSTICS_CONTROL.replace("then: str):", "then: str, extra=None):")),
        ("helper-rebound", _DIAGNOSTICS_CONTROL + "_announcing_child = print\n"),
        ("announce-rebound", _DIAGNOSTICS_CONTROL + "announce_pid_code = str\n"),
        ("announce-imported-elsewhere", _DIAGNOSTICS_CONTROL.replace("from tests.support.concurrency import announce_pid_code", "from somewhere import announce_pid_code")),
        ("tail-not-literal", _DIAGNOSTICS_CONTROL.replace("'import time; time.sleep(1)')", "then)")),
        ("tail-not-a-sleep", _DIAGNOSTICS_CONTROL.replace("'import time; time.sleep(1)'", "'import os; os.system(\"x\")'")),
        ("role-not-a-literal", _DIAGNOSTICS_CONTROL.replace("'grandchild'", "role")),
        ("no-call", _DIAGNOSTICS_CONTROL.replace("    _announcing_child(tmp_path, 'grandchild', 'import time; time.sleep(1)')\n", "    pass\n")),
    ],
)
def test_a_changed_announcing_helper_or_caller_is_rejected(name: str, source: str) -> None:
    assert source != _DIAGNOSTICS_CONTROL, name
    with pytest.raises(AssertionError):
        announcing_child_tails(ast.parse(source))


def test_the_reviewed_announcing_construction_is_accepted_as_a_control() -> None:
    assert announcing_child_tails(ast.parse(_DIAGNOSTICS_CONTROL)) == ["import time; time.sleep(1)"]


_MARKER_CONTROL = (
    "import subprocess, sys\nfrom tools import process_tree\n"
    f"def {_MARKER_TEST}(tmp_path, monkeypatch):\n"
    "    marker = tmp_path / 'ran'\n"
    "    process_tree.popen([sys.executable, '-c', f\"open({str(marker)!r}, 'w').close()\"])\n"
)


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("marker-elsewhere", _MARKER_CONTROL.replace("tmp_path / 'ran'", "tmp_path.parent / 'ran'")),
        ("marker-reassigned-before-launch", _MARKER_CONTROL.replace("    marker = tmp_path / 'ran'\n", "    marker = tmp_path / 'ran'\n    marker = tmp_path.parent / 'ran'\n")),
        ("marker-rebound-by-for", _MARKER_CONTROL.replace("    marker = tmp_path / 'ran'\n", "    marker = tmp_path / 'ran'\n    for marker in [tmp_path.parent]:\n        pass\n")),
        ("marker-assigned-after-launch", _MARKER_CONTROL.replace("    marker = tmp_path / 'ran'\n", "").replace(".close()\"])\n", ".close()\"])\n    marker = tmp_path / 'ran'\n")),
        ("tmp-path-rebound", _MARKER_CONTROL.replace("    marker =", "    tmp_path = tmp_path.parent\n    marker =")),
        ("program-changed", _MARKER_CONTROL.replace(".close()", ".write('x')")),
        ("conversion-dropped", _MARKER_CONTROL.replace("!r", "")),
        ("extra-launch", _MARKER_CONTROL + "    process_tree.popen([sys.executable, '-c', 'pass'])\n"),
        ("keyword-arguments", _MARKER_CONTROL.replace("])\n", "], shell=True)\n")),
        ("wrapper-rebound", _MARKER_CONTROL.replace("    marker =", "    process_tree = None\n    marker =")),
        ("wrapper-imported-elsewhere", _MARKER_CONTROL.replace("from tools import process_tree", "from somewhere import process_tree")),
    ],
)
def test_a_changed_marker_test_is_rejected(name: str, source: str) -> None:
    assert source != _MARKER_CONTROL, name
    with pytest.raises(AssertionError):
        marker_program_parts(ast.parse(source))


def test_the_reviewed_marker_test_is_accepted_as_a_control() -> None:
    marker_program_parts(ast.parse(_MARKER_CONTROL))


_TREE_CONTROL = (
    "import subprocess, sys\nimport pytest\n"
    "from tests.support.fault_injection import TREE_SHAPES, descendant_tree\nfrom tools import process_tree\n"
    "@pytest.mark.parametrize('shape', TREE_SHAPES)\n"
    "def test_every(tmp_path, shape):\n"
    "    code, roles = descendant_tree(tmp_path, shape)\n"
    "    process = process_tree.popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
    "def test_one(tmp_path, monkeypatch):\n"
    "    code, roles = descendant_tree(tmp_path, 'middle-exited')\n"
    "    with pytest.raises(OSError):\n"
    "        process_tree.popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
)


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("code-appended-before-launch", _TREE_CONTROL.replace("    code, roles = descendant_tree(tmp_path, shape)\n", "    code, roles = descendant_tree(tmp_path, shape)\n    code += '; import optimus'\n")),
        ("code-reassigned", _TREE_CONTROL.replace("    code, roles = descendant_tree(tmp_path, 'middle-exited')\n", "    code, roles = descendant_tree(tmp_path, 'middle-exited')\n    code = 'import optimus'\n")),
        ("launched-expression-differs", _TREE_CONTROL.replace("[sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\ndef test_one", "[sys.executable, '-c', code + 'x'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\ndef test_one")),
        ("directory-outside-tmp-path", _TREE_CONTROL.replace("descendant_tree(tmp_path, shape)", "descendant_tree(tmp_path.parent, shape)")),
        ("directory-other-name", _TREE_CONTROL.replace("descendant_tree(tmp_path, 'middle-exited')", "descendant_tree(directory, 'middle-exited')")),
        ("tmp-path-rebound", _TREE_CONTROL.replace("def test_one(tmp_path, monkeypatch):\n", "def test_one(tmp_path, monkeypatch):\n    tmp_path = tmp_path.parent\n")),
        ("unknown-shape", _TREE_CONTROL.replace("'middle-exited'", "'all-exited'")),
        ("shape-parametrized-over-other-list", _TREE_CONTROL.replace("@pytest.mark.parametrize('shape', TREE_SHAPES)", "@pytest.mark.parametrize('shape', OTHER)")),
        ("shape-not-a-parameter", _TREE_CONTROL.replace("@pytest.mark.parametrize('shape', TREE_SHAPES)\ndef test_every(tmp_path, shape):\n", "def test_every(tmp_path):\n    shape = 'parent-alive'\n")),
        ("launch-with-env", _TREE_CONTROL.replace("stderr=subprocess.PIPE)\ndef test_one", "stderr=subprocess.PIPE, env={})\ndef test_one")),
        ("launch-with-shell", _TREE_CONTROL.replace("stderr=subprocess.PIPE)\n", "stderr=subprocess.PIPE, shell=True)\n")),
        ("launch-before-binding", _TREE_CONTROL.replace("    code, roles = descendant_tree(tmp_path, 'middle-exited')\n    with pytest.raises(OSError):\n        process_tree.popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n", "    process_tree.popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n    code, roles = descendant_tree(tmp_path, 'middle-exited')\n")),
        ("helper-called-twice", _TREE_CONTROL.replace("    with pytest.raises(OSError):\n", "    other = descendant_tree(tmp_path, 'parent-alive')\n    with pytest.raises(OSError):\n")),
        ("helper-rebound-in-test", _TREE_CONTROL.replace("def test_one(tmp_path, monkeypatch):\n", "def test_one(tmp_path, monkeypatch):\n    descendant_tree = print\n")),
        ("helper-rebound-at-module", _TREE_CONTROL + "descendant_tree = print\n"),
        ("helper-imported-elsewhere", _TREE_CONTROL.replace("from tests.support.fault_injection import TREE_SHAPES, descendant_tree", "from somewhere import TREE_SHAPES, descendant_tree")),
        ("wrapper-rebound", _TREE_CONTROL.replace("def test_one(tmp_path, monkeypatch):\n", "def test_one(tmp_path, monkeypatch):\n    process_tree = None\n")),
        ("no-launch", _TREE_CONTROL.replace("    with pytest.raises(OSError):\n        process_tree.popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n", "    pass\n")),
    ],
)
def test_a_changed_descendant_tree_test_is_rejected(name: str, source: str) -> None:
    assert source != _TREE_CONTROL, name
    with pytest.raises(AssertionError):
        descendant_tree_launches(ast.parse(source))


def test_the_reviewed_descendant_tree_tests_are_accepted_as_a_control() -> None:
    assert descendant_tree_launches(ast.parse(_TREE_CONTROL)) == {"test_every": set(fault_injection.TREE_SHAPES), "test_one": {"middle-exited"}}


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


def test_the_prefix_runner_validates_what_it_executes(tmp_path: Path) -> None:
    """A program whose announce prefix fails the check never runs; the directory stays empty."""
    for rogue in (
        concurrency.announce_pid_code(tmp_path.parent, "grandchild"),
        concurrency.announce_pid_code(tmp_path, "grandchild").replace("_o.getpid()", "_o.getcwd()"),
        "import os; os.system('x'); " + concurrency.announce_pid_code(tmp_path, "grandchild"),
    ):
        with pytest.raises(AssertionError):
            run_announce_prefix(rogue, tmp_path)
    assert os.listdir(tmp_path) == []
