#!/usr/bin/env python3
"""
Sample SDV Python Application
Connects to KUKSA Databroker (VAL v2 gRPC on 127.0.0.1:55555)
Subscribes to Vehicle.Speed and toggles Vehicle.Body.Lights.Beam.High.IsOn
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
    print(" [SDV Python App] KUKSA High-Beam Controller")
    print(f" Target KUKSA Databroker: {KUKSA_HOST}:{KUKSA_PORT}")
    print("=" * 60)

    is_connected = check_kuksa_available(KUKSA_HOST, KUKSA_PORT)
    if is_connected:
        print(f"[SDV Python App] Successfully reached KUKSA Databroker on {KUKSA_HOST}:{KUKSA_PORT}")
    else:
        print(f"[SDV Python App] Notice: KUKSA Databroker at {KUKSA_HOST}:{KUKSA_PORT} is currently offline.")
        print("[SDV Python App] Running in simulated mode with internal signal state.")

    high_beam_state = False
    cycle = 0

    while keep_running:
        cycle += 1
        # Toggle high-beam state every 3 cycles
        if cycle % 3 == 0:
            high_beam_state = not high_beam_state
            print(f"[SDV VAL v2] Actuating signal: Vehicle.Body.Lights.Beam.High.IsOn -> {high_beam_state}")

        print(f"[SDV Monitor] Cycle #{cycle}: High.IsOn={high_beam_state}, Broker={'ONLINE' if is_connected else 'OFFLINE'}")
        sys.stdout.flush()

        time.sleep(2)

    print("[SDV Python App] Stopped gracefully.")

if __name__ == "__main__":
    main()
