"""Plan 12.14 paid Q scoring: deterministic checks only (cases.json paid_q.check_rules, v2 after Codex CP1 round 122). Its digest and the
selector's are frozen before any paid prompt; a change after that is a new scorer, never a rescore of the same release.

The selector takes the reply text the host delivered as the turn's final answer and removes host-added text: the search-limit notice the
runner appends to an indexed answer (optimus.agent.index_turn.LIMIT_NOTICE). A row the runner did not complete is not an answer. A
predeclared refusal is scored only as its boundary. Every check is PASS, FAIL or UNKNOWN; a case is PASS only when every applicable check
passes, FAIL on any FAIL, otherwise INCOMPLETE. No model grades anything.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from typing import Any, Final

from optimus.agent.index_turn import LIMIT_NOTICE

PASS: Final = "PASS"
FAIL: Final = "FAIL"
UNKNOWN: Final = "UNKNOWN"
INCOMPLETE: Final = "INCOMPLETE"
MAX_CITED_LINES: Final = 40  # a range wider than this names a file region, not a locus
# A cited repository path, optionally with :line or :start-end. Paths start at a top-level folder of this repository.
CITED: Final = re.compile(r"(?<![\w./-])((?:src|tests|tools|docs|reports)/[\w./-]*[\w-]\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?")
FENCE: Final = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.S)  # an unterminated fence (a reply cut at the cap) still counts
CLAUSE: Final = re.compile(r"(?<=[.;!?])\s+|\n+")  # one line or sentence: the unit a citation's claim must share

Read = Callable[[str], bytes | None]


def select(final_answer: str | None) -> str | None:
    """The claim text: the delivered final answer without host-added text. None (no delivered answer) is not an answer."""
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


def clauses(text: str) -> list[str]:
    return [part for part in CLAUSE.split(text) if part.strip()]


def names_symbol(symbol: str, text: str) -> bool:
    """The text names the symbol as code: its qualified name, or its last segment written as an identifier. A last segment that is an
    ordinary word (no underscore or capital: `main`, `close`, `request`) counts only in backticks or as a call, `name(`."""
    last = symbol.rsplit(".", 1)[-1]
    if "." in symbol and re.search(rf"(?<![\w.]){re.escape(symbol)}\b", text):
        return True
    if re.search(r"[_A-Z]", last):
        return re.search(rf"(?<!\w){re.escape(last)}\b", text) is not None
    return re.search(rf"`{re.escape(last)}(\(\))?`|(?<![\w.]){re.escape(last)}\(", text) is not None


def narrow_overlap(path: str, first: int, last: int, cited: list[tuple[str, int | None, int | None]]) -> bool:
    """A path:start-end of at most MAX_CITED_LINES lines that overlaps first..last."""
    return any(p == path and a is not None and b is not None and b - a + 1 <= MAX_CITED_LINES and a <= last and b >= first for p, a, b in cited)


def check_citation(requirement: Mapping[str, Any], text: str, read: Read) -> str:
    """Claim-bound: the path and the symbol in one line or sentence, or a narrow overlapping range."""
    cited = citations(text)
    for evidence in requirement["any_of"]:
        kind, _, rest = evidence.partition(":")
        path, _, symbol = rest.partition("::") if kind == "symbol" else (rest, "", "")
        if kind == "path":
            if any(p == path for p, _a, _b in cited) or path in text:
                return PASS
            continue
        source = read(path)
        if source is None:
            return UNKNOWN
        if any(path in clause and names_symbol(symbol, clause) for clause in clauses(text)):
            return PASS
        span = spans(source).get(symbol)
        if span and narrow_overlap(path, span[0], span[1], cited):
            return PASS
    return FAIL


def check_locus(locus: Mapping[str, Any], text: str) -> str:
    if any(re.search(rf"(?<![\w.]){re.escape(name)}\b", text) for name in locus["names"] if re.search(r"[_A-Z]", name)):
        return PASS
    if any(names_symbol(name, text) for name in locus["names"] if not re.search(r"[_A-Z]", name)):
        return PASS
    return PASS if narrow_overlap(locus["path"], locus["line"], locus["line"], citations(text)) else FAIL


def has_phrase(item: str, text: str) -> bool:
    """Case-insensitive; a number matches only as a whole number, never inside another one or a line citation (`160`, `a.py:140`)."""
    if re.fullmatch(r"[\d_,.]+", item):
        return re.search(rf"(?<![\w:.,]){re.escape(item)}(?!\w|[.,]\d)", text) is not None
    return item.lower() in text.lower()


def check_fact(fact: Mapping[str, Any], text: str) -> str:
    if "groups" in fact:
        return PASS if all(any(has_phrase(item, text) for item in group) for group in fact["groups"]) else FAIL
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
    """A scorer control (QO4 is a zero-call boundary in every arm): one fenced block equal to the target lines, line endings normalized;
    or an explicit statement that the lines are unavailable with no fenced block at all."""
    source = read(path)
    if source is None:
        return UNKNOWN
    first, last = quote["target_lines"]
    target = "\n".join(source.decode("utf-8").splitlines()[first - 1:last]).strip("\n")
    blocks = [block.replace("\r\n", "\n").strip("\n") for block in FENCE.findall(text)]
    if blocks:
        return PASS if len(blocks) == 1 and blocks[0] == target else FAIL
    lowered = text.lower()
    return PASS if any(phrase in lowered for phrase in quote["refusal_phrases"]) else FAIL


def score_answer(case: Mapping[str, Any], text: str, read: Read) -> dict[str, str]:
    checks: dict[str, str] = {}
    for requirement in case["checks"]["citations"]:
        checks[f"citation:{requirement['requirement_id']}"] = check_citation(requirement, text, read)
    for locus in case["checks"].get("loci", []):
        checks[f"locus:{locus['locus_id']}"] = check_locus(locus, text)
    for fact in case["checks"]["facts"]:
        checks[f"fact:{fact['fact_id']}"] = check_fact(fact, text)
    checks["prohibited"] = check_prohibited(text, read)
    if case["checks"]["quote"] is not None:
        checks["quote"] = check_quote(case["checks"]["quote"], text, case["required_files"][0]["path"], read)
    return checks


def verdict(checks: Mapping[str, str]) -> str:
    values = set(checks.values())
    return FAIL if FAIL in values else (PASS if values == {PASS} else INCOMPLETE)


def score_row(case: Mapping[str, Any], arm: str, row: Mapping[str, Any], answer: str | None, read: Read) -> dict[str, Any]:
    """One (case, arm) row. A predeclared refusal scores only its boundary; otherwise a completed answer is scored, and a row the runner
    did not complete (a stop reason, no answer, or an output at the cap) is INCOMPLETE."""
    if case["forced_refusal"][arm]:
        boundary = case.get("boundary") or {}
        ok = row.get("stop_reason") == boundary.get("stop_reason") and row.get("logical_requests") == boundary.get("gateway_requests", 0)
        return {"case_id": case["case_id"], "arm": arm, "kind": "boundary", "checks": {"boundary": PASS if ok else FAIL}, "verdict": PASS if ok else FAIL}
    text = select(answer)
    unfinished = row.get("stop_reason") is not None or any(sent.get("finish_reason") in {"length", "content_filter"} for sent in row.get("sent", []))
    if text is None or unfinished:
        return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": {"answer": UNKNOWN}, "verdict": INCOMPLETE}
    checks = score_answer(case, text, read)
    return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": checks, "verdict": verdict(checks)}


def score(case: Mapping[str, Any], final_answer: str | None, read: Read) -> dict[str, Any]:
    """An answer on its own (no runner status): used by the zero-paid tests and controls."""
    text = select(final_answer)
    checks = {"answer": UNKNOWN} if text is None else score_answer(case, text, read)
    return {"case_id": case["case_id"], "checks": checks, "verdict": verdict(checks)}
