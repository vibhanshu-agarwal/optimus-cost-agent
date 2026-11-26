"""Unit-tier stand-in for the settle script of ``RedisTelemetryAdapter.record_settled_usage``.

Redis runs the script whole or not at all; this applies it in one step to a fake's command log and
hashes. The real script runs against Redis in the ``requires_redis`` tier.
"""

from optimus.telemetry.redis_adapter import _SETTLE_SCRIPT


def run_settle_script(commands: list[tuple[object, ...]], hashes: dict[str, dict[str, str]], args: tuple[object, ...]) -> int:
    """Apply one ``EVAL`` of the settle script; ``args`` is the full command, ``"EVAL"`` first."""
    script, numkeys, claims, cost_key, units_key, field, fingerprint, cost, units = args[1:]
    assert script == _SETTLE_SCRIPT and numkeys == 3, args
    bucket = hashes.setdefault(str(claims), {})
    if field in bucket:
        return 0
    commands.append(("TS.ADD", cost_key, "*", cost))
    commands.append(("TS.ADD", units_key, "*", units))
    bucket[str(field)] = str(fingerprint)
    return 1
