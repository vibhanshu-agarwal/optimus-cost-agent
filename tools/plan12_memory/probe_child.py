"""Plan 12.7 P1/P2 child: runs inside the isolated probe venv, never the project one, and imports nothing from the repository.

    <probe-venv-python> probe_child.py smoke <distribution>...
    <probe-venv-python> probe_child.py embed --model M --cache DIR --items N --batch B --cursor FILE [--stop-after K]

It prints one JSON object as its last stdout line. The synthetic corpus is generated in RAM from a
fixed seed and is never written; the cursor holds only the next batch index and a running hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from importlib import metadata
from pathlib import Path


def _license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    found = meta.get("License-Expression") or ""
    if not found and (text := (meta.get("License") or "").strip()) and len(text) < 80:
        found = text
    classifiers = [value.split("::")[-1].strip() for value in meta.get_all("Classifier") or [] if value.startswith("License ::")]
    return "; ".join(part for part in [found, *classifiers] if part) or "UNKNOWN"


def _smoke_redisvl() -> str:
    from redisvl.schema import IndexSchema

    schema = IndexSchema.from_dict({"index": {"name": "p127", "prefix": "p127:item", "storage_type": "json"},
                                    "fields": [{"name": "kind", "type": "tag"},
                                               {"name": "vector", "type": "vector", "attrs": {
                                                   "algorithm": "flat", "dims": 384, "distance_metric": "cosine",
                                                   "datatype": "float32"}}]})
    return f"schema with {len(schema.fields)} fields"


def _parse(module_name: str, source: bytes) -> str:
    import importlib

    from tree_sitter import Language, Parser

    language = Language(importlib.import_module(module_name).language())
    tree = Parser(language).parse(source)
    if tree.root_node.has_error:
        raise ValueError("parse tree has errors")
    count, stack = 0, [tree.root_node]
    while stack:
        node = stack.pop()
        count += 1
        stack.extend(node.children)
    return f"{count} nodes"


def _smoke_rustworkx() -> str:
    import rustworkx

    graph = rustworkx.PyDiGraph()
    nodes = graph.add_nodes_from(range(6))
    graph.add_edges_from([(nodes[i], nodes[i + 1], 1.0) for i in range(5)])
    order = rustworkx.topological_sort(graph)
    return f"topological order of {len(order)} nodes"


def _smoke_graspologic_native() -> str:
    import graspologic_native

    edges = [("a", "b", 1.0), ("b", "c", 1.0), ("c", "a", 1.0), ("d", "e", 1.0), ("e", "f", 1.0), ("f", "d", 1.0),
             ("c", "d", 0.1)]
    outcome = graspologic_native.leiden(edges=edges, seed=7)
    return f"leiden returned {type(outcome).__name__}"


def _smoke_pathspec() -> str:
    from pathspec import GitIgnoreSpec

    spec = GitIgnoreSpec.from_lines(["*.log", "!keep.log"])
    if not spec.match_file("a.log") or spec.match_file("keep.log"):
        raise ValueError("unexpected ignore semantics")
    return "negation honoured"


def _smoke_cryptography() -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    cipher = AESGCM(key)
    if cipher.decrypt(nonce, cipher.encrypt(nonce, b"synthetic", b"meta"), b"meta") != b"synthetic":
        raise ValueError("round trip failed")
    return "AES-256-GCM round trip"


def _smoke_fastembed() -> str:
    from fastembed import TextEmbedding

    return f"{len(TextEmbedding.list_supported_models())} supported models listed"


def _smoke_psutil() -> str:
    import psutil

    return f"rss {psutil.Process().memory_info().rss} bytes"


_SMOKES = {
    "redisvl": _smoke_redisvl,
    "tree-sitter": lambda: "core imported" if __import__("tree_sitter") else "",
    "tree-sitter-python": lambda: _parse("tree_sitter_python", b"def f(x):\n    return x + 1\n"),
    "tree-sitter-java": lambda: _parse("tree_sitter_java", b"class A { int f(int x) { return x + 1; } }\n"),
    "rustworkx": _smoke_rustworkx,
    "graspologic-native": _smoke_graspologic_native,
    "pathspec": _smoke_pathspec,
    "cryptography": _smoke_cryptography,
    "fastembed": _smoke_fastembed,
    "psutil": _smoke_psutil,
}


def smoke(names: list[str]) -> dict:
    rows = {}
    for name in names:
        row: dict = {}
        try:
            dist = metadata.distribution(name)
            row.update(version=dist.version, license=_license(dist),
                       wheel_tags=[line.split(":", 1)[1].strip() for line in (dist.read_text("WHEEL") or "").splitlines()
                                   if line.startswith("Tag:")])
            row["result"] = _SMOKES[name]() if name in _SMOKES else "imported metadata only"
            row["ok"] = True
        except Exception as error:  # every failure is a row, not a crash
            row.update(ok=False, error=f"{type(error).__name__}: {error}"[:400])
        rows[name] = row
    return {"python": sys.version.split()[0], "platform": sys.platform, "packages": rows}


def _corpus(items: int) -> list[str]:
    rng = random.Random(1207)
    words = ["cache", "index", "memory", "redis", "vector", "parser", "module", "graph", "token", "budget", "session",
             "anchor", "project", "worker", "cursor", "embed", "query", "ledger", "notice", "policy"]
    return [f"def {rng.choice(words)}_{i}({rng.choice(words)}): return " + " ".join(rng.choice(words) for _ in range(30))
            for i in range(items)]


def _write_cursor(path: Path, state: dict) -> None:
    partial = path.with_name(path.name + ".partial")
    with partial.open("w", encoding="utf-8") as handle:
        json.dump(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, path)


def embed(args: argparse.Namespace) -> dict:
    import numpy
    import psutil
    from fastembed import TextEmbedding

    started = time.perf_counter()
    model = TextEmbedding(model_name=args.model, cache_dir=args.cache)
    loaded = time.perf_counter()
    catalogue = {row.get("model"): row for row in TextEmbedding.list_supported_models()}
    texts = _corpus(args.items)
    cursor = Path(args.cursor)
    state = json.loads(cursor.read_text(encoding="utf-8")) if cursor.exists() else {
        "model": args.model, "items": args.items, "batch": args.batch, "next_batch": 0, "chain": hashlib.sha256().hexdigest()}
    if (state["model"], state["items"], state["batch"]) != (args.model, args.items, args.batch):
        return {"ok": False, "error": "cursor belongs to a different run"}
    batches = (args.items + args.batch - 1) // args.batch
    done_here, dimensions = 0, None
    while state["next_batch"] < batches:
        if args.stop_after is not None and done_here >= args.stop_after:
            return {"ok": True, "status": "stopped", "next_batch": state["next_batch"], "batches": batches}
        start = state["next_batch"] * args.batch
        vectors = list(model.embed(texts[start:start + args.batch], batch_size=args.batch))
        dimensions = len(vectors[0])
        chain = hashlib.sha256(bytes.fromhex(state["chain"]))
        for vector in vectors:
            chain.update(numpy.round(numpy.asarray(vector, dtype=numpy.float32), 4).astype(numpy.float32).tobytes())
        state = {**state, "next_batch": state["next_batch"] + 1, "chain": chain.hexdigest()}
        _write_cursor(cursor, state)
        done_here += 1
    elapsed = time.perf_counter() - loaded
    memory = psutil.Process().memory_info()
    entry = catalogue.get(args.model, {})
    cache = Path(args.cache)
    return {"ok": True, "status": "complete", "output_sha256": state["chain"], "batches": batches,
            "batches_this_run": done_here, "items_this_run": min(args.items, done_here * args.batch),
            "dimensions": dimensions or entry.get("dim"), "load_seconds": round(loaded - started, 3),
            "embed_seconds": round(elapsed, 3),
            "items_per_second": round(min(args.items, done_here * args.batch) / elapsed, 1) if done_here else None,
            "peak_working_set_bytes": getattr(memory, "peak_wset", None), "rss_bytes": memory.rss,
            "cpu_count": os.cpu_count(), "model_license": entry.get("license"), "model_sources": entry.get("sources"),
            "model_cache_bytes": sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) if cache.exists() else 0}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    smoke_parser = sub.add_parser("smoke")
    smoke_parser.add_argument("names", nargs="+")
    embed_parser = sub.add_parser("embed")
    for name in ("--model", "--cache", "--cursor"):
        embed_parser.add_argument(name, required=True)
    embed_parser.add_argument("--items", type=int, required=True)
    embed_parser.add_argument("--batch", type=int, required=True)
    embed_parser.add_argument("--stop-after", type=int)
    args = parser.parse_args(argv)
    try:
        output = smoke(args.names) if args.mode == "smoke" else embed(args)
    except Exception as error:
        output = {"ok": False, "error": f"{type(error).__name__}: {error}"[:400]}
    print(json.dumps(output, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
