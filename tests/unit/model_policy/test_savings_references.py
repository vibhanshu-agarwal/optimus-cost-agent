"""Plan 12.9 Task 1: the savings-report reference configuration (D3: any configured model, registry or not)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from optimus_model_policy.registry import RegistryError
from optimus_model_policy.savings_references import load_references, packaged_references, parse_references
from optimus_security import usage_capture_contract as uc

_ENTRY = """\
  - id: ref-a
    display: Reference A
    unit: usd_per_million_tokens
    prices: {input: "1.00", output: "4.00", cached_input: "0.10"}
    reasoning_billed_as_output: true
    reasoning_source: {url: "https://example.test/billing", quote: "Reasoning is output.", fetched_on: "2026-11-01"}
    source: {url: "https://example.test/prices", price_as_of: "2026-11-01"}
"""


def _write(tmp_path, body: str, name: str = "refs.yaml"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_the_packaged_references_load_and_are_independent_of_the_registry():
    references = load_references(packaged_references())

    assert len(references.references) >= 1
    assert all(r.source.price_as_of is not None for r in references.references)
    assert references.benchmark is not None


def test_a_reference_outside_the_registry_loads_from_its_own_price_evidence(tmp_path):
    references = load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY))

    (reference,) = references.references
    assert reference.id == "ref-a" and reference.prices.input == Decimal("1.00")
    assert reference.source.price_as_of == date(2026, 11, 1)


def test_the_snapshot_id_ignores_formatting_but_not_prices(tmp_path):
    first = load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY, "a.yaml")).references[0]
    reformatted = load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY.replace('"1.00"', '"1"'), "b.yaml")).references[0]
    repriced = load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY.replace('"1.00"', '"1.01"'), "c.yaml")).references[0]

    assert first.snapshot_id == reformatted.snapshot_id != repriced.snapshot_id


def test_a_missing_date_or_price_loads_and_is_left_for_the_report_to_call_unavailable(tmp_path):
    body = _ENTRY.replace('cached_input: "0.10"', "cached_input: null").replace(', price_as_of: "2026-11-01"', ", price_as_of: null")

    (reference,) = load_references(_write(tmp_path, "version: 1\nreferences:\n" + body)).references

    assert reference.prices.cached_input is None and reference.source.price_as_of is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.replace("    unit:", "    colour: red\n    unit:"),
        lambda e: e.replace('"1.00"', "1.5"),
        lambda e: e.replace('"1.00"', '"-1"'),
        lambda e: e.replace("id: ref-a", "id: Ref A"),
        lambda e: e.replace("usd_per_million_tokens", "usd_per_token"),
        lambda e: e.replace('url: "https://example.test/prices"', "evidence: docs/x.md, url: \"https://example.test/p\""),
        lambda e: e.replace("reasoning_billed_as_output: true", "reasoning_billed_as_output: \"yes\""),
    ],
)
def test_malformed_references_are_refused(tmp_path, mutate):
    with pytest.raises(RegistryError) as raised:
        load_references(_write(tmp_path, "version: 1\nreferences:\n" + mutate(_ENTRY)))
    assert raised.value.code in {"REFERENCES_INVALID", "YAML_REJECTED"}


def test_duplicate_ids_and_unordered_tiers_are_refused(tmp_path):
    with pytest.raises(RegistryError):
        load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY + _ENTRY, "dup.yaml"))
    tiers = _ENTRY.replace("    reasoning_billed", "    tiers:\n"
                           "      - {min_input_tokens: 200, prices: {input: \"2\", output: \"8\", cached_input: \"0.2\"}}\n"
                           "      - {min_input_tokens: 100, prices: {input: \"3\", output: \"9\", cached_input: \"0.3\"}}\n"
                           "    reasoning_billed")
    with pytest.raises(RegistryError):
        load_references(_write(tmp_path, "version: 1\nreferences:\n" + tiers, "tiers.yaml"))


def test_a_long_context_tier_applies_from_its_threshold(tmp_path):
    body = _ENTRY.replace("    reasoning_billed", "    tiers:\n"
                          "      - {min_input_tokens: 1000, prices: {input: \"2\", output: \"8\", cached_input: \"0.2\"}}\n"
                          "    reasoning_billed")
    (reference,) = load_references(_write(tmp_path, "version: 1\nreferences:\n" + body)).references

    assert reference.prices_for(999).input == Decimal("1.00")
    assert reference.prices_for(1000).input == Decimal("2")


def test_every_packaged_reference_is_a_valid_reference_snapshot_record():
    for reference in load_references(packaged_references()).references:
        payload = {"kind": uc.REFERENCE_SNAPSHOT, "at": "2026-11-01T00:00:00+00:00", "snapshot_id": reference.snapshot_id,
                   "reference": reference.model_dump(mode="json")}
        assert uc.validate_payload(payload, writer="gateway") == uc.REFERENCE_SNAPSHOT


def test_display_text_refuses_control_characters(tmp_path):
    with pytest.raises(RegistryError):
        load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY.replace("display: Reference A", 'display: "A\u0007B"')))


# --- Plan 12.9 Checkpoint A (round 93) ---------------------------------------------------------------------------


def test_a_billing_rule_needs_its_own_dated_source_or_stays_unknown(tmp_path):
    unsourced = _ENTRY.replace(
        '    reasoning_source: {url: "https://example.test/billing", quote: "Reasoning is output.", fetched_on: "2026-11-01"}\n', "")
    unknown = unsourced.replace("reasoning_billed_as_output: true", "reasoning_billed_as_output: null")

    with pytest.raises(RegistryError):
        load_references(_write(tmp_path, "version: 1\nreferences:\n" + unsourced))
    assert load_references(_write(tmp_path, "version: 1\nreferences:\n" + unknown, "u.yaml")).references[0].reasoning_source is None
    assert all(r.reasoning_source is not None for r in load_references(packaged_references()).references
               if r.reasoning_billed_as_output is not None)


def test_a_reference_without_any_source_loads_beside_a_sourced_one(tmp_path):
    bare = _ENTRY.replace("ref-a", "ref-b").replace('    source: {url: "https://example.test/prices", price_as_of: "2026-11-01"}',
                                                    '    source: {price_as_of: "2026-11-01"}')

    references = load_references(_write(tmp_path, "version: 1\nreferences:\n" + _ENTRY + bare))

    assert [r.source.locator for r in references.references] == ["https://example.test/prices", None]


def test_an_override_parses_from_the_exact_bytes_its_launch_verified(tmp_path):
    raw = ("version: 1\nreferences:\n" + _ENTRY).encode("utf-8")

    assert parse_references(raw, "savings-references.yaml") == load_references(_write(tmp_path, raw.decode("utf-8")))
    with pytest.raises(RegistryError):
        parse_references(b"version: 1\nreferences: [{id: x}]\n", "savings-references.yaml")


def test_long_text_fits_the_reports_string_bound(tmp_path):
    body = ("version: 1\nreferences:\n" + _ENTRY + "benchmark:\n  text: " + "x" * 513 +
            "\n  limitations: l\n  source: {evidence: e, price_as_of: null}\n")

    with pytest.raises(RegistryError):
        load_references(_write(tmp_path, body))
