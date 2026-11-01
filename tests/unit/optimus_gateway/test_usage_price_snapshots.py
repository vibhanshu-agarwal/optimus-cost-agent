"""Plan 12.9 Task 2: price snapshots through the Gateway's capture outbox, and `price_snapshot_id` on usage envelopes only
once its snapshot is durable locally (ADR-034)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from optimus_gateway import usage_price_snapshots as snapshots
from optimus_gateway.decisions import _decision_usage
from optimus_gateway.responses import _gateway_usage
from optimus_gateway.upstream_client import DecisionResult, ProviderMessageResult
from optimus_model_policy.binding import compose_trusted_snapshot, packaged_defaults
from optimus_model_policy.savings_references import CategoryPrices, Reference, ReferenceSet, Source
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc


@pytest.fixture
def writer(tmp_path):
    outbox = ob.OutboxWriter(tmp_path / "outbox")
    snapshots.configure(outbox)
    yield outbox
    snapshots.configure(None)
    outbox.close()


@pytest.fixture(scope="module")
def policy():
    return SimpleNamespace(snapshot=compose_trusted_snapshot(packaged_defaults()))


def _reference(ref_id="ref-a"):
    return Reference(id=ref_id, display=ref_id, unit="usd_per_million_tokens",
                     prices=CategoryPrices(input="1", output="4", cached_input="0.1"), reasoning_billed_as_output=True,
                     source=Source(url="https://example.test/p", price_as_of=date(2026, 11, 1)))


def _records(outbox):
    outbox.close()
    return [record.payload for record in ob.scan_stream(outbox.directory).records]


def test_a_registry_snapshot_is_a_valid_content_derived_record_of_tiers_roles_and_prices(policy):
    first, again = snapshots.registry_payload(policy.snapshot), snapshots.registry_payload(policy.snapshot)

    assert first is not None and again is not None
    assert uc.validate_payload(first, writer="gateway") == uc.REGISTRY_SNAPSHOT
    assert first["snapshot_id"] == again["snapshot_id"]  # captured twice, the same snapshot
    assert first["registry_hash"] == policy.snapshot.effective_hash and first["price_as_of"] is None
    models = policy.snapshot.policy.models
    assert [e["model"] for e in first["entries"]] == sorted(models)
    assert all(Decimal(e["input_usd_per_million"]) == models[e["model"]].prices.input_usd_per_million for e in first["entries"])
    assert any(e["roles"] for e in first["entries"])


def test_a_reference_snapshot_keeps_the_reference_id_and_the_contract_recomputes_it():
    payload = snapshots.reference_payload(_reference())

    assert payload is not None and payload["snapshot_id"] == _reference().snapshot_id
    assert uc.validate_payload(payload, writer="gateway") == uc.REFERENCE_SNAPSHOT
    altered = {**payload, "reference": {**payload["reference"], "display": "other"}}
    with pytest.raises(uc.ContractError):
        uc.validate_payload(altered, writer="gateway")


def test_without_accounting_or_a_registry_the_usage_envelope_keeps_its_earlier_bytes(writer, policy):
    snapshots.configure(None)
    assert snapshots.stamp({"cost_usd": "0"}, policy) == {"cost_usd": "0"}  # no accounting
    snapshots.configure(writer)
    assert snapshots.stamp({"cost_usd": "0"}, None) == {"cost_usd": "0"}  # accounting, but no enforced registry
    assert not writer.directory.exists()  # nothing was written


def test_the_snapshot_id_is_stamped_once_durable_and_its_snapshot_written_once(writer, policy):
    first = snapshots.stamp({}, policy)
    second = snapshots.stamp({}, policy)

    assert first == second == {"price_snapshot_id": snapshots.registry_payload(policy.snapshot)["snapshot_id"]}
    assert [p["kind"] for p in _records(writer)] == [uc.REGISTRY_SNAPSHOT]


def test_a_failed_snapshot_write_leaves_the_id_absent_and_is_retried(tmp_path, policy):
    closed = ob.OutboxWriter(tmp_path / "closed")
    closed.close()
    snapshots.configure(closed)
    try:
        assert snapshots.stamp({}, policy) == {}
        working = ob.OutboxWriter(tmp_path / "working")
        snapshots.configure(working)
        assert "price_snapshot_id" in snapshots.stamp({}, policy)
        working.close()
    finally:
        snapshots.configure(None)


def test_a_failed_write_on_the_same_writer_is_submitted_again(policy):
    class Writer:
        def __init__(self):
            self.submitted = []

        def submit(self, payload):
            ticket = ob.Ticket()
            ticket._resolve(None if not self.submitted else object(), "QUEUE_FULL" if not self.submitted else None)
            self.submitted.append(payload["kind"])
            return ticket

    flaky = Writer()
    snapshots.configure(flaky)
    try:
        assert snapshots.stamp({}, policy) == {}
        assert "price_snapshot_id" in snapshots.stamp({}, policy)
        assert "price_snapshot_id" in snapshots.stamp({}, policy)
    finally:
        snapshots.configure(None)
    assert flaky.submitted == [uc.REGISTRY_SNAPSHOT] * 2  # once refused, once durable, then never again


def test_each_adopted_reference_is_captured_once(writer):
    references = ReferenceSet(version=1, references=(_reference("ref-a"), _reference("ref-b")))

    snapshots.record_references(references)
    snapshots.record_references(references)

    payloads = _records(writer)
    assert [p["reference"]["id"] for p in payloads] == ["ref-a", "ref-b"]
    assert [p["snapshot_id"] for p in payloads] == [r.snapshot_id for r in references.references]


def test_completion_and_decision_envelopes_carry_the_durable_snapshot_id(writer, policy):
    config = SimpleNamespace(provider="openrouter", model_policy=policy)
    completion = ProviderMessageResult(
        message_id="msg-1", output_text="ok", input_tokens=3, output_tokens=2, total_tokens=5, billing_units=5,
        cost_usd=Decimal("0.00005"), provider="openrouter", resolved_provider=None, requested_model="m-1",
        resolved_model="m-1", model_version=None, cache_hit=False,
    )
    decision = DecisionResult(decision_id="d-1", answers={}, input_tokens=3, output_tokens=1, cost_usd=Decimal("0.00001"),
                              resolved_provider=None, resolved_model="m-1")

    expected = snapshots.registry_payload(policy.snapshot)["snapshot_id"]
    assert _gateway_usage(config=config, model="m-1", provider_result=completion, gateway_request_id="gw-1")["price_snapshot_id"] == expected
    assert _decision_usage(config=config, model="m-1", result=decision, gateway_request_id="gw-2")["price_snapshot_id"] == expected
