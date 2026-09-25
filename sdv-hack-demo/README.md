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

The vehicle application accepts `true` or `false`. The remote sensor application
receives that value, updates its state, and sends its current state back every
two seconds. Both applications also accept manual `true` or `false` input.

## Architecture

```text
Vehicle RPi: 172.19.229.101
  vehicle_high_beam_mw_com
        -> mw::com SHM(accessed by mw::com proxy of gatewayd)
  gatewayd
        -> gateway IPC
  someipd
        -> SOME/IP event 0x8430
  vehicle_high_beam_bridge
        -> UDP 172.19.229.79:35001

Remote RPi: 172.19.229.79
  vehicle_high_beam_remote_app
        -> UDP 172.19.229.101:35000
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

If you prefer to run the Bazel commands manually (step-by-step), the demo build does these builds in order:

```bash
# From the workspace root
bazel build --config=aarch64-linux //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com

# Build the gateway and its integration test targets (run from inc_someip_gateway/ or workspace root)
cd inc_someip_gateway
bazel build --config=aarch64-linux \
  //score/config:config_file \
  //score/gatewayd \
  //score/serializer:null_serializer \
  //score/someipd

# Build the demo-local bridge and remote app from the workspace root.
# --host_copt=-std=gnu11 is required for Bazel's host pkg-config helper.
cd ..
bazel build --config=aarch64-linux --host_copt=-std=gnu11 \
  //sdv-hack-demo/bridge:vehicle_high_beam_bridge \
  //sdv-hack-demo/remote_app:vehicle_high_beam_remote_app

# Then run packaging
cd sdv-hack-demo
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

## Deploy

Transfer the archives from the build host. Enter the SSH password directly when
prompted.

```bash
scp dist/high-beam-vehicle-aarch64.tar.gz <user>@172.19.229.101:/tmp/
scp dist/high-beam-remote-aarch64.tar.gz <user>@172.19.229.79:/tmp/
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
export HIGH_BEAM_VEHICLE_IP=172.19.229.101
export HIGH_BEAM_REMOTE_IP=172.19.229.79
export HIGH_BEAM_BRIDGE_UDP_PORT=35000
export HIGH_BEAM_REMOTE_UDP_PORT=35001
```

Verify that required libraries were extracted:

```bash
find ~/high-beam -name 'libvsomeip3.so.3' -type f -print
```

## Run the Demo

### 1. Start the Remote Sensor

On `172.19.229.79`:

```bash
~/high-beam/run/start-remote.sh
```

The remote app listens on UDP port `35001` and sends sensor frames to
`172.19.229.101:35000`.

### 2. Start the Vehicle Stack

On `172.19.229.101`:

```bash
~/high-beam/run/start-vehicle.sh
```

This launcher:

1. Creates a vehicle SOME/IP configuration with unicast address `172.19.229.101`.
2. Starts `someipd` in the background.
3. Starts `gatewayd` in the background.
4. Starts the UDP bridge in the background.
5. Starts the vehicle application in the foreground.

The vehicle application accepts:

```text
true
false
```

The remote sensor terminal also accepts `true` or `false`. Its next two-second
UDP update is delivered to the vehicle app.

## Expected Logs

When `true` is entered in the vehicle application, the following messages show
the forward path:

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

Vehicle-side background logs are stored in:

```text
~/high-beam/someipd.log
~/high-beam/gatewayd.log
~/high-beam/bridge.log
```

## Inspect and Troubleshoot

Check UDP listeners on either Pi:

```bash
ss -lunp | grep -E ':35000|:35001' || true
```

Check connectivity:

```bash
ping -c 3 172.19.229.101
ping -c 3 172.19.229.79
```

If a firewall is active, allow UDP:

```bash
# Vehicle RPi
sudo ufw allow from 172.19.229.79 to any port 35000 proto udp

# Remote RPi
sudo ufw allow from 172.19.229.101 to any port 35001 proto udp
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
sudo pkill -9 -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null || true
rm -f /tmp/vsomeip*.lck
```

On the Remote RPi:

```bash
pkill -9 -f vehicle_high_beam_remote_app 2>/dev/null || true
```

## Project Files

```text
sdv-hack-demo/
  build-aarch64.sh              Build all ARM64 demo targets
  package-aarch64.sh            Produce vehicle and remote archives
  deploy/start-vehicle.sh       Launch vehicle stack on 172.19.229.101
  deploy/start-remote.sh        Launch remote sensor on 172.19.229.79
  deploy/network.env            Editable vehicle/remote address configuration
  vehicle_app/                  Vehicle `mw::com` application source
  architecture.drawio           Editable architecture diagram
```
