"""Where the tests launch child processes: a read-only inventory of launch call sites.

Test support only. A lexical walk of `tests/`: it finds calls that start a process, names the
launch mechanism from the command as written, and notes any default-excluded marker on the
enclosing test, class or module. Only tracked files are read. It does not resolve import aliases
or helper-level markers, with one deliberate exception: the repository's own launch wrapper,
`tools.process_tree.popen`, is recognised under whatever name the module's own imports bind it to
(`from tools import process_tree`, `from tools.process_tree import popen`, `import tools.process_tree`,
with or without `as`); a `.popen` attribute of anything else is not a launch. A site is keyed by
file, enclosing function and its position among that function's launch calls, so the key survives
line shifts. A launch written inside a string that a test hands to a child interpreter is not a
call in this file and is not found here; such embedded programs need their own proof.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tools.tracked_repository_files import tracked_repository_files

_CALLS = {"subprocess.Popen", "subprocess.run", "subprocess.check_output", "subprocess.check_call", "subprocess.call",
          "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell", "stdio_client", "StdioServerParameters"}
WRAPPER_MODULE = "tools.process_tree"
WRAPPER_FUNCTION = "popen"
_EXCLUDED_MARKERS = {"requires_redis", "requires_gateway", "requires_mcp_http", "requires_mcp_stdio", "e2e",
                     "requires_live_gateway", "requires_phoenix", "requires_os_keyring", "requires_os_keyring_write",
                     "requires_acpx", "requires_zed", "requires_windows_desktop", "evidence_investigation",
                     "requires_evidence_handoff_postgres", "requires_evidence_handoff_service", "requires_real_agents"}


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _markers(decorators: list[ast.expr]) -> set[str]:
    found: set[str] = set()
    for decorator in decorators:
        text = ast.unparse(decorator)
        for marker in _EXCLUDED_MARKERS:
            if f"mark.{marker}" in text:
                found.add(marker)
    return found


def _mechanism(program: str, command: str) -> str:
    lowered = command.lower()
    if "sys.executable" in program or "python" in program.lower():
        if "'pytest'" in lowered or '"pytest"' in lowered:
            return "python:nested_pytest"
        if "'-c'" in lowered or '"-c"' in lowered:
            return "python:inline_script"
        if "'-m'" in lowered or '"-m"' in lowered:
            return "python:module"
        return "python:script_file"
    for tool in ("git", "taskkill", "tasklist", "uv", "pre-commit", "powershell", "pwsh", "bash", "node", "npm", "docker", "cmd", "icacls", "wsl"):
        if program.strip("'\"").lower() in {tool, f"{tool}.exe"}:
            return f"tool:{tool}"
    return "indirect"


def wrapper_calls(tree: ast.Module) -> set[str]:
    """The call spellings under which this module's own imports bind `tools.process_tree.popen`.

    Only a binding established by an import counts; the spelling is what `_name` renders for a
    call through it. Relative imports and other modules' `popen` attributes bind nothing.
    """
    package, _, module = WRAPPER_MODULE.rpartition(".")
    spellings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if node.module == package and alias.name == module:
                    spellings.add(f"{alias.asname or alias.name}.{WRAPPER_FUNCTION}")
                elif node.module == WRAPPER_MODULE and alias.name == WRAPPER_FUNCTION:
                    spellings.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == WRAPPER_MODULE:
                    spellings.add(f"{alias.asname or alias.name}.{WRAPPER_FUNCTION}")
    return spellings


def launch_sites(root: Path) -> list[dict[str, object]]:
    """Every launch call under `tests/`, with its key, mechanism and excluding markers."""
    sites: list[dict[str, object]] = []
    for path in sorted(tracked_repository_files(root, pathspecs=["tests"])):
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(root).as_posix()
        wrappers = wrapper_calls(tree)
        module_markers: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
                text = ast.unparse(node.value)
                module_markers = {marker for marker in _EXCLUDED_MARKERS if f"mark.{marker}" in text}
        positions: dict[str, int] = {}

        def visit(
            node: ast.AST, function: str, markers: set[str], relative: str = relative, positions: dict[str, int] = positions,
            wrappers: set[str] = wrappers,
        ) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(child, child.name, markers | _markers(child.decorator_list))
                    continue
                if isinstance(child, ast.ClassDef):
                    visit(child, function, markers | _markers(child.decorator_list))
                    continue
                call_name = _name(child.func) if isinstance(child, ast.Call) else ""
                if isinstance(child, ast.Call) and (
                    call_name in _CALLS or call_name in wrappers or call_name.split(".")[-1] in {"stdio_client", "StdioServerParameters"}
                ):
                    program, command = "", ""
                    if child.args:
                        first = child.args[0]
                        command = ast.unparse(first)[:200]
                        program = ast.unparse(first.elts[0]) if isinstance(first, (ast.List, ast.Tuple)) and first.elts else ast.unparse(first)[:60]
                    positions[function] = positions.get(function, 0) + 1
                    sites.append({
                        "key": f"{relative}::{function}#{positions[function]}", "file": relative, "line": child.lineno,
                        "function": function, "program": program, "command": command,
                        "mechanism": _mechanism(program, command), "excluded_by_marker": sorted(markers),
                        "call": call_name, "wrapper": WRAPPER_MODULE + "." + WRAPPER_FUNCTION if call_name in wrappers else None,
                    })
                visit(child, function, markers)

        visit(tree, "<module>", module_markers)
    return sites


def default_python_sites(root: Path) -> list[dict[str, object]]:
    """Launch sites with no default-excluded marker that start Python or pass a prepared command."""
    return [
        site for site in launch_sites(root)
        if not site["excluded_by_marker"] and (str(site["mechanism"]).startswith("python") or site["mechanism"] == "indirect")
    ]
