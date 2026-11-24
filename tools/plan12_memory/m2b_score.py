"""Plan 12.14 paid Q scoring: deterministic checks only (cases.json paid_q.check_rules). Its digest and the selector's are frozen before any
paid prompt; a change after that is a new scorer, never a rescore of the same release.

The selector takes the reply text the host delivered as the turn's final answer and removes host-added text: the search-limit notice the
runner appends to an indexed answer (optimus.agent.index_turn.LIMIT_NOTICE). Every check is PASS, FAIL or UNKNOWN; the case is PASS only
when every applicable check passes, FAIL on any FAIL, otherwise INCOMPLETE. No model grades anything.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from optimus.agent.index_turn import LIMIT_NOTICE

PASS: Final = "PASS"
FAIL: Final = "FAIL"
UNKNOWN: Final = "UNKNOWN"
# A cited repository path, optionally with :line or :start-end. Paths start at a top-level folder of this repository.
CITED: Final = re.compile(r"(?<![\w./-])((?:src|tests|tools|docs|reports)/[\w./-]*[\w-]\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?")
FENCE: Final = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.S)  # an unterminated fence (a reply cut at the cap) still counts
# A line that reads as Python code, fenced or not: in an exact-quotation case it must be the file's own.
CODE_LINE: Final = re.compile(r"^\s*(?:def |class |return\b|for |if |elif |while |with |import |from \S+ import |[A-Za-z_][\w.\[\]\"']*\s*[+-]?=\s)")

Read = Callable[[str], bytes | None]


def select(final_answer: str | None) -> str | None:
    """The claim text: the delivered final answer without host-added text. None (no delivered answer) makes every check UNKNOWN."""
    if final_answer is None:
        return None
    text = final_answer.rstrip()
    if text.endswith(LIMIT_NOTICE):
        text = text[: -len(LIMIT_NOTICE)].rstrip()
    return text


def spans(source: bytes) -> dict[str, tuple[int, int]]:
    """Every def and class by qualified name, decorators included (as the golds' extraction)."""
    out: dict[str, tuple[int, int]] = {}

    def visit(node: ast.AST, owner: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                start = min([child.lineno, *[d.lineno for d in child.decorator_list]])
                name = (*owner, child.name)
                out[".".join(name)] = (start, child.end_lineno or start)
                visit(child, name)
            else:
                visit(child, owner)

    visit(ast.parse(source), ())
    return out


def citations(text: str) -> list[tuple[str, int | None, int | None]]:
    out = []
    for match in CITED.finditer(text):
        start = int(match[2]) if match[2] else None
        out.append((match[1], start, int(match[3]) if match[3] else start))
    return out


def check_citation(requirement: Mapping[str, Any], text: str, read: Read) -> str:
    cited = citations(text)
    for evidence in requirement["any_of"]:
        kind, _, rest = evidence.partition(":")
        path, _, symbol = rest.partition("::") if kind == "symbol" else (rest, "", "")
        if path not in text:
            continue
        if kind == "path":
            return PASS
        source = read(path)
        if source is None:
            return UNKNOWN
        if names_symbol(symbol, text):
            return PASS
        span = spans(source).get(symbol)
        if span and any(p == path and a is not None and b is not None and a <= span[1] and b >= span[0] for p, a, b in cited):
            return PASS
    return FAIL


def names_symbol(symbol: str, text: str) -> bool:
    """The reply names the symbol as code: its qualified name, or its last segment written as an identifier. A last segment that is an
    ordinary word (no underscore or capital: `main`, `close`, `request`) counts only in backticks or as a call, `name(`."""
    last = symbol.rsplit(".", 1)[-1]
    if "." in symbol and re.search(rf"(?<![\w.]){re.escape(symbol)}\b", text):
        return True
    if re.search(r"[_A-Z]", last):
        return re.search(rf"(?<!\w){re.escape(last)}\b", text) is not None
    return re.search(rf"`{re.escape(last)}(\(\))?`|(?<![\w.]){re.escape(last)}\(", text) is not None


def has_phrase(item: str, text: str) -> bool:
    """Case-insensitive; a number matches only as a whole number, never inside another one or a line citation (`160`, `a.py:140`)."""
    if re.fullmatch(r"[\d_,.]+", item):
        return re.search(rf"(?<![\w:.,]){re.escape(item)}(?!\w|[.,]\d)", text) is not None
    return item.lower() in text.lower()


def check_fact(fact: Mapping[str, Any], text: str) -> str:
    if "any_of" in fact:
        return PASS if any(has_phrase(item, text) for item in fact["any_of"]) else FAIL
    if "all_of" in fact:
        return PASS if all(has_phrase(item, text) for item in fact["all_of"]) else FAIL
    found = {name for name in fact["of"] if re.search(rf"\b{re.escape(name)}\b", text)}
    return PASS if len(found) >= fact["at_least"] else FAIL


def check_prohibited(text: str, read: Read) -> str:
    """A cited path absent from the snapshot, or a cited line beyond its file, fails the case."""
    for path, start, end in citations(text):
        source = read(path)
        if source is None:
            return FAIL
        length = source.count(b"\n") + (0 if source.endswith(b"\n") else 1)
        if any(line is not None and not 1 <= line <= length for line in (start, end)):
            return FAIL
    return PASS


def check_quote(quote: Mapping[str, Any], text: str, path: str, read: Read) -> str:
    """Every quoted code line (inside a fence, closed or cut off) and every unfenced line that reads as code must appear in the snapshot
    file, compared without surrounding whitespace; then either the target lines are all quoted or the reply says it was not given them."""
    source = read(path)
    if source is None:
        return UNKNOWN
    file_lines = source.decode("utf-8").splitlines()
    known = {line.strip() for line in file_lines if line.strip()}
    quoted = [line.strip() for block in FENCE.findall(text) for line in block.splitlines() if line.strip()]
    unfenced = [line.strip() for line in FENCE.sub("", text).splitlines() if CODE_LINE.match(line)]
    if any(line not in known for line in [*quoted, *unfenced]):
        return FAIL
    first, last = quote["target_lines"]
    target = [line.strip() for line in file_lines[first - 1:last] if line.strip()]
    if target and all(line in quoted for line in target):
        return PASS
    lowered = text.lower()
    return PASS if any(phrase in lowered for phrase in quote["refusal_phrases"]) else FAIL


def score(case: Mapping[str, Any], final_answer: str | None, read: Read) -> dict[str, Any]:
    text = select(final_answer)
    checks: dict[str, str] = {}
    if text is None:
        checks["answer"] = UNKNOWN
    else:
        for requirement in case["checks"]["citations"]:
            checks[f"citation:{requirement['requirement_id']}"] = check_citation(requirement, text, read)
        for fact in case["checks"]["facts"]:
            checks[f"fact:{fact['fact_id']}"] = check_fact(fact, text)
        checks["prohibited"] = check_prohibited(text, read)
        if case["checks"]["quote"] is not None:
            checks["quote"] = check_quote(case["checks"]["quote"], text, case["required_files"][0]["path"], read)
    values = set(checks.values())
    verdict = FAIL if FAIL in values else (PASS if values == {PASS} else "INCOMPLETE")
    return {"case_id": case["case_id"], "checks": checks, "verdict": verdict}


def score_all(cases: Sequence[Mapping[str, Any]], answers: Mapping[tuple[str, str], str | None], reads: Mapping[str, Read]) -> list[dict[str, Any]]:
    """One row per (case, arm) answered; `reads` maps a case's snapshot to its reader."""
    by_id = {case["case_id"]: case for case in cases}
    return [{**score(by_id[case_id], answer, reads[by_id[case_id]["snapshot"]]), "arm": arm} for (case_id, arm), answer in sorted(answers.items())]
