"""Explicit allowlists for evidence-gather host adapters.

Scenario files may select only these IDs. No adversarial-driver adapter is registered.
"""

from __future__ import annotations

from dataclasses import dataclass

CLIENT_ADAPTER_IDS = frozenset({"zed_acp_client"})
FIXTURE_ADAPTER_IDS = frozenset({"hermetic_user_data_fixture"})
PRECONDITION_ADAPTER_IDS = frozenset({"capture_root_ready"})
COLLECTOR_ADAPTER_IDS = frozenset(
    {"acp_stream_collector", "zed_crash_collector", "dwm_capture_collector"}
)
DETECTOR_ADAPTER_IDS = frozenset({"completion_detector", "crash_detector", "render_detector"})


@dataclass(frozen=True, slots=True)
class HostRegistry:
    clients: frozenset[str]
    fixtures: frozenset[str]
    preconditions: frozenset[str]
    collectors: frozenset[str]
    detectors: frozenset[str]


def build_registry() -> HostRegistry:
    return HostRegistry(
        clients=CLIENT_ADAPTER_IDS,
        fixtures=FIXTURE_ADAPTER_IDS,
        preconditions=PRECONDITION_ADAPTER_IDS,
        collectors=COLLECTOR_ADAPTER_IDS,
        detectors=DETECTOR_ADAPTER_IDS,
    )


def assert_scenario_adapters_registered(scenario, registry: HostRegistry) -> None:
    from evidence_handoff.collector.models import Scenario

    if not isinstance(scenario, Scenario):
        raise TypeError("scenario")
    if scenario.client.adapter_id not in registry.clients:
        raise ValueError("unknown_adapter")
    if scenario.fixture.adapter_id not in registry.fixtures:
        raise ValueError("unknown_adapter")
    for item in scenario.preconditions:
        if item.adapter_id not in registry.preconditions:
            raise ValueError("unknown_adapter")
    for item in scenario.collection:
        if item.adapter_id not in registry.collectors:
            raise ValueError("unknown_adapter")
    for item in scenario.detection:
        if item.adapter_id not in registry.detectors:
            raise ValueError("unknown_adapter")
