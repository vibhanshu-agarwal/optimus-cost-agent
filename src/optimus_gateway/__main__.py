from __future__ import annotations

import argparse
import sys

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Optimus Gateway stub on loopback.")
    parser.add_argument("--bind-host", default=None, help="Loopback bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default: 8765)")
    args = parser.parse_args(argv)

    try:
        config = GatewayServiceConfig.from_env()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.bind_host is not None:
        config = GatewayServiceConfig(
            bind_host=args.bind_host,
            bind_port=config.bind_port,
            shared_secret=config.shared_secret,
            anthropic_api_key=config.anthropic_api_key,
        )
    if args.port is not None:
        config = GatewayServiceConfig(
            bind_host=config.bind_host,
            bind_port=args.port,
            shared_secret=config.shared_secret,
            anthropic_api_key=config.anthropic_api_key,
        )

    server = serve_gateway(config=config)
    host, port = server.server_address
    print(f"optimus local gateway listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down", flush=True)
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
