from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from sys import argv

from optimus.guardrails.unicode_confusables import contains_dangerous_confusable


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
        if contains_dangerous_confusable(raw_text):
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


_DEFAULT_AGENT_CONFIG_GLOBS = (
    "**/AGENTS.md",
    "**/CLAUDE.md",
    ".mcp.json",
    ".agents/**/*.md",
    ".claude/**/*.md",
    ".codex/**/*.toml",
    ".cursor/**/*.json",
    ".cursor/**/*.mdc",
    ".github/copilot-instructions.md",
    ".vscode/mcp.json",
    ".windsurfrules",
    ".clinerules",
)


def scan_paths(paths: tuple[Path, ...], *, root: Path | None = None) -> tuple[TrustScanResult, ...]:
    scanner = ConfigTrustScanner()
    base = root or Path.cwd()
    results: list[TrustScanResult] = []
    for path in paths:
        if not path.is_file():
            results.append(
                TrustScanResult(
                    verdict=TrustScanVerdict.BLOCK,
                    subject=TrustScanSubject.CONFIG_FILE,
                    source_path=path.as_posix(),
                    findings=(
                        TrustScanFinding(
                            "injection.unscannable_path",
                            "config path is not a readable file",
                            path.as_posix(),
                        ),
                    ),
                )
            )
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        try:
            source = path.resolve(strict=False).relative_to(base.resolve(strict=False)).as_posix()
        except ValueError:
            source = path.as_posix()
        results.append(scanner.scan_text(text, subject=TrustScanSubject.CONFIG_FILE, source_path=source))
    return tuple(results)


def default_agent_config_paths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for pattern in _DEFAULT_AGENT_CONFIG_GLOBS:
        paths.extend(root.glob(pattern))
    return tuple(dict.fromkeys(paths))


def main(args: list[str] | None = None) -> int:
    raw_args = argv[1:] if args is None else args
    root = Path.cwd()
    paths = tuple(Path(arg) for arg in raw_args) if raw_args else default_agent_config_paths(root)
    blocked = [result for result in scan_paths(paths, root=root) if not result.allowed]
    for result in blocked:
        rules = ",".join(finding.rule_id for finding in result.findings)
        print(f"{result.sanitized_summary}: {rules}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
