"""CLI argv must never carry the store admin password."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _roots(tmp_path: Path) -> dict[str, Path]:
    roots = {
        "control": tmp_path / "control",
        "capture": tmp_path / "capture",
        "staging": tmp_path / "staging",
        "quarantine": tmp_path / "quarantine",
        "forbidden": tmp_path / "forbidden",
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    return roots


def test_parser_rejects_raw_admin_password_flag() -> None:
    from evidence_handoff_runtime.lifecycle_cli import _build_parser

    parser = _build_parser()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--admin-password" not in option_strings
    assert "--admin-password-file" in option_strings


def test_status_reads_password_file_and_keeps_secret_out_of_argv(tmp_path: Path, capsys) -> None:
    from evidence_handoff_runtime import lifecycle_cli

    roots = _roots(tmp_path)
    password = "cli-admin-password-canary-value"
    password_file = tmp_path / "admin.password"
    password_file.write_text(password + "\n", encoding="utf-8")

    argv = [
        "status",
        "--control-root",
        str(roots["control"]),
        "--lock-path",
        str(tmp_path / "lifecycle.lock"),
        "--capture-root",
        str(roots["capture"]),
        "--staging-root",
        str(roots["staging"]),
        "--quarantine-root",
        str(roots["quarantine"]),
        "--forbidden-root",
        str(roots["forbidden"]),
        "--admin-password-file",
        str(password_file),
    ]
    assert password not in argv
    assert password not in " ".join(argv)

    code = lifecycle_cli.main(argv)
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["summary_code"] == "feature_disabled_operator_relay"
    assert password not in captured.out
    assert password not in captured.err
    assert password not in argv


def test_missing_password_file_fails_closed(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle_cli import main

    roots = _roots(tmp_path)
    argv = [
        "status",
        "--control-root",
        str(roots["control"]),
        "--lock-path",
        str(tmp_path / "lifecycle.lock"),
        "--capture-root",
        str(roots["capture"]),
        "--staging-root",
        str(roots["staging"]),
        "--quarantine-root",
        str(roots["quarantine"]),
        "--forbidden-root",
        str(roots["forbidden"]),
        "--admin-password-file",
        str(tmp_path / "missing.password"),
    ]
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code != 0


def _required_status_argv(tmp_path: Path, password_file: Path, *extra: str) -> list[str]:
    roots = _roots(tmp_path)
    return [
        "status",
        "--control-root",
        str(roots["control"]),
        "--lock-path",
        str(tmp_path / "lifecycle.lock"),
        "--capture-root",
        str(roots["capture"]),
        "--staging-root",
        str(roots["staging"]),
        "--quarantine-root",
        str(roots["quarantine"]),
        "--forbidden-root",
        str(roots["forbidden"]),
        "--admin-password-file",
        str(password_file),
        *extra,
    ]


def test_parser_exposes_explicit_backend_id_defaulting_to_docker(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle_cli import _build_parser

    parser = _build_parser()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--backend-id" in option_strings

    password_file = tmp_path / "admin.password"
    password_file.write_text("cli-admin-password-canary-value\n", encoding="utf-8")
    args = parser.parse_args(_required_status_argv(tmp_path, password_file))
    assert args.backend_id == "docker"


def test_parser_accepts_only_implemented_docker_backend_id(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle_cli import _build_parser

    parser = _build_parser()
    password_file = tmp_path / "admin.password"
    password_file.write_text("cli-admin-password-canary-value\n", encoding="utf-8")

    accepted = parser.parse_args(_required_status_argv(tmp_path, password_file, "--backend-id", "docker"))
    assert accepted.backend_id == "docker"

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(_required_status_argv(tmp_path, password_file, "--backend-id", "wslc"))
    assert raised.value.code != 0

    with pytest.raises(SystemExit) as raised_unknown:
        parser.parse_args(
            _required_status_argv(tmp_path, password_file, "--backend-id", "native-windows")
        )
    assert raised_unknown.value.code != 0
