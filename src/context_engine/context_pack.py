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

from .retrieval import Hit, Ranked

SIGNATURE_SHARE: Final = 0.25  # of what optional context has; bodies get the rest
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
    disclosure: str  # "required", "signature", "body" or "omitted"
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

    @property
    def complete(self) -> bool:
        return not self.missing_required


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


def assemble_pack(*, required: Sequence[str], ranked: Sequence[Ranked], read: Callable[[str], bytes | None], estimate: Callable[[str], int], budget_tokens: int) -> Pack:
    """`read` returns the file's current bytes, or None when policy no longer admits it. `estimate` is the route's token estimator."""
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
    if used > budget_tokens:
        return Pack("", 0, budget_tokens, tuple(selected), {}, tuple(required))
    if missing:
        return Pack(required_text, used, budget_tokens, tuple(selected), hashes, tuple(missing))

    room = budget_tokens - used
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

    signature_lines: list[str] = []
    shown_signature: set[str] = set()
    for item in verified:
        line = _signature_line(item.hit)
        if line is None:
            continue
        candidate = "\n".join([SECTION_SIGNATURES, *signature_lines, line])
        if estimate(candidate) > signatures_room:
            continue
        signature_lines.append(line)
        shown_signature.add(item.hit.id)
    signature_text = "\n".join([SECTION_SIGNATURES, *signature_lines]) if signature_lines else ""
    used_signatures = estimate(signature_text) if signature_text else 0

    bodies_room = room - used_signatures
    body_blocks: list[str] = []
    shown_body: set[str] = set()
    for item in verified:
        hit = item.hit
        excerpt = _excerpt(contents[hit.path] or b"", hit) if hit.kind != "file" else None
        if not excerpt:
            continue
        block = f"--- {_where(hit)} ---\n{excerpt}"
        candidate = "\n".join([SECTION_BODIES, *body_blocks, block])
        if estimate(candidate) > bodies_room:
            continue
        body_blocks.append(block)
        shown_body.add(hit.id)
        hashes[hit.path] = hit.file_hash
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
    return Pack(text, estimate(text) if text else 0, budget_tokens, tuple(selected), hashes, (), tuple(stale))


def _reason(item: Ranked) -> str:
    return "matched by " + ", ".join(sorted(item.ranks))


def _omitted(item: Ranked, reason: str) -> Selected:
    hit = item.hit
    return Selected(hit.path, hit.kind, hit.symbol, hit.file_hash, hit.start_line, hit.end_line, "omitted", item.score, dict(item.ranks), reason)
