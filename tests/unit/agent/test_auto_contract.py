import ast
import json
from pathlib import Path

import pytest

import optimus.agent.auto_contract as contract
from optimus.agent.auto_contract import CONTRACT_VERSION, build_classifier_input
from optimus.runtime.modes import ExecutionMode


def test_short_prompt_is_kept_whole_and_serialized_in_the_frozen_shape():
    built = build_classifier_input(
        "Rename foo to bar in utils.py", mode="AGENT", attachments=[("src/utils.py", 1200)], previous_tier="easy"
    )

    assert json.loads(built.to_json()) == {
        "contract": CONTRACT_VERSION,
        "prompt": "Rename foo to bar in utils.py",
        "truncated": False,
        "mode": "AGENT",
        "attachments": {"count": 1, "size": "<4KB", "extensions": [".py"]},
        "previous_tier": "easy",
    }
    assert built.to_json().startswith('{"contract":"auto-input-v1","prompt":')


def test_long_prompt_is_cut_to_4kb_even_when_the_budget_is_larger():
    built = build_classifier_input("x" * 5000, mode="CHAT", excerpt_budget_bytes=10_000)

    assert built.prompt == "x" * 4096
    assert built.truncated is True


def test_cut_never_splits_a_multibyte_character():
    # "é" is two UTF-8 bytes: a 5-byte budget fits "ab" and one "é", not half of the second.
    built = build_classifier_input("abéé", mode="CHAT", excerpt_budget_bytes=5)

    assert built.prompt == "abé"
    assert built.truncated is True


def test_prompt_exactly_at_budget_is_not_truncated():
    built = build_classifier_input("a" * 100, mode="CHAT", excerpt_budget_bytes=100)

    assert built.truncated is False


@pytest.mark.parametrize("budget", [0, -1])
def test_configuration_without_excerpt_budget_is_refused(budget):
    with pytest.raises(ValueError, match="no excerpt budget"):
        build_classifier_input("hello", mode="CHAT", excerpt_budget_bytes=budget)


@pytest.mark.parametrize(("total", "bucket"), [(0, "<4KB"), (4095, "<4KB"), (4096, "<64KB"), (65535, "<64KB"), (65536, "larger")])
def test_attachment_size_buckets(total, bucket):
    built = build_classifier_input("p", mode="CHAT", attachments=[("a.txt", total)])

    assert built.attachment_size == bucket


def test_extensions_are_distinct_lowercased_sorted_and_capped_at_five():
    files = [("Z.PY", 1), ("a.py", 1), ("b.md", 1), ("c.ts", 1), ("d.rs", 1), ("e.go", 1), ("f.c", 1), ("Makefile", 1)]

    built = build_classifier_input("p", mode="AGENT", attachments=files)

    assert built.attachment_count == 8
    assert built.attachment_extensions == (".c", ".go", ".md", ".py", ".rs")


def test_attachment_order_does_not_change_the_contract():
    files = [("a.py", 10), ("b.md", 20)]

    assert build_classifier_input("p", mode="CHAT", attachments=files) == build_classifier_input(
        "p", mode="CHAT", attachments=list(reversed(files))
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"mode": "PLAN"}, "not an ACP session mode"), ({"mode": "CHAT", "previous_tier": "review"}, "not a routable tier")],
)
def test_invalid_mode_or_tier_is_refused(kwargs, message):
    with pytest.raises(ValueError, match=message):
        build_classifier_input("p", **kwargs)


def test_negative_attachment_size_is_refused():
    with pytest.raises(ValueError, match="negative"):
        build_classifier_input("p", mode="CHAT", attachments=[("a.py", -1)])


def test_modes_match_the_acp_execution_modes():
    assert set(contract._MODES) == {ExecutionMode.CHAT.value, ExecutionMode.AGENT.value}


def test_contract_imports_only_the_standard_library():
    # The pilot's separate DSPy environment loads this file by path, without the product's dependencies.
    tree = ast.parse(Path(contract.__file__).read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert imported <= {"__future__", "collections", "dataclasses", "json", "pathlib", "typing"}
