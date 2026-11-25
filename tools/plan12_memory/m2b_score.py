"""Plan 12.14 paid Q scoring (cases.json paid_q.check_rules, v5 after Codex CP1 round 122 attempt 3). Its digest and the selector's are
frozen before any paid prompt; a change after that is a new scorer, never a rescore of the same release.

The selector takes the reply text the host delivered as the turn's final answer and removes host-added text: the search-limit notice the
runner appends to an indexed answer (optimus.agent.index_turn.LIMIT_NOTICE). A row the runner allowed no send is scored only as its
boundary; an answer is scored only on a settled row. Deterministic checks are a screen: a fact is a relationship, every one of its groups
and its supporting locus in one paragraph of the reply, no sentence carrying it negated (unless the fact is itself a negation), no forbidden
extra. Every check is PASS, FAIL or UNKNOWN; the screen FAILs on any FAIL and is INCOMPLETE on any UNKNOWN, and those are final. A screen
PASS is PENDING_AUDIT: lexical checks cannot establish what a claim asserts (Codex CP1 attempt 3 finding 5), so only the plan's CP3 support
audit, a reviewer's recorded ruling on that answer against its oracle and snapshot, makes it PASS (supported) or FAIL (unsupported). No
model grades anything inside this script.
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
PENDING_AUDIT: Final = "PENDING_AUDIT"
MAX_CITED_LINES: Final = 40  # a range wider than this names a file region, not a locus
# A cited repository path, optionally with :line or :start-end. Paths start at a top-level folder of this repository.
CITED: Final = re.compile(r"(?<![\w./-])((?:src|tests|tools|docs|reports)/[\w./-]*[\w-]\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?")
FENCE: Final = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.S)  # an unterminated fence (a reply cut at the cap) still counts
SENTENCE: Final = re.compile(r"(?<=[.;!?])\s+|\n+")
PARAGRAPH: Final = re.compile(r"\n\s*\n")
NEGATION: Final = re.compile(r"\b(?:not|never|neither|nor)\b|n't\b", re.I)
# A line that reads as Python code, fenced or not: in an exact-quotation reply it must be the file's own.
CODE_LINE: Final = re.compile(r"^\s*(?:def |class |return\b|for |if |elif |while |with |import |from \S+ import |[A-Za-z_][\w.\[\]\"']*\s*[+-]?=\s)")

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


def sentences(text: str) -> list[str]:
    return [part for part in SENTENCE.split(text) if part.strip()]


def paragraphs(text: str) -> list[str]:
    return [part for part in PARAGRAPH.split(text) if part.strip()]


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
    """A forward path:start-end of at most MAX_CITED_LINES lines that overlaps first..last."""
    return any(p == path and a is not None and b is not None and a <= b and b - a + 1 <= MAX_CITED_LINES and a <= last and b >= first for p, a, b in cited)


def check_citation(requirement: Mapping[str, Any], text: str, read: Read) -> str:
    """Claim-bound: the path and the symbol in one sentence, or a narrow forward range overlapping the symbol."""
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
        if any(path in sentence and names_symbol(symbol, sentence) for sentence in sentences(text)):
            return PASS
        span = spans(source).get(symbol)
        if span and narrow_overlap(path, span[0], span[1], cited):
            return PASS
    return FAIL


def locus_in(locus: Mapping[str, Any], text: str) -> bool:
    """The locus named as code (an identifier name, or `Owner.method`), or a narrow forward range covering its line."""
    if any(names_symbol(name, text) for name in locus["names"]):
        return True
    return narrow_overlap(locus["path"], locus["line"], locus["line"], citations(text))


def check_locus(locus: Mapping[str, Any], text: str) -> str:
    return PASS if locus_in(locus, text) else FAIL


def has_phrase(item: str, text: str) -> bool:
    """Case-insensitive; a number matches only as a whole number, never inside another one or a line citation (`160`, `a.py:140`)."""
    if re.fullmatch(r"[\d_,.]+", item):
        return re.search(rf"(?<![\w:.,]){re.escape(item)}(?!\w|[.,]\d)", text) is not None
    return item.lower() in text.lower()


def _fact_in(fact: Mapping[str, Any], unit: str, loci: Mapping[str, Mapping[str, Any]]) -> bool:
    if not all(any(has_phrase(item, unit) for item in group) for group in fact["groups"]):
        return False
    if any(has_phrase(item, unit) for item in fact.get("forbid", [])):
        return False
    if fact.get("locus") and not locus_in(loci[fact["locus"]], unit):
        return False
    if not fact.get("negated"):
        carrying = [s for s in sentences(unit) if any(has_phrase(item, s) for group in fact["groups"] for item in group)]
        if any(NEGATION.search(s) for s in carrying):
            return False
    return True


def check_fact(fact: Mapping[str, Any], text: str, loci: Mapping[str, Mapping[str, Any]] = {}) -> str:  # noqa: B006 - read-only default
    if "of" in fact:
        found = {name for name in fact["of"] if re.search(rf"\b{re.escape(name)}\b", text)}
        return PASS if len(found) >= fact["at_least"] else FAIL
    return PASS if any(_fact_in(fact, unit, loci) for unit in paragraphs(text)) else FAIL


def check_prohibited(text: str, read: Read) -> str:
    """A cited path absent from the snapshot, a cited line beyond its file, or a reversed range fails the case."""
    for path, start, end in citations(text):
        source = read(path)
        if source is None:
            return FAIL
        length = source.count(b"\n") + (0 if source.endswith(b"\n") else 1)
        if any(line is not None and not 1 <= line <= length for line in (start, end)) or (start is not None and end is not None and end < start):
            return FAIL
    return PASS


UNTRUE: Final = re.compile(r"\b(?:false|untrue|incorrect|wrong)\b", re.I)


def check_quote(quote: Mapping[str, Any], text: str, path: str, read: Read) -> str:
    """A scorer control (QO4 is a zero-call boundary in every arm): exactly one closed fenced block equal to the target lines with only
    line endings normalized, and no other code; or a sentence naming the requested lines or source as unavailable, with no fence, no
    code-like line, and no negation or denial in that sentence (Codex CP1 attempt 3 finding 5)."""
    source = read(path)
    if source is None:
        return UNKNOWN
    if text.count("```") % 2:
        return FAIL  # an unterminated fence is never a complete quote
    first, last = quote["target_lines"]
    target = "\n".join(source.decode("utf-8").splitlines()[first - 1:last])
    blocks = [block.replace("\r\n", "\n").removesuffix("\n") for block in FENCE.findall(text.replace("\r\n", "\n"))]
    unfenced_code = [line for line in FENCE.sub("", text).splitlines() if CODE_LINE.match(line)]
    if blocks:
        return PASS if len(blocks) == 1 and blocks[0] == target and not unfenced_code else FAIL
    if unfenced_code:
        return FAIL
    explicit = any(any(p in s.lower() for p in quote["refusal_phrases"]) and re.search(r"\b(?:lines?|source|requested|quote)\b", s, re.I)
                   and not NEGATION.search(s) and not UNTRUE.search(s) for s in sentences(text))
    return PASS if explicit else FAIL


def score_answer(case: Mapping[str, Any], text: str, read: Read) -> dict[str, str]:
    checks: dict[str, str] = {}
    loci = {locus["locus_id"]: locus for locus in case["checks"].get("loci", [])}
    for requirement in case["checks"]["citations"]:
        checks[f"citation:{requirement['requirement_id']}"] = check_citation(requirement, text, read)
    for locus in loci.values():
        checks[f"locus:{locus['locus_id']}"] = check_locus(locus, text)
    for fact in case["checks"]["facts"]:
        checks[f"fact:{fact['fact_id']}"] = check_fact(fact, text, loci)
    checks["prohibited"] = check_prohibited(text, read)
    if case["checks"]["quote"] is not None:
        checks["quote"] = check_quote(case["checks"]["quote"], text, case["required_files"][0]["path"], read)
    return checks


def verdict(checks: Mapping[str, str]) -> str:
    """The lexical screen: FAIL on any FAIL, PASS when every check passes, otherwise INCOMPLETE."""
    values = set(checks.values())
    return FAIL if FAIL in values else (PASS if values == {PASS} else INCOMPLETE)


def answer_verdict(screen: str, audit: Mapping[str, Any] | None) -> str:
    """A screen FAIL or INCOMPLETE is final. A screen PASS is PENDING_AUDIT until the CP3 support audit rules on that answer: supported is
    PASS, unsupported is FAIL. Lexical checks cannot establish what a claim asserts (Codex CP1 attempt 3 finding 5)."""
    if screen != PASS:
        return screen
    if audit is None:
        return PENDING_AUDIT
    supported = audit.get("supported")
    if not isinstance(supported, bool) or not audit.get("reviewer"):
        raise ValueError("an audit ruling needs a reviewer and a boolean `supported`")
    return PASS if supported else FAIL


def score_row(case: Mapping[str, Any], arm: str, row: Mapping[str, Any], answer: str | None, read: Read, audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One (case, arm) row. A row the runner allowed no send (its own expected_logical_requests, so F on the outline cases before Task 3's
    outline too) scores only its boundary: a clean expected_zero_call terminal with the declared stop reason, zero Gateway requests and no
    emitted answer. Otherwise only a settled row's delivered answer is scored, screen first, then the support audit; any other row is
    INCOMPLETE."""
    if row["expected_logical_requests"] == 0:
        boundary = case.get("boundary") or {}
        ok = (row.get("terminal") == "expected_zero_call" and row.get("stop_reason") == boundary.get("stop_reason")
              and row.get("logical_requests") == boundary.get("gateway_requests", 0) and not row.get("emitted_answer"))
        return {"case_id": case["case_id"], "arm": arm, "kind": "boundary", "checks": {"boundary": PASS if ok else FAIL}, "verdict": PASS if ok else FAIL}
    text = select(answer)
    settled = row.get("terminal") == "settled" and not any(sent.get("finish_reason") in {"length", "content_filter"} for sent in row.get("sent", []))
    if text is None or not settled:
        return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": {"answer": UNKNOWN}, "verdict": INCOMPLETE}
    checks = score_answer(case, text, read)
    screen = verdict(checks)
    return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": checks, "screen": screen, "verdict": answer_verdict(screen, audit)}


def score(case: Mapping[str, Any], final_answer: str | None, read: Read, audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """An answer on its own (no runner status): used by the zero-paid tests and controls."""
    text = select(final_answer)
    checks = {"answer": UNKNOWN} if text is None else score_answer(case, text, read)
    screen = verdict(checks)
    return {"case_id": case["case_id"], "checks": checks, "screen": screen, "verdict": answer_verdict(screen, audit)}
