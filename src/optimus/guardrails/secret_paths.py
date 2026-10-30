"""The secret-path rule (#385): one predicate shared by model-issued file access (the permission guard's
``deny.path.secret``) and automatic workspace context, so a secret file is never read for the model either way.

A path is secret when any component is a credential name (``.env``, ``.pypirc``, ``.netrc``, SSH keys,
``credentials``, ``token``, ``secrets``), an ``.env.*`` variant (``.env.local``, ``.env.production``), or a
``*.pem`` / ``*.key`` file. Components compare case-insensitively.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

_SECRET_NAMES = frozenset({".env", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "credentials", "token", "secrets"})


def is_secret_path(path: str) -> bool:
    """Whether any component of ``path`` (either separator style) names a secret or credential file."""
    parts = PurePosixPath(path.replace("\\", "/")).as_posix().lower().split("/")
    return any(_is_secret_name(part) for part in parts)


def target_secret(target: Path, root: Path) -> bool:
    """Whether a resolved target is secret, judged from path metadata alone (its content is never opened). As with
    `runtime_tree.target_reserved`, a target inside the workspace is judged by its workspace-relative parts, so a
    workspace under an ancestor named like a secret keeps its files; a target outside it by its absolute parts."""
    try:
        relative = target.relative_to(root)
    except ValueError:
        return is_secret_path(target.as_posix())
    return is_secret_path(relative.as_posix())


def _is_secret_name(part: str) -> bool:
    return part in _SECRET_NAMES or part.startswith(".env.") or part.endswith((".pem", ".key"))
