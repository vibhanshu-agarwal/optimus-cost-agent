import runpy
from pathlib import Path


def test_pyproject_declares_optimus_agent_console_script():
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in text
    assert 'optimus-agent = "optimus.acp.__main__:main"' in text


def test_module_entrypoint_exists():
    module_globals = runpy.run_module("optimus.acp.__main__", run_name="optimus.acp.__main__")

    assert "main" in module_globals
