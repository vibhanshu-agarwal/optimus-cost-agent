# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["packaging==26.3", "pip-audit==2.10.1"]
# ///
"""Audit every public package/version pin in the project uv.lock."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import tomllib
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PYPI_SOURCE = {"registry": "https://pypi.org/simple"}
PYPI_RELEASE_URL = re.compile(r"https://pypi\.org/pypi/([^/]+)/([^/]+)/json")
INVALID_PYPI_RESPONSE = 3
APPROVAL = re.compile(r"https://github\.com/vibhanshu-agarwal/optimus-cost-agent/(issues|pull)/[1-9][0-9]*")
EXCEPTION_FIELDS = {"package", "version", "advisory", "rationale", "owner", "approval", "expires"}

type Pin = tuple[str, str]
type Finding = tuple[str, str, str]


class AuditError(Exception):
    """The inventory, policy or audit response could not be verified."""


def _pin(name: object, version: object) -> Pin:
    if not isinstance(name, str) or not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.!+_-]+", version):
        raise AuditError("invalid dependency pin")
    try:
        return canonicalize_name(name, validate=True), str(Version(version))
    except InvalidName, InvalidVersion:
        raise AuditError("invalid dependency pin") from None


def read_lock(path: Path) -> set[Pin]:
    with path.open("rb") as lock:
        data = tomllib.load(lock)
    packages = data.get("package")
    if data.get("version") != 1 or not isinstance(packages, list):
        raise AuditError("unsupported lockfile format")
    pins = set()
    for package in packages:
        if not isinstance(package, dict):
            raise AuditError("invalid lockfile package")
        pin = _pin(package.get("name"), package.get("version"))
        source = package.get("source")
        if pin[0] == "optimus-cost-agent" and source == {"editable": "."}:
            continue
        if source != PYPI_SOURCE:
            raise AuditError(f"unsupported lockfile source for {pin[0]}")
        pins.add(pin)
    if not pins:
        raise AuditError("empty public dependency inventory")
    return pins


def pin_batches(pins: set[Pin]) -> list[set[Pin]]:
    """Requirements files admit one version of each name per audit."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for name, version in sorted(pins):
        by_name[name].append(version)
    batches: list[set[Pin]] = []
    for name, versions in by_name.items():
        for index, version in enumerate(versions):
            if index == len(batches):
                batches.append(set())
            batches[index].add((name, version))
    return batches


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError("duplicate JSON field")
        result[key] = value
    return result


def _advisory_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", value):
        raise AuditError("invalid advisory ID")
    return value.upper()


def audit_result(result: subprocess.CompletedProcess[str], expected: set[Pin]) -> set[Finding]:
    if result.returncode == INVALID_PYPI_RESPONSE:
        raise AuditError("could not verify PyPI release advisory data")
    if result.returncode not in (0, 1):
        raise AuditError(f"auditor exited with code {result.returncode}")
    data = json.loads(result.stdout, object_pairs_hook=_unique_json_object)
    if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
        raise AuditError("invalid auditor report")
    seen = set()
    findings = set()
    for item in data["dependencies"]:
        if not isinstance(item, dict):
            raise AuditError("invalid auditor dependency record")
        if "skip_reason" in item:
            raise AuditError("auditor skipped a dependency")
        pin = _pin(item.get("name"), item.get("version"))
        if pin not in expected or pin in seen:
            raise AuditError("auditor returned an unexpected or duplicate pin")
        seen.add(pin)
        vulns = item.get("vulns")
        if not isinstance(vulns, list):
            raise AuditError("invalid auditor advisory list")
        for record in vulns:
            if not isinstance(record, dict):
                raise AuditError("invalid auditor advisory record")
            findings.add((*pin, _advisory_id(record.get("id"))))
    if seen != expected:
        raise AuditError(f"auditor returned {len(seen)} of {len(expected)} expected pins")
    if result.returncode != int(bool(findings)):
        raise AuditError("auditor exit status disagrees with its advisory report")
    return findings


def read_exceptions(path: Path, today: date) -> set[Finding]:
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
    if not isinstance(data, dict) or set(data) != {"exceptions"} or not isinstance(data["exceptions"], list):
        raise AuditError("invalid exception policy")
    exceptions = set()
    for entry in data["exceptions"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != EXCEPTION_FIELDS
            or any(not isinstance(value, str) or not value.strip() for value in entry.values())
        ):
            raise AuditError("incomplete exception record")
        pin = _pin(entry["package"], entry["version"])
        key = (*pin, _advisory_id(entry["advisory"]))
        if key in exceptions:
            raise AuditError("duplicate advisory exception")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", entry["owner"]):
            raise AuditError("invalid exception owner")
        if not APPROVAL.fullmatch(entry["approval"]):
            raise AuditError("invalid exception approval reference")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", entry["expires"]):
            raise AuditError("invalid exception expiry date")
        try:
            expiry = date.fromisoformat(entry["expires"])
        except ValueError:
            raise AuditError("invalid exception expiry date") from None
        if expiry <= today:
            raise AuditError(f"expired exception for {pin[0]}=={pin[1]} {key[2]}")
        exceptions.add(key)
    return exceptions


def _validate_pypi_advisory(advisory: object) -> None:
    if not isinstance(advisory, dict):
        raise AuditError("invalid PyPI advisory list")
    _advisory_id(advisory.get("id"))

    aliases = advisory.get("aliases")
    if not isinstance(aliases, list):
        raise AuditError("invalid PyPI advisory aliases")
    for alias in aliases:
        _advisory_id(alias)

    fixes = advisory.get("fixed_in")
    if not isinstance(fixes, list) or any(not isinstance(version, str) for version in fixes):
        raise AuditError("invalid PyPI advisory fix versions")
    try:
        for version in fixes:
            Version(version)
    except InvalidVersion:
        raise AuditError("invalid PyPI advisory fix versions") from None

    withdrawn = advisory.get("withdrawn")
    if withdrawn is not None:
        # Warehouse emits a UTC timestamp. pip-audit skips on any non-null value.
        if not isinstance(withdrawn, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", withdrawn):
            raise AuditError("invalid PyPI advisory withdrawal timestamp")
        try:
            datetime.fromisoformat(withdrawn)
        except ValueError:
            raise AuditError("invalid PyPI advisory withdrawal timestamp") from None


def _validate_pypi_release(url: str, release: object) -> Pin:
    match = PYPI_RELEASE_URL.fullmatch(url)
    if match is None or not isinstance(release, dict):
        raise AuditError("invalid PyPI release response")
    info = release.get("info")
    advisories = release.get("vulnerabilities")
    if not isinstance(info, dict) or not isinstance(advisories, list):
        raise AuditError("incomplete PyPI release response")
    for advisory in advisories:
        _validate_pypi_advisory(advisory)
    expected_name, expected_version = _pin(*match.groups())
    name, version = _pin(info.get("name"), info.get("version"))
    if name != expected_name or Version(version) != Version(expected_version):
        raise AuditError("PyPI release does not match the requested pin")
    return expected_name, expected_version


def _run_pip_audit() -> int:
    # pip-audit 2.10.1 selects this factory in its CLI. Adapt its transport in
    # the child process so validation sees exactly the response it will use.
    from pip_audit import _cli

    if sys.argv[-2:-1] != ["-r"]:
        return INVALID_PYPI_RESPONSE
    expected = set()
    try:
        for line in Path(sys.argv[-1]).read_text(encoding="utf-8").splitlines():
            name, _, version = line.partition("==")
            expected.add(_pin(name, version))
    except AuditError, OSError, ValueError:
        return INVALID_PYPI_RESPONSE
    if not expected:
        return INVALID_PYPI_RESPONSE

    verified = set()
    original_service = _cli.PyPIService

    def validated_service(*, cache_dir, timeout):
        service = original_service(cache_dir=cache_dir, timeout=timeout)
        request = service.session.get

        def verified_get(*, url, timeout):
            response = request(url=url, timeout=timeout)
            if response.status_code < 400:
                if response.status_code != 200:
                    raise AuditError("unexpected PyPI release status")
                verified.add(_validate_pypi_release(url, response.json(object_pairs_hook=_unique_json_object)))
            return response

        service.session.get = verified_get
        return service

    _cli.PyPIService = validated_service
    exit_code = 0
    try:
        _cli.audit()
    except SystemExit as result:
        if result.code not in (None, 0, 1):
            raise
        exit_code = int(result.code or 0)
    except AuditError, ValueError, RecursionError:
        return INVALID_PYPI_RESPONSE
    finally:
        _cli.PyPIService = original_service
    # Reject a successful-looking report if the pinned CLI stops using our
    # factory or fails to validate a response for every pin in this batch.
    if verified != expected:
        return INVALID_PYPI_RESPONSE
    return exit_code


def scan(pins: set[Pin], temp: Path) -> set[Finding]:
    findings = set()
    for batch in pin_batches(pins):
        requirements = temp / "pins.txt"
        requirements.write_text(
            "".join(f"{name}=={version}\n" for name, version in sorted(batch)),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                "-P",
                str(Path(__file__).resolve()),
                "--pypi-audit-child",
                "--strict",
                "--no-deps",
                "--disable-pip",
                "--vulnerability-service",
                "pypi",
                "--timeout",
                "15",
                "--progress-spinner",
                "off",
                "--format",
                "json",
                "--cache-dir",
                str(temp / "cache"),
                "-r",
                str(requirements),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=600,
        )
        findings.update(audit_result(result, batch))
    return findings


def main() -> int:
    try:
        pins = read_lock(ROOT / "uv.lock")
        exceptions = read_exceptions(ROOT / ".github" / "dependency-audit-exceptions.json", datetime.now(UTC).date())
        with tempfile.TemporaryDirectory(prefix="optimus-dependency-audit-") as temp:
            findings = scan(pins, Path(temp))
    except AuditError as error:
        print(f"Dependency audit failed: {error}", file=sys.stderr)
        return 1
    except OSError, ValueError, RecursionError, subprocess.SubprocessError:
        print("Dependency audit failed: could not read, parse or complete the audit", file=sys.stderr)
        return 1

    unexcepted = findings - exceptions
    print(f"Dependency audit: {len(pins)} pins audited, {len(findings)} advisories, {len(findings & exceptions)} excepted")
    for name, version, advisory in sorted(unexcepted):
        print(f"Unexcepted advisory: {name}=={version} {advisory}", file=sys.stderr)
    return int(bool(unexcepted))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--pypi-audit-child"]:
        del sys.argv[1]
        raise SystemExit(_run_pip_audit())
    raise SystemExit(main())
