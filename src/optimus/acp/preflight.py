from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from optimus.acp.local_infra import DEFAULT_REDIS_URL
from optimus.agent.state_store import validate_redis_url
from optimus.redis.runtime import RedisRuntime, RedisRuntimeShutdownIncomplete
from optimus_model_policy.binding import RouteBinding

DEFAULT_REDIS_URL_HINT = DEFAULT_REDIS_URL
_LOCAL_STARTUP_RUNBOOK = (
    "docs/runbooks/local-live-dependencies.md"
)
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
    cli_model: str | None = None,
) -> str:
    """Validate operator environment. Returns the validated Redis URL on success. ``cli_model`` is the launch's
    own ``--model``, which the strict auth probe resolves exactly as the launch does."""
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
            _require_gateway_auth(env, cli_model=cli_model)
        if workspace_root is not None:
            _require_workspace_root(workspace_root)
    except BaseException as exc:
        # The probe runtime is an OWNED lifetime: it is closed on every path. A close
        # failure here must never replace the preflight failure the operator needs to
        # see, so it travels as a note on that failure instead.
        _close_probe_runtime_after_failure(runtime, exc)
        raise
    _close_probe_runtime(runtime)
    return redis_url


def _close_probe_runtime(runtime: RedisRuntime) -> None:
    """Close the probe runtime on the success path; an unfinished teardown fails preflight.

    Seam 2, checkpoint B: ``close`` observes the runtime's single teardown under its
    shutdown budget. A runtime that cannot reach terminal disposition is a Redis
    problem the operator should know about before serving starts, so it is reported as
    a preflight failure rather than leaked as a live owner thread.
    """
    try:
        runtime.close()
    except RedisRuntimeShutdownIncomplete as exc:
        raise PreflightFailure(
            exit_code=2,
            user_message=f"The Redis preflight probe did not shut down within its budget. ({exc})",
        ) from exc


def _close_probe_runtime_after_failure(runtime: RedisRuntime, failure: BaseException) -> None:
    """Best-effort close behind a failure that is already propagating; never mask it."""
    try:
        runtime.close()
    except Exception as exc:  # noqa: BLE001 - attached, never substituted for the real failure
        _attach_note(failure, f"redis preflight probe runtime close also failed: {exc!r}")


def _attach_note(failure: BaseException, note: str) -> None:
    """``add_note`` for any exception, including a frozen-dataclass one.

    ``PreflightFailure`` is a frozen dataclass, whose ``__setattr__`` refuses the
    ``__notes__`` attribute ``add_note`` creates on first use. The note is attached
    through the base-class setattr instead, exactly where ``add_note`` would put it.
    """
    try:
        failure.add_note(note)
    except AttributeError:
        notes = list(getattr(failure, "__notes__", None) or ())
        notes.append(note)
        object.__setattr__(failure, "__notes__", notes)


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
                f"(see {_LOCAL_STARTUP_RUNBOOK} for named Redis dependency startup)."
            ),
        )
    try:
        return validate_redis_url(redis_url)
    except ValueError as exc:
        raise PreflightFailure(exit_code=2, user_message=str(exc)) from exc


def _require_redis_timeseries(runtime: RedisRuntime) -> None:
    """
    Validates that the provided Redis runtime includes TimeSeries support. If the
    required support is not available, a `PreflightFailure` exception is raised
    with a descriptive message. TimeSeries support is essential for running
    specific command sets required by the application.

    :param runtime: RedisRuntime instance representing the Redis runtime to be
        validated.
    :raises PreflightFailure: Raised if the Redis runtime lacks TimeSeries
        support.
    :rtype: None
    """
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


def _probe_route_binding(model_id: str, shared_secret: str) -> RouteBinding | None:
    """The strict auth probe's route binding under the enforced shipped registry (closure plan v3), so the enforced
    Gateway does not refuse it as unbound (BINDING_REQUIRED). It remains a real, possibly billed request."""
    from optimus.acp.context_attachment import ordinary_route_policy
    from optimus_model_policy.binding import trusted_snapshot

    snapshot = trusted_snapshot()
    if snapshot is None:
        return None
    policy = ordinary_route_policy(snapshot=snapshot, model_id=model_id, shared_secret=shared_secret)
    bound = policy.capture(session_id="preflight", turn_seq=0, deliver_notice=lambda _text: False).bind(stage="auth-probe", input_text="preflight")
    if bound is None:
        raise PreflightFailure(
            exit_code=2, user_message=f"the strict auth probe cannot use {model_id}: it needs a disclosure notice the probe cannot show"
        )
    return bound.binding


def _require_gateway_auth(environ: Mapping[str, str], *, cli_model: str | None = None) -> None:
    """
    Validates the authentication credentials for the Optimus gateway using preflight checks. This function attempts to
    initiate a request to the gateway with provided environment configurations to ensure that the credentials are valid.
    If the authentication fails or the gateway is unreachable, appropriate exceptions are raised to indicate the issue.

    :param environ: A dictionary-like object that contains environment variables required for gateway configuration.
                    These environment variables include but are not limited to keys such as ``OPTIMUS_GATEWAY_URL``.
    :type environ: Mapping[str, str]

    :return: This function does not return a value. It performs a validation check on the gateway authentication credentials.
    :rtype: None

    :raises PreflightFailure: If the gateway rejects the authentication probe (e.g., due to invalid API key) or if the
                               gateway is unreachable. The exception includes specific exit codes and user-friendly
                               messages to indicate the nature of the failure.
    """
    from optimus.agent.defaults import AgentModelError, resolve_agent_model
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient
    from optimus.gateway.errors import GatewayHttpError
    from optimus.gateway.route_binding import RouteIdentityError

    settings = OptimusGatewaySettings.from_env(environ)
    client = GatewayClient(settings=settings)
    gateway_url = environ.get("OPTIMUS_GATEWAY_URL", "").strip()
    try:
        # The probe uses the launch's own model (its --model, else the environment, else the default), and an
        # unusable model is a typed refusal here, before any request (Fable review 1, F1).
        probe_model = resolve_agent_model(environ, cli_model=cli_model)
        route_binding = _probe_route_binding(probe_model, settings.optimus_api_key.get_secret_value())
    except (AgentModelError, RouteIdentityError) as exc:
        raise PreflightFailure(exit_code=2, user_message=f"AGENT_MODEL_INVALID: {exc}") from exc
    try:
        client.create_response(
            model=probe_model,
            input_text="preflight",
            metadata={"purpose": "preflight_auth_probe"},
            route_binding=route_binding,
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
    """
    Collects and performs a series of preflight checks to validate the environment and configuration
    necessary for application execution. The checks include validation of gateway credentials,
    Redis URL and connectivity, Redis time series support, workspace writability, and optional
    gateway authentication when in strict mode.

    The function consolidates the results of all preflight checks into a list of `PreflightCheckResult`
    objects, detailing the name of the check, its pass status, and any additional information.

    :param environ: Optional mapping of environment variables to override the default OS environment.
    :type environ: Mapping[str, str] | None
    :param workspace_root: Path to the application's workspace root. If provided, its directory
        existence and writability are validated.
    :type workspace_root: Path | None
    :param strict: If True, additional strict validation such as gateway authentication probes
        are performed.
    :type strict: bool
    :param require_timeseries: If True, checks are performed to ensure Redis TimeSeries support is available.
    :type require_timeseries: bool
    :return: A list of `PreflightCheckResult` objects, each representing the result of a specific preflight check.
    :rtype: list[PreflightCheckResult]
    """
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
            # Seam 2, checkpoint B: the probe runtime is closed on every path, and a
            # teardown that does not finish is a reported check, not a silent leak.
            try:
                runtime.close()
            except RedisRuntimeShutdownIncomplete as exc:
                results.append(
                    PreflightCheckResult(
                        name="redis probe shutdown",
                        passed=False,
                        detail=f"The Redis preflight probe did not shut down within its budget. ({exc})",
                    )
                )

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
    """Exercise TS.ADD on the runtime's OWN owner loop.

    Seam 2, checkpoint B: the probe used to run this coroutine on the process-global
    bridge loop while the client belonged to the runtime's loop -- two owners on one
    client. It now submits an operation factory to the runtime, like every other
    consumer.
    """

    async def _probe() -> None:
        await runtime.client.execute_command("TS.ADD", _REDIS_TS_PROBE_KEY, "*", 1)
        await runtime.client.delete(_REDIS_TS_PROBE_KEY)

    runtime.run_sync(_probe)
