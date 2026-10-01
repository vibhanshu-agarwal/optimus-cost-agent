"""Plan 12.2 Task 4: the model-policy package stays neutral and ships its defaults.

The host and the Gateway share one validator, so the package must not import the agent runtime,
the Gateway or the security package (spec 3), and the reviewed defaults must be package data.
"""

from __future__ import annotations

import ast
from importlib import resources
from pathlib import Path

import optimus_model_policy

_FORBIDDEN = ("optimus", "optimus_gateway", "optimus_security", "evidence_handoff", "evidence_handoff_runtime")


def test_the_package_imports_no_host_gateway_or_security_module() -> None:
    package_dir = Path(optimus_model_policy.__file__).parent
    offenders: list[str] = []
    for source in sorted(package_dir.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in _FORBIDDEN:
                    offenders.append(f"{source.name}: {name}")
    assert offenders == []


def test_the_reviewed_defaults_are_package_data() -> None:
    defaults = resources.files("optimus_model_policy").joinpath("defaults.yaml")
    assert defaults.is_file()
    assert "schema_version: 1" in defaults.read_text(encoding="utf-8")
