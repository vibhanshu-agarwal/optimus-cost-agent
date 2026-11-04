"""Plan 12.10 Task 4: fusion, one pinned generation per retrieval, visible channel failures and the pure pack. The route itself is proved
against real Redis in tests/integration/context; here the storage port answers from a table so each decision can be isolated."""

from __future__ import annotations

import base64
import hashlib

import pytest

from context_engine.code_index import path_id
from context_engine.context_pack import assemble_pack
from context_engine.index_worker import StorageRefusedError, StorageUnavailableError
from context_engine.repo_map import MapFile, neighbours
from context_engine.retrieval import CatalogueFile, Hit, Ranked, Retriever, fuse, query_terms, read_catalogue, seed_map


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hit(ident: str, path: str = "a.py", *, kind: str = "symbol", symbol: str | None = None, file_hash: str = "0" * 64, lines: tuple[int, int] | None = (1, 2), signature: str | None = None) -> Hit:
    start, end = lines or (None, None)
    return Hit(id=ident, kind=kind, path=path, file_hash=file_hash, symbol=symbol, signature=signature, start_line=start, end_line=end)


def _wire(hit: Hit) -> dict:
    return {
        "id": hit.id, "kind": hit.kind, "path": hit.path, "file_hash": hit.file_hash, "language": hit.language,
        **({"symbol": hit.symbol} if hit.symbol else {}), **({"start_line": hit.start_line, "end_line": hit.end_line} if hit.start_line else {}),
    }


class _Storage:
    def __init__(self, *, current=None, answers=None, failures=None, catalogue=()):
        self.current = {"epoch": 7, "coverage": {"complete": False}, "revision": "r" * 64} if current is None else current
        self.answers = answers or {}
        self.failures = failures or {}
        self.catalogue = list(catalogue)
        self.calls: list[tuple[str, dict]] = []

    def call(self, op, **fields):
        self.calls.append((op, fields))
        failure = self.failures.get(fields.get("mode", op))
        if failure is not None:
            raise failure
        if op == "coverage":
            return {"current": self.current or None}
        if op == "catalogue":
            return {"files": self.catalogue, "cursor": None}
        answer = self.answers.get((fields["mode"], fields.get("path_id") or fields.get("symbol")), self.answers.get(fields["mode"], []))
        return {"records": [_wire(hit) for hit in answer]}


class _Embedder:
    identity = "e"
    dimensions = 2

    def embed(self, texts):
        return [b"\0" * 8 for _ in texts]


def test_query_terms_fold_like_records_and_stay_inside_the_route_limit():
    assert set(query_terms("Where is parseFile? see DataNode")) >= {"parsefile", "parse", "file", "datanode", "where"}
    assert all(term == term.lower() for term in query_terms("ABC Def_Ghi"))
    assert len(query_terms(" ".join(f"word{i}" for i in range(200)))) == 64


def test_fusion_rewards_agreement_and_is_a_stable_order():
    both, lexical_only, dense_only = _hit("both"), _hit("lex"), _hit("den")
    first = fuse({"lexical": [lexical_only, both], "dense": [dense_only, both]})
    assert first[0].hit.id == "both"
    assert first[0].ranks == {"dense": 2, "lexical": 2}
    assert fuse({"dense": [dense_only, both], "lexical": [lexical_only, both]}) == first


def test_fusion_ties_prefer_a_named_file_then_symbols_then_path():
    named = _hit("n", "z.py", kind="file")
    symbol = _hit("s", "b.py")
    section = _hit("d", "a.md", kind="section")
    plain = _hit("f", "a.py", kind="file")
    # Each is first in its own equally weighted channel, so all four scores tie.
    order = fuse({"lexical": [plain], "dense": [section], "memory": [symbol], "structure": [named]}, named=["z.py"], weights={"lexical": 1, "dense": 1, "memory": 1, "structure": 1})
    assert [item.hit.id for item in order] == ["n", "s", "d", "f"]


def test_a_retrieval_pins_one_epoch_for_every_channel():
    storage = _Storage(answers={"lexical": [_hit("a")], "dense": [_hit("b")]})
    result = Retriever(storage, _Embedder()).retrieve("find parse", named_paths=["a.py"], named_symbols=["A.b"])
    assert result.state == "ok" and result.epoch == 7
    queries = [fields for op, fields in storage.calls if op == "query"]
    assert queries and all(fields["epoch"] == 7 for fields in queries)
    assert {fields["mode"] for fields in queries} >= {"lexical", "dense", "path", "symbol"}


def test_nothing_published_is_said_rather_than_treated_as_no_matches():
    storage = _Storage(current={})
    result = Retriever(storage, _Embedder()).retrieve("x")
    assert result.state == "unpublished" and result.ranked == ()
    assert [op for op, _ in storage.calls] == ["coverage"]


def test_a_lost_channel_is_reported_and_the_others_still_answer():
    storage = _Storage(answers={"lexical": [_hit("a")]}, failures={"dense": StorageUnavailableError("down")})
    result = Retriever(storage, _Embedder()).retrieve("x")
    assert result.state == "ok"
    assert [item.hit.id for item in result.ranked] == ["a"]
    assert result.channels["dense"] == "unavailable" and result.channels["lexical"] == "1 results"


def test_absent_embeddings_fall_back_to_lexical_visibly():
    storage = _Storage(answers={"lexical": [_hit("a")]})
    result = Retriever(storage, None).retrieve("x")
    assert result.channels["dense"] == "no embedding artifact"
    assert all(fields.get("mode") != "dense" for _, fields in storage.calls)


def test_the_memory_channel_says_when_it_has_no_authorized_source():
    assert Retriever(_Storage(), None).retrieve("x").channels["memory"] == "no authorized source"
    only = Retriever(_Storage(), None).retrieve("x", memory=[_hit("m")])
    assert only.channels["memory"] == "1 results" and only.ranked[0].ranks == {"memory": 1}


@pytest.mark.parametrize("code", ["EPOCH_EXPIRED", "NOT_PUBLISHED"])
def test_a_generation_that_moved_is_tried_again_at_most_twice_then_called_expired(code):
    storage = _Storage(failures={"lexical": StorageRefusedError(code)})
    result = Retriever(storage, None).retrieve("x")
    assert result.state == "expired" and result.ranked == ()
    assert [op for op, _ in storage.calls].count("coverage") == 2


def test_an_outage_never_raises_into_the_turn():
    assert Retriever(_Storage(failures={"coverage": StorageUnavailableError("down")}), None).retrieve("x").state == "unavailable"
    assert Retriever(_Storage(failures={"coverage": StorageRefusedError("SCOPE_UNKNOWN")}), None).retrieve("x").state == "unpublished"
    assert Retriever(_Storage(failures={"coverage": StorageRefusedError("SCOPE_DROPPING")}), None).retrieve("x").state == "unavailable"


def test_a_cancelled_turn_stops_asking():
    storage = _Storage()
    result = Retriever(storage, _Embedder(), cancelled=lambda: True).retrieve("x")
    assert all(op == "coverage" for op, _ in storage.calls)
    assert result.channels["lexical"].startswith("not asked")


def test_dense_sends_the_embedders_vector():
    storage = _Storage()
    Retriever(storage, _Embedder()).retrieve("x")
    dense = next(fields for op, fields in storage.calls if fields.get("mode") == "dense")
    assert base64.b64decode(dense["vector"]) == b"\0" * 8


def test_structure_follows_only_observed_imports():
    files = [MapFile("pkg/a.py", ("pkg.b",)), MapFile("pkg/b.py"), MapFile("pkg/c.py", ("pkg.a",)), MapFile("pkg/d.py")]
    assert neighbours(files, ["pkg/a.py"]) == ["pkg/b.py", "pkg/c.py"]
    catalogue = [{"path": item.path, "file_hash": "0" * 64, "language": "python", "modified": None, "description": ("imports: " + " ".join(item.imports)) if item.imports else None} for item in files]
    storage = _Storage(catalogue=catalogue)
    Retriever(storage, None).retrieve("x", named_paths=["pkg/a.py"])
    asked = {fields["path_id"] for op, fields in storage.calls if fields.get("mode") == "path"}
    assert asked == {path_id("pkg/a.py"), path_id("pkg/b.py"), path_id("pkg/c.py")}


def test_recency_uses_the_catalogues_dates_in_a_stable_order():
    catalogue = [{"path": f"f{i}.py", "file_hash": "0" * 64, "language": "python", "modified": i, "description": None} for i in range(12)]
    storage = _Storage(catalogue=catalogue)
    Retriever(storage, None).retrieve("x")
    asked = [fields["path_id"] for op, fields in storage.calls if fields.get("mode") == "path"]
    assert asked == [path_id(f"f{i}.py") for i in range(11, 3, -1)]


def test_the_seed_map_is_the_same_text_for_every_prompt_of_a_generation():
    catalogue = [CatalogueFile("a.py", "0" * 64, "python", 1, "imports: b"), CatalogueFile("b.py", "0" * 64, "python", 2, None)]
    storage = _Storage(answers={("path", path_id("b.py")): [_hit("s", "b.py", symbol="B.run")]})
    first, second = seed_map(storage, 7, catalogue, budget_chars=1000), seed_map(storage, 7, catalogue, budget_chars=1000)
    assert first == second
    assert first.text.splitlines()[0] == "b.py: B.run"


def test_read_catalogue_follows_every_page():
    class Paged(_Storage):
        def call(self, op, **fields):
            self.calls.append((op, fields))
            if "cursor" not in fields:
                return {"files": [{"path": "a.py", "file_hash": "0" * 64}], "cursor": "next"}
            return {"files": [{"path": "b.py", "file_hash": "0" * 64}], "cursor": None}

    assert [item.path for item in read_catalogue(Paged(), 7)] == ["a.py", "b.py"]


# --- the pack -----------------------------------------------------------------------------------


SOURCE = b"def a():\n    return 1\n\ndef b():\n    return 2\n"


def _estimate(text: str) -> int:
    return len(text)


def _ranked(hit: Hit, score: float = 1.0) -> Ranked:
    return Ranked(hit, score, {"lexical": 1})


def _read(files: dict[str, bytes]):
    return files.get


def test_a_body_is_shown_only_when_the_file_still_has_the_indexed_bytes():
    fresh = _hit("f", "a.py", symbol="a", file_hash=_sha(SOURCE), lines=(1, 2), signature="def a()")
    pack = assemble_pack(required=(), ranked=[_ranked(fresh)], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=10_000)
    assert "    return 1" in pack.text and pack.stale_paths == ()
    assert pack.file_sha256s == {"a.py": _sha(SOURCE)}


def test_a_changed_file_gives_neither_body_nor_signature_and_is_reported_stale():
    stale = _hit("f", "a.py", symbol="a", file_hash=_sha(b"older bytes"), signature="def old_secret_name()")
    pack = assemble_pack(required=(), ranked=[_ranked(stale)], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=10_000)
    assert pack.text == "" and pack.stale_paths == ("a.py",)
    assert pack.selected[0].disclosure == "omitted" and pack.selected[0].reason == "the file changed since it was indexed"


def test_a_file_policy_now_refuses_is_left_out():
    hit = _hit("f", "secret.py", symbol="a", file_hash=_sha(SOURCE), signature="def a()")
    pack = assemble_pack(required=(), ranked=[_ranked(hit)], read=_read({}), estimate=_estimate, budget_tokens=10_000)
    assert pack.text == "" and pack.selected[0].reason == "refused by the file policy now"


def test_required_evidence_comes_first_and_whole():
    other = _hit("f", "b.py", symbol="b", file_hash=_sha(SOURCE), lines=(4, 5), signature="def b()")
    pack = assemble_pack(required=("a.py",), ranked=[_ranked(other)], read=_read({"a.py": SOURCE, "b.py": SOURCE}), estimate=_estimate, budget_tokens=10_000)
    assert pack.text.index("--- a.py ---") < pack.text.index("b.py:4-5")
    assert SOURCE.decode() in pack.text
    assert pack.complete


def test_required_overflow_is_incomplete_never_quietly_smaller():
    pack = assemble_pack(required=("a.py",), ranked=(), read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=10)
    assert not pack.complete and pack.text == "" and pack.missing_required == ("a.py",)


def test_a_required_file_that_cannot_be_read_is_incomplete():
    pack = assemble_pack(required=("gone.py",), ranked=(), read=_read({}), estimate=_estimate, budget_tokens=10_000)
    assert not pack.complete and pack.missing_required == ("gone.py",)
    binary = assemble_pack(required=("b.bin",), ranked=(), read=_read({"b.bin": b"\xff\xfe"}), estimate=_estimate, budget_tokens=10_000)
    assert not binary.complete


def test_a_required_file_is_not_repeated_as_optional():
    same = _hit("f", "a.py", symbol="a", file_hash=_sha(SOURCE), signature="def a()")
    pack = assemble_pack(required=("a.py",), ranked=[_ranked(same)], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=10_000)
    assert pack.text.count("def a()") == 1


def test_disclosure_narrows_with_the_budget_and_the_rest_is_reported():
    hits = [_hit(f"h{i}", "a.py", symbol=f"s{i}", file_hash=_sha(SOURCE), lines=(1, 5), signature=f"def s{i}()") for i in range(8)]
    wide = assemble_pack(required=(), ranked=[_ranked(h) for h in hits], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=10_000)
    assert {item.disclosure for item in wide.selected} == {"body"}
    narrow = assemble_pack(required=(), ranked=[_ranked(h) for h in hits], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=160)
    assert narrow.tokens <= 160
    kinds = {item.disclosure for item in narrow.selected}
    assert "omitted" in kinds and kinds & {"signature", "body"}
    assert all(item.reason == "over the budget" for item in narrow.selected if item.disclosure == "omitted")


def test_a_large_item_does_not_stop_smaller_ones_after_it():
    big = b"x\n" * 5000
    files = {"big.py": big, "a.py": SOURCE}
    hits = [_hit("big", "big.py", symbol="big", file_hash=_sha(big), lines=(1, 5000)), _hit("small", "a.py", symbol="a", file_hash=_sha(SOURCE), lines=(1, 2))]
    pack = assemble_pack(required=(), ranked=[_ranked(h) for h in hits], read=_read(files), estimate=_estimate, budget_tokens=400)
    assert "    return 1" in pack.text


def test_the_same_inputs_give_the_same_pack():
    hits = [_hit(f"h{i}", "a.py", symbol=f"s{i}", file_hash=_sha(SOURCE), lines=(1, 2), signature=f"def s{i}()") for i in range(4)]
    def make():
        return assemble_pack(required=(), ranked=[_ranked(h) for h in hits], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=300)

    assert make() == make()


def test_the_manifest_side_never_holds_a_body():
    hit = _hit("f", "a.py", symbol="a", file_hash=_sha(SOURCE), lines=(1, 2), signature="def a()")
    pack = assemble_pack(required=(), ranked=[_ranked(hit)], read=_read({"a.py": SOURCE}), estimate=_estimate, budget_tokens=10_000)
    assert "return 1" not in repr(pack.selected)
