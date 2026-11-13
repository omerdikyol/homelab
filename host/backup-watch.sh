#!/bin/sh
# Backup watchdog, run hourly by backup-watch.timer. Two checks:
#
#   1. The USB SSD holding the second repository is mounted. On 2026-09-13 its
#      JMS583 USB-NVMe bridge dropped off the bus, fstab's nofail let the system
#      carry on with an empty mountpoint, and nothing said so.
#   2. Each repository (HDD, SSD, and off-site Cloudflare R2 since 2026-09-15)
#      has a snapshot younger than MAX_AGE_HOURS. This is the
#      check that matters, because it catches every way a backup can quietly
#      stop, including ones nobody has thought of. The USB plan had in fact
#      never succeeded, and Backrest's error hooks did not fire for its failures.
#
# Same rules as temp-watch.sh, so it never spams: notify when something goes
# wrong, repeat at most every 6 hours while it stays wrong, notify once when
# everything is fine again.
set -u
[ -r /etc/smartd-ntfy.env ] && . /etc/smartd-ntfy.env
[ -r /etc/home-server-backup.env ] && { set -a; . /etc/home-server-backup.env; set +a; }
NTFY_TOPIC="${NTFY_TOPIC:-}"
USB_MOUNT="${BACKUP_USB_MOUNT:-/srv/backup-usb}"              # the three overrides are for testing
STATE="${BACKUP_WATCH_STATE:-/var/lib/backup-watch.state}"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"                   # runs are nightly: one missed night trips it
R2_GRACE="${BACKUP_R2_GRACE:-/var/lib/backup-watch.r2-grace}"  # epoch until which an empty R2 repository is expected (first upload)
REPEAT_AFTER=21600

age_hours() {   # repository -> hours since its newest snapshot; empty if unreadable or empty
  restic -r "$1" snapshots --no-lock --json 2>/dev/null | python3 -c '
import datetime, json, sys
def parse(t):   # restic writes nanoseconds, which fromisoformat rejects
    offset = t[-6:] if t[-6] in "+-" else "+00:00"
    return datetime.datetime.fromisoformat(t[:19] + offset)
snaps = json.load(sys.stdin)
if snaps:
    newest = max(parse(s["time"]) for s in snaps)
    print(int((datetime.datetime.now(datetime.timezone.utc) - newest).total_seconds() // 3600))'
}

PROBLEMS=""
add() { PROBLEMS="${PROBLEMS:+$PROBLEMS; }$1"; }

REPOS="local:/srv/backup/restic"
if mountpoint -q "$USB_MOUNT" && [ -f "$USB_MOUNT/restic/config" ]; then
  REPOS="$REPOS usb:$USB_MOUNT/restic"
else
  add "the USB SSD is not mounted at $USB_MOUNT, so the USB backup cannot run"
fi
if [ -r /etc/home-server-r2.env ]; then   # off-site copy; restic reads the keys from the environment
  set -a; . /etc/home-server-r2.env; AWS_DEFAULT_REGION=auto; set +a
  REPOS="$REPOS r2:s3:${R2_ENDPOINT%/}/BUCKET"
fi
for entry in $REPOS; do
  name=${entry%%:*}; path=${entry#*:}
  age=$(age_hours "$path")
  if [ -z "$age" ] && [ "$name" = r2 ] && [ "$(date +%s)" -lt "$(cat "$R2_GRACE" 2>/dev/null || echo 0)" ]; then continue
  elif [ -z "$age" ]; then add "the $name repository cannot be read or has no snapshots"
  elif [ "$age" -ge "$MAX_AGE_HOURS" ]; then add "the $name repository's newest snapshot is ${age}h old"
  fi
done

# The dumps that the snapshots are meant to contain: a failed or stale run means
# the databases in the latest backup are old or half written (2026-09-14 and
# 09-15 both timed out and nothing said so).
DUMPS="${BACKUP_DUMPS_DIR:-/home/USER/backup-dumps}"
result=$(systemctl show home-server-dumps.service -p Result --value 2>/dev/null)
[ -n "$result" ] && [ "$result" != success ] && add "the nightly database dumps failed ($result)"
newest=$(find "$DUMPS" -maxdepth 1 -type f -mmin -$((MAX_AGE_HOURS * 60)) 2>/dev/null | head -1)
[ -z "$newest" ] && add "no database dump in $DUMPS is younger than ${MAX_AGE_HOURS}h"

PREV=ok; WHEN=0
[ -r "$STATE" ] && . "$STATE"
NOW=$(date +%s)

send() {
  [ -n "$NTFY_TOPIC" ] && curl -fsS -m 20 -H "Title: homelab backups $1" -H "Priority: $2" \
    -H "Tags: floppy_disk" -d "$3" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
  logger -t backup-watch "$1: $3"
}

if [ -n "$PROBLEMS" ]; then
  if [ "$PREV" = ok ] || [ $((NOW - WHEN)) -ge "$REPEAT_AFTER" ]; then
    send "problem" high "$PROBLEMS."
    WHEN=$NOW
  fi
  LEVEL=bad
else
  [ "$PREV" = bad ] && send "ok again" default "every repository is reachable and has a recent snapshot"
  LEVEL=ok; WHEN=0
fi

printf 'PREV=%s\nWHEN=%s\n' "$LEVEL" "$WHEN" > "$STATE"
