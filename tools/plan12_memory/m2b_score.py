"""Plan 12.14 paid Q scoring (cases.json paid_q.check_rules, v7 after Codex CP1 round 122 attempt 5). Its digest and the selector's are
frozen before any paid prompt; a change after that is a new scorer, never a rescore of the same release.

The selector takes the reply text the host delivered as the turn's final answer and removes host-added text: the search-limit notice the
runner appends to an indexed answer (optimus.agent.index_turn.LIMIT_NOTICE). A row the runner allowed no send is scored only as its
boundary; an answer is scored only on a settled row. Deterministic checks are a screen: a fact is a relationship, every one of its groups
and its supporting locus in one paragraph of the reply, no sentence carrying it negated (unless the fact is itself a negation), no forbidden
extra. Every check is PASS, FAIL or UNKNOWN; the screen FAILs on any FAIL and is INCOMPLETE on any UNKNOWN, and those are final. A screen
PASS is PENDING_AUDIT: lexical checks cannot establish what a claim asserts (Codex CP1 attempt 3 finding 5), so only the plan's CP3 support
audit, both designated reviewers' rulings bound to that exact answer, which must be the one the producer recorded, makes it PASS
(supported) or FAIL (unsupported). No
model grades anything inside this script.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from optimus.agent.index_turn import LIMIT_NOTICE
from tools.plan12_memory import m2b_paid as paid

PASS: Final = "PASS"
FAIL: Final = "FAIL"
UNKNOWN: Final = "UNKNOWN"
INCOMPLETE: Final = "INCOMPLETE"
PENDING_AUDIT: Final = "PENDING_AUDIT"
HELD: Final = "HELD"  # a screen FAIL the operator held as possibly false: excluded from every gate, never rescored (Q-release gate item 6)
MAX_CITED_LINES: Final = 40  # a range wider than this names a file region, not a locus
# A cited repository path, optionally with :line or :start-end. Paths start at a top-level folder of this repository.
CITED: Final = re.compile(r"(?<![\w./-])((?:src|tests|tools|docs|reports)/[\w./-]*[\w-]\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?")
SENTENCE: Final = re.compile(r"(?<=[.;!?])\s+|\n+")
PARAGRAPH: Final = re.compile(r"\n\s*\n")
NEGATION: Final = re.compile(r"\b(?:not|never|neither|nor)\b|n't\b", re.I)

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


def score_answer(case: Mapping[str, Any], text: str, read: Read) -> dict[str, str]:
    """Every screen check of one answer. No quote control runs: QO4 is a zero-call boundary in every arm, and its oracle makes the
    standalone quote control conditional, so none is tested (Codex CP1 attempt 5 finding 5)."""
    checks: dict[str, str] = {}
    loci = {locus["locus_id"]: locus for locus in case["checks"].get("loci", [])}
    for requirement in case["checks"]["citations"]:
        checks[f"citation:{requirement['requirement_id']}"] = check_citation(requirement, text, read)
    for locus in loci.values():
        checks[f"locus:{locus['locus_id']}"] = check_locus(locus, text)
    for fact in case["checks"]["facts"]:
        checks[f"fact:{fact['fact_id']}"] = check_fact(fact, text, loci)
    checks["prohibited"] = check_prohibited(text, read)
    return checks


def verdict(checks: Mapping[str, str]) -> str:
    """The screen: FAIL on any FAIL, PASS when every check passes, otherwise INCOMPLETE."""
    values = set(checks.values())
    return FAIL if FAIL in values else (PASS if values == {PASS} else INCOMPLETE)


AUDIT_REVIEWERS: Final = frozenset({"fable-5.2", "codex-gpt-6.2-sol"})  # the plan's CP3 reviewers: Fable 5.2, then one Codex CLI review


def _sha(text: str) -> str:
    return "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


SCORER_SHA256: Final = "hex:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# The sealed cases (evaluation contract inputs.cases_sha256, CP1): paid scoring runs against exactly these bytes (Codex CP1 attempt 7, B).
SEALED_CASES_SHA256: Final = "hex:17a8e68d6fdac9acb91e4d885a4128a7609a411c5967a96e438d655c69e6ea36"  # pragma: allowlist secret - a content digest
# Where the operator's authority for a hold is recorded: a comment on the plan's issue (Codex round 124 B4).
OPERATOR_COMMENT: Final = re.compile(r"https://github\.com/vibhanshu-agarwal/optimus-cost-agent/issues/548#issuecomment-\d+")


@dataclass(frozen=True)
class VerifiedCases:
    """The paid cases as read from their sealed bytes, with each row's allowance from the frozen schedule (Codex round 124 B3): the scorer
    never takes a caller's digest string or a row's own allowance on trust."""

    sha256: str
    by_id: Mapping[str, Mapping[str, Any]]
    allowance: Mapping[tuple[str, str], int]


def verify_cases(data: bytes, *, u_equals_b: bool, outline_available: bool) -> VerifiedCases:
    digest = "hex:" + hashlib.sha256(data).hexdigest()
    if digest != SEALED_CASES_SHA256:
        raise ValueError("paid scoring needs the sealed cases bytes")
    cases = json.loads(data)["paid_q"]["cases"]
    return VerifiedCases(digest, MappingProxyType({case["case_id"]: case for case in cases}),
                         MappingProxyType(paid.expected_calls(cases, u_equals_b=u_equals_b, outline_available=outline_available)))


def material_claims(case: Mapping[str, Any]) -> tuple[str, ...]:
    """The claims a support ruling must rule on, one by one: each of the screen's citation and fact checks (Codex round 124 B4)."""
    return (*(f"citation:{r['requirement_id']}" for r in case["checks"]["citations"]), *(f"fact:{f['fact_id']}" for f in case["checks"]["facts"]))


def audit_identity(case: Mapping[str, Any], arm: str, *, release: str | None, answer: str, cases_sha256: str | None,
                   input_sha256: str | None = None, pack_sha256: str | None = None) -> dict[str, Any]:
    """What a support-audit ruling is bound to: exactly one answer's bytes in one release, case and arm, at one snapshot, under this
    scorer and these cases (Codex CP1 attempt 4 finding 5), and on a paid row the exact request the model received (Q-release gate item 15)
    and the pack it carried (Codex round 124 B4)."""
    return {"release": release, "case_id": case["case_id"], "arm": arm, "answer_sha256": _sha(answer), "snapshot": case["snapshot"],
            "scorer_sha256": SCORER_SHA256, "cases_sha256": cases_sha256, "input_sha256": input_sha256, "pack_sha256": pack_sha256}


def _claims_quoted(audit: Mapping[str, Any] | None, delivered: str) -> bool:
    """Every claim a ruling supports quotes, verbatim, the evidence it relied on, and each quote is in what the model received (item 15;
    Codex round 124 B4, per material claim): a fact true of the repository but absent from the request supports nothing."""
    rulings = audit.get("rulings") if isinstance(audit, Mapping) else None
    for ruling in rulings if isinstance(rulings, list | tuple) else ():
        for claim in ruling.get("claims") or () if isinstance(ruling, Mapping) else ():
            if isinstance(claim, Mapping) and claim.get("supported") is True:
                quotes = claim.get("quotes")
                if not (isinstance(quotes, list | tuple) and quotes and all(isinstance(q, str) and q.strip() and q in delivered for q in quotes)):
                    return False
    return True


def _ruling_valid(ruling: Any, claims: Sequence[str]) -> bool:
    """A reviewer named by a string (a list or dict is malformed, never a raise: Codex CP1 attempt 7, B), a boolean `supported`, a
    non-blank string reason, and one ruling per material claim, exactly those claims, the ruling supported only when every claim is
    (Codex round 124 B4)."""
    if not (isinstance(ruling, Mapping) and isinstance(ruling.get("reviewer"), str) and ruling["reviewer"] in AUDIT_REVIEWERS
            and isinstance(ruling.get("supported"), bool) and isinstance(ruling.get("reason"), str) and bool(ruling["reason"].strip())):
        return False
    ruled = ruling.get("claims")
    if not (isinstance(ruled, list | tuple) and all(isinstance(c, Mapping) and isinstance(c.get("check"), str) and isinstance(c.get("supported"), bool) for c in ruled)):
        return False
    return sorted(c["check"] for c in ruled) == sorted(claims) and ruling["supported"] == all(c["supported"] for c in ruled)


def _held(audit: Mapping[str, Any] | None, identity: Mapping[str, Any]) -> bool:
    """The operator's predeclared hold on a suspected false screen failure (Q-release gate item 6): bound to this exact answer, with a
    non-blank reason and the operator's authority, a link to their comment on #548 (Codex round 124 B4). It only removes the answer from
    every gate; nothing is rescored."""
    hold = audit.get("operator_hold") if isinstance(audit, Mapping) else None
    return (isinstance(hold, Mapping) and audit.get("identity") == dict(identity) and isinstance(hold.get("reason"), str) and bool(hold["reason"].strip())
            and hold.get("by") == "operator" and isinstance(hold.get("authority"), str) and OPERATOR_COMMENT.fullmatch(hold["authority"]) is not None)


def answer_verdict(screen: str, audit: Mapping[str, Any] | None, identity: Mapping[str, Any], claims: Sequence[str]) -> tuple[str, str]:
    """(verdict, audit status). A screen FAIL or INCOMPLETE is final. A screen PASS becomes PASS only when the audit record is bound to
    this exact answer (`identity`) and holds one valid ruling from each designated CP3 reviewer (a boolean `supported`, a non-blank
    string reason and a ruling on each of `claims`), both supported; both unsupported is FAIL. A missing, mismatched, malformed, incomplete
    or disputed ruling stays PENDING_AUDIT and contributes to no gate (Codex CP1 attempts 4-5, finding 5)."""
    if screen == FAIL and _held(audit, identity):
        return HELD, "operator hold: suspected false screen failure, not rescored"
    if screen != PASS:
        return screen, "not needed"
    if not isinstance(audit, Mapping):
        return PENDING_AUDIT, "missing"
    if audit.get("identity") != dict(identity):
        return PENDING_AUDIT, "mismatched"
    rulings = audit.get("rulings")
    if (not isinstance(rulings, list | tuple) or len(rulings) != len(AUDIT_REVIEWERS) or not all(_ruling_valid(r, claims) for r in rulings)
            or {r["reviewer"] for r in rulings} != AUDIT_REVIEWERS):
        return PENDING_AUDIT, "incomplete ruling"
    supported = {r["supported"] for r in rulings}
    if supported == {True}:
        return PASS, "supported"
    if supported == {False}:
        return FAIL, "unsupported"
    return PENDING_AUDIT, "disputed: held for the operator"


def _boundary_text(case: Mapping[str, Any], row: Mapping[str, Any], answer: str | None) -> bool:
    """What a clean refusal delivered: nothing, or exactly production's too-large notice for one of the case's required files, which is
    what the producer stores for a refused row (Codex round 124 B3); either way bound to the producer's recorded answer digest."""
    if answer is None:
        return row.get("answer_sha256") is None
    required = [item["path"] for item in case.get("required_files", [])]
    return row.get("answer_sha256") == _sha(answer) and not paid.emitted_answer(row.get("stop_reason"), answer, required)


def score_row(case: Mapping[str, Any], arm: str, row: Mapping[str, Any], answer: str | None, read: Read, audit: Mapping[str, Any] | None = None, *,
              cases: VerifiedCases, release: str, delivered_input: str | None) -> dict[str, Any]:
    """One paid (case, arm) row, scored against the producer's own record. A row the runner allowed no send (its own
    expected_logical_requests, so F on the outline cases before Task 3's outline too) scores only its boundary: a clean expected_zero_call
    terminal with the declared stop reason, zero Gateway requests and no emitted answer. Otherwise only a settled row's delivered answer is
    scored, and only when it is the answer the producer recorded (its case, arm and answer_sha256; Codex CP1 attempt 5 finding 5): screen
    first, then its bound support audit under the verified cases digest. Any other row is INCOMPLETE.

    `cases` is read from the sealed bytes (verify_cases) and `case` must be its own (Codex round 124 B3); the row's allowance must be the
    frozen schedule's, never just the producer's. `release` is the release being scored: a row from any other release is INCOMPLETE (Codex
    CP1 attempt 7, B). A boundary row must be the producer's own row for this case and arm, say explicitly that it emitted no answer, and
    carry no answer text beyond production's own refusal notice. An answer is scored only with the request text the model received
    (`delivered_input`, from the sink outside the repository), which must be the row's own sent input; each supported claim must quote
    from it (item 15)."""
    if not isinstance(cases, VerifiedCases) or cases.by_id.get(case.get("case_id")) != case:
        raise ValueError("paid scoring needs the case read from the sealed cases bytes")
    if not (isinstance(release, str) and release):
        raise ValueError("paid scoring needs the expected release")
    if row.get("release") != release:
        return {"case_id": case["case_id"], "arm": arm, "kind": "row", "checks": {"release": UNKNOWN}, "reason": "another release", "verdict": INCOMPLETE}
    allowance = cases.allowance.get((case["case_id"], arm))
    if allowance is None or row.get("expected_logical_requests") != allowance:
        return {"case_id": case["case_id"], "arm": arm, "kind": "row", "checks": {"allowance": UNKNOWN}, "reason": "the row's allowance is not the frozen schedule's",
                "verdict": INCOMPLETE}
    if allowance == 0:
        boundary = case.get("boundary") or {}
        ok = ((row.get("case_id"), row.get("arm")) == (case["case_id"], arm) and row.get("terminal") == "expected_zero_call"
              and row.get("stop_reason") == boundary.get("stop_reason") and row.get("logical_requests") == boundary.get("gateway_requests", 0)
              and row.get("emitted_answer") is False and _boundary_text(case, row, answer))
        return {"case_id": case["case_id"], "arm": arm, "kind": "boundary", "checks": {"boundary": PASS if ok else FAIL}, "verdict": PASS if ok else FAIL}
    text = select(answer)
    settled = row.get("terminal") == "settled" and not any(sent.get("finish_reason") in {"length", "content_filter"} for sent in row.get("sent", []))
    producers = answer is not None and (row.get("case_id"), row.get("arm"), row.get("answer_sha256")) == (case["case_id"], arm, _sha(answer))
    if answer is None or text is None or not settled or not producers:
        reason = "not the producer's answer" if answer is not None and settled and not producers else "no settled answer"
        return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": {"answer": UNKNOWN}, "reason": reason, "verdict": INCOMPLETE}
    sent_input = (row.get("sent") or [{}])[0].get("input_sha256")
    if delivered_input is None or sent_input is None or _sha(delivered_input) != sent_input:
        return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": {"answer": UNKNOWN}, "reason": "the delivered input is not the row's",
                "verdict": INCOMPLETE}
    checks = score_answer(case, text, read)
    screen = verdict(checks)
    identity = audit_identity(case, arm, release=release, answer=answer, cases_sha256=cases.sha256, input_sha256=sent_input, pack_sha256=row.get("pack_sha256"))
    final, status = answer_verdict(screen, audit, identity, material_claims(case))
    if final == PASS and not _claims_quoted(audit, delivered_input):
        final, status = PENDING_AUDIT, "a supported claim quotes nothing the model received"
    return {"case_id": case["case_id"], "arm": arm, "kind": "answer", "checks": checks, "screen": screen, "audit": status, "audit_identity": identity, "verdict": final}


def score(case: Mapping[str, Any], final_answer: str | None, read: Read, audit: Mapping[str, Any] | None = None, *, release: str | None = None,
          arm: str = "X", cases_sha256: str | None = None) -> dict[str, Any]:
    """An answer on its own (no runner status): used by the zero-paid tests and controls."""
    text = select(final_answer)
    checks = {"answer": UNKNOWN} if final_answer is None or text is None else score_answer(case, text, read)
    screen = verdict(checks)
    identity = audit_identity(case, arm, release=release, answer=final_answer or "", cases_sha256=cases_sha256)
    final, status = answer_verdict(screen, audit, identity, material_claims(case))
    return {"case_id": case["case_id"], "checks": checks, "screen": screen, "audit": status, "audit_identity": identity, "verdict": final}
