"""Frozen literal and binding-derived seed tests."""

from __future__ import annotations

import hashlib

from tools.plan1126_runtime_audit.corpus import derived_seed, literal_seeds


def test_regression_corpus_replays_frozen_literal_seeds() -> None:
    before = literal_seeds(binding_commit="0" * 40)
    after = literal_seeds(binding_commit="f" * 40)
    assert before == after == (0, 1, 42, 18446744073709551615)


def test_fresh_seed_is_first_64_bits_of_binding_commit_scenario_and_index() -> None:
    commit = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
    expected = int.from_bytes(hashlib.sha256(f"{commit}delivery7".encode()).digest()[:8], "big")
    assert derived_seed(commit, "delivery", 7) == expected
    assert derived_seed(commit, "delivery", 7) != derived_seed(commit, "delivery", 8)
