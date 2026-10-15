#!/usr/bin/env python3
"""Emit a periodic target heartbeat for deployment and log-view testing."""

import json
import os
import signal
import socket
import time
from pathlib import Path

running = True


def stop(_signum, _frame):
    global running
    running = False


def read_meminfo_kb(key):
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, value = line.split(":", 1)
            if name == key:
                return int(value.strip().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return None


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    hostname = socket.gethostname()

    while running:
        try:
            uptime_seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        except (OSError, ValueError, IndexError):
            uptime_seconds = None
        try:
            load_average = list(os.getloadavg())
        except (AttributeError, OSError):
            load_average = None

        record = {
            "app": "pi-heartbeat-monitor",
            "hostname": hostname,
            "uptime_seconds": uptime_seconds,
            "memory_total_kb": read_meminfo_kb("MemTotal"),
            "memory_available_kb": read_meminfo_kb("MemAvailable"),
            "load_average": load_average,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        print(json.dumps(record), flush=True)
        for _ in range(5):
            if not running:
                break
            time.sleep(1)

    print(json.dumps({"app": "pi-heartbeat-monitor", "state": "stopped"}), flush=True)


if __name__ == "__main__":
    main()
