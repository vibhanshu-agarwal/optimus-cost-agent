"""Normalize ACP client-supplied mcpServers into secret-safe identities."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, NoReturn, Sequence
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from optimus.guardrails.prompt_injection import ConfigTrustScanner, TrustScanSubject, TrustScanVerdict

_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_INJECTION_ENV_NAMES = frozenset(
    {
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
        "NODE_OPTIONS",
        "PYTHONSTARTUP",
        "PYTHONPATH",
        "PATH",
    }
)
_CREDENTIAL_FP_DOMAIN = b"p11-fu-9-client-mcp-credential-fingerprint-v1"
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class ClientMcpConfigError(Exception):
    """Safe, rule-id-only rejection of a client MCP configuration entry."""

    def __init__(self, rule_id: str) -> None:
        self.rule_id = rule_id
        super().__init__(rule_id)

    def __repr__(self) -> str:
        return f"ClientMcpConfigError(rule_id={self.rule_id!r})"

    def __str__(self) -> str:
        return self.rule_id


@dataclass(frozen=True)
class ClientMcpSafeIdentity:
    transport: str
    server_name: str
    canonical_target: str
    arguments: tuple[str, ...]
    credential_name_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class ClientMcpSafeView:
    provenance: str
    transport: str
    server_name: str
    canonical_target: str
    arguments: tuple[str, ...]
    credential_names: tuple[str, ...]
    credential_name_fingerprints: tuple[str, ...]
    scanner_rule_ids: tuple[str, ...]
    disposition: str


class ClientMcpRuntimeCapability:
    """Opaque slot-backed holder for transient client MCP credentials."""

    __slots__ = ("_safe_identity", "_safe_view", "_header_values", "_env_values")

    def __init__(
        self,
        *,
        safe_identity: ClientMcpSafeIdentity,
        safe_view: ClientMcpSafeView,
        header_values: Mapping[str, str],
        env_values: Mapping[str, str],
    ) -> None:
        object.__setattr__(self, "_safe_identity", safe_identity)
        object.__setattr__(self, "_safe_view", safe_view)
        object.__setattr__(self, "_header_values", dict(header_values))
        object.__setattr__(self, "_env_values", dict(env_values))

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("client mcp runtime capability is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("client mcp runtime capability is immutable")

    def __getattribute__(self, name: str) -> object:
        if name == "__dict__":
            raise TypeError("client mcp runtime capability is not serializable")
        return object.__getattribute__(self, name)

    @property
    def safe_identity(self) -> ClientMcpSafeIdentity:
        return object.__getattribute__(self, "_safe_identity")

    def safe_view(self) -> ClientMcpSafeView:
        return object.__getattribute__(self, "_safe_view")

    def constructed_child_environ(self) -> dict[str, str]:
        baseline: dict[str, str] = {}
        if os.name == "nt":
            system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
            if system_root:
                baseline["SystemRoot"] = system_root
        env_values: dict[str, str] = object.__getattribute__(self, "_env_values")
        return {**baseline, **env_values}

    def __repr__(self) -> str:
        identity = self.safe_identity
        return (
            "ClientMcpRuntimeCapability("
            f"transport={identity.transport!r}, "
            f"server_name={identity.server_name!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def __getstate__(self) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")

    def __setstate__(self, state: object) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")

    def __reduce_ex__(self, protocol: int) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")

    def __copy__(self) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")

    def __deepcopy__(self, memo: dict[int, object]) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")

    def model_dump(self, *args: object, **kwargs: object) -> NoReturn:
        raise TypeError("client mcp runtime capability is not serializable")


class ClientMcpConfigNormalizer:
    def __init__(self, *, scanner: ConfigTrustScanner | None = None) -> None:
        self._scanner = scanner or ConfigTrustScanner()

    def normalize(
        self,
        entries: Sequence[Mapping[str, object]] | None,
        *,
        workspace_root: Path,
        controlled_path: str,
        hmac_key: bytes,
    ) -> tuple[ClientMcpRuntimeCapability, ...]:
        del workspace_root  # reserved for later disposition/cwd binding
        if entries is None or len(entries) == 0:
            return ()

        names = [_require_str(entry.get("name"), rule_id="client_mcp.invalid_server_name") for entry in entries]
        _reject_duplicate_names(names)

        capabilities: list[ClientMcpRuntimeCapability] = []
        for index, entry in enumerate(entries):
            capabilities.append(
                self._normalize_one(
                    entry,
                    index=index,
                    controlled_path=controlled_path,
                    hmac_key=hmac_key,
                )
            )
        return tuple(capabilities)

    def _normalize_one(
        self,
        entry: Mapping[str, object],
        *,
        index: int,
        controlled_path: str,
        hmac_key: bytes,
    ) -> ClientMcpRuntimeCapability:
        server_name = _require_str(entry.get("name"), rule_id="client_mcp.invalid_server_name")
        if _SERVER_NAME_RE.fullmatch(server_name) is None:
            raise ClientMcpConfigError("client_mcp.invalid_server_name")

        transport = _parse_transport(entry)
        scan_chunks = [server_name]
        header_values: dict[str, str] = {}
        env_values: dict[str, str] = {}
        arguments: tuple[str, ...] = ()
        credential_names: list[str] = []
        fingerprints: list[str] = []

        if transport == "stdio":
            command = _require_str(entry.get("command"), rule_id="client_mcp.invalid_stdio_command")
            args_raw = entry.get("args", [])
            if not isinstance(args_raw, list) or not all(isinstance(item, str) for item in args_raw):
                raise ClientMcpConfigError("client_mcp.invalid_stdio_args")
            arguments = tuple(args_raw)
            env_items = _parse_named_values(
                entry.get("env", []),
                duplicate_rule="client_mcp.duplicate_env_name",
                case_insensitive=(os.name == "nt"),
                injection_check=True,
            )
            for env_index, (env_name, env_value) in enumerate(env_items):
                env_values[env_name] = env_value
                credential_names.append(env_name)
                fingerprints.append(
                    _fingerprint(hmac_key, kind="env", name=env_name, index=env_index, value=env_value)
                )
            canonical_target = _resolve_stdio_command(command, controlled_path=controlled_path)
            scan_chunks.extend([command, *arguments, *credential_names])
        else:
            url = _require_str(entry.get("url"), rule_id="client_mcp.invalid_url")
            header_items = _parse_named_values(
                entry.get("headers", []),
                duplicate_rule="client_mcp.duplicate_header_name",
                case_insensitive=True,
                injection_check=False,
            )
            for header_index, (header_name, header_value) in enumerate(header_items):
                header_values[header_name] = header_value
                credential_names.append(header_name)
                fingerprints.append(
                    _fingerprint(
                        hmac_key,
                        kind="header",
                        name=header_name.casefold(),
                        index=header_index,
                        value=header_value,
                    )
                )
            canonical_target, query_fingerprints = _canonicalize_url(url, hmac_key=hmac_key)
            fingerprints.extend(query_fingerprints)
            for query_name, _ in parse_qsl(urlsplit(canonical_target).query, keep_blank_values=True):
                credential_names.append(query_name)
            scan_chunks.extend([canonical_target, *credential_names])

        # `_meta` is intentionally ignored and never enters identity or scan text.
        _ = entry.get("_meta")

        scan_text = "\n".join(scan_chunks)
        scan = self._scanner.scan_text(
            scan_text,
            subject=TrustScanSubject.CLIENT_MCP_CONFIG,
            source_path=f"acp:mcpServers[{index}]",
        )
        if scan.verdict is TrustScanVerdict.BLOCK:
            raise ClientMcpConfigError(scan.findings[0].rule_id)

        identity = ClientMcpSafeIdentity(
            transport=transport,
            server_name=server_name,
            canonical_target=canonical_target,
            arguments=arguments,
            credential_name_fingerprints=tuple(fingerprints),
        )
        view = ClientMcpSafeView(
            provenance="client_supplied_acp",
            transport=transport,
            server_name=server_name,
            canonical_target=canonical_target,
            arguments=arguments,
            credential_names=tuple(credential_names),
            credential_name_fingerprints=tuple(fingerprints),
            scanner_rule_ids=(),
            disposition="normalized",
        )
        return ClientMcpRuntimeCapability(
            safe_identity=identity,
            safe_view=view,
            header_values=header_values,
            env_values=env_values,
        )


def _reject_duplicate_names(names: Sequence[str]) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ClientMcpConfigError("client_mcp.duplicate_server_name")
        seen.add(name)


def _parse_transport(entry: Mapping[str, object]) -> str:
    if "type" not in entry:
        return "stdio"
    transport = entry.get("type")
    if transport in {"http", "sse"}:
        return str(transport)
    raise ClientMcpConfigError("client_mcp.invalid_transport")


def _require_str(value: object, *, rule_id: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ClientMcpConfigError(rule_id)
    return value


def _parse_named_values(
    raw: object,
    *,
    duplicate_rule: str,
    case_insensitive: bool,
    injection_check: bool,
) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        raise ClientMcpConfigError("client_mcp.invalid_named_values")
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise ClientMcpConfigError("client_mcp.invalid_named_values")
        name = _require_str(item.get("name"), rule_id="client_mcp.invalid_named_values")
        value = item.get("value")
        if not isinstance(value, str):
            raise ClientMcpConfigError("client_mcp.invalid_named_values")
        key = name.casefold() if case_insensitive else name
        if key in seen:
            raise ClientMcpConfigError(duplicate_rule)
        seen.add(key)
        if injection_check and name.casefold() in {item.casefold() for item in _INJECTION_ENV_NAMES}:
            raise ClientMcpConfigError("client_mcp.injection_env_name")
        items.append((name, value))
    return items


def _fingerprint(hmac_key: bytes, *, kind: str, name: str, index: int, value: str) -> str:
    msg = _CREDENTIAL_FP_DOMAIN + b"\0" + f"{kind}\0{name}\0{index}\0{value}".encode("utf-8")
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def _resolve_stdio_command(command: str, *, controlled_path: str) -> str:
    path = Path(command)
    if path.is_absolute() or os.path.isabs(command):
        resolved = path.resolve()
        if not resolved.exists():
            raise ClientMcpConfigError("client_mcp.command_not_found")
        return _normcase_path(resolved)

    # Bare commands are filenames only — no directory components or traversal.
    if command in {".", ".."} or "/" in command or "\\" in command or os.sep in command or (
        os.altsep is not None and os.altsep in command
    ):
        raise ClientMcpConfigError("client_mcp.invalid_bare_command")
    if Path(command).name != command:
        raise ClientMcpConfigError("client_mcp.invalid_bare_command")

    extensions = [""]
    if os.name == "nt":
        pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
        extensions = [""] + [ext for ext in pathext.split(os.pathsep) if ext]

    for directory in controlled_path.split(os.pathsep):
        if not directory:
            continue
        base = Path(directory).resolve()
        for ext in extensions:
            candidate_name = command if ext == "" or command.lower().endswith(ext.lower()) else f"{command}{ext}"
            if Path(candidate_name).name != candidate_name:
                raise ClientMcpConfigError("client_mcp.invalid_bare_command")
            candidate = (base / candidate_name).resolve()
            if not _is_within_directory(candidate, base):
                continue
            if candidate.exists() and candidate.is_file():
                return _normcase_path(candidate)
    raise ClientMcpConfigError("client_mcp.command_not_found")


def _is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _normcase_path(path: Path) -> str:
    text = str(path)
    if sys.platform == "win32":
        return os.path.normcase(text)
    return text


def _canonicalize_url(url: str, *, hmac_key: bytes) -> tuple[str, tuple[str, ...]]:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"}:
        raise ClientMcpConfigError("client_mcp.invalid_url")
    if parts.username is not None or parts.password is not None:
        raise ClientMcpConfigError("client_mcp.invalid_url_userinfo")
    if parts.fragment:
        raise ClientMcpConfigError("client_mcp.invalid_url_fragment")
    if not parts.hostname:
        raise ClientMcpConfigError("client_mcp.invalid_url")

    scheme = parts.scheme.lower()
    host = _canonicalize_host(parts.hostname)
    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = host if port is None else f"{host}:{port}"

    path = _canonicalize_path(parts.path or "/")
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    fingerprints: list[str] = []
    rendered_pairs: list[tuple[str, str]] = []
    for index, (name, value) in enumerate(query_pairs):
        fp = _fingerprint(hmac_key, kind="query", name=name, index=index, value=value)
        fingerprints.append(fp)
        rendered_pairs.append((name, fp))
    query = "&".join(f"{_encode_query_name(name)}={fp}" for name, fp in rendered_pairs)
    return urlunsplit((scheme, netloc, path, query, "")), tuple(fingerprints)


def _canonicalize_host(hostname: str) -> str:
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
        if isinstance(ip, ipaddress.IPv6Address):
            return f"[{ip.compressed}]"
        return ip.compressed
    except ValueError:
        pass
    try:
        return hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ClientMcpConfigError("client_mcp.invalid_url") from exc


def _canonicalize_path(path: str) -> str:
    if path == "":
        return "/"
    segments = path.split("/")
    encoded: list[str] = []
    for index, segment in enumerate(segments):
        if index == 0 and segment == "":
            encoded.append("")
            continue
        encoded.append(_canonicalize_percent_segment(segment))
    result = "/".join(encoded)
    return result if result.startswith("/") else f"/{result}"


def _canonicalize_percent_segment(segment: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char == "%" and index + 2 < len(segment):
            hex_part = segment[index + 1 : index + 3]
            if re.fullmatch(r"[0-9A-Fa-f]{2}", hex_part):
                raw = bytes.fromhex(hex_part)
                if len(raw) == 1 and chr(raw[0]) in _UNRESERVED:
                    out.append(chr(raw[0]))
                else:
                    out.append(f"%{hex_part.upper()}")
                index += 3
                continue
        if char in _UNRESERVED:
            out.append(char)
        else:
            out.append(quote(char, safe=""))
        index += 1
    return "".join(out)


def _encode_query_name(name: str) -> str:
    return quote(name, safe="")
