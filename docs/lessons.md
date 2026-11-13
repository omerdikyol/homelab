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

## More incidents

### A copied systemd UMask made a service's code unreadable inside its image

- **Seen:** the first run of a new auto-deploy unit built the new commit, the container exited
  with code 2 within seconds, and the runner restored the previous image.
- **Cause:** the unit was copied from another app's with `UMask=0077`, so the git checkout
  wrote a source file as mode 600. The image copies it as root and runs as an unprivileged
  uid, which then could not open the script; Python exits with 2 when it cannot read it. The
  original app was unaffected because its container does not drop privileges.
- **Fix:** `UMask=0022` in the unit and `chmod -R a+rX` on the checkout. The next run
  deployed and the container was healthy.
- **Guard:** the umask is commented in the unit, and the runner's rollback kept the old
  version serving the whole time.

### A digest updater cannot discover a new image tag

- **Seen:** the nightly image update could not pull two images because the registry
  throttled it, and a transient Compose file counted as a failed app.
- **Cause:** digests are checked only for the tag already written in Compose. Publishing a
  new version tag changes nothing the updater looks at, so it can never notice a new release.
- **Guard:** Renovate opens daily, reviewable pull requests for new tags; the host updater
  applies the merged tag one service at a time and checks health. Registry throttling is
  retried later, and an ephemeral validation skip is not treated as a failed persistent app.

### A major upgrade started with an empty search index

- **Seen:** after a 7.x to 8.x upgrade of a file-sync app, the service was up and every file
  was there, but search found nothing older than the restart.
- **Cause:** 8.x writes a versioned index and checks the schema on startup, so the old index
  is neither read nor migrated. Only new or changed files were indexed. The release notes say
  it in one line.
- **Fix:** one re-index command in the running container; 12,807 files in 1 minute 4 seconds
  while serving. The flag that skips TLS is needed because the internal transport has none
  unless configured, not a shortcut.
- **Guard:** a major version bump is not a tag bump. Read the release notes for a required
  one-off command before restarting, and verify that an old file is findable before deleting
  the old index.

### A hostname that answered 302 for ten minutes and then did not

- **Seen:** a newly published app answered `302` to the Access login at first request, which
  looked exactly like Access protecting it. Ten minutes later its health, login and root paths
  answered `200` from the app itself, while a hostname known to be protected still redirected.
- **Cause:** the hostname had been given the same policy as another app, which is **Bypass**.
  Bypass is right for apps whose native clients cannot pass Access and wrong for one that is
  only opened in a browser. It was reachable from the internet with nothing but its own
  password, and the docs written from the first observation said otherwise.
- **Fix:** the hostname joined the Access application that protects the dashboard, verified by
  the key id in the challenge, and the app got a login back-off in the meantime (2 s doubling to
  5 minutes per address).
- **Guard:** a 302 to an access proxy proves a policy exists at that moment. Check the data
  paths as well as the root, check again after DNS settles, and compare with a hostname known
  to be protected: `curl -o /dev/null -w '%{http_code} %{redirect_url}'`.

### The machine idled hot because the CPU was never allowed to sleep

- **Seen:** the laptop was audibly working at night. At 03:03 the disk was 95% busy at
  99 MB/s with load 9.8 while the CPU was 76% idle at 53 °C and drew 8.36 W doing nothing.
- **Cause:** two unrelated things. The noise was a photo library's integrity check reading
  every asset in one burst, on top of the database dumps and the backup, on a 5400 rpm disk
  where seeks are what you hear. The heat was a measurement profile that pinned the governor
  to `performance` and disabled most cpuidle states, so cores never reached deep idle.
- **Fix:** the library's nightly jobs spread across 00:00 to 04:30, with the checksum check
  limited to 15% of the library per night. A small script switches between a `general` profile
  (powersave, all idle states, 1.83 W measured) and the old measurement profile (8.36 W) and
  warns when the live settings do not match the saved mode.
- **Also learned:** turbo cannot be re-enabled on this laptop at all, and `pkill -f <script>`
  from an SSH command kills the shell running that command, because the pattern matches its own
  command line. Kill by PID taken from `/proc/<pid>/cmdline` instead.
