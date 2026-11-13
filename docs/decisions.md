# Decisions

Why it is built the way it is. Each entry names the alternatives that lost.

## Platform

- **Docker Compose, one directory per app, no orchestrator.** One host and one operator:
  `docker compose` plus a small control script is enough, and any app can be stopped alone
  for measurements.
- **Nightly image updates use the Docker CLI on the host,** not a container with write access
  to the Docker socket. The job checks running services only, follows their configured tag, and
  restores the previous image if the health check fails. It never selects a new version tag;
  those changes go through reviewable pull requests (Renovate) and per-app runbooks.
- **Pinned image tags** for most apps, so an upgrade is a decision, not a side effect. A few
  apps with small, backed-up state track `latest`.
- **Memory and CPU limits on the apps that grow,** zram swap in front of the disk swap, BFQ on
  the hard disk, healthchecks every 120 seconds. The rationale is measured, not assumed.

## Access and security

- **Cloudflare Tunnel with Access (Google login) for public URLs, Tailscale as the fallback, no
  open router ports.** Access protects apps without a login of their own, and the tunnel avoids
  exposing the home IP address.
- **Bypass only for apps whose native clients cannot pass Access** and which authenticate
  themselves, with a rate-limit rule on the login paths.
- **The Docker API goes through a read-only proxy; no app mounts the socket.** Six tools mounted
  it read-only, which still grants the whole API and so root on the host. The proxy answers
  GET for containers, images, events, info, version, ping and logs, and refuses POST. Chosen
  over removing the Docker views, which are what those tools are for.
- **The backup UI has its own login as well as Access.** It holds the repository password and
  the off-site key and can restore and forget snapshots. Without its own login, anything on the
  host that can reach its loopback port could.
- **Log history in VictoriaLogs, collected by Vector,** over Loki with Grafana: one small
  container with its own search page (41 MB RAM measured) instead of two larger ones. A live log
  viewer stays for the present; container logs are capped in Docker because the history lives
  in the log store.
- **Alerts through the public ntfy service with a secret topic,** not a self-hosted one: push to
  the phone has to work exactly when the server is down.

## Storage and backup

- **Backrest over restic, three independent repositories:** internal disk, USB SSD and off-site
  object storage, nightly at staggered times, retention 7 daily, 4 weekly, 12 monthly. A
  shell-script predecessor was killed mid-run by a systemd timeout.
- **Off-site in Cloudflare R2** (about $0.70 a month for 54 GiB), over Backblaze B2 (half the
  price, but a new account and restores free only up to 3x storage), a second-hand disk at
  another address (only as fresh as the last manual swap) and Google Drive (about twice the
  price, slower uploads). Encrypted by restic before upload.
- **Database dumps before snapshots,** because a live SQLite or Postgres file can be captured
  torn.
- **Write-heavy caches live on the USB SSD,** since the SMR system disk stalls under sustained
  writes.
- **Backups and dumps run at best-effort-low IO priority, not idle.** The idle class under BFQ
  can starve them; the dumps timed out two nights running.

## Removing apps

- **Apps are removed by measured use.** A periodic review counts what each app holds and looks
  for its requests in the log history. Nine unused apps were removed in one pass, which cut
  containers from 53 to 40 and container memory from 6.3 GB to 3.9 GB.

## An assistant over personal data, without a new stack

- **One stdio MCP server instead of another model, vector database and web interface.** The
  assistant stays in the client I already use. It runs as a disposable container behind a
  dedicated forced-command SSH account, with read-only data mounts and no listening port. See
  [`security-model.md`](security-model.md).
