from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class TrustScanSubject(StrEnum):
    CONFIG_FILE = "config_file"
    MCP_DESCRIPTOR = "mcp_descriptor"
    TOOL_OUTPUT = "tool_output"


class TrustScanVerdict(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TrustScanFinding:
    rule_id: str
    reason: str
    excerpt: str


@dataclass(frozen=True)
class TrustScanResult:
    verdict: TrustScanVerdict
    subject: TrustScanSubject
    source_path: str
    findings: tuple[TrustScanFinding, ...]

    @property
    def allowed(self) -> bool:
        return self.verdict is TrustScanVerdict.ALLOW

    @property
    def sanitized_summary(self) -> str:
        return f"{_sanitize_source(self.source_path)}: {self.verdict.value}"


_TEXT_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "injection.ignore_previous",
        re.compile(r"\b(ignore|discard|override|disregard|forget)\b.{0,240}\b(previous|prior|above|system|developer)\b.{0,240}\binstructions?\b", re.IGNORECASE | re.DOTALL),
        "embedded instruction attempts to override higher-priority instructions",
    ),
    (
        "injection.exfiltration_endpoint",
        re.compile(r"\b(pipe|send|post|upload|exfiltrate|ship)\b.{0,100}\b(output|logs?|environment|env|secrets?)\b.{0,120}https?://", re.IGNORECASE | re.DOTALL),
        "embedded instruction attempts to send local output or secrets to a remote endpoint",
    ),
    (
        "injection.secret_access_instruction",
        re.compile(r"\b(read|cat|open|print|dump|send)\b.{0,80}(\.env|id_rsa|id_ed25519|credentials|token|secrets?|os\.environ|\$env:)", re.IGNORECASE | re.DOTALL),
        "embedded instruction attempts to access secrets or environment values",
    ),
    (
        "injection.fetch_execute_instruction",
        re.compile(r"(curl|wget|irm|iwr|Invoke-WebRequest|Invoke-RestMethod).{0,120}\|\s*(sh|bash|zsh|pwsh|powershell|iex|Invoke-Expression)\b", re.IGNORECASE | re.DOTALL),
        "embedded instruction contains fetch-and-execute behavior",
    ),
)

_CONFUSABLES = frozenset({"\u0430", "\u0435", "\u043e", "\u0440", "\u0441", "\u0445", "\u0443", "\u0456", "\uff41", "\uff45", "\uff49", "\uff4f"})


class ConfigTrustScanner:
    def scan_text(self, text: str, *, subject: TrustScanSubject, source_path: str) -> TrustScanResult:
        raw_text = text
        normalized = unicodedata.normalize("NFKC", text)
        findings: list[TrustScanFinding] = []

        for rule_id, pattern, reason in _TEXT_RULES:
            match = pattern.search(normalized)
            if match is not None:
                findings.append(TrustScanFinding(rule_id, reason, _excerpt(match.group(0))))

        if _contains_control_character(normalized):
            findings.append(TrustScanFinding("injection.control_character", "ANSI or control character detected", "<control>"))
        if _contains_format_control(normalized):
            findings.append(TrustScanFinding("injection.unicode_format_control", "Unicode format or bidi control detected", "<format-control>"))
        if any(char in _CONFUSABLES for char in raw_text) or "xn--" in raw_text.lower():
            findings.append(TrustScanFinding("injection.unicode_confusable", "Unicode confusable or punycode detected", "<confusable>"))

        return TrustScanResult(
            verdict=TrustScanVerdict.BLOCK if findings else TrustScanVerdict.ALLOW,
            subject=subject,
            source_path=source_path,
            findings=tuple(findings),
        )


def _contains_control_character(text: str) -> bool:
    return any((ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127 for char in text)


def _contains_format_control(text: str) -> bool:
    return any(unicodedata.category(char) == "Cf" for char in text)


def _excerpt(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:120]


def _sanitize_source(source_path: str) -> str:
    return source_path.replace("\\", "/")
