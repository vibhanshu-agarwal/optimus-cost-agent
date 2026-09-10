"""R16-B: the authenticated historical source snapshot -- provenance, dispatch, and refusals.

These controls run WITHOUT the historical Git object: the snapshot must supply exactly the declared
paths with a verified commit -> tree -> blob chain, refuse every tampering the review enumerated, and
never fall back to (or require) a live repository. Representation v2: the manifest carries no digests, so
every blob id below is DERIVED from the verified tree chain (``verify_all``), never read from scanned text.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.plan1126_runtime_audit import historical_source as hs
from tools.plan1126_runtime_audit.source import GitCommitSource

ROOT = Path(__file__).resolve().parents[4]
OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"  # pragma: allowlist secret - historical commit-identity pin
IDENTITY = hs.HISTORICAL_SNAPSHOTS[OVERLAY]
FIXTURE = ROOT / "tests" / "fixtures" / "plan1126_runtime_audit" / "historical-source" / OVERLAY


def _snapshot() -> hs.HistoricalSourceSnapshot:
    return hs.HistoricalSourceSnapshot(IDENTITY)


def _manifest() -> dict:
    return json.loads((FIXTURE / "manifest.json").read_bytes().replace(b"\r\n", b"\n").decode("utf-8"))


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "historical-source"
    shutil.copytree(FIXTURE, root / OVERLAY)
    return root


def _blob_ids() -> dict[str, str]:
    """path -> blob id, DERIVED from the verified chain (the manifest carries none)."""
    return _snapshot().verify_all()


def _write_object(root: Path, object_id: str, content: bytes) -> None:
    (root / OVERLAY / "objects" / f"{object_id}.b64").write_bytes(base64.b64encode(content) + b"\n")


# --- positive provenance ------------------------------------------------------------------


def test_the_snapshot_resolves_every_declared_path_with_a_verified_chain() -> None:
    snapshot = _snapshot()
    verified = snapshot.verify_all()
    manifest = _manifest()
    assert set(verified) == set(manifest["files"]) and len(verified) == 42
    digest = hashlib.sha256()
    for path in sorted(verified):
        data = snapshot.read_bytes(path)
        assert hs._git_object_id("blob", data) == verified[path]
        assert len(data) == manifest["files"][path]["size"] and manifest["files"][path]["mode"] == "100644"
        digest.update(path.encode("utf-8") + b"\0" + data + b"\0")
    assert digest.hexdigest() == IDENTITY.content_sha256
    assert snapshot.commit == OVERLAY


def test_the_manifest_carries_no_digests() -> None:
    """Identity lives in code: no object id or digest appears in any scanned text file of the fixture."""
    manifest = _manifest()
    assert set(manifest) == {"schema", "scope", "files", "object_count"}
    assert all(set(row) == {"mode", "size"} for row in manifest["files"].values())
    assert not re.search(r"[0-9a-f]{40}", (FIXTURE / "manifest.json").read_text(encoding="utf-8"))


def test_the_snapshot_is_pinned_in_code_not_in_its_own_manifest() -> None:
    manifest_bytes = (FIXTURE / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(manifest_bytes).hexdigest() == IDENTITY.manifest_sha256
    commit = base64.b64decode((FIXTURE / "objects" / f"{OVERLAY}.b64").read_bytes().strip(), validate=True)
    assert hs._git_object_id("commit", commit) == OVERLAY
    assert commit.startswith(b"tree " + IDENTITY.tree.encode("ascii"))


def test_read_text_normalizes_only_line_endings() -> None:
    snapshot = _snapshot()
    path = "src/optimus/acp/__main__.py"
    assert "\r" not in snapshot.read_text(path)
    assert snapshot.read_text(path).encode("utf-8") == snapshot.read_bytes(path).replace(b"\r\n", b"\n")


def test_the_snapshot_never_requires_the_historical_git_object(tmp_path: Path) -> None:
    """The load path performs no Git resolution: an empty repository with no objects serves it identically."""
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    assert subprocess.run(["git", "cat-file", "-t", OVERLAY], cwd=repo, capture_output=True).returncode != 0
    served = hs.historical_source(OVERLAY, repository=repo)
    assert isinstance(served, hs.HistoricalSourceSnapshot)
    assert served.verify_all() == _snapshot().verify_all()
    assert served.read_text("src/optimus/acp/server.py") == _snapshot().read_text("src/optimus/acp/server.py")


# --- explicit dispatch ----------------------------------------------------------------------


def test_dispatch_is_by_pinned_identity_only(tmp_path: Path) -> None:
    """A commit that is not a pinned identity stays on the strict Git path; an unresolvable one fails there
    (exit 128 from git rev-parse) and is never rescued by a snapshot."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    with pytest.raises(subprocess.CalledProcessError):
        hs.historical_source("0" * 40, repository=repo)
    with pytest.raises(subprocess.CalledProcessError):
        hs.historical_source("fac32284888850bacde93815265cbabe3afd4664", repository=repo)  # pragma: allowlist secret - one hex digit off the pin
    assert isinstance(hs.historical_source(OVERLAY.upper(), repository=repo), hs.HistoricalSourceSnapshot)


def test_a_live_commit_still_uses_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "m"], cwd=repo, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    assert isinstance(hs.historical_source(head, repository=repo), GitCommitSource)


# --- refusals --------------------------------------------------------------------------------


def test_out_of_scope_and_escaping_paths_are_refused() -> None:
    snapshot = _snapshot()
    for bad in ("src/optimus/acp/not_in_scope.py", "pyproject.toml", "../src/optimus/acp/server.py", "/etc/passwd", "src/optimus/acp/../acp/server.py", ""):
        with pytest.raises(hs.HistoricalSourceError):
            snapshot.read_text(bad)


def test_tampered_blob_bytes_are_refused_even_with_a_recomputed_manifest_digest(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    manifest = _manifest()
    path = "src/optimus/acp/server.py"
    blob_id = _blob_ids()[path]
    original = base64.b64decode((root / OVERLAY / "objects" / f"{blob_id}.b64").read_bytes().strip(), validate=True)
    tampered = original + b"\n# tampered\n"
    _write_object(root, blob_id, tampered)
    # Even an attacker who rewrites the manifest's size to the tampered bytes is refused: the manifest
    # hash is pinned in code, and the blob no longer hashes to the tree entry's id.
    manifest["files"][path]["size"] = len(tampered)
    (root / OVERLAY / "manifest.json").write_bytes(json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8") + b"\n")
    with pytest.raises(hs.HistoricalSourceError, match="pinned identity"):
        hs.HistoricalSourceSnapshot(IDENTITY, root=root)
    # And with the ORIGINAL manifest (pin intact) the tampered object itself is refused at resolution.
    shutil.copy(FIXTURE / "manifest.json", root / OVERLAY / "manifest.json")
    snapshot = hs.HistoricalSourceSnapshot(IDENTITY, root=root)
    with pytest.raises(hs.HistoricalSourceError, match="does not hash to its id"):
        snapshot.read_text(path)


def test_swapped_proof_is_refused(tmp_path: Path) -> None:
    """Two real blobs swapped under each other's ids: both are genuine objects, neither matches its path."""
    root = _copy_fixture(tmp_path)
    ids = _blob_ids()
    a, b = "src/optimus/acp/server.py", "src/optimus/acp/bootstrap.py"
    ida, idb = ids[a], ids[b]
    pa, pb = root / OVERLAY / "objects" / f"{ida}.b64", root / OVERLAY / "objects" / f"{idb}.b64"
    da, db = pa.read_bytes(), pb.read_bytes()
    pa.write_bytes(db)
    pb.write_bytes(da)
    snapshot = hs.HistoricalSourceSnapshot(IDENTITY, root=root)
    with pytest.raises(hs.HistoricalSourceError, match="does not hash to its id"):
        snapshot.read_text(a)


def test_an_omitted_object_is_refused(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    path = "src/optimus/redis/runtime.py"
    (root / OVERLAY / "objects" / f"{_blob_ids()[path]}.b64").unlink()
    snapshot = hs.HistoricalSourceSnapshot(IDENTITY, root=root)
    with pytest.raises(hs.HistoricalSourceError, match="snapshot file missing"):
        snapshot.read_text(path)
    # an omitted TREE on the chain breaks every path below it
    tree_id = IDENTITY.tree
    (root / OVERLAY / "objects" / f"{tree_id}.b64").unlink()
    with pytest.raises(hs.HistoricalSourceError, match="snapshot file missing"):
        hs.HistoricalSourceSnapshot(IDENTITY, root=root).read_text("src/optimus/acp/server.py")


def test_a_commit_object_naming_another_tree_is_refused(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    forged = b"tree " + ("0" * 40).encode() + b"\nauthor x <x> 0 +0000\ncommitter x <x> 0 +0000\n\nforged\n"
    _write_object(root, OVERLAY, forged)  # its id no longer matches the pinned commit id
    with pytest.raises(hs.HistoricalSourceError, match="does not hash to its id"):
        hs.HistoricalSourceSnapshot(IDENTITY, root=root)


def test_unknown_identity_has_no_snapshot(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    other = hs.SnapshotIdentity(commit="1" * 40, tree=IDENTITY.tree, manifest_sha256=IDENTITY.manifest_sha256, content_sha256=IDENTITY.content_sha256, directory=OVERLAY)
    with pytest.raises(hs.HistoricalSourceError, match="snapshot file missing"):
        hs.HistoricalSourceSnapshot(other, root=root)


def test_a_wrong_content_pin_is_refused_before_any_byte_is_served(tmp_path: Path) -> None:
    """The SHA-256 content pin binds the whole scope independently of Git's SHA-1 chain."""
    root = _copy_fixture(tmp_path)
    other = hs.SnapshotIdentity(commit=OVERLAY, tree=IDENTITY.tree, manifest_sha256=IDENTITY.manifest_sha256, content_sha256="0" * 64, directory=OVERLAY)
    snapshot = hs.HistoricalSourceSnapshot(other, root=root)  # chain verification alone still passes
    with pytest.raises(hs.HistoricalSourceError, match="content digest"):
        snapshot.read_text("src/optimus/acp/server.py")
    with pytest.raises(hs.HistoricalSourceError, match="content digest"):
        snapshot.verify_all()


def test_the_snapshot_is_data_never_executed() -> None:
    """The archived modules are read as text only: nothing under the fixture is importable or a package."""
    assert not any(p.suffix == ".py" for p in (FIXTURE / "objects").iterdir())
    assert not (FIXTURE / "__init__.py").exists() and not (FIXTURE / "objects" / "__init__.py").exists()
