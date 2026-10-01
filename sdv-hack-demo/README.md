# SDV High-Beam Demo

## Overview

This project demonstrates a bidirectional vehicle high-beam signal across two
Edge Devices. It uses Eclipse S-CORE `mw::com` shared memory on the Rpi
side, a SOME/IP gateway, and a compact UDP transport between the vehicle and
remote device(now we are using RPi need to change to Ardino).

The signal is:

```text
Vehicle.Body.Lights.Beam.High.IsOn
```

The demo also carries the initial vehicle-dynamics signals from the LoLa
example:

```text
Vehicle.speed
Vehicle.speedAck
```

The vehicle application provides a menu for publishing high-beam booleans or
speed values. The remote endpoint acknowledges configured non-high-beam
payloads, so `speed` returns as `speedAck`. New route entries can be added to
`signal_routes.json` without changing the UDP frame implementation.

## Architecture

```text
Vehicle RPi: 10.56.121.101
  vehicle_high_beam_mw_com
        -> mw::com SHM(accessed by mw::com proxy of gatewayd)
  gatewayd
        -> gateway IPC
  someipd
        -> SOME/IP event 0x8430
  vehicle_high_beam_bridge
      -> UDP 10.56.121.79:35001

Remote RPi: 10.56.121.79
  vehicle_high_beam_remote_app
        -> UDP 10.56.121.101:35000
```

### Forward Flow: Vehicle to Remote

```text
Vehicle app publishes High.IsOn
  -> mw::com GenericSkeleton and SHM
  -> gatewayd GenericProxy
  -> someipd
  -> SOME/IP service 0x4300, instance 0x1000, event 0x8430
  -> vehicle_high_beam_bridge
  -> UDP port 35001 on the Remote RPi
  -> remote sensor application
```

### Reverse Flow: Remote to Vehicle

```text
Remote sensor application
  -> UDP port 35000 on the Vehicle RPi
  -> vehicle_high_beam_bridge
  -> SOME/IP service 0x4300, instance 0x1001, event 0x8431
  -> someipd
  -> gatewayd GenericSkeleton
  -> mw::com SHM
  -> Vehicle app GenericProxy
```

### Component Roles

| Component | Role |
| --- | --- |
| `vehicle_high_beam_mw_com` | Vehicle-side publisher and subscriber using `mw::com`. |
| `gatewayd` | Uses `GenericProxy` for the local Tx service and `GenericSkeleton` for the local Rx service. |
| `someipd` | Owns the local SOME/IP/vSomeIP binding and gateway IPC connection. |
| `vehicle_high_beam_bridge` | Converts vehicle SOME/IP events to UDP and remote UDP frames to vehicle SOME/IP events. |
| `vehicle_high_beam_remote_app` | Remote sensor state machine; receives/sends UDP frames and publishes state every two seconds. |

## Prerequisites

### Build Host

- Linux x86_64 host
- Bazel/Bazelisk
- SSH and `scp`
- ARM64 build support configured in this workspace
- Raspberry Pi addresses reachable from the build host

The build scripts cross-compile with Bazel's `aarch64-linux` configuration.
The local `$HOME/aarch64_toolchain` is a build-host toolchain and is not copied
to the RPIs.

### Raspberry Pis

Both devices must run a 64-bit Linux distribution:

```bash
uname -m
```

Expected output:

```text
aarch64
```

Install basic runtime and transfer dependencies on both Pis:

```bash
sudo apt update
sudo apt install -y rsync openssh-server ca-certificates libstdc++6 libgcc-s1 libc6 libatomic1
sudo systemctl enable --now ssh
```

## Build and Package

Run on the build host from the demo folder (all sources are included under `sdv-hack-demo`):

```bash
cd sdv-hack-demo
bash build-aarch64.sh
bash package-aarch64.sh
```

The scripts create these Git-ignored archives:

```text
dist/high-beam-vehicle-aarch64.tar.gz
dist/high-beam-remote-aarch64.tar.gz
```

The archives include the executables, required Bazel runfiles, vSomeIP shared
libraries, `score_com_serializer.so`, configuration files, and launch scripts.

Important build note:

- The `bash build-aarch64.sh` step performs cross-compilation using Bazel and
  requires the full workspace (not just the `sdv-hack-demo` folder) plus a
  configured aarch64 cross-toolchain on the build host. The build host must
  have the workspace root accessible so Bazel can build `someipd`, `gatewayd`,
  and other dependencies. By default this workspace expects a local toolchain
  at `$HOME/aarch64_toolchain` to satisfy cross-compilation.

- After `package-aarch64.sh` completes, the produced archives are self-contained
  for runtime on the RPis — you only need to extract the appropriate archive
  on each Pi and run the scripts in `~/high-beam/run/` (no Bazel or toolchain is
  required on the RPis).

- If you want to avoid requiring the full workspace on the build host, you can
  either: (A) vendor prebuilt `someipd`/`gatewayd` and required libraries into
  `sdv-hack-demo/prebuilt/` and adjust the packaging script, or (B) add a
  standalone WORKSPACE and dependency fetching under `sdv-hack-demo` (larger
  effort). I can implement option A if you prefer a single-folder build flow.

- `build-aarch64.sh` rebuilds `someipd` and `gatewayd` from
  [inc_someip_gateway](../inc_someip_gateway) every time, so any change made
  there (for example to `mw_com_config.json`, `mw_someip_config.json`, or the
  gateway source) is picked up automatically the next time you run
  `bash build-aarch64.sh && bash package-aarch64.sh`. Always redeploy both
  archives after such a change — mixing an old daemon binary with a new
  `signal_routes.json`/`mw_com_config.json` is a common source of startup
  failures.

## Deploy

Transfer the archives from the build host. Enter the SSH password directly when
prompted.

```bash
scp dist/high-beam-vehicle-aarch64.tar.gz <user>@10.56.121.101:/tmp/
scp dist/high-beam-remote-aarch64.tar.gz <user>@10.56.121.79:/tmp/
```

On the Vehicle RPi:

```bash
rm -rf ~/high-beam
mkdir -p ~/high-beam
tar -xzf /tmp/high-beam-vehicle-aarch64.tar.gz -C ~/high-beam
```

On the Remote RPi:

```bash
rm -rf ~/high-beam
mkdir -p ~/high-beam
tar -xzf /tmp/high-beam-remote-aarch64.tar.gz -C ~/high-beam
```

Both archives include `~/high-beam/network.env`. Edit that file on either RPi
when the devices receive new IP addresses:

```bash
nano ~/high-beam/network.env
```

```bash
export HIGH_BEAM_VEHICLE_IP=10.56.121.101
export HIGH_BEAM_REMOTE_IP=10.56.121.79
export HIGH_BEAM_BRIDGE_UDP_PORT=35000
export HIGH_BEAM_REMOTE_UDP_PORT=35001
```

Verify that required libraries were extracted:

```bash
find ~/high-beam -name 'libvsomeip3.so.3' -type f -print
```

## Run the Demo

Both launchers automatically stop stale `someipd`/`gatewayd`/`vehicle_high_beam*`
processes and remove any leftover `/tmp/vsomeip*.lck` file before starting, and
they refuse to start if UDP port 35000/35001 is still in use. If you ever start
the apps manually (not via the launcher), clean up first:

```bash
pkill -TERM -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null || true
sleep 1
pkill -KILL -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null || true
rm -f /tmp/vsomeip*.lck
```

### 1. Start the Remote Sensor

On `10.56.121.79`:

```bash
~/high-beam/run/start-remote.sh
```

The remote app listens on UDP port `35001` and sends sensor frames to
`10.56.121.101:35000`.

### 2. Start the Vehicle Stack

On `10.56.121.101`:

```bash
~/high-beam/run/start-vehicle.sh
```

This launcher:

1. Creates a vehicle SOME/IP configuration with unicast address `10.56.121.101`.
2. Starts `someipd` in the background.
3. Starts `gatewayd` in the background.
4. Starts the UDP bridge in the background.
5. Starts the vehicle application in the foreground.

The vehicle application accepts:

```text
true
false
```

It also accepts this menu:

```text
1   Select high-beam and enter true or false
2   Select speed and enter a numeric value
q   Quit
```

The speed payload is the vehicle-dynamics example representation: an 8-byte
`double` followed by a 1-byte quality value (currently `3`).

The remote sensor also provides a menu:

```text
1   Select high-beam and enter true or false
2   Send Vehicle.speedAck to the vehicle (enter a numeric value)
q   Quit the input menu
```

The remote endpoint acknowledges incoming `Vehicle.speed` payloads as
`Vehicle.speedAck`. If you enter `12345` in the remote menu, it sends that
number on the reverse event; expect `Remote sent Vehicle.speedAck to
vehicle=12345` remotely and `Vehicle app received Vehicle.speedAck =
12345.000000` on the vehicle. Its high-beam state continues to send a UDP
update every two seconds.

## Expected Logs

When `true` is entered in the vehicle application (menu option `1`), the
following messages show the forward path:

```text
Vehicle app published Vehicle.Body.Lights.Beam.High.IsOn=true
Bridge forwarded vehicle-to-remote High.IsOn=true
Remote app converted UDP to SOME/IP High.IsOn=true
```

When the remote app sends its state, the reverse path produces:

```text
Remote sensor converted SOME/IP to UDP High.IsOn=true
Bridge converted UDP to SOME/IP High.IsOn=true
Vehicle app received Vehicle.Body.Lights.Beam.High.IsOn=true
```

When a numeric value is entered in the vehicle application (menu option `2`),
the `Vehicle.speed` round trip produces:

```text
Vehicle app published Vehicle.speed = 55.000000
Bridge forwarded vehicle_dynamics vehicle-to-remote value=55
Remote received Vehicle.speed=55
Remote acknowledged Vehicle.speedAck=55
Bridge converted UDP to SOME/IP vehicle_dynamics value=55
Vehicle app received Vehicle.speedAck = 55.000000
```

This exact round trip has been confirmed live on hardware; the vehicle app
receives its own `Vehicle.speedAck` within about a second of publishing.

### Both directions share one acknowledgement channel

`vehicle::VehicleDynamicsService` only defines two events: `speed` (vehicle to
remote) and `speedAck` (remote to vehicle) — there is no separate "remote's own
speed" event in this example. This means:

- When the **vehicle** publishes `Vehicle.speed`, the remote decodes it,
  echoes it straight back, and the vehicle sees its own value arrive as
  `Vehicle.speedAck`.
- When you manually enter a value in the **remote** app's menu option `2`, it
  is sent on that same `speedAck` channel — the vehicle app will show it as
  `Vehicle app received Vehicle.speedAck=<value>`, not as a new `Vehicle.speed`.

Both directions work and are bidirectional, but they use the same wire event
in the reverse direction, so a remote-entered value and an echoed
acknowledgement are indistinguishable to the vehicle app. Adding a genuinely
independent "remote-originated speed" signal would require a third event in
`signal_routes.json`/`mw_com_config.json`/`mw_someip_config.json` (for example
`speedRemote`), which is not part of the current vehicle-dynamics example.

Vehicle-side background logs are stored in:

```text
~/high-beam/someipd.log
~/high-beam/gatewayd.log
~/high-beam/bridge.log
```

## Watch Logs Live

Run these on the Vehicle RPi while the demo is running to follow each
process's output as it happens.

Follow a single log:

```bash
tail -f ~/high-beam/someipd.log
tail -f ~/high-beam/gatewayd.log
tail -f ~/high-beam/bridge.log
```

Follow all three vehicle-side logs at once, each line prefixed with its source:

```bash
tail -f ~/high-beam/someipd.log ~/high-beam/gatewayd.log ~/high-beam/bridge.log
```

Follow only High.IsOn state changes across all logs:

```bash
tail -f ~/high-beam/someipd.log ~/high-beam/gatewayd.log ~/high-beam/bridge.log | grep --line-buffered 'High.IsOn'
```

The vehicle application and the remote sensor run in the foreground, so their
output appears directly in the terminal where you launched
`~/high-beam/run/start-vehicle.sh` or `~/high-beam/run/start-remote.sh`. To
capture that output to a file as well while still seeing it live, restart with
`tee`:

```bash
~/high-beam/run/start-vehicle.sh 2>&1 | tee ~/high-beam/vehicle_app.log
```

```bash
~/high-beam/run/start-remote.sh 2>&1 | tee ~/high-beam/remote_app.log
```

Check whether the background processes are still running:

```bash
pgrep -af 'someipd|gatewayd|vehicle_high_beam'
```

## Inspect and Troubleshoot

If `someipd` or `gatewayd` crash immediately with:

```text
Assertion `result && "Instance id exceeds fixed size"' failed.
```

a service/instance identifier used internally by the gateway exceeded its
32-character limit. This happens if a service-instance key is derived from a
long string (for example a full service type name) instead of the short
numeric instance ID. Rebuild `someipd`/`gatewayd` from
[inc_someip_gateway](../inc_someip_gateway) after fixing the identifier and
redeploy — the vehicle and remote apps do not need to change.

If gatewayd logs:

```text
[gatewayd] Failed to create RemoteServiceInstance for '<instance specifier>'
```

or someipd logs:

```text
[someipd] Dropping SOME/IP event: no IPC subscriber connected for event_id=...
```

repeatedly (not just once at startup), the gateway's IPC binding never
completed its handshake with someipd for that instance. Stop everything,
remove `/tmp/vsomeip*.lck`, and restart in the order remote first, then
vehicle.

Check UDP listeners on either Pi:

```bash
ss -lunp | grep -E ':35000|:35001' || true
```

Check connectivity:

```bash
ping -c 3 10.56.121.101
ping -c 3 10.56.121.79
```

If a firewall is active, allow UDP:

```bash
# Vehicle RPi
sudo ufw allow from 10.56.121.79 to any port 35000 proto udp

# Remote RPi
sudo ufw allow from 10.56.121.101 to any port 35001 proto udp
```

If a runtime library is missing, confirm the archive contains real files rather
than unresolved symlinks:

```bash
find ~/high-beam -name 'libvsomeip3.so.3' -type f -print
find ~/high-beam -name 'score_com_serializer.so' -type f -print
```

## Stop the Demo

On the Vehicle RPi:

```bash
pkill -TERM -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null || true
sleep 1
pkill -KILL -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null || true
rm -f /tmp/vsomeip*.lck
```

On the Remote RPi:

```bash
pkill -TERM -f vehicle_high_beam_remote_app 2>/dev/null || true
sleep 1
pkill -KILL -f vehicle_high_beam_remote_app 2>/dev/null || true
```

Always clear the lock file and stop both daemons before extracting a new
archive over an old one; a stale `/tmp/vsomeip.lck` or leftover `someipd`
process holding UDP port 35000/35001 is the most common cause of a failed
restart.

## Project Files

```text
sdv-hack-demo/
  build-aarch64.sh              Build all ARM64 demo targets
  package-aarch64.sh            Produce vehicle and remote archives
  deploy/start-vehicle.sh       Launch vehicle stack on 10.56.121.101
  deploy/start-remote.sh        Launch remote sensor on 10.56.121.79
  deploy/network.env            Editable vehicle/remote address configuration
  signal_routes.json             Configured SOME/IP-to-UDP route mapping
  vehicle_app/                  Vehicle `mw::com` application source
  architecture.drawio           Editable architecture diagram
```
