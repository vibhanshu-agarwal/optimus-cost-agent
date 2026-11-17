# Memory purge held pending by the data directory

A memory purge completes only when the memory store's data directory holds nothing but Redis's current snapshot and AOF
set. When anything else is there, the Gateway leaves the purge `pending` and its `purge_status` reply says why:

```json
{"purge_state": "pending", "files": "unexpected_files", "blocking": ["temp-4242.rdb"], "next": "inspect_data_files",
 "runbook": "docs/runbooks/memory-purge-pending-files.md"}
```

`blocking` holds display labels: at most 16, with non-printable characters shown as `?` and each cut at 200 characters.
Never use one as a file name. Take exact entries from the listing in step 3.

The Gateway never removes a file itself, because no listing can prove a file is one Redis made and has finished with. That
check is yours. While Redis runs it may reuse a file name between your check and your removal: it opens its next increment
with truncate-and-create and only then publishes it in the manifest. So everything below happens with **the store
stopped**. Until a blocking file is gone it may still hold the purged text.

## 1. Find the store

The non-secret store facts are in `<config_root>/memory-store/memory-store.json`. Read `container`, `volume`, `image` and
`resource` from it. Then confirm that the container is the one Optimus provisioned. This command only reads:

```bash
docker inspect --format '{{index .Config.Labels "optimus.memory.resource"}}' <container>
```

The label must equal `resource`. If it does not, stop: this is not the store's container.

## 2. Stop the store

```bash
docker stop <container>
```

Memory is unavailable until step 5: the Gateway answers `MEMORY_UNAVAILABLE`, and nothing is lost. With Redis stopped,
nothing writes to the volume, so nothing you check below can change before you act on it.

## 3. Look at what is there

Use a one-off container on the store's volume, with the store's own image:

```bash
docker run --rm -v <volume>:/data <image> find /data -mindepth 1 -maxdepth 2 -printf '%i %y %s %TY-%Tm-%TdT%TT %P\n'
```

```bash
docker run --rm -v <volume>:/data <image> sh -c 'cat /data/appendonlydir/*.manifest'
```

Each line gives the entry's inode number, type, size, modification time and path relative to `/data`. Find each
`blocking` label among them.

## 4. Decide, by reason

| `files` | What it means | What to do |
|---|---|---|
| `unexpected_files` | A name other than `dump.rdb` and `appendonlydir` at the top, or something that is not a regular file. `temp-<pid>.rdb`, `temp-rewriteaof-<pid>.aof` and `temp-rewriteaof-bg-<pid>.aof` are a snapshot's or rewrite's working files, which a Redis killed mid-fork leaves behind. | With the store stopped, no Redis process uses one, so a working file with a Redis working-file name may go. Anything else: find out what wrote it, since it may hold memory text, and dispose of it as you would that text. |
| `retained_files` | A file in `appendonlydir` that the manifest does not name: an old base or increment that the rewrite could not delete. | Check that the manifest from step 3 does not list it. With the store stopped, Redis cannot make it current again, so it may go. |
| `history_files` | The manifest still lists a superseded file. Redis deletes these itself after a rewrite. | Remove nothing. Start the store (step 5), wait a minute and ask again. If it stays, read `docker logs <container>` for the delete error and fix its cause (permissions or disk). Never edit the manifest. |
| `manifest_unreadable` | The manifest is not one Redis writes: a malformed line, no base or two, increments out of sequence, a name that does not match its type or sequence, or a listed file that is missing. | Remove and edit nothing. Keep a copy of the manifest and the listing, and report it. The purge stays pending. |
| `file_inventory_unavailable` | The Gateway could not list the directory: Docker is not reachable, the container lacks the label or does not publish the configured port, or the listing failed or was malformed. | Nothing in `/data` is at fault. Fix the cause from step 1, then start the store. |

To remove one entry, use its inode number from step 3, so the command acts on exactly that entry whatever its name holds.
Never use a wildcard:

```bash
docker run --rm -v <volume>:/data <image> find /data -mindepth 1 -maxdepth 2 -xdev -inum <inode> -print -delete
```

It prints the one path it removed. If it prints anything else, or nothing, stop and look again.

## 5. Start the store and check again

```bash
docker start <container>
```

Then ask for the same item's `purge_status` again, as whatever requested the purge does when it retries. The restarted Redis
has a new run id, so the disk step starts over with a fresh rewrite and snapshot. The Gateway then reads the directory
again, and the purge completes once nothing blocks it.
