# Working on this repo with AI agents

The private repository has a rulebook for any AI agent or new maintainer. This is the
sanitized version. It is why I can let an agent change infrastructure and still trust the
result: the rules are short, specific and checkable, and the repo explains itself.

## Reading order

1. The rulebook, all of it.
2. The incident log, searched for the app or mechanism about to be touched.
3. The app's README and its Compose file.
4. The runbooks for the procedure and the decisions log for why it is built that way.
5. Live state on the host: settings kept in app databases can differ from the repo.

## Rules that must never be broken

1. **Secrets never enter the repository.** They live in gitignored `.env` files and in the
   password manager. Do not print them in logs or commits.
2. **Nothing without a login of its own is published without Access.** The dashboard and the
   log viewer have no authentication at all.
3. **Respect the slow disk.** Heavy write jobs run one at a time at low IO priority, never on
   top of the scheduled jobs, and the timetable of those jobs is written down.
4. **Respect the USB SSD's heat.** It drops off the bus after about 76 seconds of full-speed
   writes. Sustained SSD writes need a temperature guard.
5. **Do not delete user data** (photos, documents, backups) without the owner's explicit
   go-ahead. Move it aside instead.
6. **Claims need measurements.** Write "measured X before, Y after, method Z", not "should be
   faster".
7. **Everything must stay stoppable.** Never change the firewall policy or restart the Docker
   daemon casually.

## How work is done

1. **Read before changing,** including live state on the host.
2. **Change the repo first,** validate, then deploy the same file:
   ```sh
   scp <app>/docker-compose.yml host:/tmp/new.yml
   ssh host 'docker compose --project-directory ~/<app> -f /tmp/new.yml config -q && echo valid'
   scp <app>/docker-compose.yml host:~/<app>/ && ssh host '~/ctl.sh <app> start'
   ```
3. **Settings that live inside apps** are changed through their APIs or config files with a
   script, and the resulting values are written into that app's README.
4. **Verify on the host:** the container is healthy, the endpoint answers, and the setting reads
   back as intended.
5. **Write it down,** then commit and push.

Every new app follows one checklist: loopback-only port, no Docker socket, restart policy, CPU
and memory limits, a healthcheck every 120 seconds, a README, an uptime monitor, an Access
policy, backup paths and a setup-page entry.

## Measuring

Resource claims use two small scripts (in [`host/`](../host)):

- `metrics-sample.py` samples `/proc` and `/sys` every 10 seconds into a CSV (CPU split,
  context switches, pressure stall, memory, swap, disk, network, package power, temperature,
  conntrack), with a phase label read from a file.
- `metrics-compare.py` compares two labelled windows on 10-minute block means and reports the
  change, a bootstrap 95% confidence interval, a permutation p-value, a Holm-adjusted p-value
  across the metrics, and lag-1 autocorrelation.

Method: a labelled idle window before, a settle period, an equal window after, block statistics,
Holm correction across metrics, and an independent agent re-deriving the numbers from the raw
CSV. Report the caveats: time of day, restarts, what else differed between windows.

## Documentation conventions

- **App README:** a table first (host directory, data paths, URL, port, login), then sections that
  explain why things are set the way they are, with dates and measured numbers. Commands are
  copy-pasteable.
- **Compose comments** explain non-obvious settings in one or two lines, with the number that
  justified them.
- **Incident log:** every incident gets symptom, cause, fix and guard. Add to it whenever
  something breaks or surprises.
- **Decisions log:** why a design was chosen over the alternatives.
- Plain, specific prose, no marketing words, absolute dates.

## Commits

- A summary line in the imperative that states the outcome, under about 72 characters.
- A body with what was wrong, the cause, what changed and measured numbers.
- One logical change per commit. Never commit `.env` or personal data.

## Practical notes for agents

- The Mac's shell is zsh: `for a in $list` does not split a string; use arrays.
- Pass Python to the host as a file or a quoted heredoc. Nested quotes in `ssh '...'` break.
- `pkill -f <pattern>` also matches the `ssh` command that contains the pattern and kills your own
  session. Match on `/proc/<pid>/cmdline` instead.
- Root cannot write files owned by another user in `/dev/shm` or `/tmp` (`fs.protected_regular`):
  write them as the owning user.
- Walking big trees on the slow disk (`du`, `grep -r`) skews any measurement running at the time.
- Long jobs: run on the host with `nohup ... > log` and wait with a background
  `until grep -q DONE log` loop instead of holding an SSH session open.
- `docker compose up -d` starts every service in the file, including ones stopped on purpose.
  Remove a service from the file to keep it gone.
- Never set `memswap_limit` equal to `mem_limit`: the resulting swap cap of 0 is lost at the next
  `systemctl daemon-reload`. Allow a little swap instead.
- SSH takes keys only and refuses root. Run `sshd -t` before reloading after any sshd change.
- Reboots keep stopped stacks stopped: after a power loss Docker restarts only what was running,
  and after the guarded reboot script exactly what was running before it comes back.
