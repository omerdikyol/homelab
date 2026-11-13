# Self-hosted home server

How I run my own cloud on one consumer laptop: photos, files, passwords, documents,
notes, calendar and contacts, budgeting, music and location history, with backups,
monitoring and a written recovery plan. This repository is a **sanitized write-up**:
the architecture, the rules I operate by, and the incidents that taught me those rules.
The real configuration repository is private, because it holds hostnames, network
addresses and a map of what is exposed where.

## At a glance

| | |
|---|---|
| Host | one laptop, Ubuntu 24.04, 8 cores, 15.5 GiB RAM |
| Storage | 1 TB SMR hard disk (the bottleneck of everything) plus a 256 GB USB SSD |
| Runtime | Docker Compose, one directory per app, about 48 containers |
| Public access | Cloudflare Tunnel with Cloudflare Access (Google login); no router ports open |
| Private access | Tailscale |
| Backups | restic, three repositories: local disk, USB SSD, off-site object storage, nightly |
| Observability | Uptime Kuma, Beszel, Dozzle, Vector into VictoriaLogs (30-day history), ntfy alerts |
| Docs | runbooks, design decisions, disaster-recovery guide, and an incident log (about 2,200 lines) |

## Design rules

1. **Secrets never enter the repository.** They live in gitignored `.env` files on the host
   and in a password manager. Nothing in git can leak them.
2. **Nothing without its own login is published without Access.** Several apps (a log
   viewer, a dashboard) have no authentication at all and rely entirely on Cloudflare
   Access. Bypass exists only where a native client cannot pass Access and the app
   authenticates by itself.
3. **No open ports.** Public traffic comes in through an outbound tunnel; private apps are
   reachable only over the tailnet. Containers bind to loopback unless they must not.
4. **Respect the slow disk.** Sustained writes of tens of gigabytes stall the machine
   (load 45, IO pressure 90%). Heavy jobs run one at a time at low IO priority, and the
   nightly jobs are spread across the night so nothing overlaps.
5. **Everything is stoppable.** A killswitch stops every container; another command cuts
   only internet access. A manual stop survives a reboot.
6. **Reboots are guarded.** A monthly reboot refuses to run while a measurement, an import
   or a stream is active, then re-checks every endpoint and reports to my phone.
7. **Delete what nobody uses.** Apps are reviewed by measured use, not by whether they
   might be useful.
8. **Write it down.** Every incident gets a cause, a fix and a guard (a check that would
   have caught it), recorded where the next maintainer will look.

## Layers

- **Edge:** Cloudflare Tunnel, Access policies per hostname, Tailscale for tailnet-only apps.
- **Apps:** self-hosted replacements for the usual cloud services, each in its own Compose
  project with memory limits on the ones that grow.
- **Host:** disk health (smartd), temperature watching, a temperature guard for the USB SSD
  (it drops off the bus after about 76 seconds of full-speed writes), zram swap, BFQ on the
  hard disk, healthchecks every two minutes.
- **Backups:** nightly restic snapshots plus database dumps, an alert if any repository has
  no snapshot in 30 hours or the last dump did not succeed, and a written
  disaster-recovery guide for rebuilding from scratch.
- **Alerts:** push notifications through ntfy; uptime monitors per endpoint.

## Read next

- [`docs/lessons.md`](docs/lessons.md): five incidents, each with what was seen, the cause,
  the fix and the guard.
- [`docs/security-model.md`](docs/security-model.md): how access is layered and how a
  read-only personal-data tool for an AI assistant is exposed without opening a port.

## What this shows

Operating real services as one person: choosing boring defaults, measuring before
changing, making failures visible, and leaving documentation that someone else could
rebuild the system from. The full configuration, including the recovery guide, is private;
I'm happy to walk through it in an interview.
