from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

import keyring as _keyring_module

from optimus_gateway import usage_capture
from optimus_gateway.model_policy import GatewayModelPolicy
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_model_policy import RegistryError, RegistrySnapshot
from optimus_model_policy.binding import (
    BindingError,
    approval_literal,
    auto_snapshot,
    operator_override,
    trusted_snapshot,
    use_operator_override,
)
from optimus_model_policy.stage_c import StageCGuard, StageCLedgerError, compose_stage_c_envelope, require_stage_c_profile
from optimus_model_policy.test_profiles import TEST_PROFILE_NAMES, compose_test_profile_snapshot
from optimus_security.accounting_config import AccountingConfigError, accounting_literal
from optimus_security.accounting_config import read as read_accounting_config
from optimus_security.launch_manifest import (
    LaunchManifestError,
    read_manifest_hmac_key,
    verify_gateway_child_manifest,
)

# Plan 9.96, Task 5 Step 4: these names must NEVER be read from the standalone
# entrypoint's inherited environment. bind_host/bind_port are code-derived
# CLI arguments from the authorized parent; a value present under either of
# these names in os.environ indicates an attempt to reopen the closed bind
# seam and must fail closed before any other startup work.
_REJECTED_INHERITED_NAMES = ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT")


def _reject_inherited_bind_env(environ: dict[str, str]) -> str | None:
    """Return an error message if a rejected inherited bind name is present."""
    present = [name for name in _REJECTED_INHERITED_NAMES if environ.get(name, "").strip()]
    if present:
        return (
            "optimus-local-gateway: refusing inherited bind settings "
            f"({', '.join(sorted(present))}); bind host/port must be supplied "
            "via --bind-host/--port from the authorized parent, never from "
            "the environment."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Optimus Gateway stub on loopback.")
    parser.add_argument(
        "--bind-host",
        required=True,
        help="Loopback bind host, code-derived by the authorized parent (no inherited default).",
    )
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Bind port, code-derived by the authorized parent (no inherited default).",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help=(
            "Serialized, HMAC-signed GatewayChildManifest from the authorized parent. "
            "Direct unmanifested startup fails closed."
        ),
    )
    parser.add_argument(
        "--plan12-test-profile",
        choices=TEST_PROFILE_NAMES,
        default=None,
        help=(
            "Reviewed Plan 12.2 test profile, composed here independently; the signed manifest must bind "
            "its exact effective hash. Grants nothing by itself."
        ),
    )
    parser.add_argument(
        "--plan12-stage-c-ledger",
        default=None,
        help=(
            "The resolved ledger of the shared Plan 12.2 Stage C test envelope, initialized by the release "
            "ceremony. The envelope is composed here; the signed manifest must bind it. Never created here."
        ),
    )
    parser.add_argument(
        "--registry-override",
        default=None,
        help=(
            "The operator's registry override in the trusted config root (ADR-025), composed here over the shipped "
            "defaults; the signed manifest must bind the resulting effective hash. Never with a test profile."
        ),
    )
    parser.add_argument(
        "--auto-composition",
        action="store_true",
        help=(
            "Compose the Auto registry (Plan 12.4 Design 1): the shipped defaults, the shipped Auto overlay and any "
            "registry override, here independently; the signed manifest must bind its exact effective hash."
        ),
    )
    parser.add_argument(
        "--accounting-root",
        default=None,
        help=(
            "The accounting root under the trusted config root (Plan 12.8, ADR-032): this Gateway's capture stream and any "
            "approved accounting configuration. The literal is composed here; the signed manifest must bind it."
        ),
    )
    args = parser.parse_args(argv)
    if args.plan12_stage_c_ledger is not None and args.plan12_test_profile is None:
        parser.error("--plan12-stage-c-ledger needs --plan12-test-profile")
    if args.registry_override is not None and args.plan12_test_profile is not None:
        parser.error("--registry-override cannot be combined with --plan12-test-profile")
    if args.auto_composition and args.plan12_test_profile is not None:
        parser.error("--auto-composition cannot be combined with --plan12-test-profile")

    environ = dict(os.environ)

    rejection_message = _reject_inherited_bind_env(environ)
    if rejection_message is not None:
        print(rejection_message, file=sys.stderr)
        return 2

    # Construct the config FIRST (pure: no socket/network/side effects until
    # serve_gateway is called), then verify the manifest against the config's
    # ACTUAL resolved provider/base_url/credentials/bind — not just the raw
    # environment reads. This ordering means the manifest check validates
    # exactly what will be used to serve traffic, closing the window where a
    # validly-signed manifest for one endpoint could be paired with a
    # different provider/base_url/credential and still pass.
    try:
        config = GatewayServiceConfig.from_env(environ, bind_host=args.bind_host, bind_port=args.port)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Plan 12.2 Task 5: compose the trusted model registry this install enforces (None while
    # enforcement is inactive); the manifest must bind exactly its approval literal. A named test
    # profile is composed here from its own reviewed source, never taken from the parent (release
    # supplement V2); the HMAC-signed manifest must still name its hash.
    try:
        if args.registry_override is not None:
            override = Path(args.registry_override)
            # Only the override file itself, a regular file in the root it names, is composed (ADR-025).
            if operator_override(override.parent) != override:
                raise BindingError("OPERATOR_OVERRIDE_UNSAFE", "not the operator registry override")
            use_operator_override(override)
        registry: RegistrySnapshot | None
        if args.plan12_test_profile is not None:
            registry = compose_test_profile_snapshot(args.plan12_test_profile)
        else:
            registry = auto_snapshot() if args.auto_composition else trusted_snapshot()
    except (BindingError, RegistryError) as exc:
        print(f"optimus-local-gateway: model registry is not trustworthy ({exc.code}); refusing to start.", file=sys.stderr)
        return 2

    # Plan 12.2 Task 13 (Stage C): compose the shared test envelope from the actual ledger argument and
    # this Gateway's own source; the signed manifest must bind exactly its literal.
    envelope = None
    if args.plan12_stage_c_ledger is not None:
        try:
            envelope = compose_stage_c_envelope(ledger=Path(args.plan12_stage_c_ledger))
            # A missing profile or registry pins nothing, so it is refused like a migrated one.
            require_stage_c_profile(envelope, args.plan12_test_profile or "", "" if registry is None else registry.effective_hash)
        except BindingError as exc:
            print(f"optimus-local-gateway: Stage C envelope is not usable ({exc.code}); refusing to start.", file=sys.stderr)
            return 2

    # Plan 12.8: compose the accounting literal from the actual root and the configuration bytes found there; the signed
    # manifest must bind exactly it, so an unapproved or swapped configuration refuses to start.
    accounting_dir = None if args.accounting_root is None else Path(args.accounting_root)
    accounting_bound = accounting_config = accounting_refusal = None
    if accounting_dir is not None:
        try:
            captured_literal, accounting_config, accounting_refusal = read_accounting_config(accounting_dir)
            accounting_bound = accounting_literal(accounting_dir, captured_literal)
        except AccountingConfigError as exc:
            print(f"optimus-local-gateway: accounting configuration is not usable ({exc.code}); refusing to start.", file=sys.stderr)
            return 2

    try:
        hmac_key = read_manifest_hmac_key(_keyring_module)
        verify_gateway_child_manifest(
            args.manifest,
            hmac_key=hmac_key,
            provider=config.provider,
            base_url=config.base_url,
            provider_api_key=config.provider_api_key,
            shared_secret=config.shared_secret,
            bind_host=config.bind_host,
            bind_port=config.bind_port,
            model_registry=None if registry is None else approval_literal(registry),
            stage_c_envelope=None if envelope is None else envelope.literal,
            accounting=accounting_bound,
        )
    except LaunchManifestError as exc:
        print(f"optimus-local-gateway: manifest validation failed ({exc.code}); refusing to start.", file=sys.stderr)
        return 2

    if registry is not None:
        config = replace(
            config,
            model_policy=GatewayModelPolicy.for_launch(
                snapshot=registry, approved_hash=registry.effective_hash, shared_secret=config.shared_secret
            ),
        )

    guard = None
    if envelope is not None:
        try:
            guard = StageCGuard.open(Path(envelope.ledger), envelope)
        except (StageCLedgerError, OSError) as exc:
            code = exc.code if isinstance(exc, StageCLedgerError) else "STAGE_C_LEDGER_UNREADABLE"
            print(f"optimus-local-gateway: Stage C ledger cannot be opened ({code}); refusing to start.", file=sys.stderr)
            return 2
        config = replace(config, stage_c_guard=guard)

    accounting = None
    if accounting_dir is not None:
        accounting = usage_capture.start_accounting(
            accounting_dir, accounting_config, refusal=accounting_refusal, keyring_backend=_keyring_module,
            log=lambda line: print(line, file=sys.stderr),
        )  # the configuration verified above, never a second read
        config = replace(config, usage_store=accounting.store)

    try:
        server = serve_gateway(config=config)
        host = str(server.server_address[0])
        port = server.server_address[1]
        print(
            f"optimus local gateway listening on http://{host}:{port} "
            f"(provider={config.provider})",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("shutting down", flush=True)
            server.shutdown()
    finally:
        if guard is not None:
            guard.close()
        if accounting is not None:
            accounting.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
