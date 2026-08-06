import ast
from pathlib import Path


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_independent_contract_modules_do_not_cross_import_deployable_packages():
    root = Path(__file__).resolve().parents[3]
    agent_imports = imported_modules(root / "src/optimus/gateway/mcp_models.py")
    gateway_imports = imported_modules(root / "src/optimus_gateway/mcp_models.py")

    assert all(not module.startswith("optimus_gateway") for module in agent_imports)
    assert all(not module.startswith("optimus.") for module in gateway_imports)
