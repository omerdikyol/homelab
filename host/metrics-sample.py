#!/usr/bin/env python3
"""Sample homelab's resource use every few seconds into a CSV, for before/after
comparisons. Reads /proc and /sys only, so it costs almost nothing. Run as
root: package power (RAPL) is root-only.

  sudo systemd-run --unit=homelab-metrics -p Nice=10 python3 metrics-sample.py /dev/shm/homelab-metrics.csv
  echo idle-before > /dev/shm/homelab-phase     # label the rows that follow

Every rate is a delta over the interval, not an instantaneous reading.
SELFCHECK=1 python3 metrics-sample.py        # asserts, touches nothing
"""
import csv, glob, os, sys, time

INTERVAL = 10          # seconds
DISK = "sda"
NIC = "enp11s0"
PHASE = "/dev/shm/homelab-phase"
FIELDS = ["ts", "phase", "dt", "cpu_user", "cpu_sys", "cpu_iowait", "cpu_idle", "ctxt_s", "intr_s", "procs_running",
          "procs_blocked", "load1", "psi_cpu_some", "psi_mem_some", "psi_mem_full", "psi_io_some", "psi_io_full",
          "mem_used_mb", "mem_avail_mb", "swap_used_mb", "swapin_kb_s", "swapout_kb_s", "majflt_s", "disk_read_kb_s",
          "disk_write_kb_s", "disk_util", "wan_rx_kb_s", "wan_tx_kb_s", "pkg_watts", "temp_c", "conntrack"]


def read(path, default=""):
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return default


def counters():
    c = {"t": time.monotonic()}
    for line in read("/proc/stat").splitlines():
        parts = line.split()
        if parts[0] == "cpu":
            user, nice, system, idle, iowait, irq, softirq, steal = map(int, parts[1:9])
            c.update(user=user + nice, sys=system + irq + softirq, idle=idle, iowait=iowait, steal=steal)
        elif parts[0] in ("ctxt", "intr", "procs_running", "procs_blocked"):
            c[parts[0]] = int(parts[1])
    for res in ("cpu", "memory", "io"):
        for line in read(f"/proc/pressure/{res}").splitlines():
            kind, *kv = line.split()
            c[f"psi_{res}_{kind}"] = int(dict(x.split("=") for x in kv)["total"])
    vm = dict(line.split() for line in read("/proc/vmstat").splitlines())
    c.update(pswpin=int(vm["pswpin"]), pswpout=int(vm["pswpout"]), majflt=int(vm["pgmajfault"]))
    mem = {line.split(":")[0]: int(line.split()[1]) for line in read("/proc/meminfo").splitlines()}
    c.update(mem_used=mem["MemTotal"] - mem["MemAvailable"], mem_avail=mem["MemAvailable"],
             swap_used=mem["SwapTotal"] - mem["SwapFree"])
    for line in read("/proc/diskstats").splitlines():
        p = line.split()
        if p[2] == DISK:
            c.update(rd_sect=int(p[5]), wr_sect=int(p[9]), io_ms=int(p[12]))
    for line in read("/proc/net/dev").splitlines()[2:]:
        name, data = line.split(":", 1)
        if name.strip() == NIC:
            d = data.split()
            c.update(rx=int(d[0]), tx=int(d[8]))
    energy = read("/sys/class/powercap/intel-rapl:0/energy_uj").strip()
    c["energy"] = int(energy) if energy else None
    temps = [int(read(z).strip() or 0) for z in glob.glob("/sys/class/thermal/thermal_zone*/temp")]
    c["temp"] = max(temps) / 1000 if temps else None
    c["conntrack"] = int(read("/proc/sys/net/netfilter/nf_conntrack_count", "0").strip() or 0)
    c["load1"] = float(read("/proc/loadavg").split()[0])
    return c


def row(a, b, wrap):
    dt = b["t"] - a["t"]
    ticks = sum(b[k] - a[k] for k in ("user", "sys", "idle", "iowait", "steal")) or 1
    pct = lambda k: 100 * (b[k] - a[k]) / ticks
    psi = lambda k: 100 * (b[k] - a[k]) / (dt * 1e6) if k in a and k in b else ""
    rate = lambda k, scale=1: (b[k] - a[k]) * scale / dt
    watts = ""
    if a["energy"] is not None and b["energy"] is not None:
        de = b["energy"] - a["energy"]
        watts = (de + wrap if de < 0 else de) / 1e6 / dt
    return {
        "dt": round(dt, 2), "cpu_user": pct("user"), "cpu_sys": pct("sys"), "cpu_iowait": pct("iowait"),
        "cpu_idle": pct("idle"), "ctxt_s": rate("ctxt"), "intr_s": rate("intr"), "procs_running": b["procs_running"],
        "procs_blocked": b["procs_blocked"], "load1": b["load1"], "psi_cpu_some": psi("psi_cpu_some"),
        "psi_mem_some": psi("psi_memory_some"), "psi_mem_full": psi("psi_memory_full"), "psi_io_some": psi("psi_io_some"),
        "psi_io_full": psi("psi_io_full"), "mem_used_mb": b["mem_used"] / 1024, "mem_avail_mb": b["mem_avail"] / 1024,
        "swap_used_mb": b["swap_used"] / 1024, "swapin_kb_s": rate("pswpin", 4), "swapout_kb_s": rate("pswpout", 4),
        "majflt_s": rate("majflt"), "disk_read_kb_s": rate("rd_sect", 0.5), "disk_write_kb_s": rate("wr_sect", 0.5),
        "disk_util": min(100, 100 * (b["io_ms"] - a["io_ms"]) / (dt * 1000)), "wan_rx_kb_s": rate("rx", 1 / 1024),
        "wan_tx_kb_s": rate("tx", 1 / 1024), "pkg_watts": watts, "temp_c": b["temp"], "conntrack": b["conntrack"],
    }


def main(path):
    wrap = int(read("/sys/class/powercap/intel-rapl:0/max_energy_range_uj", "0").strip() or 0)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        out = csv.DictWriter(fh, FIELDS)
        if new:
            out.writeheader()
        prev = counters()
        while True:
            time.sleep(INTERVAL - (time.monotonic() - prev["t"]) % INTERVAL)
            cur = counters()
            r = row(prev, cur, wrap)
            r.update(ts=int(time.time()), phase=read(PHASE, "unlabelled").strip())
            out.writerow({k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()})
            fh.flush()
            prev = cur


def selfcheck():
    a = counters()
    time.sleep(1)
    b = counters()
    r = row(a, b, 0)
    assert 99 <= r["cpu_user"] + r["cpu_sys"] + r["cpu_iowait"] + r["cpu_idle"] <= 101, r
    assert r["mem_used_mb"] > 0 and r["disk_util"] >= 0 and set(r) | {"ts", "phase"} == set(FIELDS), set(FIELDS) ^ set(r)
    # a wrapped energy counter still gives a positive power
    a2, b2 = dict(a, energy=900, t=0.0), dict(b, energy=100, t=1.0)
    assert abs(row(a2, b2, 1000)["pkg_watts"] - 200 / 1e6) < 1e-9
    print("selfcheck ok")


if __name__ == "__main__":
    selfcheck() if os.environ.get("SELFCHECK") else main(sys.argv[1])
