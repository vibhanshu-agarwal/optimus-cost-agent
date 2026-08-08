"""Immutable migration manifest and PostgreSQL applicator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_ROOT = REPO_ROOT / "migrations" / "evidence_handoff"

# Digests are pinned to committed SQL bytes. Changing a migration requires a new file.
_PINNED: tuple[tuple[str, str], ...] = (
    (
        "001_ledger_v1.sql",
        "bd0851fa6be469d545a05b4fa352f16605bcaa840ac633c18d3adebb52f80ee1",
    ),
    (
        "002_sequence_unique_per_instance.sql",
        "ebacad0524aa02420eafbdcc0c9f640ad90bed65f72745064520360ffa695489",
    ),
)


class MigrationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"MigrationError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class MigrationEntry:
    filename: str
    sha256: str


@dataclass(frozen=True, slots=True)
class MigrationManifest:
    entries: tuple[MigrationEntry, ...]

    @staticmethod
    def digest_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def load(cls) -> MigrationManifest:
        entries = tuple(MigrationEntry(filename=name, sha256=digest) for name, digest in _PINNED)
        manifest = cls(entries=entries)
        manifest.verify()
        return manifest

    def verify(self) -> None:
        for entry in self.entries:
            path = MIGRATIONS_ROOT / entry.filename
            if not path.is_file():
                raise MigrationError("migration_file_missing")
            actual = self.digest_file(path)
            if actual != entry.sha256:
                raise MigrationError("migration_digest_mismatch")


def apply_migrations(conninfo: str) -> MigrationManifest:
    manifest = MigrationManifest.load()
    with psycopg.connect(conninfo) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_handoff_schema_migrations (
                filename TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for entry in manifest.entries:
            existing = conn.execute(
                "SELECT sha256 FROM evidence_handoff_schema_migrations WHERE filename = %s",
                (entry.filename,),
            ).fetchone()
            if existing is not None:
                if existing[0] != entry.sha256:
                    raise MigrationError("migration_digest_mismatch")
                continue
            sql = (MIGRATIONS_ROOT / entry.filename).read_text(encoding="utf-8")
            for statement in _split_sql_statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO evidence_handoff_schema_migrations(filename, sha256) VALUES (%s, %s)",
                (entry.filename, entry.sha256),
            )
        conn.commit()
    return manifest


def _split_sql_statements(sql: str) -> list[str]:
    """Split on semicolons outside dollar-quoted or single-quoted strings."""
    statements: list[str] = []
    buffer: list[str] = []
    in_dollar = False
    in_single = False
    i = 0
    length = len(sql)
    while i < length:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < length else ""
        if not in_single and sql.startswith("$$", i):
            in_dollar = not in_dollar
            buffer.append("$$")
            i += 2
            continue
        if not in_dollar and ch == "'" and not in_single:
            in_single = True
            buffer.append(ch)
            i += 1
            continue
        if in_single and ch == "'" and nxt == "'":
            buffer.append("''")
            i += 2
            continue
        if in_single and ch == "'":
            in_single = False
            buffer.append(ch)
            i += 1
            continue
        if ch == ";" and not in_dollar and not in_single:
            statement = "".join(buffer).strip()
            if statement and not all(
                line.strip().startswith("--") or not line.strip() for line in statement.splitlines()
            ):
                # Drop pure-comment lines but keep SQL.
                cleaned_lines = [
                    line for line in statement.splitlines() if line.strip() and not line.strip().startswith("--")
                ]
                cleaned = "\n".join(cleaned_lines).strip()
                if cleaned:
                    statements.append(cleaned)
            buffer = []
            i += 1
            continue
        buffer.append(ch)
        i += 1
    trailing = "".join(buffer).strip()
    if trailing:
        cleaned_lines = [
            line for line in trailing.splitlines() if line.strip() and not line.strip().startswith("--")
        ]
        cleaned = "\n".join(cleaned_lines).strip()
        if cleaned:
            statements.append(cleaned)
    return statements


__all__ = [
    "MIGRATIONS_ROOT",
    "MigrationEntry",
    "MigrationError",
    "MigrationManifest",
    "apply_migrations",
]
