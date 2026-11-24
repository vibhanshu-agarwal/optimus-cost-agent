import json
from datetime import date, datetime
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from tools import check_dependency_audit as audit


def report(*items, code=0):
    return CompletedProcess([], code, json.dumps({"dependencies": items, "fixes": []}), "")


def dependency(name="pillow", version="13.0.0", vulns=()):
    return {"name": name, "version": version, "vulns": list(vulns)}


@pytest.fixture
def lockfile(tmp_path):
    path = tmp_path / "uv.lock"
    path.write_text(
        'version = 1\n[[package]]\nname = "optimus-cost-agent"\n'
        'version = "0.1.0"\nsource = {editable = "."}\n'
        '[[package]]\nname = "pillow"\nversion = "13.0.0"\n'
        'source = {registry = "https://pypi.org/simple"}\n'
        '[[package]]\nname = "pillow"\nversion = "13.1.0"\n'
        "resolution-markers = [\"sys_platform == 'win32'\"]\n"
        'source = {registry = "https://pypi.org/simple"}\n'
        '[[package]]\nname = "colorama"\nversion = "0.4.6"\n'
        'source = {registry = "https://pypi.org/simple"}\n',
        encoding="utf-8",
    )
    return path


def test_lock_accounts_for_each_marker_specific_version(lockfile):
    pins = audit.read_lock(lockfile)
    assert pins == {("pillow", "13.0.0"), ("pillow", "13.1.0"), ("colorama", "0.4.6")}
    assert audit.pin_batches(pins) == [
        {("colorama", "0.4.6"), ("pillow", "13.0.0")},
        {("pillow", "13.1.0")},
    ]


@pytest.mark.parametrize(
    ("original", "replacement", "reason"),
    [
        ("pypi.org", "mirror.example", "source"),
        ('name = "optimus-cost-agent"', 'name = "other-project"', "source"),
        ('editable = "."', 'virtual = "."', "source"),
        ('editable = "."', 'editable = "other"', "source"),
        ('editable = "."', 'directory = "."', "source"),
        ('editable = "."', 'git = "https://example.org/project"', "source"),
        ('editable = "."', 'url = "https://example.org/project.whl"', "source"),
        ('source = {editable = "."}', "", "source"),
        ("version = 1", "version = 2", "format"),
    ],
)
def test_lock_rejects_unsupported_source_or_format(lockfile, original, replacement, reason):
    data = lockfile.read_text(encoding="utf-8").replace(original, replacement)
    lockfile.write_text(data, encoding="utf-8")
    with pytest.raises(audit.AuditError, match=reason):
        audit.read_lock(lockfile)


def test_lock_rejects_empty_public_inventory(lockfile):
    header, _, after_root = lockfile.read_text(encoding="utf-8").partition("[[package]]")
    local, _, _ = after_root.partition("[[package]]")
    lockfile.write_text(header + "[[package]]" + local, encoding="utf-8")
    with pytest.raises(audit.AuditError, match="empty public dependency inventory"):
        audit.read_lock(lockfile)


@pytest.mark.parametrize(
    "result",
    [
        report(),
        report({"name": "pillow", "skip_reason": "not on PyPI"}),
        report(dependency(), dependency()),
        report(dependency(), dependency("extra")),
        report(dependency("pillow", "13.1.0")),
        report(dependency(), code=1),
        report(dependency(vulns=[{"id": "PYSEC-2026-1"}]), code=0),
        report(dependency(vulns=[{"id": "garbage\ntext"}]), code=1),
        report({"name": "pillow", "version": "13.0.0"}),
        CompletedProcess([], 2, "", "upstream error"),
    ],
)
def test_incomplete_or_inconsistent_audit_fails_closed(result):
    with pytest.raises(audit.AuditError):
        audit.audit_result(result, {("pillow", "13.0.0")})


def test_audit_parses_clean_and_advisory_results():
    expected = {("pillow", "13.0.0")}
    assert not audit.audit_result(report(dependency()), expected)
    result = report(
        dependency(vulns=[{"id": "PYSEC-2026-1", "aliases": ["CVE-2026-1234"]}]),
        code=1,
    )
    assert audit.audit_result(result, expected) == {
        ("pillow", "13.0.0", "PYSEC-2026-1"),
    }


@pytest.fixture
def exception_record():
    return {
        "package": "pillow",
        "version": "13.0.0",
        "advisory": "PYSEC-2026-1",
        "owner": "vibhanshu-agarwal",
        "rationale": "A reviewed, bounded exception",
        "approval": "https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/700",
        "expires": "2026-12-01",
    }


def policy(tmp_path, *records):
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps({"exceptions": records}), encoding="utf-8")
    return path


def test_exact_pin_and_advisory_required(tmp_path, exception_record):
    today = date(2026, 11, 24)
    advisory = {("pillow", "13.0.0", "PYSEC-2026-1")}
    base = audit.read_exceptions(policy(tmp_path), today)
    assert advisory - base == advisory
    reviewed = audit.read_exceptions(policy(tmp_path, exception_record), today)
    assert not (advisory - reviewed)
    for field, value in [
        ("package", "colorama"),
        ("version", "13.1.0"),
        ("advisory", "PYSEC-2026-2"),
    ]:
        edited = exception_record | {field: value}
        exemptions = audit.read_exceptions(policy(tmp_path, edited), today)
        assert advisory - exemptions == advisory


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expires", "2026-11-24"),
        ("expires", "20261125"),
        ("expires", "2026-02-30"),
        ("owner", 42),
        ("owner", ""),
        ("rationale", " "),
        ("approval", "https://example.org/700"),
    ],
)
def test_exception_requires_current_review_metadata(tmp_path, exception_record, field, value):
    path = policy(tmp_path, exception_record | {field: value})
    with pytest.raises(audit.AuditError):
        audit.read_exceptions(path, date(2026, 11, 24))


def test_duplicate_exceptions_are_invalid(tmp_path, exception_record):
    normalized_duplicate = exception_record | {"package": "Pillow", "advisory": "pysec-2026-1"}
    path = policy(tmp_path, exception_record, normalized_duplicate)
    with pytest.raises(audit.AuditError, match="duplicate"):
        audit.read_exceptions(path, date(2026, 11, 24))


@pytest.mark.parametrize("field", ["owner", "extra"])
def test_exception_requires_exact_fields(tmp_path, exception_record, field):
    if field == "owner":
        del exception_record[field]
    else:
        exception_record[field] = "unexpected"
    with pytest.raises(audit.AuditError, match="incomplete"):
        audit.read_exceptions(policy(tmp_path, exception_record), date(2026, 11, 24))


@pytest.mark.parametrize(
    ("document", "reason"),
    [
        ('{"exceptions": [], "extra": true}', "invalid exception policy"),
        ('{"exceptions": [], "exceptions": []}', "duplicate JSON field"),
    ],
)
def test_exception_document_rejects_extra_or_duplicate_keys(tmp_path, document, reason):
    path = tmp_path / "exceptions.json"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(audit.AuditError, match=reason):
        audit.read_exceptions(path, date(2026, 11, 24))


@pytest.fixture
def exception_path(lockfile, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", lockfile.parent)
    directory = lockfile.parent / ".github"
    directory.mkdir()
    return directory / "dependency-audit-exceptions.json"


def test_cli_audits_all_batches_and_keeps_vendor_output_private(exception_path, monkeypatch, capsys):
    exception_path.write_text('{"exceptions": []}', encoding="utf-8")
    calls = []

    def fake_auditor(command, **kwargs):
        assert {"--strict", "--no-deps", "--disable-pip"} <= set(command)
        assert kwargs["capture_output"]
        pins = audit.Path(command[-1]).read_text(encoding="utf-8").splitlines()
        calls.append(pins)
        if len(calls) == 1:
            return report(dependency(), dependency("colorama", "0.4.6"))
        response = report(dependency(version="13.1.0", vulns=[{"id": "PYSEC-2026-1"}]), code=1)
        response.stderr = "raw upstream message"
        return response

    monkeypatch.setattr(audit.subprocess, "run", fake_auditor)
    assert audit.main() == 1
    assert calls == [["colorama==0.4.6", "pillow==13.0.0"], ["pillow==13.1.0"]]
    captured = capsys.readouterr()
    assert "3 pins audited, 1 advisories, 0 excepted" in captured.out
    assert captured.err == "Unexcepted advisory: pillow==13.1.0 PYSEC-2026-1\n"


@pytest.mark.parametrize("has_unexcepted", [False, True])
def test_cli_applies_only_the_reviewed_exception(exception_path, exception_record, monkeypatch, capsys, has_unexcepted):
    class FrozenTime:
        @staticmethod
        def now(tz):
            return datetime(2000, 1, 1, tzinfo=tz)

    monkeypatch.setattr(audit, "datetime", FrozenTime)
    reviewed_exception = exception_record | {"expires": "2000-01-02"}
    exception_path.write_text(json.dumps({"exceptions": [reviewed_exception]}), encoding="utf-8")
    findings = {("pillow", "13.0.0", "PYSEC-2026-1")}
    if has_unexcepted:
        findings.add(("pillow", "13.1.0", "PYSEC-2026-1"))
    monkeypatch.setattr(audit, "scan", lambda *_: findings)

    assert audit.main() == int(has_unexcepted)
    captured = capsys.readouterr()
    assert f"3 pins audited, {len(findings)} advisories, 1 excepted" in captured.out
    assert captured.err == ("Unexcepted advisory: pillow==13.1.0 PYSEC-2026-1\n" if has_unexcepted else "")


@pytest.mark.parametrize("decoder_recursion", [False, True], ids=["invalid-json", "decoder-recursion"])
def test_cli_rejects_unreadable_auditor_output(exception_path, monkeypatch, capsys, decoder_recursion):
    exception_path.write_text('{"exceptions": []}', encoding="utf-8")
    malformed = "private malformed response"
    if decoder_recursion:

        def loads(raw, **kwargs):
            if raw == malformed:
                raise RecursionError("private decoder exception")
            return json.loads(raw, **kwargs)

        monkeypatch.setattr(audit, "json", SimpleNamespace(loads=loads))
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *_, **__: CompletedProcess([], 0, malformed, ""),
    )
    assert audit.main() == 1
    assert capsys.readouterr().err == ("Dependency audit failed: could not read, parse or complete the audit\n")
