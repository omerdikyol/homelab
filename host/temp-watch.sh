#!/bin/sh
# Temperature watchdog. smartd already alerts on the disk; nothing watched the
# CPU, the chipset or the GPU, which matters on a laptop that runs with the lid
# closed.
#
# Alerts go to the same ntfy topic as everything else. Rules, so it never spams:
#   - notify when the level rises (ok -> warn -> critical)
#   - while still hot, repeat at most once an hour
#   - notify once when it comes back down
set -u
[ -r /etc/smartd-ntfy.env ] && . /etc/smartd-ntfy.env
NTFY_TOPIC="${NTFY_TOPIC:-}"
STATE=/var/lib/temp-watch.state
CPU_WARN=85
CPU_CRIT=95
GPU_WARN=90
REPEAT_AFTER=3600

read_zone() {   # thermal zone type -> millidegrees, empty if absent
  for z in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$z/type" 2>/dev/null)" = "$1" ] && cat "$z/temp" 2>/dev/null && return
  done
}
hwmon_temp() {  # hwmon name -> celsius, empty if absent or unreadable
  for h in /sys/class/hwmon/hwmon*; do
    if [ "$(cat "$h/name" 2>/dev/null)" = "$1" ]; then
      # a suspended GPU returns EINVAL on read, which is not an error worth showing
      v=$(cat "$h/temp1_input" 2>/dev/null) || return
      [ -n "$v" ] && echo $((v / 1000))
      return
    fi
  done
}

CPU=$(read_zone x86_pkg_temp); CPU=${CPU:-0}; CPU=$((CPU / 1000))
[ "$CPU" -eq 0 ] && CPU=$(hwmon_temp coretemp)
PCH=$(hwmon_temp pch_cometlake)
GPU=$(hwmon_temp nouveau)
DISK=$(smartctl -A /dev/sda 2>/dev/null | awk '/Temperature_Celsius/ {print $10}')

LEVEL=ok
[ "${CPU:-0}" -ge "$CPU_WARN" ] && LEVEL=warn
[ "${GPU:-0}" -ge "$GPU_WARN" ] && LEVEL=warn
[ "${CPU:-0}" -ge "$CPU_CRIT" ] && LEVEL=critical

PREV=ok; WHEN=0
[ -r "$STATE" ] && . "$STATE"
NOW=$(date +%s)
MSG="CPU ${CPU:-?}C, chipset ${PCH:-?}C, GPU ${GPU:-?}C, disk ${DISK:-?}C (load $(cut -d' ' -f1 /proc/loadavg))"

rank() { case "$1" in ok) echo 0;; warn) echo 1;; critical) echo 2;; esac; }
send() {
  [ -n "$NTFY_TOPIC" ] && curl -fsS -m 20 -H "Title: homelab temperature $1" -H "Priority: $2" \
    -H "Tags: thermometer" -d "$3" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
  logger -t temp-watch "$1: $3"
}

if [ "$(rank "$LEVEL")" -gt "$(rank "$PREV")" ]; then
  send "$LEVEL" "$([ "$LEVEL" = critical ] && echo urgent || echo high)" "$MSG"
  WHEN=$NOW
elif [ "$LEVEL" != ok ] && [ $((NOW - WHEN)) -ge "$REPEAT_AFTER" ]; then
  send "$LEVEL still" high "$MSG"
  WHEN=$NOW
elif [ "$LEVEL" = ok ] && [ "$PREV" != ok ]; then
  send "back to normal" default "$MSG"
  WHEN=0
fi

printf 'PREV=%s\nWHEN=%s\n' "$LEVEL" "$WHEN" > "$STATE"
