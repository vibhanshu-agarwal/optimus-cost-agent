"""What files the memory store's data directory holds, for a purge's disk step (Plan 12.11; Codex CP2 review 1, finding 2).

Redis reports a rewrite and a snapshot as done even when it could not delete an old AOF file, so counters alone never prove
that purged text left the declared boundary. After both have run, the directory must hold only what the current AOF manifest
names (no history file), the snapshot and the AOF directory: anything else may still hold the text, and the purge stays
pending. The inventory is read through the local Docker engine from the provisioned container, which must carry the
configured resource label and publish the configured port.

A Redis killed mid-fork leaves the fork's temporary file behind, and the next server never removes another process's (found on
the real store in the CP2 rerun on 1051ae5): a purge after such a crash would stay pending forever. So the Gateway removes such a
file only on evidence that Redis made it and that nothing uses it any more (Codex CP2 review 2, findings 1 and 4): see `abandoned`.
Nothing else is ever removed. Names are listed NUL-delimited with their type and owner, so no name can pass for another (finding 3).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from optimus_security.memory_store_config import MemoryStoreConfig

RESOURCE_LABEL: Final = "optimus.memory.resource"  # the label local_infra puts on the container it provisions
_DATA: Final = "/data"
_AOF_DIR: Final = "appendonlydir"
_SNAPSHOT: Final = "dump.rdb"
_SEPARATOR: Final = "\0--optimus-inventory--\0"
# A snapshot or rewrite fork's working file, named by the fork's process id; only these are ever removed.
_REDIS_TEMP: Final = re.compile(r"temp-(?P<rdb>\d+)\.rdb|temp-rewriteaof-(?:bg-)?(?P<aof>\d+)\.aof")


@dataclass(frozen=True)
class Entry:
    kind: str  # find's %y: "f" a regular file, "d" a directory, anything else is neither
    owner: str  # the owning uid
    path: str  # relative to the data directory, as listed (any bytes but NUL and "/")


@dataclass(frozen=True)
class Inventory:
    entries: tuple[Entry, ...]  # everything in the data directory and one level below it
    pids: frozenset[str]  # the processes alive in the container when it was listed
    manifest: str  # the AOF manifest's text


class InventoryUnavailable(Exception):
    """The files could not be listed: the disk step cannot be shown complete."""


def residue(inventory: Inventory) -> str | None:
    """Why the files may still hold deleted text, or None when they hold only the current snapshot and AOF set."""
    top = {entry.path: entry.kind for entry in inventory.entries if "/" not in entry.path}
    if set(top) - {_SNAPSHOT, _AOF_DIR} or top.get(_AOF_DIR) != "d" or top.get(_SNAPSHOT, "f") != "f":
        return "unexpected_files"  # a leftover temporary snapshot or rewrite file, or anything else
    aof = [entry for entry in inventory.entries if "/" in entry.path]
    if any(entry.kind != "f" or not entry.path.startswith(_AOF_DIR + "/") for entry in aof):
        return "unexpected_files"
    listed: set[str] = set()
    for line in inventory.manifest.splitlines():
        fields = line.split()
        if not fields:
            continue
        entry = dict(zip(fields[::2], fields[1::2], strict=False))
        if "file" not in entry or entry.get("type") not in ("b", "i", "h"):
            return "manifest_unreadable"
        if entry["type"] == "h":
            return "history_files"  # Redis kept a superseded file in its manifest
        listed.add(entry["file"])
    if not listed:
        return "manifest_unreadable"
    names = {entry.path.removeprefix(_AOF_DIR + "/") for entry in aof}
    manifests = {name for name in names if name.endswith(".manifest")}
    if len(manifests) != 1 or names - manifests - listed:
        return "retained_files"  # an old base or increment the rewrite left behind, or a file Redis does not name
    return None


def abandoned(inventory: Inventory) -> tuple[str, ...]:
    """The fork working files a Redis that died left behind: a regular file directly under the data directory, under the name
    Redis gives a snapshot or rewrite fork's working file, owned by the user that owns the AOF manifest (the server's), whose
    fork's process is gone. A file anyone else made, or one a fork could still be writing, is never chosen. The caller removes
    these only while Redis reports no fork. A new fork that reuses the dead one's process id between that check and the removal
    only loses its own unfinished file: Redis renames it in only when the fork finishes, so that fork fails and the next disk
    step starts another; no file Redis has started to use is affected. AOF parts are never removed: Redis may reuse an unlisted
    one's name (finding 1), so one stays residue."""
    manifests = [entry for entry in inventory.entries if entry.path.startswith(_AOF_DIR + "/") and entry.path.endswith(".manifest")]
    if len(manifests) != 1:
        return ()
    found = []
    for entry in inventory.entries:
        match = _REDIS_TEMP.fullmatch(entry.path)
        if match and entry.kind == "f" and entry.owner == manifests[0].owner and (match["rdb"] or match["aof"]) not in inventory.pids:
            found.append(entry.path)
    return tuple(found)


def parse(output: str) -> Inventory:
    parts = output.split(_SEPARATOR)
    if len(parts) != 4 or parts[0]:
        raise InventoryUnavailable("unparsable listing")
    _, listing, pids, manifest = parts
    entries = []
    for record in listing.split("\0"):
        if record:
            kind, owner, path = record.split(" ", 2)  # a malformed record is a ValueError: the listing is unusable
            entries.append(Entry(kind, owner, path))
    return Inventory(tuple(entries), frozenset(pid for pid in pids.split("\0") if pid), manifest)


def docker_inventory(config: MemoryStoreConfig) -> Callable[[float, tuple[str, ...]], Inventory]:
    """An inventory of the provisioned container's data directory, read with `docker exec`, each step within `timeout`. The
    `remove` paths (relative to the data directory, from `abandoned`) are deleted first, passed as arguments, never as script."""

    def read(timeout: float, remove: tuple[str, ...]) -> Inventory:
        docker = shutil.which("docker")
        if docker is None:
            raise InventoryUnavailable("docker not found")
        try:
            view = subprocess.run([docker, "inspect", "--type", "container", config.container],
                                  capture_output=True, text=True, check=False, timeout=timeout)
            details = json.loads(view.stdout)[0] if view.returncode == 0 else None
            if details is None or (details.get("Config") or {}).get("Labels", {}).get(RESOURCE_LABEL) != config.resource:
                raise InventoryUnavailable("not the provisioned container")
            bindings = (details.get("HostConfig") or {}).get("PortBindings") or {}
            if not any(str(binding.get("HostPort")) == str(config.port) for spec in bindings.values() for binding in spec or ()):
                raise InventoryUnavailable("container does not publish the configured port")
            mark = r"printf '\0--optimus-inventory--\0'"  # the shell's printf writes the NULs; argv cannot hold one
            script = (f'cd {_DATA} && {{ [ "$#" -eq 0 ] || rm -f -- "$@"; }} && {mark} && '
                      rf"find {_DATA} -mindepth 1 -maxdepth 2 -printf '%y %U %P\0' && {mark} && "
                      rf"find /proc -mindepth 1 -maxdepth 1 -name '[0-9]*' -printf '%f\0' && {mark} && cat {_DATA}/{_AOF_DIR}/*.manifest")
            listing = subprocess.run([docker, "exec", config.container, "sh", "-c", script, "sh", *remove],
                                     capture_output=True, encoding="utf-8", errors="replace", check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError, AttributeError) as exc:
            raise InventoryUnavailable(type(exc).__name__) from None
        if listing.returncode != 0:
            raise InventoryUnavailable("listing failed")
        return parse(listing.stdout)

    return read
