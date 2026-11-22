# Memory purge held pending by the data directory

A purge's cleanup in configured backups (Plan 12.12) is separate from this: `/memory backup` shows "backup cleanup pending"
for withdrawn items, and the next verified backup retires the older generations that may hold their text. A target that
was offline does not resume by itself: reconnect it, run `/memory backup now`, and check that `/memory backup` no longer
shows cleanup pending; if the folder's identity changed, configure it again. A synced target is cleaned only by
`/memory backup now` too.

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

## 2. Stop the store, and keep it stopped

An Optimus launch starts the store again when it finds it stopped. So first close every Optimus client on this machine:
every IDE window or agent session that uses Optimus. Start none until step 5. Then stop the store and check that it
stopped:

```bash
docker stop <container>
```

```bash
docker inspect --format '{{.State.Running}} {{.State.StartedAt}}' <container>
```

It must print `false`. Note the `StartedAt` value it prints. If a command fails, or prints anything else, stop here and
start again from step 1.

Memory is unavailable until step 5, and nothing is lost. While Redis is stopped nothing writes to the volume, so nothing
you check below can change before you act on it.

## 3. Look at what is there

Use a one-off container on the store's volume, with the store's own image:

```bash
docker run --rm -v <volume>:/data <image> find /data -mindepth 1 -maxdepth 2 -printf '%i %n %y %s %TY-%Tm-%TdT%TT %P\n'
```

```bash
docker run --rm -v <volume>:/data <image> sh -c 'cat /data/appendonlydir/*.manifest'
```

Each line gives the entry's inode number, its link count, type, size, modification time and path relative to `/data`. Find
each `blocking` label among them.

## 4. Decide, by reason

| `files` | What it means | What to do |
|---|---|---|
| `unexpected_files` | A name other than `dump.rdb` and `appendonlydir` at the top, or something that is not a regular file. `temp-<pid>.rdb`, `temp-rewriteaof-<pid>.aof` and `temp-rewriteaof-bg-<pid>.aof` are a snapshot's or rewrite's working files, which a Redis killed mid-fork leaves behind. | With the store stopped, no Redis process uses one, so a working file with a Redis working-file name may go. Anything else: find out what wrote it, since it may hold memory text, and dispose of it as you would that text. |
| `retained_files` | A file in `appendonlydir` that the manifest does not name: an old base or increment that the rewrite could not delete. | Check that the manifest from step 3 does not list it. With the store stopped, Redis cannot make it current again, so it may go. |
| `history_files` | The manifest still lists a superseded file. Redis deletes these itself after a rewrite. | Remove nothing. Start the store (step 5), wait a minute and ask again. If it stays, read `docker logs <container>` for the delete error and fix its cause (permissions or disk). Never edit the manifest. |
| `manifest_unreadable` | The manifest is not one Redis writes: a malformed line, no base or two, increments out of sequence, a name that does not match its type or sequence, or a listed file that is missing. | Remove and edit nothing. Keep a copy of the manifest and the listing, and report it. The purge stays pending. |
| `file_inventory_unavailable` | The Gateway could not list the directory: Docker is not reachable, the container lacks the label or does not publish the configured port, or the listing failed or was malformed. | Nothing in `/data` is at fault. Fix the cause from step 1, then start the store. |

Only a regular file (`f`) with a link count of `1` may be removed. An entry with more links is another name for a file that
may be current, such as a hard link to the current base: leave it, and report it like `manifest_unreadable`.

To remove one entry, use its inode number from step 3, so the command acts on exactly that entry whatever its name holds.
Never use a wildcard. First check, without removing anything, that the store is still stopped and that exactly one path
matches:

```bash
docker inspect --format '{{.State.Running}}' <container> | grep -qx false && docker run --rm -v <volume>:/data <image> find /data -mindepth 1 -maxdepth 2 -xdev -type f -inum <inode> -links 1 -print
```

It must print exactly the one path you chose. If it prints nothing, more than one path or another path, stop. Then remove
it with the same check:

```bash
docker inspect --format '{{.State.Running}}' <container> | grep -qx false && docker run --rm -v <volume>:/data <image> find /data -mindepth 1 -maxdepth 2 -xdev -type f -inum <inode> -links 1 -print -delete
```

Before step 5, run the `docker inspect` command from step 2 again. It must still print `false` and the same `StartedAt`. If
it does not, the store started during maintenance: stop it, then start again from step 3.

## 5. Start the store and check again

```bash
docker start <container>
```

Then ask for the same item's `purge_status` again, as whatever requested the purge does when it retries. The restarted Redis
has a new run id, so the disk step starts over with a fresh rewrite and snapshot. The Gateway then reads the directory
again, and the purge completes once nothing blocks it.
