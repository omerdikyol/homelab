# Lessons from running it

Five incidents, lightly edited from the private log. Each has what was seen, the cause,
the fix and the guard.

## An outside review found the doors left open

- **Seen:** an independent review found SSH accepting passwords on every interface; six
  containers mounting the Docker socket; a dashboard able to read the whole filesystem,
  including the backup credentials and every `.env`; several monitoring endpoints listening
  on every address, one listing every public hostname; the tunnel token visible on a process
  command line; a password manager seeing every client as the Docker gateway, so its login
  rate limit was one shared bucket.
- **Cause:** defaults and upstream example files kept from first setup. The socket mounts
  were judged acceptable because the pages sat behind Access, but Access controls who reaches
  a page, not what a compromised container can do.
- **Fix:** SSH keys only and no root login; a read-only Docker API proxy for all six socket
  consumers (a restart request through it returns 403); the dashboard mounts only its config;
  monitoring bound to loopback or a unix socket; the tunnel token moved into the environment;
  the password manager reads the real client address from a trusted header; image tags pinned
  instead of floating. Afterwards only three ports listened on every address.
- **Guard:** the "add a new app" runbook requires loopback ports and no Docker socket, and a
  one-line `ss` check lists everything listening on every address; it should show only the
  expected few.

## Nine apps ran for nobody

- **Seen:** measured use before a clean-up: one app with zero chats ever, one with a single
  bookmark, one with zero operations in its logs, and so on. Together about 2.5 GB of 6.3 GB
  container memory, 27 GB of images and a dozen monitors and public hostnames.
- **Cause:** apps were added because they might be useful, and nothing ever checked whether
  they were.
- **Fix:** all nine removed. Containers went from 53 to 40, container memory from 6,272 to
  3,913 MB, disk used from 271 to 241 GB, and uptime monitors from 78 to 55. Settings were
  archived before removal.
- **Guard:** a periodic usage review runbook: count what each app holds, look for its requests
  in the log history, remove what nobody uses.

## Database dumps timed out two nights and nobody was told

- **Seen:** the dump service failed with a timeout on two nights, one snapshot started while
  dumps were still being written, and one app's dump was an empty 4 KB file every night.
- **Cause:** both nights fell inside a heavy indexing job that starved the disk. The unit ran
  at the idle IO class, which under BFQ only gets the disk when nothing else reads. The empty
  dump was an old leftover file; the real data lived in other paths. The backup watcher only
  checked snapshot age.
- **Fix:** best-effort IO priority with a two-hour limit and the real database files dumped;
  a run afterwards took 121 seconds.
- **Guard:** the watcher alerts when the dumps' last result is not success or no dump is
  younger than 30 hours.

## One name server, and the first off-site upload died with it

- **Seen:** the first upload to object storage ran for 3 hours 29 minutes and failed with a
  DNS error. In the same hour, three different services logged lookup failures at once, and
  all recovered by themselves.
- **Cause:** the host had a single name server, the router. While it returned SERVFAIL,
  nothing else could be asked. The backup tool resumed on its own and kept the 30 GB already
  uploaded, so the cost was time, not data.
- **Fix:** three name servers in a fixed order (router first, then two public resolvers),
  with DHCP's DNS disabled so the order stays deterministic. Tested by pointing the first
  server at an unreachable address: a fresh lookup still answered in 5.1 seconds.
- **Guard:** the backup watcher alerts when any repository has no snapshot in 30 hours.
- **Also learned:** containers on Docker networks use Docker's resolver, which keeps the
  list read at start, so restart a container to be sure it uses a new one. And never check
  "nothing changed" with a checksum of `iptables-save`: the dump includes packet counters.

## The dashboard showed data from its last restart

- **Seen:** the dashboard seemed not to update. A widget sat at 13.6% while the file it reads
  said 14.7%, then 19.8%, then 23.3%. Host figures were frozen the same way.
- **Cause:** host scripts wrote their JSON the safe way, to a temporary file renamed over the
  old one, but the container bind-mounted each file. A single-file bind mount pins the inode
  it started with, so every rename created a file the container never saw. Every figure had
  shown the state of the last container restart since the dashboard was built; frequent
  restarts during development hid it.
- **Fix:** the scripts write into a directory and the container mounts the directory
  read-only. Checked over two refreshes: file and dashboard agreed at 58.9%, then 64.2%.
- **Guard:** mount a folder whenever the host side replaces a file atomically. A single-file
  mount is only safe for a file edited in place.
