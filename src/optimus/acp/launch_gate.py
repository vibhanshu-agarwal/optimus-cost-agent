"""Launch candidate resolution and authorization gate.

Plan 9.96, Task 4: The operator sees the complete display-safe effective
configuration and can author one exact durable or one-shot approval;
headless launch remains read-only.

Step 2: Two-phase config-root resolution. Before reading a custom
OPTIMUS_CONFIG_ROOT, validate file type, containment, symlink target,
owner/current-user accessibility, and platform permissions before parsing
.env.gateway. On POSIX, require current UID ownership and reject any
group/other permission bit (st_mode & 0o077). On Windows, inspect the DACL
through an injectable adapter.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from optimus.acp.launch_approvals import (
    ApprovalError,
    DiagnosticGrant,
    KeyringApprovalStore,
    compute_secret_fingerprint,
)
from optimus.acp.launch_policy import (
    DEFAULT_LIVE_MAX_COST_USD,
    DEFAULT_MAX_PLANNING_TURNS,
    LAUNCH_VARIABLE_POLICIES,
    LOCAL_GATEWAY_PREFIX,
    LaunchEnvironmentSnapshot,
    LaunchPolicyError,
    LaunchVariablePolicy,
    LaunchVariableTier,
    PropagationTarget,
    classify_variable,
)
from optimus.acp.local_gateway_secrets import (
    ProviderCredentialConfigurationError,
    ProviderCredentialResolution,
    resolve_provider_credentials,
    resolve_shared_secret,
)
from optimus.acp.operator_paths import OperatorPaths
from optimus.acp.trusted_paths import WorkspaceIdentity
from optimus_security.sanitization import mask_uri_userinfo, validate_secret_length

# Plan 9.96, Task 5 Batch 3 Step 5: the reviewed default each monotonic-tier
# name is compared against in _authorize_monotonic_grants(). Values <= this
# default are a tightening (or exact match) and require no approval; values
# above it require an exact matching grant in the approval record.
_MONOTONIC_DEFAULTS: Mapping[str, object] = {
    "OPTIMUS_LIVE_MAX_COST_USD": DEFAULT_LIVE_MAX_COST_USD,
    "OPTIMUS_MAX_PLANNING_TURNS": DEFAULT_MAX_PLANNING_TURNS,
}


@dataclass(frozen=True)
class LaunchDisplayRow:
    """One row of the operator-facing launch configuration display."""

    name: str
    tier: LaunchVariableTier
    source_class: str
    display_value: str
    decision: str


@dataclass(frozen=True)
class LaunchCandidate:
    """Complete resolved launch candidate before authorization.

    security_literals, secret_fingerprints, and monotonic_grants are the EXACT
    inputs used to compute security_snapshot_digest. Callers building an
    approval record (e.g. the CLI) MUST reuse these fields verbatim rather
    than reconstructing them from display_rows (which contain display-safe,
    possibly-masked values) — otherwise the resulting record's independently
    computed digest can never match this candidate's digest.
    """

    inherited: LaunchEnvironmentSnapshot
    workspace_identity: WorkspaceIdentity
    operator_paths: OperatorPaths
    security_snapshot_digest: str
    display_rows: tuple[LaunchDisplayRow, ...]
    gateway_environ: Mapping[str, str]
    agent_environ: Mapping[str, str]
    secret_inventory: tuple[str, ...]
    security_literals: Mapping[str, str]
    secret_fingerprints: Mapping[str, str]
    monotonic_grants: Mapping[str, str]
    model_observation: str | None
    provider_credentials: ProviderCredentialResolution | None
    shared_secret: str | None


@dataclass(frozen=True)
class AuthorizedLaunch:
    """Authorized launch with approval metadata."""

    candidate: LaunchCandidate
    approval_id: str
    approval_mode: str
    launch_session_id: str
    diagnostic_grant: DiagnosticGrant | None = None


class LaunchGateError(ValueError):
    """Raised when launch authorization fails."""

    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


# --- Config-root and .env.gateway permission validation ---


def validate_config_file_permissions(
    file_path: Path,
    *,
    platform_name: str | None = None,
    win32_security_adapter: object | None = None,
) -> None:
    """Validate that a config file has restrictive permissions.

    On POSIX: require current UID ownership and reject any group/other
    permission bit (st_mode & 0o077).
    On Windows: uses an injectable security adapter to check the DACL.

    Raises LaunchGateError if validation fails.
    """
    platform = platform_name or sys.platform

    if not file_path.exists():
        raise LaunchGateError(
            code="CONFIG_FILE_NOT_FOUND",
            detail="configuration file does not exist",
        )

    if not file_path.is_file():
        raise LaunchGateError(
            code="CONFIG_FILE_NOT_REGULAR",
            detail="configuration path is not a regular file",
        )

    # Resolve symlinks and validate the target exists.
    resolved = file_path.resolve()
    if not resolved.exists():
        raise LaunchGateError(
            code="CONFIG_SYMLINK_TARGET_MISSING",
            detail="symlink target does not exist",
        )

    if platform != "win32":
        _validate_posix_permissions(resolved)
    else:
        _validate_windows_permissions(resolved, adapter=win32_security_adapter)


def _validate_posix_permissions(file_path: Path) -> None:
    """POSIX: require current UID ownership and reject group/other bits."""
    try:
        stat = file_path.stat()
    except OSError as exc:
        raise LaunchGateError(
            code="CONFIG_FILE_STAT_FAILED",
            detail="cannot stat configuration file",
        ) from exc

    # Require current UID ownership.
    current_uid = os.getuid()
    if stat.st_uid != current_uid:
        raise LaunchGateError(
            code="CONFIG_FILE_WRONG_OWNER",
            detail="configuration file not owned by current user",
        )

    # Reject any group/other permission bit.
    if stat.st_mode & 0o077:
        raise LaunchGateError(
            code="CONFIG_FILE_PERMISSIONS_TOO_OPEN",
            detail="configuration file has group or other permissions",
        )


def _validate_windows_permissions(file_path: Path, *, adapter: object | None = None) -> None:
    """Windows: check DACL through injectable adapter.

    Allow current user, SYSTEM, and Administrators. Reject read/write allow
    ACEs for Everyone, Users, Authenticated Users, or unknown principals.
    """
    if adapter is not None:
        # Use the injected adapter for testing.
        check = getattr(adapter, "check_file_permissions", None)
        if check is not None:
            result = check(file_path)
            if result is not True:
                raise LaunchGateError(
                    code="CONFIG_FILE_PERMISSIONS_TOO_OPEN",
                    detail=str(result) if result else "Windows DACL check failed",
                )
        return

    # Real Windows DACL check: enumerate every ACE and reject unless every
    # allow-ACE's SID is the current user, SYSTEM, or Administrators.
    try:
        _check_windows_dacl_real(file_path)
    except (OSError, AttributeError, ImportError) as exc:
        raise LaunchGateError(
            code="CONFIG_FILE_PLATFORM_CHECK_FAILED",
            detail="platform cannot verify file permissions",
        ) from exc


# --- Real Windows DACL enumeration (ctypes) ---
# S-1-5-18 = SYSTEM, S-1-5-32-544 = Administrators (well-known, stable across
# all Windows installs and locales). The current user's SID is resolved from
# the process token at check time.
_SID_SYSTEM = "S-1-5-18"
_SID_ADMINISTRATORS = "S-1-5-32-544"
# OWNER RIGHTS: a well-known placeholder SID (not a distinct principal) that
# Windows attaches to nearly every newly created file via ACL inheritance.
# It represents "whoever currently owns this file" — since ownership itself
# is validated by the POSIX-equivalent containment checks earlier in the
# pipeline and this SID cannot resolve to Everyone/Users/Authenticated Users,
# it is safe to allow. Rejecting it would fail virtually every normal file.
_SID_OWNER_RIGHTS = "S-1-3-4"
_ACCESS_ALLOWED_ACE_TYPE = 0x00
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_ACL_SIZE_INFORMATION_CLASS = 2


def _check_windows_dacl_real(file_path: Path) -> None:
    """Enumerate the file's DACL and reject unauthorized allow-ACEs.

    Every module-level Win32 function used here has explicit argtypes/restype
    declarations — ctypes silently mismarshals pointer-sized arguments when
    left to infer types from bare Python ints, which is exactly the class of
    "looks right, fails on real Windows" bug found earlier in this plan
    (Task 2's SHGetKnownFolderPath GUID issue). Declaring types explicitly
    forces ctypes to marshal correctly rather than truncating/misreading.
    """
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    advapi32.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetFileSecurityW.restype = wintypes.BOOL

    advapi32.GetSecurityDescriptorDacl.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL

    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL

    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetAce.restype = wintypes.BOOL

    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    file_str = str(file_path)

    # 1. Get the security descriptor.
    needed = wintypes.DWORD(0)
    advapi32.GetFileSecurityW(file_str, _DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(needed))
    if needed.value == 0:
        raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot size security descriptor")

    sd_buffer = ctypes.create_string_buffer(needed.value)
    if not advapi32.GetFileSecurityW(
        file_str, _DACL_SECURITY_INFORMATION, sd_buffer, needed.value, ctypes.byref(needed)
    ):
        raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot read security descriptor")

    # 2. Extract the DACL pointer from the security descriptor.
    dacl_present = wintypes.BOOL()
    dacl_ptr = ctypes.c_void_p()
    dacl_defaulted = wintypes.BOOL()
    if not advapi32.GetSecurityDescriptorDacl(
        sd_buffer, ctypes.byref(dacl_present), ctypes.byref(dacl_ptr), ctypes.byref(dacl_defaulted)
    ):
        raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot extract DACL")
    if not dacl_present.value or not dacl_ptr:
        raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="no DACL present on file")

    # 3. Get the ACE count.
    class _AclSizeInformation(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    size_info = _AclSizeInformation()
    if not advapi32.GetAclInformation(
        dacl_ptr, ctypes.byref(size_info), ctypes.sizeof(size_info), _ACL_SIZE_INFORMATION_CLASS
    ):
        raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot read ACL information")

    allowed_sids = {_current_user_sid_string(), _SID_SYSTEM, _SID_ADMINISTRATORS, _SID_OWNER_RIGHTS}

    # 4. Enumerate every ACE. Reject any ACCESS_ALLOWED_ACE whose SID is not
    # in the allowlist. Deny ACEs don't grant access so they're not checked.
    for index in range(size_info.AceCount):
        ace_ptr = ctypes.c_void_p()
        if not advapi32.GetAce(dacl_ptr, index, ctypes.byref(ace_ptr)):
            raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot read ACE")

        # ACE_HEADER: AceType (BYTE) at offset 0.
        ace_type = ctypes.cast(ace_ptr, ctypes.POINTER(ctypes.c_ubyte))[0]
        if ace_type != _ACCESS_ALLOWED_ACE_TYPE:
            continue  # Not an allow ACE; doesn't grant access.

        # ACCESS_ALLOWED_ACE layout: Header (4 bytes) + Mask (4 bytes) + SidStart.
        sid_address = ace_ptr.value + 8
        sid_ptr = ctypes.c_void_p(sid_address)

        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
            raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot convert ACE SID to string")
        try:
            sid_str = sid_str_ptr.value or ""
        finally:
            kernel32.LocalFree(sid_str_ptr)

        if sid_str not in allowed_sids:
            raise LaunchGateError(
                code="CONFIG_FILE_PERMISSIONS_TOO_OPEN",
                detail="an unauthorized principal has allow access to the configuration file",
            )


def _current_user_sid_string() -> str:
    """Resolve the current process token's user SID as a string (e.g. S-1-5-21-...)."""
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot open process token")

    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if needed.value == 0:
            raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot size token user info")

        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, buf, needed.value, ctypes.byref(needed)):
            raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot read token user info")

        # TOKEN_USER { SID_AND_ATTRIBUTES User; } where SID_AND_ATTRIBUTES { PSID Sid; DWORD Attributes; }.
        # The first pointer-sized field of the buffer is the PSID.
        sid_ptr_value = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]

        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid_ptr_value), ctypes.byref(sid_str_ptr)):
            raise LaunchGateError(code="CONFIG_FILE_DACL_UNREADABLE", detail="cannot convert user SID to string")
        try:
            return sid_str_ptr.value or ""
        finally:
            kernel32.LocalFree(sid_str_ptr)
    finally:
        kernel32.CloseHandle(token)


def resolve_launch_candidate(
    *,
    snapshot: LaunchEnvironmentSnapshot,
    workspace_identity: WorkspaceIdentity,
    operator_paths: OperatorPaths,
    hmac_key: bytes,
    credential_keyring_backend: object | None = None,
) -> LaunchCandidate:
    """Resolve the complete launch candidate from the captured environment.

    Classifies all OPTIMUS_* variables, rejects unknown/internal-only inherited
    names, computes display rows and security snapshot digest, and projects
    Gateway/agent child environments from the canonical registry.

    Does NOT reread os.environ — uses only the immutable snapshot.
    """
    # 1. Classify and reject unknown/internal-only names.
    display_rows: list[LaunchDisplayRow] = []
    secret_inventory: list[str] = []
    security_literals: dict[str, str] = {}
    secret_fingerprints: dict[str, str] = {}
    monotonic_grants: dict[str, str] = {}

    # Check all present OPTIMUS_* variables.
    for name, value in snapshot.values.items():
        if not name.startswith("OPTIMUS_") and name not in LAUNCH_VARIABLE_POLICIES:
            continue

        try:
            policy = classify_variable(name)
        except LaunchPolicyError as exc:
            # Unknown OPTIMUS_* name present in inherited env — reject.
            if name.startswith("OPTIMUS_") or name.startswith(LOCAL_GATEWAY_PREFIX):
                raise LaunchGateError(
                    code="UNCLASSIFIED_VARIABLE",
                    detail=name,
                ) from exc
            continue

        # Internal-only variables must not be inherited.
        if policy.tier == LaunchVariableTier.INTERNAL_ONLY:
            if value.strip():
                raise LaunchGateError(
                    code="INTERNAL_ONLY_INHERITED",
                    detail=name,
                )

        # Build display row.
        display_value = policy.display(value)
        decision = _compute_decision(policy, value)
        display_rows.append(LaunchDisplayRow(
            name=name,
            tier=policy.tier,
            source_class="inherited",
            display_value=display_value,
            decision=decision,
        ))

        # Accumulate for snapshot digest.
        if policy.tier == LaunchVariableTier.SECRET:
            # Plan 9.96, Task 6 Batch 2: enforce the MAX_SECRET_TEXT_CHARS
            # cap Batch 1 deliberately deferred. StreamingTextSanitizer's
            # cross-chunk overlap bound assumes every configured secret is
            # <= MAX_SECRET_TEXT_CHARS; an over-length secret would exceed
            # that bound and could leak across a chunk boundary the overlap
            # window can't cover. Fail closed before authorization, not a
            # silent downgrade -- this is a correctness precondition for a
            # security guarantee, not a diagnostics nicety.
            try:
                validate_secret_length(value)
            except ValueError as exc:
                raise LaunchGateError(code="SECRET_TOO_LONG", detail=name) from exc
            secret_inventory.append(name)
            fp = compute_secret_fingerprint(value, field_name=name, hmac_key=hmac_key)
            secret_fingerprints[name] = fp
        elif policy.tier == LaunchVariableTier.SECURITY:
            # For URI fields, store masked literal.
            if "url" in name.lower():
                security_literals[name] = mask_uri_userinfo(value.strip())
            else:
                security_literals[name] = value.strip()
        elif policy.tier == LaunchVariableTier.MONOTONIC_LIMIT:
            try:
                policy.parser(value)
            except ValueError as exc:
                raise LaunchGateError(code="MONOTONIC_VALUE_INVALID", detail=name) from exc
            monotonic_grants[name] = value.strip()

    # Also check non-OPTIMUS provider keys that are in the registry.
    for name in LAUNCH_VARIABLE_POLICIES:
        if name.startswith("OPTIMUS_"):
            continue
        value = snapshot.values.get(name, "")
        if value.strip():
            policy = LAUNCH_VARIABLE_POLICIES[name]
            display_rows.append(LaunchDisplayRow(
                name=name,
                tier=policy.tier,
                source_class="inherited",
                display_value=policy.display(value),
                decision=_compute_decision(policy, value),
            ))
            if policy.tier == LaunchVariableTier.SECRET:
                secret_inventory.append(name)
                fp = compute_secret_fingerprint(value, field_name=name, hmac_key=hmac_key)
                secret_fingerprints[name] = fp

    # 2. Detect model observation.
    model_value = snapshot.values.get("OPTIMUS_AGENT_MODEL", "").strip()
    model_observation = model_value or None

    # 2a. Validate .env.gateway permissions BEFORE it is parsed. This lives
    # here — inside resolve_launch_candidate, the single place that actually
    # calls resolve_provider_credentials/resolve_shared_secret below — rather
    # than in each caller, so every caller (the optimus-trust CLI, __main__.py's
    # authorized launch path, or any future caller) gets this check
    # structurally and cannot bypass it by calling resolve_launch_candidate
    # directly without remembering to validate first. Two independent
    # "remember to call the permission check" call sites is exactly the
    # duplicated-security-check shape that produced the Task 4 digest bug.
    env_gateway_path = operator_paths.config_root / ".env.gateway"
    if env_gateway_path.is_file():
        validate_config_file_permissions(env_gateway_path)

    # 2b. Single-read credential resolution (Step 3). Resolve provider
    # credentials and the shared secret exactly once here, using only the
    # immutable snapshot (never os.environ) and the already-validated
    # operator config root. Downstream Gateway startup (Task 5) must consume
    # these resolved objects from AuthorizedLaunch rather than re-resolving
    # from .env.gateway/keyring/ambient environment.
    import keyring as _default_keyring_module

    keyring_backend = credential_keyring_backend or _default_keyring_module
    try:
        provider_credentials = resolve_provider_credentials(
            snapshot.values,
            config_root=operator_paths.config_root,
            keyring_backend=keyring_backend,
        )
    except ProviderCredentialConfigurationError:
        provider_credentials = None
    resolved_shared_secret = resolve_shared_secret(
        snapshot.values,
        config_root=operator_paths.config_root,
        keyring_backend=keyring_backend,
    )

    # 2c. Fold the RESOLVED credentials (which may come from .env.gateway or
    # keyring, not just the environment scan above) into the digest inputs.
    # Without this, swapping a .env.gateway-sourced provider key or shared
    # secret would leave the digest unchanged and a stale approval would
    # remain valid after the effective credential changed — a real
    # approval-reuse hole. Using fixed field names distinct from the
    # OPTIMUS_* env names below avoids collisions; env-sourced values get
    # fingerprinted twice (once by name, once here) which is harmless — the
    # digest only needs to change when the EFFECTIVE value changes.
    if provider_credentials is not None and provider_credentials.secrets is not None:
        resolved = provider_credentials.secrets
        secret_fingerprints["_resolved_provider_api_key"] = compute_secret_fingerprint(
            resolved.model_provider_api_key,
            field_name="_resolved_provider_api_key",
            hmac_key=hmac_key,
        )
        security_literals["_resolved_provider"] = resolved.provider
        if resolved.base_url:
            security_literals["_resolved_base_url"] = resolved.base_url
    if resolved_shared_secret:
        secret_fingerprints["_resolved_shared_secret"] = compute_secret_fingerprint(
            resolved_shared_secret,
            field_name="_resolved_shared_secret",
            hmac_key=hmac_key,
        )

    # 3. Compute security snapshot digest using the SINGLE shared function
    # also used by build_approval_record(). This is required — using two
    # independent hash computations (even with equivalent inputs) produces
    # permanently incompatible digests and breaks authorization entirely.
    from optimus.acp.launch_approvals import (
        LAUNCH_POLICY_COMPATIBILITY,
        compute_security_snapshot_digest,
    )

    snapshot_digest = compute_security_snapshot_digest(
        security_literals=security_literals,
        secret_fingerprints=secret_fingerprints,
        workspace_digest=workspace_identity.digest,
        registry_version=LAUNCH_POLICY_COMPATIBILITY,
    )

    # 4. Project child environments from registry.
    gateway_environ = _project_child_env(snapshot, PropagationTarget.GATEWAY_CHILD)
    agent_environ = _project_child_env(snapshot, PropagationTarget.AGENT_CHILD)

    return LaunchCandidate(
        inherited=snapshot,
        workspace_identity=workspace_identity,
        operator_paths=operator_paths,
        security_snapshot_digest=snapshot_digest,
        display_rows=tuple(sorted(display_rows, key=lambda r: r.name)),
        gateway_environ=gateway_environ,
        agent_environ=agent_environ,
        secret_inventory=tuple(sorted(secret_inventory)),
        security_literals=dict(security_literals),
        secret_fingerprints=dict(secret_fingerprints),
        monotonic_grants=dict(monotonic_grants),
        model_observation=model_observation,
        provider_credentials=provider_credentials,
        shared_secret=resolved_shared_secret,
    )


def authorize_launch(
    *,
    candidate: LaunchCandidate,
    store: KeyringApprovalStore,
    approval_id: str | None = None,
    launch_session_id: str,
) -> AuthorizedLaunch:
    """Authorize a launch candidate against the keyring approval store.

    For headless launches, reads an existing durable approval.
    For one-shot, consumes the identified record.
    """

    ws_digest = candidate.workspace_identity.digest

    if approval_id and approval_id.startswith("p996_"):
        # One-shot consumption.
        try:
            record = store.consume_one_shot(approval_id, candidate.security_snapshot_digest)
        except ApprovalError as exc:
            raise LaunchGateError(code=exc.code, detail=exc.detail) from exc
        return AuthorizedLaunch(
            candidate=candidate,
            approval_id=record.approval_id,
            approval_mode="one-shot",
            launch_session_id=launch_session_id,
        )

    # Durable approval.
    try:
        record = store.read_durable(ws_digest)
    except ApprovalError as exc:
        raise LaunchGateError(code=exc.code, detail=exc.detail) from exc

    if record is None:
        raise LaunchGateError(
            code="NO_APPROVAL",
            detail="no durable approval found for this workspace",
        )

    # Verify snapshot digest matches.
    if record.security_snapshot_digest != candidate.security_snapshot_digest:
        raise LaunchGateError(
            code="SNAPSHOT_MISMATCH",
            detail="effective configuration changed since approval",
        )

    _authorize_monotonic_grants(candidate=candidate, record_monotonic_grants=record.monotonic_grants)

    return AuthorizedLaunch(
        candidate=candidate,
        approval_id=record.approval_id,
        approval_mode="durable",
        launch_session_id=launch_session_id,
    )


def _authorize_monotonic_grants(
    *,
    candidate: LaunchCandidate,
    record_monotonic_grants: Mapping[str, str],
) -> None:
    """Enforce Global Constraint 12 for monotonic-limit variables.

    Plan 9.96, Task 5 Batch 3 Step 5: monotonic_grants is no longer part of
    security_snapshot_digest (digest equality cannot express direction —
    only "changed or unchanged" — so it wrongly forced re-approval on a pure
    tightening). This function performs the actual comparison instead: for
    each present monotonic-tier name, a value <= the reviewed default is
    always allowed (tightening/equal is free); a value > the default
    requires an EXACT matching entry in the approval record's own
    monotonic_grants (the reviewed, approved value) — not merely "any
    higher value was once approved." Any parseable-but-unmatched loosening
    fails closed with MONOTONIC_LOOSENING_UNAPPROVED.
    """
    for name, raw_value in candidate.monotonic_grants.items():
        policy = LAUNCH_VARIABLE_POLICIES[name]
        parsed_value = policy.parser(raw_value)
        default_value = _MONOTONIC_DEFAULTS[name]
        if parsed_value <= default_value:
            continue  # Tightening or equal-to-default: free, no approval needed.
        approved_raw = record_monotonic_grants.get(name)
        if approved_raw is None or approved_raw.strip() != raw_value:
            raise LaunchGateError(code="MONOTONIC_LOOSENING_UNAPPROVED", detail=name)


def _compute_decision(policy: LaunchVariablePolicy, value: str) -> str:
    """Compute the human-readable decision for a variable."""
    if policy.tier == LaunchVariableTier.SECRET:
        return "requires exact HMAC approval"
    if policy.tier == LaunchVariableTier.INTERNAL_ONLY:
        return "rejected (internal-only)"
    if policy.tier == LaunchVariableTier.MONOTONIC_LIMIT:
        return "monotonic: tighten allowed, loosen requires approval"
    if policy.tier == LaunchVariableTier.OPERATIONAL:
        return "allowed under bounded-model predicate"
    return "requires exact approval"


def _project_child_env(snapshot: LaunchEnvironmentSnapshot, target: PropagationTarget) -> dict[str, str]:
    """Project the authorized child environment for a target."""
    child: dict[str, str] = {}
    for name, policy in LAUNCH_VARIABLE_POLICIES.items():
        if target in policy.propagation:
            value = snapshot.values.get(name, "").strip()
            if value:
                child[name] = value
    return child
