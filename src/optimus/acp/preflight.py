from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from optimus.agent.state_store import validate_redis_url
from optimus.redis.runtime import RedisRuntime

DEFAULT_REDIS_URL_HINT = "redis://127.0.0.1:6379/0"
_REDIS_TS_PROBE_KEY = "optimus:preflight:timeseries-probe"


@dataclass(frozen=True)
class PreflightFailure(Exception):
    exit_code: int
    user_message: str

    def __str__(self) -> str:
        return self.user_message


def run_preflight(
    environ: Mapping[str, str] | None = None,
    *,
    workspace_root: Path | None = None,
    strict: bool = False,
    require_timeseries: bool = False,
) -> str:
    """Validate operator environment. Returns the validated Redis URL on success."""
    env = os.environ if environ is None else environ
    _require_gateway_credentials(env)
    redis_url = _require_redis_url(env)
    runtime = RedisRuntime.from_url(redis_url)
    try:
        try:
            runtime.ping()
        except ConnectionError as exc:
            raise PreflightFailure(
                exit_code=2,
                user_message=f"Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL. ({exc})",
            ) from exc
        if require_timeseries:
            _require_redis_timeseries(runtime)
        if strict:
            _require_gateway_auth(env)
        if workspace_root is not None:
            _require_workspace_root(workspace_root)
        return redis_url
    finally:
        runtime.close()


def _require_gateway_credentials(environ: Mapping[str, str]) -> None:
    missing = tuple(name for name in ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY") if not environ.get(name, "").strip())
    if missing:
        raise PreflightFailure(
            exit_code=2,
            user_message=(
                "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent "
                "(or run `optimus-agent --setup` to configure the local gateway)."
            ),
        )


def _require_redis_url(environ: Mapping[str, str]) -> str:
    redis_url = environ.get("OPTIMUS_REDIS_URL", "").strip()
    if not redis_url:
        raise PreflightFailure(
            exit_code=2,
            user_message=(
                f"Set OPTIMUS_REDIS_URL={DEFAULT_REDIS_URL_HINT} "
                "(start one with: docker run --rm -d -p 6379:6379 redis:8)."
            ),
        )
    try:
        return validate_redis_url(redis_url)
    except ValueError as exc:
        raise PreflightFailure(exit_code=2, user_message=str(exc)) from exc


def _require_redis_timeseries(runtime: RedisRuntime) -> None:
    try:
        _probe_redis_timeseries(runtime)
    except Exception as exc:
        raise PreflightFailure(
            exit_code=2,
            user_message=(
                "Redis lacks TimeSeries support. Use redis:8 or redis/redis-stack-server "
                f"(LLD section 10 requires TS.* commands). ({exc})"
            ),
        ) from exc


def _require_gateway_auth(environ: Mapping[str, str]) -> None:
    from optimus.agent.defaults import resolve_agent_model
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient
    from optimus.gateway.errors import GatewayHttpError

    settings = OptimusGatewaySettings.from_env(environ)
    client = GatewayClient(settings=settings)
    probe_model = resolve_agent_model(environ)
    gateway_url = environ.get("OPTIMUS_GATEWAY_URL", "").strip()
    try:
        client.create_response(
            model=probe_model,
            input_text="preflight",
            metadata={"purpose": "preflight_auth_probe"},
        )
    except GatewayHttpError as exc:
        if exc.status_code in {401, 403}:
            raise PreflightFailure(exit_code=2, user_message="OPTIMUS_API_KEY was rejected by the gateway.") from exc
        if exc.status_code > 0:
            raise PreflightFailure(
                exit_code=2,
                user_message=f"Gateway at {gateway_url} rejected the auth probe request: {exc}",
            ) from exc
        raise PreflightFailure(
            exit_code=2,
            user_message=f"Gateway is not reachable at {gateway_url}. ({exc})",
        ) from exc
    except Exception as exc:
        message = str(exc)
        if "401" in message or "403" in message:
            raise PreflightFailure(exit_code=2, user_message="OPTIMUS_API_KEY was rejected by the gateway.") from exc
        raise PreflightFailure(
            exit_code=2,
            user_message=f"Gateway is not reachable at {gateway_url}. ({exc})",
        ) from exc


def _require_workspace_root(workspace_root: Path) -> None:
    resolved = workspace_root.resolve()
    if not resolved.is_dir():
        raise PreflightFailure(exit_code=2, user_message=f"Workspace root is not a directory: {resolved}")
    if not os.access(resolved, os.W_OK):
        raise PreflightFailure(exit_code=2, user_message=f"Workspace root is not writable: {resolved}")


@dataclass(frozen=True)
class PreflightCheckResult:
    name: str
    passed: bool
    detail: str


def collect_preflight_checks(
    environ: Mapping[str, str] | None = None,
    *,
    workspace_root: Path | None = None,
    strict: bool = False,
    require_timeseries: bool = False,
) -> list[PreflightCheckResult]:
    """Run pre-flight checks independently and return one result per check."""
    env = os.environ if environ is None else environ
    results: list[PreflightCheckResult] = []
    redis_url: str | None = None
    runtime: RedisRuntime | None = None

    missing_gateway = tuple(name for name in ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY") if not env.get(name, "").strip())
    if missing_gateway:
        results.append(
            PreflightCheckResult(
                name="gateway credentials",
                passed=False,
                detail=f"Missing: {', '.join(missing_gateway)}",
            )
        )
    else:
        results.append(PreflightCheckResult(name="gateway credentials", passed=True, detail="present"))

    raw_redis_url = env.get("OPTIMUS_REDIS_URL", "").strip()
    if not raw_redis_url:
        results.append(
            PreflightCheckResult(
                name="redis url",
                passed=False,
                detail=f"Set OPTIMUS_REDIS_URL={DEFAULT_REDIS_URL_HINT}",
            )
        )
    else:
        try:
            redis_url = validate_redis_url(raw_redis_url)
            results.append(PreflightCheckResult(name="redis url", passed=True, detail=redis_url))
        except ValueError as exc:
            results.append(PreflightCheckResult(name="redis url", passed=False, detail=str(exc)))

    if redis_url is not None:
        runtime = RedisRuntime.from_url(redis_url)
        try:
            try:
                runtime.ping()
                results.append(PreflightCheckResult(name="redis connectivity", passed=True, detail="PING ok"))
            except ConnectionError as exc:
                results.append(
                    PreflightCheckResult(
                        name="redis connectivity",
                        passed=False,
                        detail=f"Redis is not reachable ({exc})",
                    )
                )
            if require_timeseries and any(
                check.name == "redis connectivity" and check.passed for check in results
            ):
                try:
                    _probe_redis_timeseries(runtime)
                    results.append(PreflightCheckResult(name="redis timeseries", passed=True, detail="TS.ADD ok"))
                except Exception as exc:
                    results.append(
                        PreflightCheckResult(
                            name="redis timeseries",
                            passed=False,
                            detail=(
                                "Redis lacks TimeSeries support. Use redis:8 or redis/redis-stack-server "
                                f"(LLD section 10 requires TS.* commands). ({exc})"
                            ),
                        )
                    )
        finally:
            runtime.close()

    if strict and not missing_gateway:
        try:
            _require_gateway_auth(env)
            results.append(PreflightCheckResult(name="gateway auth", passed=True, detail="auth probe accepted"))
        except PreflightFailure as exc:
            results.append(PreflightCheckResult(name="gateway auth", passed=False, detail=exc.user_message))

    if workspace_root is not None:
        resolved = workspace_root.resolve()
        if not resolved.is_dir():
            results.append(
                PreflightCheckResult(
                    name="workspace writable",
                    passed=False,
                    detail=f"Workspace root is not a directory: {resolved}",
                )
            )
        elif not os.access(resolved, os.W_OK):
            results.append(
                PreflightCheckResult(
                    name="workspace writable",
                    passed=False,
                    detail=f"Workspace root is not writable: {resolved}",
                )
            )
        else:
            results.append(PreflightCheckResult(name="workspace writable", passed=True, detail=str(resolved)))

    return results


def format_preflight_table(checks: Sequence[PreflightCheckResult]) -> str:
    if not checks:
        return "Check  Status  Detail\n(no checks)"
    name_width = max(len(check.name) for check in checks)
    lines = [f"{'Check':<{name_width}}  Status  Detail", "-" * (name_width + 18)]
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"{check.name:<{name_width}}  {status:<6}  {check.detail}")
    return "\n".join(lines)


def first_preflight_failure(checks: Sequence[PreflightCheckResult]) -> PreflightCheckResult | None:
    for check in checks:
        if not check.passed:
            return check
    return None


def _probe_redis_timeseries(runtime: RedisRuntime) -> None:
    from optimus.redis.async_bridge import sync_await

    async def _probe() -> None:
        await runtime.client.execute_command("TS.ADD", _REDIS_TS_PROBE_KEY, "*", 1)
        await runtime.client.delete(_REDIS_TS_PROBE_KEY)

    sync_await(_probe())
