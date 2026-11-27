"""Where repository code launches a child process: a read-only inventory of the launches in `src/` and `tools/` (#661).

Test support only. #540's `child_launch_inventory` reads `tests/`; a child that a test starts by calling repository code
(a helper-owned launch) is not written there. This is the same lexical walk over the two directories that hold such code,
so a launch added to either must be classified in `tests/unit/tools/helper_launches.json` before the guard passes.

A launch is a reference to one of the process-starting calls below, called or merely named (`factory = subprocess.Popen`
starts a process when the factory is called). A reference is keyed by file and enclosing function, and the map records how
many launch references that function holds, so a new function and a new launch in a known function both fail. Only tracked
files are read. Aliases of these names are not followed, with one exception: the repository's own wrapper
(`process_tree.popen`, `process_tree.run_bounded`, `tools.process_tree`) is matched by name wherever it is imported.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tools.tracked_repository_files import tracked_repository_files

LAUNCH_NAMES = {
    "subprocess.Popen", "subprocess.run", "subprocess.check_output", "subprocess.check_call", "subprocess.call",
    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
    "os.system", "os.popen", "os.startfile", "os.execv", "os.execve", "os.execvp", "os.execl", "os.execlp",
    "os.spawnl", "os.spawnv", "os.spawnlp", "os.spawnvp",
    "process_tree.popen", "process_tree.run_bounded", "run_bounded", "popen",
    "multiprocessing.Process", "multiprocessing.Pool", "ProcessPoolExecutor", "stdio_client", "StdioServerParameters",
}
DIRECTORIES = ("src", "tools")


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


# Launch APIs reached through an object (`loop.subprocess_exec`, `anyio.open_process`) are matched by their last name.
_TAIL_NAMES = {"open_process", "subprocess_exec", "subprocess_shell", "posix_spawn", "posix_spawnp"}


def _is_launch(name: str) -> bool:
    return (name in LAUNCH_NAMES or name.endswith(".process_tree.popen") or name.endswith(".process_tree.run_bounded")
            or name.rpartition(".")[2] in _TAIL_NAMES)


def _not_a_launch(tree: ast.AST) -> set[int]:
    """Nodes that name a launch API without starting anything: annotations, and the class argument of `isinstance`."""
    skipped: set[int] = set()

    def mark(node: ast.AST | None) -> None:
        if node is not None:
            skipped.update(id(inner) for inner in ast.walk(node))

    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            mark(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            mark(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mark(node.returns)
        elif isinstance(node, ast.Call) and _name(node.func) in {"isinstance", "issubclass"} and len(node.args) > 1:
            mark(node.args[1])
    return skipped


def scan_source(relative: str, source: str) -> dict[str, dict[str, object]]:
    """`file::function` -> how many launch references it holds and what each names, for one module's source."""
    found: dict[str, dict[str, object]] = {}
    tree = ast.parse(source)
    skipped = _not_a_launch(tree)

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if isinstance(child, ast.ClassDef):
                visit(child, function)
                continue
            if isinstance(child, (ast.Attribute, ast.Name)) and id(child) not in skipped and _is_launch(_name(child)):
                entry = found.setdefault(f"{relative}::{function}", {"count": 0, "names": []})
                entry["count"] = int(entry["count"]) + 1  # type: ignore[call-overload]
                entry["names"].append(_name(child))  # type: ignore[attr-defined]
                continue  # an Attribute's own children are the same name
            visit(child, function)

    visit(tree, "<module>")
    return found


def launch_functions(root: Path) -> dict[str, dict[str, object]]:
    """Every tracked module under src/ and tools/, scanned."""
    found: dict[str, dict[str, object]] = {}
    for path in sorted(tracked_repository_files(root, pathspecs=list(DIRECTORIES))):
        if path.suffix == ".py":
            found.update(scan_source(path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")))
    return found
