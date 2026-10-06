# SDV Databroker Speed Demo

## Overview

This deployment runs KUKSA Databroker in place of the vehicle app for the
remote speed signal. It uses Eclipse S-CORE `mw::com` shared memory, a SOME/IP
gateway, and a compact UDP transport between the vehicle and remote Raspberry
Pis. The high-beam route remains in the demo assets but is not consumed in this
speed-only mode.

The broker exposes this VSS path:

```text
Vehicle.Speed
```

The remote app labels its input event `speedAck`. The gateway remaps that input
to the installed broker's existing `VehicleDynamicsService.speed` binding on
Service1; the broker source and binary remain unchanged:

```text
VehicleDynamicsService.speedAck
```

When a numeric speed is entered on the remote, it sends `speedAck`. The bridge
uses SOME/IP event ID 1, and the gateway publishes it as the existing typed
`speed` sample on Service1. KUKSA maps that sample to `Vehicle.Speed`. New
route entries can be added to `signal_routes.json` without changing the UDP
frame implementation.

## Architecture

```text
Vehicle RPi: 10.56.121.101
  KUKSA Databroker
        <- mw::com SHM (`VehicleDynamicsService.speed` on Service1)
  gatewayd
        -> gateway IPC
  someipd
    -> SOME/IP service 0x1921, instance 0x0002, event 0x0001
  vehicle_high_beam_bridge
      -> UDP 10.56.121.79:35001

Remote RPi: 10.56.121.79
  vehicle_high_beam_remote_app
        -> UDP 10.56.121.101:35000
```

### Remote Speed Flow

```text
Remote user enters speed
  -> remote app sends `speedAck` over UDP
  -> vehicle_high_beam_bridge
  -> SOME/IP service 0x1921, instance 0x0002, event 0x0001
  -> someipd and gatewayd
  -> typed mw::com sample in shared memory
  -> KUKSA Databroker exposes `Vehicle.Speed`
```

### Component Roles

| Component | Role |
| --- | --- |
| `databroker-mw-com-demo` | Uses the existing Service1 `speed` binding and exposes `Vehicle.Speed`. |
| `gatewayd` | Maps the remote `speedAck` input to a typed Service1 `speed` sample. |
| `someipd` | Owns the local SOME/IP/vSomeIP binding and gateway IPC connection. |
| `vehicle_high_beam_bridge` | Converts SOME/IP events to UDP and remote UDP frames to SOME/IP events. |
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
sudo apt install -y rsync openssh-server ca-certificates libstdc++6 libgcc-s1 libc6 libatomic1 libacl1
sudo systemctl enable --now ssh
```

## Build and Package

KUKSA Databroker is already installed on the vehicle Pi. This workflow does
not rebuild, copy, or replace its executable. By default,
`start-vehicle.sh` uses
`~/vehicle-dynamics-example/bin/databroker-mw-com-demo` and that installation's
`mw_com_provider/generated/vehicle_dynamics_lola_config.json`.

Build and package the gateway and speed mapping from the workspace root on the
x86_64 build host:

```bash
cd ~/reference_integration_fork
bash sdv-hack-demo/build-aarch64.sh
bash sdv-hack-demo/package-aarch64.sh
```

On the vehicle Pi, verify the existing installation matches the launcher's
defaults:

```bash
test -x ~/vehicle-dynamics-example/bin/databroker-mw-com-demo
test -f ~/vehicle-dynamics-example/bin/mw_com_provider/generated/vehicle_dynamics_lola_config.json
```

If both commands succeed, start the vehicle stack with
`~/high-beam/run/start-vehicle.sh`; no `DATABROKER_BIN` or `SCORE_CONFIG`
overrides are needed. The separate-terminal broker command later in this guide
uses these same paths.

The scripts create these Git-ignored archives:

```text
dist/high-beam-vehicle-aarch64.tar.gz
dist/high-beam-remote-aarch64.tar.gz
```

The archives include the gateway executables, required Bazel runfiles, vSomeIP
shared libraries, `score_com_serializer.so`, the speed mapping, and launch
scripts. They do not contain or replace the existing Databroker installation.

Important build note:

- The `bash build-aarch64.sh` step performs cross-compilation using Bazel and
  requires the full workspace (not just the `sdv-hack-demo` folder) plus a
  configured aarch64 cross-toolchain on the build host. The build host must
  have the workspace root accessible so Bazel can build `someipd`, `gatewayd`,
  and other dependencies. By default this workspace expects a local toolchain
  at `$HOME/aarch64_toolchain` to satisfy cross-compilation.

- After packaging, deploy the gateway archive to the vehicle Pi and the remote
  app archive to the remote Pi. Keep the existing Databroker installation in
  place; no Bazel or build toolchain is required on the Pis.

- The packaged provider maps the gateway's `speed` sample on Service1 to
  `Vehicle.Speed`. The gateway presents the remote `speedAck` input as that
  existing binding; no Databroker source edits or binary deployment are needed.

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

On the remote Pi (`10.56.121.79`), start the remote application:

```bash
~/high-beam/run/start-remote.sh
```

On the vehicle Pi (`10.56.121.101`), start the gateway and Databroker stack:

```bash
~/high-beam/run/start-vehicle.sh
```

This starts `someipd`, `gatewayd`, the UDP bridge, and KUKSA Databroker. It does
not start the vehicle application. At the remote menu, choose option `2` and
enter a numeric speed.

### Run Each Process Separately

Use these commands instead of `start-vehicle.sh` when you want each vehicle
process in its own terminal. Do not run both methods at the same time.

Once on the vehicle Pi, prepare the SOME/IP config:

```bash
cd ~/high-beam
source ./network.env
cp vsomeip-gateway-services.json vsomeip-vehicle.json
sed -i "s/\"unicast\": \"127.0.0.1\"/\"unicast\": \"${HIGH_BEAM_VEHICLE_IP}\"/" vsomeip-vehicle.json
```

In **each vehicle-side terminal**, run this setup first:

```bash
cd ~/high-beam
source ./network.env
vsomeip_lib_dir="$(find "$PWD/someipd.runfiles" -name 'libvsomeip3.so.3' -printf '%h\n' -quit)"
test -n "$vsomeip_lib_dir" || { echo "libvsomeip3.so.3 not found"; exit 1; }
export LD_LIBRARY_PATH="$PWD:$vsomeip_lib_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

Start these in order, each in a separate terminal. After `gatewayd` starts,
wait about 10 seconds before starting the broker.

**Terminal 1: SOME/IP daemon**

```bash
VSOMEIP_CONFIGURATION="$PWD/vsomeip-vehicle.json" \
  ./someipd --configuration "$PWD/mw_someip_config.bin"
```

**Terminal 2: gateway daemon**

```bash
./gatewayd --configuration "$PWD/mw_someip_config.bin" \
  --service_instance_manifest "$PWD/mw_com_config.json"
```

**Terminal 3: UDP/SOME/IP bridge**

```bash
export HIGH_BEAM_BIND_IP=0.0.0.0
export SIGNAL_ROUTE_CONFIG="$PWD/signal_routes.json"
VSOMEIP_CONFIGURATION="$PWD/vsomeip-vehicle.json" \
VEHICLE_DOMAIN_CONFIG="$PWD/vsomeip-vehicle.json" \
  ./vehicle_high_beam_bridge
```

**Terminal 4: existing KUKSA Databroker**

```bash
cd ~/vehicle-dynamics-example/bin
./databroker-mw-com-demo \
  --address 0.0.0.0:55555 \
  --provider-config "$HOME/high-beam/remote_speed_provider_config.json" \
  --score-config "$PWD/mw_com_provider/generated/vehicle_dynamics_lola_config.json" \
  --include-vss-path Vehicle.Speed
```

On the remote Pi, start `~/high-beam/run/start-remote.sh` in its own terminal.
Then enter a speed using menu option `2`.

On the vehicle Pi, connect the CLI and subscribe:

```bash
cd ~/vehicle-dynamics-example/bin
./databroker-cli --server http://127.0.0.1:55555
```

At the CLI prompt:

```text
subscribe Vehicle.Speed
```

The remote should log `Remote published Vehicle.speedAck=<value>`; the CLI
should report the same value for `Vehicle.Speed`. Useful vehicle-side logs:

```bash
tail -f ~/high-beam/gatewayd.log ~/high-beam/someipd.log ~/high-beam/bridge.log
```

To stop the vehicle stack, press `Ctrl+C` in the Databroker terminal, then run:

```bash
pkill -TERM -x gatewayd 2>/dev/null || true
pkill -TERM -x someipd 2>/dev/null || true
pkill -TERM -f '[v]ehicle_high_beam_bridge' 2>/dev/null || true
pkill -TERM -f '[d]atabroker-mw-com-demo' 2>/dev/null || true
rm -f /tmp/vsomeip*.lck /tmp/vsomeip-[0-9]*
```

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

The broker runs in the foreground in the terminal where you launched
`start-vehicle.sh`; remote menu output appears in the terminal running
`start-remote.sh`. To save the broker and vehicle-side output while watching it:

```bash
~/high-beam/run/start-vehicle.sh 2>&1 | tee ~/high-beam/databroker.log
```

```bash
~/high-beam/run/start-remote.sh 2>&1 | tee ~/high-beam/remote_app.log
```

Check whether the background processes are still running:

```bash
pgrep -af 'someipd|gatewayd|vehicle_high_beam|databroker-mw-com-demo'
```

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
pkill -TERM -x gatewayd 2>/dev/null || true
pkill -TERM -x someipd 2>/dev/null || true
pkill -TERM -f '[v]ehicle_high_beam_bridge' 2>/dev/null || true
pkill -TERM -f '[d]atabroker-mw-com-demo' 2>/dev/null || true
sleep 1
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
  vehicle_app/                  Optional legacy vehicle-app source; not packaged
  architecture.drawio           Editable architecture diagram
```
