"""Report drift between the model registry and OpenRouter's public catalog (ADR-004 decision 6).

Free and read-only: it reads the public ``/api/v1/models`` catalog and each registry model's
``/api/v1/models/<id>/endpoints`` listing, compares prices, windows, max outputs, quantizations,
endpoint presence and expiration dates with the registry, and prints the discrepancies. It never
edits the registry; changes go through a reviewed PR. Raw responses can be saved as a dated snapshot.

Usage:
    python tools/check_model_registry_drift.py --fetch --snapshot-dir DIR
    python tools/check_model_registry_drift.py --catalog FILE --endpoints-dir DIR

Exit status: 0 no drift, 1 drift reported, 2 the catalog could not be read or the snapshot saved.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Any

from optimus_model_policy import RegistrySnapshot, load_registry

CATALOG_URL = "https://openrouter.ai/api/v1/models"
ENDPOINTS_URL = "https://openrouter.ai/api/v1/models/{model_id}/endpoints"
_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class Drift:
    model_id: str
    code: str
    detail: str


def _per_million(per_token: Any) -> Decimal | None:
    try:
        return (Decimal(str(per_token)) * _PER_MILLION).normalize()
    except (InvalidOperation, ValueError):
        return None


def _endpoint_matches(listed: Mapping[str, Any], provider: str) -> bool:
    wanted = provider.casefold()
    tag = str(listed.get("tag") or "").casefold()
    name = str(listed.get("provider_name") or "").casefold()
    return tag == wanted or tag.split("/")[0] == wanted or name == wanted


def compare(snapshot: RegistrySnapshot, catalog: Mapping[str, Any], endpoints_by_model: Mapping[str, Any]) -> list[Drift]:
    """Every discrepancy between the registry and the catalog, in registry order."""
    listed = {str(item.get("id")): item for item in catalog.get("data", []) if isinstance(item, Mapping)}
    drifts: list[Drift] = []
    for model_id, entry in snapshot.policy.models.items():
        item = listed.get(model_id)
        if item is None:
            drifts.append(Drift(model_id, "MODEL_NOT_LISTED", "not in the public catalog"))
            continue
        if item.get("expiration_date"):
            drifts.append(Drift(model_id, "EXPIRATION_DATE", f"catalog expiration_date {item['expiration_date']}"))
        endpoints = (endpoints_by_model.get(model_id) or {}).get("data", {}).get("endpoints", [])
        for registry_endpoint in entry.route.endpoints:
            matches = [e for e in endpoints if isinstance(e, Mapping) and _endpoint_matches(e, registry_endpoint.provider)]
            if not matches:
                drifts.append(Drift(model_id, "ENDPOINT_NOT_FOUND", f"no listed endpoint for provider {registry_endpoint.provider!r}"))
                continue
            wanted = (registry_endpoint.quantization or "").casefold()
            same_quantization = [e for e in matches if wanted and str(e.get("quantization") or "").casefold() == wanted]
            if not same_quantization and len(matches) > 1:
                # Several listed endpoints and nothing to tell them apart: comparing one would guess.
                drifts.append(
                    Drift(model_id, "ENDPOINT_AMBIGUOUS", f"{len(matches)} listed endpoints for {registry_endpoint.provider!r}; record the quantization")
                )
                continue
            listed_endpoint = (same_quantization or matches)[0]
            pricing = listed_endpoint.get("pricing") or {}
            for field, registry_value in (
                ("prompt", entry.prices.input_usd_per_million),
                ("completion", entry.prices.output_usd_per_million),
            ):
                listed_value = _per_million(pricing.get(field))
                if listed_value is None or listed_value != registry_value.normalize():
                    drifts.append(Drift(model_id, "PRICE", f"{registry_endpoint.provider} {field}: registry {registry_value}, listed {listed_value}"))
            for field, registry_value in (
                ("context_length", registry_endpoint.context_window_tokens),
                ("max_completion_tokens", registry_endpoint.max_output_tokens),
            ):
                listed_value = listed_endpoint.get(field)
                if listed_value != registry_value:
                    drifts.append(Drift(model_id, "CAPACITY", f"{registry_endpoint.provider} {field}: registry {registry_value}, listed {listed_value}"))
            listed_quant = listed_endpoint.get("quantization")
            if (listed_quant or None) != registry_endpoint.quantization and listed_quant not in (None, "unknown"):
                drifts.append(Drift(model_id, "QUANTIZATION", f"{registry_endpoint.provider}: registry {registry_endpoint.quantization}, listed {listed_quant}"))
    return drifts


def _fetch_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "optimus-registry-drift/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https public catalog URLs
        return json.load(response)


def fetch(snapshot: RegistrySnapshot, *, fetcher: Callable[[str], Any]) -> tuple[Any, dict[str, Any]]:
    catalog = fetcher(CATALOG_URL)
    endpoints: dict[str, Any] = {}
    for model_id in snapshot.policy.models:
        endpoints[model_id] = fetcher(ENDPOINTS_URL.format(model_id=urllib.parse.quote(model_id, safe="/")))
    return catalog, endpoints


def _snapshot_name(model_id: str) -> str:
    """A file name valid on every platform: ``/`` becomes ``__``, anything else unsafe ``_``."""
    safe = model_id.replace("/", "__")
    return "endpoints-" + "".join(c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in safe) + ".json"


def _save_snapshot(directory: Path, catalog: Any, endpoints: Mapping[str, Any]) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"openrouter-{stamp}"
    target.mkdir(parents=True, exist_ok=False)
    (target / "models.json").write_text(json.dumps(catalog, indent=1, sort_keys=True), encoding="utf-8")
    for model_id, payload in endpoints.items():
        (target / _snapshot_name(model_id)).write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    return target


def _load_saved(catalog_file: Path, endpoints_dir: Path, snapshot: RegistrySnapshot) -> tuple[Any, dict[str, Any]]:
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    endpoints: dict[str, Any] = {}
    for model_id in snapshot.policy.models:
        path = endpoints_dir / _snapshot_name(model_id)
        if path.is_file():
            endpoints[model_id] = json.loads(path.read_text(encoding="utf-8"))
    return catalog, endpoints


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, help="defaults file (default: the packaged defaults.yaml)")
    parser.add_argument("--override", type=Path, help="optional operator override file")
    parser.add_argument("--fetch", action="store_true", help="read the live public catalog and endpoints")
    parser.add_argument("--snapshot-dir", type=Path, help="with --fetch, save the raw responses here")
    parser.add_argument("--catalog", type=Path, help="a saved models.json instead of fetching")
    parser.add_argument("--endpoints-dir", type=Path, help="the saved endpoints-*.json directory")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    if args.registry is None:
        with resources.as_file(resources.files("optimus_model_policy").joinpath("defaults.yaml")) as packaged:
            snapshot = load_registry(packaged, args.override)
    else:
        snapshot = load_registry(args.registry, args.override)

    try:
        if args.fetch:
            catalog, endpoints = fetch(snapshot, fetcher=lambda url: _fetch_json(url, args.timeout))
        elif args.catalog is not None and args.endpoints_dir is not None:
            catalog, endpoints = _load_saved(args.catalog, args.endpoints_dir, snapshot)
        else:
            parser.error("use --fetch, or --catalog with --endpoints-dir")
    except (OSError, ValueError) as exc:
        print(f"catalog unavailable: {type(exc).__name__}", file=sys.stderr)
        return 2

    if args.fetch and args.snapshot_dir is not None:
        try:
            print(f"saved snapshot: {_save_snapshot(args.snapshot_dir, catalog, endpoints)}")
        except OSError as exc:
            print(f"snapshot not saved: {type(exc).__name__}", file=sys.stderr)
            return 2

    drifts = compare(snapshot, catalog, endpoints)
    print(f"registry {snapshot.policy.policy_version} (effective {snapshot.effective_hash[:12]}): {len(drifts)} discrepancies")
    for drift in drifts:
        print(f"  {drift.model_id}: {drift.code}: {drift.detail}")
    return 1 if drifts else 0


if __name__ == "__main__":
    raise SystemExit(main())
