"""What files the memory store's data directory holds, for a purge's disk step (Plan 12.11; Codex CP2 review 1, finding 2).

Redis reports a rewrite and a snapshot as done even when it could not delete an old AOF file, so counters alone never prove
that purged text left the declared boundary. After both have run, the directory must hold only what the current AOF manifest
names (no history file), the snapshot and the AOF directory: anything else may still hold the text, and the purge stays
pending. The inventory is read through the local Docker engine from the provisioned container, which must carry the
configured resource label and publish the configured port.

Nothing is ever removed (Codex CP2 review 3, finding 2): no listing can show that Redis made a file and has retired it, so a
fork's working file that a killed Redis left behind holds the purge pending, with its reason, until the operator removes it.
Names are listed NUL-delimited with their type (review 2, finding 3), and a listing that is not exactly what `find` and the
manifest produce is unavailable, never clean (review 3, finding 4).
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
_RECORD = re.compile(r"([a-zA-Z?]) ((?:[^/\0]+/)?[^/\0]+)")  # find's %y, a space, then one or two path segments
_FIELD = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Entry:
    kind: str  # find's %y: "f" a regular file, "d" a directory, anything else is neither
    path: str  # relative to the data directory, as listed (any bytes but NUL and "/")


@dataclass(frozen=True)
class Inventory:
    entries: tuple[Entry, ...]  # everything in the data directory and one level below it, each path once
    manifest: str  # the AOF manifest's text


class InventoryUnavailable(Exception):
    """The files could not be listed, or the listing is malformed: the disk step cannot be shown complete."""


def residue(inventory: Inventory) -> str | None:
    """Why the files may still hold deleted text, or None when they hold only the current snapshot and AOF set."""
    top = {entry.path: entry.kind for entry in inventory.entries if "/" not in entry.path}
    if set(top) - {_SNAPSHOT, _AOF_DIR} or top.get(_AOF_DIR) != "d" or top.get(_SNAPSHOT, "f") != "f":
        return "unexpected_files"  # a fork's working file a killed Redis left behind, or anything else
    aof = [entry for entry in inventory.entries if "/" in entry.path]
    if any(entry.kind != "f" or not entry.path.startswith(_AOF_DIR + "/") for entry in aof):
        return "unexpected_files"
    listed: set[str] = set()
    for line in inventory.manifest.splitlines():
        fields = line.split()
        if not fields:
            continue
        keys = fields[::2]
        if len(fields) % 2 or len(set(keys)) != len(keys) or not all(_FIELD.fullmatch(key) for key in keys):
            return "manifest_unreadable"  # a field without its value, or one twice: not the manifest Redis writes
        entry = dict(zip(keys, fields[1::2], strict=True))
        if "file" not in entry or "/" in entry["file"] or entry.get("type") not in ("b", "i", "h") or not entry.get("seq", "").isdigit():
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


def parse(output: str) -> Inventory:
    """The listing `docker_inventory` reads, checked whole: its framing, every record terminated and well formed, each path
    once. Anything else is InventoryUnavailable."""
    parts = output.split(_SEPARATOR)
    if len(parts) != 3 or parts[0] or not parts[1].endswith("\0"):
        raise InventoryUnavailable("unparsable listing")
    entries = []
    for record in parts[1][:-1].split("\0"):
        match = _RECORD.fullmatch(record)
        if match is None:
            raise InventoryUnavailable("malformed listing record")
        entries.append(Entry(match[1], match[2]))
    if len({entry.path for entry in entries}) != len(entries):
        raise InventoryUnavailable("a path listed twice")
    return Inventory(tuple(entries), parts[2])


def docker_inventory(config: MemoryStoreConfig) -> Callable[[float], Inventory]:
    """An inventory of the provisioned container's data directory, read with `docker exec`, each step within `timeout`."""

    def read(timeout: float) -> Inventory:
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
            script = (rf"{mark} && find {_DATA} -mindepth 1 -maxdepth 2 -printf '%y %P\0' && {mark} && "
                      f"cat {_DATA}/{_AOF_DIR}/*.manifest")
            listing = subprocess.run([docker, "exec", config.container, "sh", "-c", script],
                                     capture_output=True, encoding="utf-8", errors="replace", check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError, AttributeError) as exc:
            raise InventoryUnavailable(type(exc).__name__) from None
        if listing.returncode != 0:
            raise InventoryUnavailable("listing failed")
        return parse(listing.stdout)

    return read
