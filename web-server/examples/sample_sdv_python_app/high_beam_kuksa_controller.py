#!/usr/bin/env python3
"""
Sample SDV Python simulation with a TCP reachability probe.
Toggles a local high-beam Boolean; it does not use VAL v2, subscribe to
Vehicle.Speed, or write signals to KUKSA Databroker.
"""

import os
import sys
import time
import socket
import signal

keep_running = True

def handle_sig(sig, frame):
    global keep_running
    keep_running = False

signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)

KUKSA_HOST = os.environ.get("VDB_HOST", "127.0.0.1")
KUKSA_PORT = int(os.environ.get("VDB_PORT", "55555"))

def check_kuksa_available(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        res = s.connect_ex((host, port))
        s.close()
        return res == 0
    except Exception:
        return False

def main():
    print("=" * 60)
    print(" [SDV Python Simulation] High-Beam Controller (local state only)")
    print(f" TCP reachability probe: {KUKSA_HOST}:{KUKSA_PORT} (not a VAL v2 connection)")
    print("=" * 60)

    is_connected = check_kuksa_available(KUKSA_HOST, KUKSA_PORT)
    if is_connected:
        print(f"[SDV Python Simulation] TCP port reachable at {KUKSA_HOST}:{KUKSA_PORT}; broker protocol not verified.")
    else:
        print(f"[SDV Python Simulation] TCP port unreachable at {KUKSA_HOST}:{KUKSA_PORT}.")
    print("[SDV Python Simulation] Running in simulated mode regardless of TCP reachability; no signals are read or written.")

    high_beam_state = False
    cycle = 0

    while keep_running:
        cycle += 1
        # Toggle high-beam state every 3 cycles
        if cycle % 3 == 0:
            high_beam_state = not high_beam_state
            print(f"[SDV Simulation] Local simulated Vehicle.Body.Lights.Beam.High.IsOn -> {high_beam_state} (not written to broker)")

        print(f"[SDV Simulation] Cycle #{cycle}: Simulated High.IsOn={high_beam_state}, TCP={'REACHABLE' if is_connected else 'UNREACHABLE'}")
        sys.stdout.flush()

        time.sleep(2)

    print("[SDV Python App] Stopped gracefully.")

if __name__ == "__main__":
    main()
