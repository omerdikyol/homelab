# Security model

## Access, in layers

1. **No inbound ports.** The router forwards nothing. Public apps are reached through an
   outbound Cloudflare Tunnel.
2. **Cloudflare Access in front of everything that has no login of its own.** A dashboard, a
   log viewer and other tools rely on it completely, so they must never be published without
   it. A bypass exists only for apps with their own login that native clients need to reach
   (password manager, file sync, calendar, music), and each is listed with the reason.
3. **Tailscale** for apps that should not be public at all, and as a fallback path.
4. **The host:** SSH keys only, no root login, passwordless sudo only for fixed commands.
5. **Containers:** loopback-only ports unless a service has to listen wider, memory limits on
   the ones that grow, no Docker socket (a read-only API proxy where something truly needs
   container information), pinned image tags.
6. **Secrets:** gitignored `.env` files on the host and a password manager. The repository
   holds no secrets and no data.

## A read-only personal-data tool for an AI assistant

I wanted an assistant to answer questions about my own notes, documents and files without
hosting another model, vector database or web interface. The design:

- **One stdio MCP server.** No listening port, no tunnel route, no Docker socket. The
  assistant and its model stay in the client I already use.
- **A dedicated SSH account** with a forced command: it accepts only the tailnet and LAN,
  cannot forward ports or run arbitrary commands, and can sudo only a root-owned launcher.
- **One disposable container per connection,** resource-limited, removed on disconnect.
- **Data is read-only.** Files and databases are bind-mounted read-only; for APIs, scoped keys
  where the upstream supports them (the photo library key can only read and view), and a
  fixed allowlist of operations where it does not. Passwords and infrastructure
  configuration are excluded on purpose.
- **Answers must cite sources.** A failed search cannot prove absence, so payment questions
  need the source record and the import coverage, not a guess.
- **Tested:** 54 synthetic and protocol tests on the Mac and in the deployed image, plus
  checks that there is no owned TCP listener, writes to data mounts are denied, resources are
  bounded, SSH forwarding is refused, and cleanup follows disconnect.

The honest limit: for APIs without scoped keys, protection depends on the deployed code being
trusted, which is why the allowlist is fixed rather than configurable.
