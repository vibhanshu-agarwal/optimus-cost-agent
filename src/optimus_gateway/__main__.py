from __future__ import annotations

import argparse
import os
import sys

import keyring as _keyring_module

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
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
    args = parser.parse_args(argv)

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
        )
    except LaunchManifestError as exc:
        print(f"optimus-local-gateway: manifest validation failed ({exc.code}); refusing to start.", file=sys.stderr)
        return 2

    server = serve_gateway(config=config)
    host, port = server.server_address
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
