"""Plan 12.2 Task 4: the free registry drift report (ADR-004 decision 6), tested offline."""

from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path

import pytest

from optimus_model_policy import load_registry
from tools.check_model_registry_drift import CATALOG_URL, compare, fetch, main

_REGISTRY = textwrap.dedent(
    """\
    schema_version: 1
    policy_version: "drift-fixture"
    fixture: true
    context_ceiling_tokens: 262144
    output_reserve_tokens: {}
    estimators: {}
    role_price_blends: {}
    alerts: {thresholds_usd: []}
    models:
      cn/alpha:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.15", output_usd_per_million: "0.60"}
        data_use: {provider_may_train_on_inputs: unverified, disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: []}
        default_reasoning: null
        route:
          estimator: unmeasured
          endpoints:
            - {provider: alpha, quantization: null, context_window_tokens: 1048576, max_output_tokens: 65536, verified: false}
      us/beta:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "1.00", output_usd_per_million: "5.00"}
        data_use: {provider_may_train_on_inputs: unverified, disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: []}
        default_reasoning: null
        route:
          estimator: unmeasured
          endpoints:
            - {provider: beta, quantization: fp8, context_window_tokens: 200000, max_output_tokens: 64000, verified: false}
    roles: {}
    """
)


def _endpoint(tag: str, prompt: str, completion: str, *, context: int, max_out: int, quant: str | None = None) -> dict:
    return {
        "tag": tag,
        "provider_name": tag.title(),
        "pricing": {"prompt": prompt, "completion": completion},
        "context_length": context,
        "max_completion_tokens": max_out,
        "quantization": quant,
    }


def _matching_catalog() -> tuple[dict, dict]:
    catalog = {"data": [{"id": "cn/alpha"}, {"id": "us/beta"}]}
    endpoints = {
        "cn/alpha": {"data": {"endpoints": [_endpoint("alpha", "0.00000015", "0.0000006", context=1048576, max_out=65536)]}},
        "us/beta": {"data": {"endpoints": [_endpoint("beta/fp8", "0.000001", "0.000005", context=200000, max_out=64000, quant="fp8")]}},
    }
    return catalog, endpoints


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    path = tmp_path / "defaults.yaml"
    path.write_text(_REGISTRY, encoding="utf-8")
    return path


def test_a_matching_catalog_reports_no_drift(registry: Path) -> None:
    catalog, endpoints = _matching_catalog()
    assert compare(load_registry(registry, None), catalog, endpoints) == []


def test_every_kind_of_drift_is_reported(registry: Path) -> None:
    catalog, endpoints = _matching_catalog()
    catalog["data"][0]["expiration_date"] = "2026-12-31"
    endpoints["cn/alpha"]["data"]["endpoints"][0]["pricing"]["completion"] = "0.0000007"
    endpoints["cn/alpha"]["data"]["endpoints"][0]["context_length"] = 262144
    endpoints["us/beta"]["data"]["endpoints"][0]["quantization"] = "fp4"

    codes = [(d.model_id, d.code) for d in compare(load_registry(registry, None), catalog, endpoints)]

    assert ("cn/alpha", "EXPIRATION_DATE") in codes
    assert ("cn/alpha", "PRICE") in codes
    assert ("cn/alpha", "CAPACITY") in codes
    assert ("us/beta", "QUANTIZATION") in codes


def test_unlisted_models_and_missing_endpoints_are_reported(registry: Path) -> None:
    catalog, endpoints = _matching_catalog()
    catalog["data"] = [{"id": "cn/alpha"}]
    endpoints["cn/alpha"]["data"]["endpoints"] = [_endpoint("someone-else", "0.00000015", "0.0000006", context=1048576, max_out=65536)]

    codes = [(d.model_id, d.code) for d in compare(load_registry(registry, None), catalog, endpoints)]

    assert codes == [("cn/alpha", "ENDPOINT_NOT_FOUND"), ("us/beta", "MODEL_NOT_LISTED")]


def test_fetch_reads_the_catalog_and_each_registry_models_endpoints(registry: Path) -> None:
    seen: list[str] = []

    def fake_fetcher(url: str) -> dict:
        seen.append(url)
        return {"data": []}

    fetch(load_registry(registry, None), fetcher=fake_fetcher)

    assert seen == [
        CATALOG_URL,
        "https://openrouter.ai/api/v1/models/cn/alpha/endpoints",
        "https://openrouter.ai/api/v1/models/us/beta/endpoints",
    ]


def test_the_report_reads_saved_responses_and_never_edits_the_registry(registry: Path, tmp_path: Path, capsys) -> None:
    catalog, endpoints = _matching_catalog()
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "models.json").write_text(json.dumps(catalog), encoding="utf-8")
    for model_id, payload in endpoints.items():
        (saved / f"endpoints-{model_id.replace('/', '__')}.json").write_text(json.dumps(payload), encoding="utf-8")
    before = hashlib.sha256(registry.read_bytes()).hexdigest()

    clean = main(["--registry", str(registry), "--catalog", str(saved / "models.json"), "--endpoints-dir", str(saved)])
    endpoints["us/beta"]["data"]["endpoints"][0]["max_completion_tokens"] = 32000
    (saved / "endpoints-us__beta.json").write_text(json.dumps(endpoints["us/beta"]), encoding="utf-8")
    drifted = main(["--registry", str(registry), "--catalog", str(saved / "models.json"), "--endpoints-dir", str(saved)])

    assert (clean, drifted) == (0, 1)
    assert "us/beta: CAPACITY" in capsys.readouterr().out
    assert hashlib.sha256(registry.read_bytes()).hexdigest() == before


def test_an_unreadable_catalog_exits_2(registry: Path, tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    assert main(["--registry", str(registry), "--catalog", str(missing), "--endpoints-dir", str(tmp_path)]) == 2
