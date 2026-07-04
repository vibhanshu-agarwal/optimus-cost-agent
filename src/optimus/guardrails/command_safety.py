from __future__ import annotations

import re
import shlex
import unicodedata
from pathlib import Path

from optimus.guardrails.network_safety import NetworkSafetyValidator
from optimus.guardrails.path_safety import PathSafetyValidator
from optimus.guardrails.validation import ValidationResult, ValidationVerdict


_PIPE_TO_SHELL = re.compile(r"(curl|wget|irm|iwr|Invoke-WebRequest|Invoke-RestMethod)\b.*\|\s*(sh|bash|zsh|pwsh|powershell|iex|Invoke-Expression)\b", re.IGNORECASE)
_FETCH_THEN_EXEC = re.compile(r"(curl|wget|irm|iwr|Invoke-WebRequest|Invoke-RestMethod)\b.*(&&|;)\s*(sh|bash|zsh|pwsh|powershell|iex|Invoke-Expression)\b", re.IGNORECASE)
_ENV_ACCESS = re.compile(r"\b(printenv|env|set)\b|\bos\.environ\b|\$env:|%[A-Za-z_][A-Za-z0-9_]*%", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_CONFUSABLES = frozenset({"\u0430", "\u0435", "\u043e", "\u0440", "\u0441", "\u0445", "\u0443", "\u0456", "\uff41", "\uff45", "\uff49", "\uff4f"})
_INTERPRETERS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell", "python", "python3", "node", "ruby", "perl"}
_INTERPRETER_PAYLOAD_FLAGS = {"-c", "-lc", "/c", "-command", "-e"}
_NON_HTTP_EGRESS = {"scp", "sftp", "ssh", "ftp", "nc", "ncat", "netcat", "telnet"}


class CommandSafetyValidator:
    def __init__(self, *, workspace_root: str | Path, allowed_network_hosts: tuple[str, ...]) -> None:
        self._paths = PathSafetyValidator(workspace_root=workspace_root)
        self._network = NetworkSafetyValidator(allowed_hosts=allowed_network_hosts)

    def validate(self, command: tuple[str, ...]) -> ValidationResult:
        return self._validate_command(command, depth=0)

    def _validate_command(self, command: tuple[str, ...], *, depth: int) -> ValidationResult:
        if not command:
            return ValidationResult(ValidationVerdict.HOLD, "shell.empty_command", "empty command requires review")
        raw_text = " ".join(command)
        text = unicodedata.normalize("NFKC", raw_text)
        lowered = text.lower()
        if _contains_control_sequence(text):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.ansi_control", "ANSI or control sequence detected")
        if _contains_bidi_or_format_control(text):
            return ValidationResult(
                ValidationVerdict.BLOCK,
                "shell.unicode_bidi_control",
                "Unicode bidi or format control character detected",
            )
        if _contains_confusable(raw_text) or _contains_punycode_host(raw_text):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.unicode_confusable", "Unicode confusable detected")
        if _is_recursive_force_delete(command, lowered):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.destructive.rm_rf", "recursive force delete denied")
        if _is_destructive_command(command, lowered):
            return ValidationResult(ValidationVerdict.HOLD, "shell.destructive.review", "destructive command requires review")
        if _PIPE_TO_SHELL.search(text):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.pipe_to_shell", "fetch-and-execute pattern denied")
        if _FETCH_THEN_EXEC.search(text):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.fetch_then_exec", "fetch-then-execute pattern denied")
        credential_result = self._credential_read(command)
        if credential_result is not None:
            return credential_result
        if _ENV_ACCESS.search(text):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.env_access", "environment access denied")
        non_http_egress = _non_http_egress(command)
        if non_http_egress is not None:
            return non_http_egress
        network_result = self._network_result(text)
        if network_result is not None and network_result.verdict is not ValidationVerdict.ALLOW:
            return network_result
        payload = _interpreter_payload(command)
        if payload is not None:
            parsed = _split_payload(payload)
            if parsed:
                payload_result = self._validate_command(tuple(parsed), depth=depth + 1)
                if payload_result.verdict is not ValidationVerdict.HOLD:
                    return payload_result
            return ValidationResult(
                ValidationVerdict.HOLD,
                "shell.opaque_interpreter",
                "interpreter payload is ambiguous and requires review",
            )
        if _is_git_no_verify_bypass(command):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.git_no_verify", "git --no-verify bypass is denied")
        if _is_git_hooks_path_bypass(command):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.git_hooks_path_bypass", "git hooksPath bypass is denied")
        if _is_allowed_command(command):
            return ValidationResult(ValidationVerdict.ALLOW, "shell.allowed", "command matched deterministic allowlist")
        return ValidationResult(
            ValidationVerdict.HOLD,
            "shell.unclassified_command",
            "unclassified shell command requires human review",
        )

    def _credential_read(self, command: tuple[str, ...]) -> ValidationResult | None:
        for token in command:
            if _is_proc_environ_path(token):
                return ValidationResult(ValidationVerdict.BLOCK, "shell.credential_read", "process environment reads are denied")
            result = self._paths.validate_read(token)
            if result.verdict is ValidationVerdict.BLOCK:
                return ValidationResult(ValidationVerdict.BLOCK, "shell.credential_read", result.reason)
        return None

    def _network_result(self, text: str) -> ValidationResult | None:
        for match in _URL.finditer(text):
            result = self._network.validate_url(match.group(0))
            if result.verdict is not ValidationVerdict.ALLOW:
                return result
        return None


def _contains_control_sequence(text: str) -> bool:
    return any((ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127 for char in text)


def _contains_bidi_or_format_control(text: str) -> bool:
    return any(unicodedata.category(char) == "Cf" for char in text)


def _contains_confusable(text: str) -> bool:
    return any(char in _CONFUSABLES for char in text)


def _contains_punycode_host(text: str) -> bool:
    return "xn--" in text.lower()


def _is_recursive_force_delete(command: tuple[str, ...], lowered: str) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name.lower()
    if executable == "rm":
        flags = "".join(token.lstrip("-").lower() for token in command[1:] if token.startswith("-"))
        return "r" in flags and "f" in flags
    if "remove-item" in lowered and "-recurse" in lowered and "-force" in lowered:
        return True
    if executable in {"format", "diskpart"}:
        return True
    return False


def _is_destructive_command(command: tuple[str, ...], lowered: str) -> bool:
    executable = Path(command[0]).name.lower()
    if executable in {"shred", "dd"}:
        return True
    if executable == "find" and "-delete" in lowered:
        return True
    if tuple(token.lower() for token in command[:3]) in {("git", "reset", "--hard"), ("git", "clean", "-fdx")}:
        return True
    return False


def _interpreter_payload(command: tuple[str, ...]) -> str | None:
    executable = Path(command[0]).name.lower()
    if executable not in _INTERPRETERS:
        return None
    lowered = tuple(token.lower() for token in command)
    for index, token in enumerate(lowered):
        if token in _INTERPRETER_PAYLOAD_FLAGS and index + 1 < len(command):
            return command[index + 1]
    return None


def _split_payload(payload: str) -> list[str]:
    try:
        return shlex.split(payload, posix=True)
    except ValueError:
        return []


def _non_http_egress(command: tuple[str, ...]) -> ValidationResult | None:
    executable = Path(command[0]).name.lower()
    if executable in _NON_HTTP_EGRESS:
        return ValidationResult(ValidationVerdict.HOLD, "network.non_http_egress", "non-HTTP network egress requires review")
    text = " ".join(command).lower()
    if any(text.startswith(f"{scheme}://") or f" {scheme}://" in text for scheme in ("ssh", "scp", "sftp", "ftp", "file")):
        return ValidationResult(ValidationVerdict.HOLD, "network.non_http_egress", "non-HTTP network egress requires review")
    return None


def _is_proc_environ_path(token: str) -> bool:
    normalized = token.replace("\\", "/").lower()
    return normalized == "/proc/self/environ" or (normalized.startswith("/proc/") and normalized.endswith("/environ"))


def _is_allowed_command(command: tuple[str, ...]) -> bool:
    executable = Path(command[0]).name.lower()
    if executable == "pytest":
        return True
    lowered = tuple(token.lower() for token in command)
    return lowered[:2] in {("git", "status"), ("git", "diff"), ("git", "log"), ("git", "show")}


def _is_git_no_verify_bypass(command: tuple[str, ...]) -> bool:
    lowered = tuple(token.lower() for token in command)
    subcommand = _git_subcommand(lowered)
    if subcommand == "commit":
        return "--no-verify" in lowered or "-n" in lowered
    if subcommand == "push":
        return "--no-verify" in lowered
    return False


def _is_git_hooks_path_bypass(command: tuple[str, ...]) -> bool:
    lowered = tuple(token.lower() for token in command)
    return _is_git_command(lowered) and any(token.startswith("core.hookspath=") for token in lowered)


def _git_subcommand(tokens: tuple[str, ...]) -> str | None:
    if not _is_git_command(tokens):
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-c", "-C"} and index + 1 < len(tokens):
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def _is_git_command(tokens: tuple[str, ...]) -> bool:
    if not tokens:
        return False
    executable = Path(tokens[0]).name.lower()
    return executable in {"git", "git.exe"}
