"""Controls for the #334 exception-site disposition gate."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools import verify_exception_site_disposition as checker
from tools.verify_exception_site_disposition import discover, verify_report


def _discover(text, **files):
    return discover({"src/demo.py": text, **files})


def _complete(inventory):
    report = deepcopy(inventory)
    for row in report["sites"]:
        row.update(review_state="source_reviewed", disposition="contain", owning_issue=334,
                   rationale="Isolate the optional operation.", evidence="fixture")
    return report


def test_lexical_aliases_groups_and_shadowing():
    inventory = _discover("""
from builtins import BaseException as Broad
from contextlib import suppress

def outer():
    swallow = suppress
    candidates = (ValueError, Broad)
    try:
        pass
    except candidates:
        pass
    with swallow(Broad):
        pass
    try:
        pass
    except* Exception:
        pass
    try:
        pass
    except:
        pass

def narrow():
    Broad = OSError
    try:
        pass
    except Broad:
        pass
""")
    assert [site["kind"] for site in inventory["sites"]] == ["except", "suppress", "except_star", "except"]
    assert not any(site["unresolved"] for site in inventory["sites"])
    assert not verify_report(inventory, _complete(inventory))


def test_unresolved_type_and_suppression_cannot_be_approved_by_the_report():
    inventory = _discover("""
from contextlib import suppress
from external import unknown

def handle(choose):
    bound = suppress if choose else unknown
    try:
        pass
    except choose_type():
        pass
    with bound(Exception):
        pass
""")
    assert len(inventory["sites"]) == 2
    assert all(site["unresolved"] for site in inventory["sites"])
    assert any("unresolved" in problem for problem in verify_report(inventory, _complete(inventory)))


def test_local_reexport_is_resolved_and_bare_overrides_change_identity():
    base = """
from .shared import Boundary
def f():
    try:
        pass
    except Boundary:
        pass
"""
    files = {"src/shared.py": "from builtins import Exception as Boundary\n"}
    inventory = _discover(base, **files)
    assert len(inventory["sites"]) == 1
    assert not inventory["sites"][0]["unresolved"]
    changed = _discover(base.replace("except Boundary:", "except:"), **files)
    errors = verify_report(changed, _complete(inventory))
    assert any("missing" in error for error in errors)
    assert any("stale" in error for error in errors)


def test_one_catch_can_carry_both_lint_annotations():
    source = {"src/demo.py": "try:\n    f()\nexcept Exception:  # noqa: BLE001\n    pass\n"}
    diagnostics = [
        ("src/demo.py", 3, 8, "BLE001", False),
        ("src/demo.py", 1, 1, "SIM105", True),
    ]
    inventory = discover(source, diagnostics)
    assert len(inventory["sites"]) == 1
    lint = inventory["sites"][0]["lint"]
    assert {(entry["code"], entry["effective"]) for entry in lint} == {("BLE001", False), ("SIM105", True)}
    assert not verify_report(inventory, _complete(inventory))


@pytest.mark.parametrize("kind", ["missing", "stale", "duplicate", "unreviewed", "mismatched_source", "wrong_outcome"])
def test_report_gate_rejects_incomplete_or_invented_dispositions(kind):
    inventory = _discover("try:\n    pass\nexcept Exception:\n    pass\n")
    report = _complete(inventory)
    if kind == "missing":
        report["sites"].clear()
    elif kind == "stale":
        report["sites"][0]["key"] = "stale"
    elif kind == "duplicate":
        report["sites"].append(deepcopy(report["sites"][0]))
    elif kind == "unreviewed":
        del report["sites"][0]["evidence"]
    elif kind == "mismatched_source":
        report["source_sha256"] = "another tree"
    else:
        report["sites"][0]["disposition"] = "unreviewed"
    assert verify_report(inventory, report)


def test_duplicate_ast_sites_have_distinct_occurrences():
    inventory = _discover("try:\n    start()\nexcept Exception:\n    pass\n" * 2)
    assert [site["occurrence"] for site in inventory["sites"]] == [1, 2]
    assert len({site["key"] for site in inventory["sites"]}) == 2
    assert not verify_report(inventory, _complete(inventory))



def test_ambiguous_manager_with_unresolved_type_still_has_a_row():
    inventory = _discover("""
from contextlib import suppress as quiet
from elsewhere import replacement, configured_errors
def f(choice):
    handler = quiet if choice else replacement
    with handler(configured_errors):
        pass
""")
    assert len(inventory["sites"]) == 1
    assert inventory["sites"][0]["unresolved"]


def test_rebinding_a_builtin_at_module_scope_is_conservative():
    inventory = _discover("""
try:
    risky()
except Exception:
    pass
Exception = OSError
""")
    assert len(inventory["sites"]) == 1
    assert inventory["sites"][0]["unresolved"]


def test_suppression_body_changes_its_identity():
    source = """
from contextlib import suppress
with suppress(Exception):
    risky()
"""
    before = _discover(source)
    after = _discover(source.replace("risky()", "other()"))
    problems = verify_report(after, _complete(before))
    assert any("missing" in item for item in problems)
    assert any("stale" in item for item in problems)


def test_pending_review_cannot_pass_with_a_proposed_terminal_disposition(tmp_path, monkeypatch, capsys):
    inventory = _discover("try:\n    pass\nexcept Exception:\n    pass\n")
    report = _complete(inventory)
    path = tmp_path / "report.json"
    monkeypatch.setattr(checker, "_inventory", lambda root: inventory)
    path.write_text(json.dumps(report), encoding="utf-8")
    assert checker.main(["--report", str(path)]) == 0
    assert "Verified 1 exception-site dispositions." in capsys.readouterr().out
    report["sites"][0]["review_state"] = "pending"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert checker.main(["--report", str(path)]) == 1
    assert "pending" in capsys.readouterr().err


@pytest.mark.parametrize(
    "path, record, issue, valid",
    [
        ("src/evidence_handoff_runtime/service.py", "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY", None, True),
        ("src/evidence_handoff_runtime/service.py", "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY", None, True),
        ("src/evidence_handoff_runtime/service.py", "unknown-owner", None, False),
        ("src/evidence_handoff_runtime/service.py", "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY", 334, False),
        ("src/demo.py", "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY", None, False),
    ],
)
def test_report_gate_accepts_only_explicit_ledger_backlog_custody(path, record, issue, valid):
    inventory = discover({path: "try:\n    perform()\nexcept Exception:\n    pass\n"})
    report = _complete(inventory)
    report["sites"][0].update(owning_issue=issue, owning_backlog_record=record)
    assert (verify_report(inventory, report) == []) is valid


def test_inventory_cli_labels_unchanged_sha256_identities(monkeypatch, capsys):
    inventory = _discover("try:\n    pass\nexcept Exception:\n    pass\n")
    monkeypatch.setattr(checker, "_inventory", lambda root: inventory)
    assert checker.main(["--inventory"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["source_sha256"] == "sha256:a3fb88214cc6847fa8c0d1e8785d4810b601436a67656d544e9ec514792504a8"
    assert output["sites"][0]["key"] == "sha256:45912d243bd39df14ba9d48db60a0c17bd9a21352495191619b955d2bf377299"
    assert output["sites"][0]["fingerprint"] == "sha256:34a6444a8a77f5826f00f5811fcc583ffe9e63ca26755ffb0cb6f5ed24df8821"
    assert not verify_report(output, _complete(output))


_FROZEN_ERROR = """
from dataclasses import dataclass
{decorator_import}

@frozen_exception
@dataclass(frozen=True)
class Refused(Exception):
    reason: str
"""
_CATCHES_IT = """
from demo_errors import Refused

def handle():
    try:
        pass
    except Refused:
        pass
"""


def test_a_frozen_exception_class_is_a_known_class_and_its_catch_resolves():
    # #694 put @frozen_exception over @dataclass(frozen=True) on eight exceptions; every catch of them read as unresolved.
    errors = _FROZEN_ERROR.format(decorator_import="from optimus.runtime.frozen_exception import frozen_exception")
    inventory = discover({"src/demo_errors.py": errors, "src/demo.py": _CATCHES_IT})
    assert inventory["sites"] == []


@pytest.mark.parametrize(
    "decorator_import",
    [
        "def frozen_exception(cls):\n    return Proxy(cls)",
        "from elsewhere import frozen_exception",
        "from optimus.runtime import frozen_exception",
    ],
    ids=["local-function", "other-module", "the-module-not-the-function"],
)
def test_a_decorator_merely_named_frozen_exception_is_not_trusted(decorator_import):
    inventory = discover({"src/demo_errors.py": _FROZEN_ERROR.format(decorator_import=decorator_import),
                          "src/demo.py": _CATCHES_IT})
    assert [site["unresolved"] for site in inventory["sites"]] == [True]


def test_a_called_frozen_exception_is_not_trusted():
    # Python applies what the call returns, not frozen_exception itself.
    errors = _FROZEN_ERROR.format(decorator_import="from optimus.runtime.frozen_exception import frozen_exception").replace(
        "@frozen_exception\n", "@frozen_exception(Replacement)\n")
    inventory = discover({"src/demo_errors.py": errors, "src/demo.py": _CATCHES_IT})
    assert [site["unresolved"] for site in inventory["sites"]] == [True]


_FROZEN = "optimus.runtime.frozen_exception"
_CATCH = """
def handle():
    try:
        pass
    except Refused:
        pass
"""


def _unresolved(text, **files):
    return [site["unresolved"] for site in discover({"src/demo.py": text, **files})["sites"]]


@pytest.mark.parametrize(
    "header, decorators",
    [
        (f"import {_FROZEN} as m\nm.frozen_exception = lambda cls: Exception", "@m.frozen_exception\n@dataclass(frozen=True)"),
        ("import dataclasses as d\nd.dataclass = lambda cls: Exception", "@d.dataclass"),
        (f"import {_FROZEN} as m\nsetattr(m, 'frozen_exception', lambda cls: Exception)", "@m.frozen_exception\n@dataclass"),
        ("import dataclasses as d\nd.dataclass += replacement", "@d.dataclass"),
        (f"import {_FROZEN} as m\nm.frozen_exception: object = replacement", "@m.frozen_exception\n@dataclass"),
        ("import dataclasses as d\ndel d.dataclass", "@d.dataclass"),
        ("import dataclasses as d\nsetattr(d, choose(), replacement)", "@d.dataclass"),
        ("import dataclasses, sys\nsys.modules['dataclasses'].dataclass = replacement", "@dataclasses.dataclass"),
        ("import builtins, dataclasses as d\nbuiltins.setattr(d, 'dataclass', replacement)", "@d.dataclass"),
        ("import dataclasses as d\ndef configure(_=setattr(d, 'dataclass', replacement)):\n    pass", "@d.dataclass"),
        ("import dataclasses as d\n@setattr(d, 'dataclass', replacement) or keep\ndef configure():\n    pass",
         "@d.dataclass"),
    ],
    # augmented and del cannot run on the real function; they pin conservative detection of the write itself.
    ids=["frozen-alias-assign", "dataclasses-alias-assign", "setattr-literal", "augmented", "annotated", "del",
         "setattr-computed-on-module", "through-sys-modules", "qualified-setattr", "in-a-default", "in-a-decorator"],
)
def test_an_overwritten_trusted_attribute_is_not_trusted(header, decorators):
    # #697: static detection of a visible write to the decorator; most forms would make Refused Exception at runtime.
    text = f"from dataclasses import dataclass\n{header}\n\n{decorators}\nclass Refused(Exception):\n    pass\n{_CATCH}"
    assert _unresolved(text) == [True]


def test_an_attribute_write_in_another_file_untrusts_the_name():
    patch = "import dataclasses\n\ndef install():\n    dataclasses.dataclass = replacement\n\ninstall()\n"
    text = f"from dataclasses import dataclass\n\n@dataclass\nclass Refused(Exception):\n    pass\n{_CATCH}"
    assert _unresolved(text, **{"src/patch.py": patch}) == [True]


_CANONICAL = "def frozen_exception(cls):\n    return cls\n"


@pytest.mark.parametrize(
    "canonical",
    [
        _CANONICAL + "if flag:\n    frozen_exception = replacement\n",
        _CANONICAL + "def install():\n    global frozen_exception\n    frozen_exception = replacement\n",
        _CANONICAL + "from elsewhere import *\n",
        _CANONICAL + "exec(code)\n",
        _CANONICAL + "def install():\n    exec(code, globals())\n",
        "class frozen_exception:\n    def __new__(cls, decorated):\n        return Exception\n",
        "@replace\n" + _CANONICAL,
        _CANONICAL + "match replacement:\n    case frozen_exception:\n        pass\n",
    ],
    ids=["conditional-rebinding", "global-rebinding", "star-import", "exec", "exec-in-a-function", "a-class",
         "a-decorated-def", "match-capture"],
)
def test_a_rebound_canonical_export_is_not_trusted(canonical):
    text = (f"from dataclasses import dataclass\nfrom {_FROZEN} import frozen_exception\n\n"
            f"@frozen_exception\n@dataclass(frozen=True)\nclass Refused(Exception):\n    pass\n{_CATCH}")
    assert _unresolved(text, **{"src/optimus/runtime/frozen_exception.py": canonical}) == [True]


_LOCAL_CLASS = """
def handle():
    @{decorator}
    class Refused(Exception):
        pass
    try:
        pass
    except Refused:
        pass
"""


@pytest.mark.parametrize(
    "imports, decorator, later",
    [
        (f"from {_FROZEN} import frozen_exception", "frozen_exception", "if flag:\n    frozen_exception = replacement"),
        ("from dataclasses import dataclass", "dataclass", "dataclass = replacement"),
        ("from dataclasses import dataclass", "dataclass",
         "def install():\n    global dataclass\n    dataclass = replacement"),
        ("from dataclasses import dataclass", "dataclass", "from elsewhere import *"),
        ("from dataclasses import dataclass", "dataclass", "exec(code)"),
        ("from dataclasses import dataclass", "dataclass", "def install():\n    exec(code, globals())"),
        ("from dataclasses import dataclass", "dataclass", "match replacement:\n    case dataclass:\n        pass"),
    ],
    ids=["conditional-rebinding", "later-rebinding", "later-global", "later-star-import", "later-exec",
         "exec-in-another-function", "match-capture"],
)
def test_a_local_class_waits_for_the_enclosing_bindings(imports, decorator, later):
    # #698: the module-level statement after the function can run before handle() is called.
    text = f"{imports}\n{_LOCAL_CLASS.format(decorator=decorator)}\n{later}\n"
    assert _unresolved(text) == [True]


@pytest.mark.parametrize(
    "text",
    [
        f"from dataclasses import dataclass\n\n@dataclass\nclass Refused(Exception):\n    pass\n{_CATCH}",
        f"from dataclasses import dataclass\n\n@dataclass(frozen=True)\nclass Refused(Exception):\n    pass\n{_CATCH}",
        (f"from dataclasses import dataclass\nfrom {_FROZEN} import frozen_exception\n\n"
         f"@frozen_exception\n@dataclass(frozen=True)\nclass Refused(Exception):\n    pass\n{_CATCH}"),
        (f"import dataclasses as d\nimport {_FROZEN} as m\nm.other = 1\nsetattr(state, name, value)\n\n"
         f"@m.frozen_exception\n@d.dataclass(frozen=True)\nclass Refused(Exception):\n    pass\n{_CATCH}"),
        "from dataclasses import dataclass\n" + _LOCAL_CLASS.format(decorator="dataclass"),
        f"from {_FROZEN} import frozen_exception\n" + _LOCAL_CLASS.format(decorator="frozen_exception"),
        (f"from dataclasses import dataclass\n\ndef stamp(box):\n    box.dataclass: bool\n\n"
         f"@dataclass\nclass Refused(Exception):\n    pass\n{_CATCH}"),
    ],
    ids=["bare-dataclass", "called-dataclass", "frozen-over-dataclass", "aliases-without-a-write",
         "local-dataclass", "local-frozen-exception", "attribute-annotation-only"],
)
def test_trusted_decorators_without_a_rebinding_still_resolve(text, request):
    # The canonical module as it is in the tree must not untrust its own export.
    canonical = Path(request.config.rootpath, "src/optimus/runtime/frozen_exception.py").read_text(encoding="utf-8")
    assert _unresolved(text, **{"src/optimus/runtime/frozen_exception.py": canonical}) == []


def test_an_untrusting_write_is_reported_first_with_its_site(tmp_path, monkeypatch, capsys):
    # One unrelated write can untrust a decorator tree-wide; the gate must say where, before any unresolved row.
    text = f"from dataclasses import dataclass\n\n@dataclass\nclass Refused(Exception):\n    pass\n{_CATCH}"
    inventory = discover({"src/demo.py": text, "src/other.py": "def f(box):\n    box.dataclass = 1\n"})
    assert inventory["untrusted_decorators"] == ["src/other.py:2 dataclasses.dataclass: attribute write named dataclass"]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_complete(inventory)), encoding="utf-8")
    monkeypatch.setattr(checker, "_inventory", lambda root: inventory)
    assert checker.main(["--report", str(path)]) == 1
    first = capsys.readouterr().err.splitlines()[0]
    assert first == "untrusted decorator src/other.py:2 dataclasses.dataclass: attribute write named dataclass"


def test_a_rebound_canonical_module_is_reported_at_its_path():
    canonical = _CANONICAL + "if flag:\n    frozen_exception = replacement\n"
    inventory = discover({"src/optimus/runtime/frozen_exception.py": canonical})
    assert inventory["untrusted_decorators"] == [
        "src/optimus/runtime/frozen_exception.py:1 optimus.runtime.frozen_exception.frozen_exception:"
        " canonical module binds frozen_exception 2 times, not once by its def"]


_CLASS_LOCAL_IMPORT = """
def decorate(cls):
    return Exception

class Box:
    @decorate
    class Refused(Exception):
        pass
    from dataclasses import dataclass as decorate

Refused = Box.Refused
try:
    raise ValueError()
except Refused:
    captured = True
"""


def test_a_class_body_decorator_sees_the_enclosing_binding_before_its_own():
    # A class body runs in order, so @decorate here is the module function and Refused is Exception.
    namespace: dict[str, object] = {}
    exec(_CLASS_LOCAL_IMPORT, namespace)  # noqa: S102 - a fixed fixture, run to show the catch is broad
    assert namespace["Refused"] is Exception and namespace["captured"]
    assert _unresolved(_CLASS_LOCAL_IMPORT) == [True]


_LAMBDA_WALRUS = """
from dataclasses import dataclass

def decorate(cls):
    return Exception

def outer():
    def configure(_=lambda: (decorate := dataclass)):
        pass
    @decorate
    class Refused(Exception):
        pass
    try:
        raise ValueError()
    except Refused:
        return Refused is Exception

broad = outer()
"""

_CLASS_IN_A_FUNCTION = """
def decorate(cls):
    return Exception

def outer():
    from dataclasses import dataclass as decorate
    class Box:
        @decorate
        class Refused(Exception):
            pass
        from dataclasses import dataclass as decorate
    try:
        raise ValueError()
    except Box.Refused:
        return Box.Refused is Exception

broad = outer()
"""

_CATCH_IN_A_CLASS_BODY = """
Refused = Exception

def outer():
    Refused = ValueError
    class Box:
        try:
            raise TypeError()
        except Refused:
            caught = True
        Refused = ValueError
    return Box.caught

broad = outer()
"""


@pytest.mark.parametrize(
    "fixture", [_LAMBDA_WALRUS, _CLASS_IN_A_FUNCTION, _CATCH_IN_A_CLASS_BODY],
    ids=["walrus-in-a-lambda-default", "class-local-name-skips-the-function", "catch-in-a-class-body"],
)
def test_lookup_follows_the_scopes_python_uses(fixture):
    # Codex round 2: each fixture runs, patches nothing, and catches broadly.
    namespace: dict[str, object] = {}
    exec(fixture, namespace)  # noqa: S102 - a fixed fixture, run to show the catch is broad
    assert namespace["broad"] is True
    assert True in _unresolved(fixture)


def test_a_dynamic_scope_does_not_hide_a_computed_write_to_the_module():
    patch = """
import dataclasses as d

def configure(_=eval("1")):
    pass

name = "dataclass"
setattr(d, name, replacement)
"""
    text = f"from dataclasses import dataclass\n\n@dataclass\nclass Refused(Exception):\n    pass\n{_CATCH}"
    assert _unresolved(text, **{"src/patch.py": patch}) == [True]


def test_a_method_named_eval_or_exec_is_not_dynamic_execution():
    text = ("from dataclasses import dataclass\n\ndef prepare(model):\n    model.eval()\n    runner.exec(job)\n\n"
            f"@dataclass\nclass Refused(Exception):\n    pass\n{_CATCH}")
    assert _unresolved(text) == []
