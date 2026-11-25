"""The context pack (Plan 12.10 Task 4; ADR-038): pure, so the same inputs always give the same text.

Order is required evidence, then optional context by progressive disclosure: signatures and descriptions, then verified bodies. A
body comes from the host's reader, and only if the file on disk still has the bytes the index saw; an item whose file changed is left
out and reported, so a stale or other-branch record never becomes current evidence. Required evidence that cannot fit makes the pack
incomplete rather than quietly smaller. The repository map is the caller's: it belongs in the stable prefix, not here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from .file_outline import build_outline
from .pack_utility import Candidate, select
from .retrieval import Hit, Ranked, lexical_terms

SIGNATURE_SHARE: Final = 0.25  # of what optional context has; bodies get the rest
REQUIRED_FLOOR_TOKENS: Final = 1024  # optional room kept above required text when there is room for it (Plan 12.14)
SECTION_REQUIRED: Final = "--- required files ---"
SECTION_SIGNATURES: Final = "--- relevant symbols and sections (from the index) ---"
SECTION_BODIES: Final = "--- verified excerpts (read from disk now) ---"


@dataclass(frozen=True)
class Selected:
    """One item the pack shows or left out, for the manifest. Never holds a body."""

    path: str
    kind: str
    symbol: str | None
    file_hash: str
    start_line: int | None
    end_line: int | None
    disclosure: str  # "required", "outline", "signature", "body" or "omitted"
    score: float = 0.0
    ranks: Mapping[str, int] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class Pack:
    text: str
    tokens: int
    budget_tokens: int
    selected: tuple[Selected, ...]
    file_sha256s: Mapping[str, str]
    missing_required: tuple[str, ...] = ()
    stale_paths: tuple[str, ...] = ()
    outline: Mapping[str, object] | None = None  # Plan 12.14: the overflow outline's body-free metadata, when the pack carries one

    @property
    def complete(self) -> bool:
        return not self.missing_required


def chosen_budget(ceiling: int, target: int, required: int) -> int:
    """Plan 12.14: the soft target, never below the required text plus a floor of optional room, never above the hard ceiling."""
    return min(ceiling, max(required + min(REQUIRED_FLOOR_TOKENS, ceiling - required), target))


def _excerpt(data: bytes, hit: Hit) -> str | None:
    if hit.start_line is None or hit.end_line is None:
        return None
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    return "\n".join(lines[max(hit.start_line - 1, 0):hit.end_line])


def _where(hit: Hit) -> str:
    return f"{hit.path}:{hit.start_line}-{hit.end_line}" if hit.start_line is not None else hit.path


def _signature_line(hit: Hit) -> str | None:
    summary = hit.signature or hit.description or hit.prose
    if summary is None and hit.symbol is None:
        return None
    label = hit.symbol or hit.kind
    return f"{_where(hit)} {label}: {' '.join((summary or '').split())}".rstrip(": ")


def assemble_pack(*, required: Sequence[str], ranked: Sequence[Ranked], read: Callable[[str], bytes | None], estimate: Callable[[str], int], budget_tokens: int,
                  policy: str = "baseline", task: str = "", protected: Sequence[str] = (), target_tokens: int | None = None,
                  overview_path: str | None = None) -> Pack:
    """`read` returns the file's current bytes, or None when policy no longer admits it. `estimate` is the route's token estimator.
    `policy` chooses which optional items fill each phase (pack_utility); `task` gives its terms and `protected` the quota places.
    With `target_tokens` (Plan 12.14), `budget_tokens` is the hard ceiling C: required text that fits it is whole, and optional room is
    chosen_budget(C, target, required) less the required text. Without it, `budget_tokens` is the whole budget, as before.
    `overview_path` (Plan 12.14, D4; with a target only) names the one required file a direct summary task asked for: when it is the whole
    required set and its text is over C, a disclosed outline of it (file_outline) stands in for it if one fits; otherwise, as before."""
    selected: list[Selected] = []
    hashes: dict[str, str] = {}
    contents: dict[str, bytes | None] = {}

    def current(path: str) -> bytes | None:
        if path not in contents:
            contents[path] = read(path)
        return contents[path]

    blocks: list[str] = []
    missing: list[str] = []
    for path in required:
        data = current(path)
        text = None
        if data is not None:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        if data is None or text is None:
            missing.append(path)
            continue
        blocks.append(f"--- {path} ---\n{text}")
        file_hash = hashlib.sha256(data).hexdigest()
        hashes[path] = file_hash
        selected.append(Selected(path, "file", None, file_hash, None, None, "required", reason="named by the task"))
    required_text = f"{SECTION_REQUIRED}\n" + "\n".join(blocks) if blocks else ""
    used = estimate(required_text) if required_text else 0
    outline = None
    if used > budget_tokens and target_tokens is not None and overview_path is not None and tuple(required) == (overview_path,) and not missing:
        # The section header is charged first, so an outline sized to its room still fits C once wrapped (gate item 10 found the gap).
        room_for_outline = budget_tokens - estimate(f"{SECTION_REQUIRED}\n")
        outline = build_outline(overview_path, contents[overview_path] or b"", estimate=estimate, max_tokens=room_for_outline)
        if outline is not None and estimate(f"{SECTION_REQUIRED}\n{outline.text}") <= budget_tokens:
            required_text = f"{SECTION_REQUIRED}\n{outline.text}"
            used = estimate(required_text)
            # file_sha256s names files whose bytes the text shows; an outline shows none, so its hash stays on the row only (Fable CP2 finding 2).
            selected[0] = Selected(overview_path, "file", None, hashes.pop(overview_path), None, None, "outline", reason="outline only: the whole file is over the budget")
        else:
            outline = None
    if used > budget_tokens:
        return Pack("", 0, budget_tokens, tuple(selected), {}, tuple(required))
    if missing:
        return Pack(required_text, used, budget_tokens, tuple(selected), hashes, tuple(missing))
    room = budget_tokens - used
    if target_tokens is not None:
        budget_tokens = chosen_budget(budget_tokens, target_tokens, used)
        # A hard ceiling holds for the whole pack: the two newlines joining its three sections are charged here (legacy is unchanged).
        room = max(0, budget_tokens - used - max(0, estimate("\n\n") - estimate("")))
    signatures_room = int(room * SIGNATURE_SHARE)
    named = set(required)
    stale: list[str] = []
    verified: list[Ranked] = []
    for item in ranked:
        hit = item.hit
        if hit.path in named:
            continue  # shown whole above
        data = current(hit.path)
        if data is None:
            selected.append(_omitted(item, "refused by the file policy now"))
        elif hashlib.sha256(data).hexdigest() != hit.file_hash:
            if hit.path not in stale:
                stale.append(hit.path)
            selected.append(_omitted(item, "the file changed since it was indexed"))
        else:
            verified.append(item)

    task_terms = lexical_terms(task) if policy != "baseline" else []
    keep = frozenset(protected)
    lines_by_id = {item.hit.id: line for item in verified if (line := _signature_line(item.hit)) is not None}
    pool = [Candidate(item.hit.id, lines_by_id[item.hit.id], item.score, ordinal) for ordinal, item in enumerate(verified) if item.hit.id in lines_by_id]
    shown_signature = {c.id for c in select(SECTION_SIGNATURES, pool, room=signatures_room, estimate=estimate, policy=policy, task_terms=task_terms, protected=keep)}
    signature_lines = [c.text for c in pool if c.id in shown_signature]
    signature_text = "\n".join([SECTION_SIGNATURES, *signature_lines]) if signature_lines else ""
    used_signatures = estimate(signature_text) if signature_text else 0

    bodies_room = room - used_signatures
    blocks_pool: list[Candidate] = []
    for ordinal, item in enumerate(verified):
        hit = item.hit
        excerpt = _excerpt(contents[hit.path] or b"", hit) if hit.kind != "file" else None
        if excerpt:
            blocks_pool.append(Candidate(hit.id, f"--- {_where(hit)} ---\n{excerpt}", item.score, ordinal))
    shown_body = {c.id for c in select(SECTION_BODIES, blocks_pool, room=bodies_room, estimate=estimate, policy=policy, task_terms=task_terms, protected=keep)}
    body_blocks = [c.text for c in blocks_pool if c.id in shown_body]
    for item in verified:
        if item.hit.id in shown_body:
            hashes[item.hit.path] = item.hit.file_hash
    body_text = "\n".join([SECTION_BODIES, *body_blocks]) if body_blocks else ""

    for item in verified:
        hit = item.hit
        if hit.id in shown_body:
            disclosure = "body"
        elif hit.id in shown_signature:
            disclosure = "signature"
        else:
            selected.append(_omitted(item, "over the budget"))
            continue
        selected.append(Selected(hit.path, hit.kind, hit.symbol, hit.file_hash, hit.start_line, hit.end_line, disclosure, item.score, dict(item.ranks), _reason(item)))

    text = "\n".join(part for part in (required_text, signature_text, body_text) if part)
    return Pack(text, estimate(text) if text else 0, budget_tokens, tuple(selected), hashes, (), tuple(stale),
                None if outline is None else {**outline.metadata(overview_path or ""), "section_tokens": used})  # V: the outline section's cost


def _reason(item: Ranked) -> str:
    return "matched by " + ", ".join(sorted(item.ranks))


def _omitted(item: Ranked, reason: str) -> Selected:
    hit = item.hit
    return Selected(hit.path, hit.kind, hit.symbol, hit.file_hash, hit.start_line, hit.end_line, "omitted", item.score, dict(item.ranks), reason)
