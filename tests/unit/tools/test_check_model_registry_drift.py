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


def test_a_fetched_snapshot_saves_only_the_public_responses(
    registry: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """--fetch sends no credential and saves exactly the public catalog and endpoint responses."""
    import tools.check_model_registry_drift as drift

    catalog, endpoints = _matching_catalog()
    by_url = {CATALOG_URL: catalog} | {
        f"https://openrouter.ai/api/v1/models/{model_id}/endpoints": payload for model_id, payload in endpoints.items()
    }
    headers_seen: list[dict[str, str]] = []

    class _Response:
        def __init__(self, body: object) -> None:
            self._body = json.dumps(body).encode()

        def read(self, *args: object) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request, timeout: float = 0):
        headers_seen.append({name.lower(): value for name, value in request.header_items()})
        return _Response(by_url[request.full_url])

    monkeypatch.setattr(drift.urllib.request, "urlopen", fake_urlopen)
    assert main(["--registry", str(registry), "--fetch", "--snapshot-dir", str(tmp_path / "snaps")]) == 0

    assert all("authorization" not in headers for headers in headers_seen)
    [saved] = list((tmp_path / "snaps").iterdir())
    assert json.loads((saved / "models.json").read_text(encoding="utf-8")) == catalog
    for model_id, payload in endpoints.items():
        assert json.loads((saved / f"endpoints-{model_id.replace('/', '__')}.json").read_text(encoding="utf-8")) == payload
    assert sorted(path.name for path in saved.iterdir()) == ["endpoints-cn__alpha.json", "endpoints-us__beta.json", "models.json"]
    assert "saved snapshot:" in capsys.readouterr().out


def test_a_slug_that_reaches_several_endpoints_is_reported_and_compared_on_its_quantization(registry: Path) -> None:
    """The registry's base slug "beta" would route to beta/bf16 as well as beta/fp8: it is not exact.
    Its facts are still compared on the endpoint whose quantization matches the record."""
    catalog, endpoints = _matching_catalog()
    cheaper_bf16 = _endpoint("beta/bf16", "0.0000005", "0.000002", context=100000, max_out=8000, quant="bf16")
    endpoints["us/beta"]["data"]["endpoints"].insert(0, cheaper_bf16)
    drifts = compare(load_registry(registry, None), catalog, endpoints)
    assert [(d.model_id, d.code) for d in drifts] == [("us/beta", "SLUG_NOT_EXACT")]
    assert "beta/bf16" in drifts[0].detail and "beta/fp8" in drifts[0].detail


def test_several_endpoints_with_nothing_to_tell_them_apart_are_not_compared(registry: Path) -> None:
    """With no recorded quantization to pick one, comparing any listed endpoint would be a guess: a
    dearer variant listed first must not produce a PRICE drift against the record."""
    catalog, endpoints = _matching_catalog()
    dearer = _endpoint("alpha/fast", "0.00000030", "0.0000012", context=1048576, max_out=65536, quant="fp8")
    endpoints["cn/alpha"]["data"]["endpoints"].insert(0, dearer)
    codes = [(d.model_id, d.code) for d in compare(load_registry(registry, None), catalog, endpoints)]
    assert codes == [("cn/alpha", "SLUG_NOT_EXACT")]


def test_an_exact_variant_slug_matches_only_itself_and_what_lies_beneath_it(tmp_path: Path) -> None:
    """An exact slug is compared with its own listing; a deeper listed variant would make it inexact."""
    path = tmp_path / "exact.yaml"
    path.write_text(_REGISTRY.replace("provider: beta,", "provider: beta/fp8,"), encoding="utf-8")
    snapshot = load_registry(path, None)
    catalog, endpoints = _matching_catalog()
    endpoints["us/beta"]["data"]["endpoints"].insert(0, _endpoint("beta/bf16", "0.0000005", "0.000002", context=1, max_out=1, quant="bf16"))
    assert compare(snapshot, catalog, endpoints) == [], "beta/bf16 is a sibling, not beneath beta/fp8"
    endpoints["us/beta"]["data"]["endpoints"].append(_endpoint("beta/fp8/eu", "0.000001", "0.000005", context=200000, max_out=64000, quant="fp8"))
    assert [d.code for d in compare(snapshot, catalog, endpoints)] == ["SLUG_NOT_EXACT"]


def test_snapshot_names_are_valid_on_every_platform() -> None:
    from tools.check_model_registry_drift import _snapshot_name

    assert _snapshot_name("cn/alpha") == "endpoints-cn__alpha.json"
    assert _snapshot_name("vendor/model:free") == "endpoints-vendor__model_free.json"
    assert _snapshot_name('a<b>c"d|e?f*g') == "endpoints-a_b_c_d_e_f_g.json"


def test_a_snapshot_that_cannot_be_saved_is_reported_as_such(
    registry: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import tools.check_model_registry_drift as drift

    catalog, endpoints = _matching_catalog()
    monkeypatch.setattr(drift, "fetch", lambda snapshot, *, fetcher: (catalog, endpoints))

    def refuse(*args: object) -> Path:
        raise FileExistsError("same-second rerun")

    monkeypatch.setattr(drift, "_save_snapshot", refuse)
    assert main(["--registry", str(registry), "--fetch", "--snapshot-dir", str(tmp_path)]) == 2
    assert "snapshot not saved: FileExistsError" in capsys.readouterr().err


def test_a_recorded_quantization_the_listing_does_not_confirm_is_drift(registry: Path) -> None:
    """The recorded quantization becomes the request's filter, so an endpoint listed as "unknown" (or
    with none) would be filtered out and every request refused."""
    catalog, endpoints = _matching_catalog()
    for listed in ("unknown", None):
        endpoints["us/beta"]["data"]["endpoints"][0]["quantization"] = listed
        codes = [(d.model_id, d.code) for d in compare(load_registry(registry, None), catalog, endpoints)]
        assert codes == [("us/beta", "QUANTIZATION")], listed


def test_an_endpoint_that_cannot_take_the_reasoning_level_is_drift(tmp_path: Path) -> None:
    path = tmp_path / "reasoning.yaml"
    path.write_text(_REGISTRY.replace("default_reasoning: null", "default_reasoning: high"), encoding="utf-8")
    snapshot = load_registry(path, None)
    catalog, endpoints = _matching_catalog()
    endpoints["us/beta"]["data"]["endpoints"][0]["supported_parameters"] = ["max_tokens", "reasoning"]
    codes = [(d.model_id, d.code) for d in compare(snapshot, catalog, endpoints)]
    assert codes == [("cn/alpha", "REASONING_UNSUPPORTED")]
