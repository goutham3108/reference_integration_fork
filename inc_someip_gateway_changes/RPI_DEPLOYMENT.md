<!--
*******************************************************************************
Copyright (c) 2026 Contributors to the Eclipse Foundation

See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.

This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0

SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# S-CORE SOME/IP Gateway - Raspberry Pi Deployment

This guide builds the S-CORE SOME/IP gateway demo for 64-bit Raspberry Pi OS,
deploys it without committing generated artifacts to Git, and validates the
signal flow through the SDV Runtime's KUKSA Databroker.

The validated target is a Raspberry Pi running 64-bit Debian Bookworm / Raspberry
Pi OS (`aarch64`). The demo runs all components on one Pi using loopback SOME/IP.
The KUKSA clients in this repository use the KUKSA VAL v1 API, so the Databroker
must be the v1-compatible runtime binary supplied with the SDV Runtime.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [1. Prepare the Raspberry Pi](#1-prepare-the-raspberry-pi)
- [2. Prepare the Build Host](#2-prepare-the-build-host)
- [3. Build ARM64 Deployment Packages](#3-build-arm64-deployment-packages)
- [4. Transfer and Extract Packages](#4-transfer-and-extract-packages)
- [5. Start the Demo](#5-start-the-demo)
- [6. Verify Signals in KUKSA](#6-verify-signals-in-kuksa)
- [Signal Flow](#signal-flow)
- [Troubleshooting](#troubleshooting)
- [Stop the Demo](#stop-the-demo)
- [Validation Criteria](#validation-criteria)

## Architecture

```text
Tire-pressure publisher / Headlight publisher
                    |
                    | SOME/IP events over vSomeIP
                    v
                someipd
                    |
                    | gateway IPC
                    v
                gatewayd
                    |
                    | mw::com events
                    v
           KUKSA tire-pressure bridge
                    |
                    | gRPC / KUKSA VAL
                    v
           Eclipse KUKSA Databroker
                    |
                    v
              Databroker CLI
```

| Component | Responsibility | Runs on Pi |
| --- | --- | --- |
| `someipd` | vSomeIP routing manager and SOME/IP network binding | Yes |
| `gatewayd` | Converts SOME/IP events into mw::com events | Yes |
| `tire_pressure_publisher` | Offers service `0x4100`, event `0x8410` | Yes |
| `headlight_publisher` | Offers service `0x4200`, event `0x8420` | Yes |
| `kuksa_tire_pressure_bridge` | Writes mw::com values into Databroker VSS signals | Yes |
| SDV Runtime | Starts the Databroker, Kit Manager, kuksa-syncer, and mock provider | Yes |
| KUKSA Databroker | Stores and serves VSS signal values on `127.0.0.1:55555` | Yes, via SDV Runtime |
| Databroker CLI | Reads the current VSS values | Yes, Docker |

## Prerequisites

### Raspberry Pi

- Raspberry Pi 4/5 or equivalent ARM64 device
- 64-bit Raspberry Pi OS or Debian Bookworm
- At least 4 GB RAM and 10 GB free disk space
- Network access to the build host
- User account with `sudo` access

Confirm the Pi architecture:

```bash
uname -m
```

Expected output:

```text
aarch64
```

### Build host

- Linux x86_64 host with Git, Bazel/Bazelisk, SSH, and `scp`
- This repository cloned locally
- SSH access to the Raspberry Pi

Set these values on the build host. Replace them with the Raspberry Pi account
name and address:

```bash
PI_USER=<pi-user>
PI_HOST=<pi-hostname-or-ip>
```

Before building or deploying, verify non-interactive SSH access:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 \
  "$PI_USER@$PI_HOST" 'uname -m; command -v rsync'
```

Expected output includes `aarch64` and `/usr/bin/rsync`. If SSH times out or
returns `Permission denied`, fix the Pi address, network route, SSH service, or
public-key authentication before continuing.

## 1. Prepare the Raspberry Pi

Run these commands on the Raspberry Pi.

### 1.1 Install SSH and transfer tools

```bash
sudo apt update
sudo apt install -y rsync openssh-server ca-certificates
sudo systemctl enable --now ssh
```

Verify:

```bash
rsync --version
systemctl is-active ssh
```

Expected SSH status:

```text
active
```

### 1.2 Install Docker for KUKSA Databroker

The Pi used for this demo has Docker's official Debian repository enabled. Use
Docker's packages in that case; do not install Debian's `docker.io` package too,
because it conflicts with `containerd.io`.

```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and log back in, then verify Docker:

```bash
docker --version
docker run --rm hello-world
```

If Docker's official repository is not configured, use the Debian package instead:

```bash
sudo apt install -y docker.io
sudo usermod -aG docker "$USER"
```

Use exactly one Docker installation method.

### 1.3 Configure passwordless SSH from the build host

Run these commands on the build host, not on the Pi:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
ssh-copy-id -i ~/.ssh/id_ed25519.pub "$PI_USER@$PI_HOST"
ssh -o BatchMode=yes -o ConnectTimeout=15 "$PI_USER@$PI_HOST" \
  'uname -m; command -v rsync'
```

Before running the deployment validation from the build host, confirm that the
SSH key works without an interactive password prompt:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 \
  "$PI_USER@$PI_HOST" 'uname -m; command -v rsync'
```

Expected output includes:

```text
aarch64
/usr/bin/rsync
```

If this command returns `Permission denied (publickey,password)`, install the
public key with `ssh-copy-id` and repeat the check before continuing. If it
times out, check the Pi address, network route, and SSH service. Validation
should stop at this preflight until passwordless SSH is working.

## 2. Prepare the Build Host

Run all remaining build commands from the repository root on the Linux build host:

```bash
cd /path/to/inc_someip_gateway
export REPO_ROOT="$PWD"
```

The repository supplies an ARM64 Bazel configuration in `.bazelrc`:

```bash
--config=aarch64-linux
```

This configuration sets both the ARM64 platform and `--cpu=aarch64`. The explicit
CPU value is needed so gRPC/Abseil select ARM64 instructions rather than x86-only
flags such as `-maes` and `-msse4.1`.

### Optional: create the reusable local toolchain tarball

The direct GCC toolchain tarball is useful for standalone ARM64 builds and a Pi
sysroot snapshot. It is not needed to run the packaged demo because the repository
already provides an ARM64 Bazel toolchain.

```bash
cd "$REPO_ROOT"
tools/make_local_aarch64_toolchain.sh
```

Output:

```text
$HOME/aarch64_toolchain/aarch64-local-toolchain.tar.gz
```

## 3. Build ARM64 Deployment Packages

Build the gateway, publishers, KUKSA bridge, configurations, and deployment
archives. Do not commit anything under `bazel-bin`, `bazel-out`, or `bazel-testlogs`.
They are already ignored by `.gitignore`.

```bash
cd "$REPO_ROOT"

bazel build --config=aarch64-linux \
  //score/config:config_file \
  //score/gatewayd \
  //score/someipd \
  //tests/integration/tire_pressure_publisher:tire_pressure_publisher \
  //tests/integration/headlight_publisher:headlight_publisher \
  //kuksa_tire_pressure_bridge/kuksa_tire_pressure_bridge:kuksa_tire_pressure_bridge \
  //deployment:gateway_tar \
  //deployment:demo_tar
```

Expected package artifacts:

```text
bazel-bin/deployment/gateway_tar-aarch64.tar.gz
bazel-bin/deployment/demo_tar-aarch64.tar.gz
```

### Copy the packages to the Raspberry Pi

Run this command on the build host after the build completes:

```bash
scp bazel-bin/deployment/gateway_tar-aarch64.tar.gz \
  bazel-bin/deployment/demo_tar-aarch64.tar.gz \
  "$PI_USER@$PI_HOST:/home/$PI_USER/"
```

`gateway_tar` includes `someipd`, `gatewayd`, their configuration, vSomeIP
runfiles, the serializer library, and `run_gateway.sh`.

`demo_tar` includes both publishers, the KUKSA bridge, its runfiles, the vSomeIP
configuration, middleware configuration, and `run_demo.sh`.

## 4. Transfer and Extract Packages

Run on the build host:

```bash
cd "$REPO_ROOT"

scp bazel-bin/deployment/gateway_tar-aarch64.tar.gz \
  bazel-bin/deployment/demo_tar-aarch64.tar.gz \
  "$PI_USER@$PI_HOST:/home/$PI_USER/"
```

Extract on the Pi:

```bash
ssh "$PI_USER@$PI_HOST"

rm -rf ~/someip-demo
mkdir -p ~/someip-demo
tar -xzf ~/gateway_tar-aarch64.tar.gz -C ~/someip-demo
tar -xzf ~/demo_tar-aarch64.tar.gz -C ~/someip-demo

cd ~/someip-demo/score_someip_gateway
find gateway demo -maxdepth 1 -type f -perm -111 -printf '%p\n' | sort
```

Deployment directory layout:

```text
~/someip-demo/score_someip_gateway/
  gateway/
    run_gateway.sh
    someipd
    gatewayd
    gatewayd_config.bin
    gatewayd_mw_com_config.json
  demo/
    run_demo.sh
    tire_pressure_publisher
    headlight_publisher
    kuksa_tire_pressure_bridge
    vsomeip-gateway-services.json
    mw_someip_config.bin
    mw_com_config.json
```

## 5. Start the Demo

Use separate terminals on the Pi or separate SSH sessions from the build host.
Start services in this order.

### Terminal 1: KUKSA Databroker

Run the ARM64 Databroker supplied by the SDV Runtime. It listens on port
`55555`. Do not use the `:main` Databroker image here: the current `0.7.2-dev`
image does not implement the v1 RPCs used by Velocitas and the bridge and will
return gRPC status `UNIMPLEMENTED` (code `12`).

```bash
cd ~/sdv-runtime-fork
./bin/arm64/databroker-arm64 \
  --vss ~/sdv-runtime-fork/data/vss-core/vss.json
```

Wait for the Databroker to report that it is listening on `127.0.0.1:55555`.

### Terminal 2: Kit Manager

Install the Kit Manager dependencies once, then start the source version. This
avoids the packaged `node-km-arm64` launcher error involving
`/snapshot/Kit-Manager/src/index.js`.

```bash
cd ~/sdv-runtime-fork/Kit-Manager
npm install
node src/index.js
```

Kit Manager listens on port `3090`. Do not start another `node src/index.js`
process if Kit Manager is already listening on that port.

### Terminal 3: SDV Runtime and kuksa-syncer

Run the setup script once. It verifies the ARM64 binaries and installs the
runtime's local Python packages:

```bash
cd ~/sdv-runtime-fork
./setup.sh
```

Then start the runtime with the external Databroker on port `55555`:

```bash
cd ~/sdv-runtime-fork
export VDB_ADDRESS=127.0.0.1:55555
export SYNCER_SERVER_URL=https://kit.digitalauto.tech
./run.sh LocalSDVRuntime
```

`run.sh` starts kuksa-syncer and the mock provider and uses the Databroker from
Terminal 1. It may also attempt to start the packaged Kit Manager; if that
prints the `/snapshot/Kit-Manager/src/index.js` error, continue using the
source Kit Manager from Terminal 2.

Verify the services from another Pi terminal:

```bash
sudo ss -ltnp | grep -E ':3090|:55555'
```

Wait until the Databroker, Kit Manager, and runtime services are ready before
continuing.

### Terminal 4: SOME/IP daemon

```bash
cd ~/someip-demo/score_someip_gateway/gateway
export VSOMEIP_CONFIGURATION=../demo/vsomeip-gateway-services.json
./run_gateway.sh someipd
```

Wait for vSomeIP to initialize and subscribe to services `0x4100` and `0x4200`.

### Terminal 5: Gateway daemon

```bash
cd ~/someip-demo/score_someip_gateway/gateway
./run_gateway.sh gatewayd
```

Wait for:

```text
[gatewayd] IPC connection to someipd established
Gateway started, waiting for shutdown signal...
```

### Terminal 6: Tire-pressure publisher

```bash
cd ~/someip-demo/score_someip_gateway/demo
./run_demo.sh tire-pressure
```

Expected output cycles from 40 down to 20:

```text
NOTIFY [4100.1000.8410] pressure=40
```

### Terminal 7: Headlight publisher

```bash
cd ~/someip-demo/score_someip_gateway/demo
./run_demo.sh headlight
```

Expected output alternates:

```text
NOTIFY [4200.1001.8420] headlights=on
NOTIFY [4200.1001.8420] headlights=off
```

### Terminal 8: KUKSA bridge

```bash
cd ~/someip-demo/score_someip_gateway/demo
./run_demo.sh kuksa-bridge 127.0.0.1:55555
```

Expected output includes:

```text
KUKSA: connected to 127.0.0.1:55555
KUKSA bridge: subscribed to gatewayd/tire_pressure.
KUKSA bridge: subscribed to gatewayd/headlight.
```

The bridge writes SOME/IP events to the Databroker using VAL v1 `Set` and
subscribes to Databroker values using VAL v1 `Subscribe`. It offers the reverse
mw::com services `kuksa/tire_pressure` and `kuksa/headlight`; gatewayd forwards
their events to outbound SOME/IP services.

## 6. Verify Signals in KUKSA

### Terminal 9: KUKSA CLI

```bash
docker run --rm -it --network host \
  ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main \
  --protocol kuksa.val.v1 \
  --server http://127.0.0.1:55555
```

At the `kuksa.val.v1 >` prompt, enter:

```text
get Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire.Pressure Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.Pressure Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire.Pressure Vehicle.Body.Lights.Beam.High.IsOn
```

Expected result shape:

```text
[get]  OK
Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure: 37 kPa
Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire.Pressure: 37 kPa
Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.Pressure: 37 kPa
Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire.Pressure: 37 kPa
Vehicle.Body.Lights.Beam.High.IsOn: true
```

Run the same `get` command again. The tire pressure changes each second and the
headlight value alternates between `true` and `false`.

Exit the CLI:

```text
quit
```

## Signal Flow

| Signal | SOME/IP service / instance / event | mw::com service | VSS destination |
| --- | --- | --- | --- |
| Tire pressure | `0x4100` / `0x1000` / `0x8410` | `gatewayd/tire_pressure` | Four `Vehicle.Chassis.Axle.*.Wheel.*.Tire.Pressure` signals |
| Headlight | `0x4200` / `0x1001` / `0x8420` | `gatewayd/headlight` | `Vehicle.Body.Lights.Beam.High.IsOn` |

The reverse services have separate IDs and require an external SOME/IP
subscriber to observe the outbound notifications:

| VSS source | mw::com service | SOME/IP service / instance / event | Payload |
| --- | --- | --- | --- |
| Four tire pressures | `kuksa/tire_pressure` | `0x4101` / `0x1002` / `0x8411` | Four uint8 values: FL, FR, RL, RR |
| High-beam state | `kuksa/headlight` | `0x4201` / `0x1003` / `0x8421` | One byte: `0` off, `1` on |

The vSomeIP configuration is loopback-based:

```json
"unicast": "127.0.0.1"
```

Therefore this guide runs the complete demo on one Pi. To place a SOME/IP
publisher on a separate ECU, replace loopback with the relevant Pi network
address and configure the other ECU's service discovery and unicast settings.

## Troubleshooting

### `No route to host` while copying to the Pi

Check the Pi address and SSH service:

```bash
hostname -I
sudo systemctl status ssh
```

Then test from the build host:

```bash
ssh -o BatchMode=yes "$PI_USER@$PI_HOST" 'uname -m'
```

### `docker.io` conflicts with `containerd.io`

Docker's official repository is configured. Use:

```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Do not install `docker.io` in that setup.

### `error while loading shared libraries`

Use the package launchers, not raw binaries:

```bash
./run_gateway.sh someipd
./run_gateway.sh gatewayd
./run_demo.sh tire-pressure
./run_demo.sh headlight
```

The scripts locate and export the vSomeIP and serializer library paths.

### KUKSA bridge cannot find its middleware configuration

Start the bridge through `run_demo.sh`. It sets `RUNFILES_DIR` to the bridge
runfiles directory and connects to the SDV Runtime Databroker on port `55555`:

```bash
./run_demo.sh kuksa-bridge 127.0.0.1:55555
```

### Databroker CLI says `Not a tty`

Run it interactively with both `-it` options:

```bash
docker run --rm -it --network host \
  ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main \
  --protocol kuksa.val.v1 \
  --server http://127.0.0.1:55555
```

### Kit-Manager or `node src/index.js` fails with `Cannot find module 'express'`

Install the local Node.js dependencies once inside `Kit-Manager` and then rerun the
server:

```bash
cd ~/sdv-runtime-fork/Kit-Manager
npm install
node src/index.js
```

If you then see `EADDRINUSE: address already in use :::3090`, another Kit-Manager
instance is already running on port `3090`. Check it with:

```bash
sudo ss -ltnp | grep :3090
```

### Kit Manager fails with `EADDRINUSE` on port `3090`

This means Kit Manager is already running. Check the existing process and do
not start a second copy:

```bash
sudo ss -ltnp | grep :3090
ps aux | grep '[n]ode'
```

### Bridge reports KUKSA `PublishValue` or `Set` `code=12`

Code `12` (`UNIMPLEMENTED`) indicates that the wrong Databroker API is being
used. Stop the `:main`/`0.7.2-dev` broker and start the SDV Runtime's bundled
ARM64 broker from Terminal 1. Rebuild and redeploy the bridge after updating
it to the VAL v1 client. Do not mark the deployment as end-to-end complete
until a KUKSA write and a reverse subscription both succeed.

The Docker KUKSA CLI also requires a real interactive TTY. Run it from a Pi
terminal with `-it`; piping commands into it can fail with `Not a tty` or a
missing `terminfo` entry.

## Stop the Demo

Run on the Pi:

```bash
pkill -f 'someipd|gatewayd|tire_pressure_publisher|headlight_publisher|kuksa_tire_pressure_bridge' || true
pkill -f 'kuksa-syncer|mock-provider|node-km|databroker|node src/index.js' || true
rm -f /tmp/vsomeip*.lck
```

The second command stops the SDV Runtime services, including kuksa-syncer,
the mock provider, Kit Manager, and the Databroker. Do not run it if other
applications on the Pi depend on the SDV Runtime.

## Validation Criteria

Declare the deployment **end-to-end successful** only when all of these checks
pass in the same run:

- SSH preflight reports `aarch64` and `/usr/bin/rsync`.
- Databroker listens on `127.0.0.1:55555`.
- Kit Manager listens on port `3090`.
- kuksa-syncer and the mock provider connect to the Databroker.
- `someipd` starts its gateway IPC server without a bind error.
- `gatewayd` reports that it is waiting for shutdown.
- Both publishers emit SOME/IP events.
- The KUKSA bridge connects and subscribes to both mw::com services.
- The KUKSA CLI reads the four tire-pressure signals and
  `Vehicle.Body.Lights.Beam.High.IsOn`.
- The bridge reports that it offered KUKSA-to-SOME/IP publishers.
- An external SOME/IP subscriber receives service `0x4101` tire-pressure
  notifications and service `0x4201` headlight notifications after the
  corresponding Databroker values change.

Any `PublishValue` or `Set` error, including gRPC code `12`, is a failed
end-to-end validation even if the SOME/IP publishers and bridge subscriptions
work.

## Build and Deployment Status

The following was verified on Raspberry Pi `aarch64` on 2026-09-17:

- Custom ARM GNU toolchain produced and ran an ARM64 executable on the Pi.
- ARM64 builds completed for `someipd`, `gatewayd`, both publishers, and the KUKSA bridge.
- `gateway_tar-aarch64.tar.gz` and `demo_tar-aarch64.tar.gz` transferred and extracted successfully.
- The ARM64 Databroker listened on `127.0.0.1:55555`.
- kuksa-syncer and the mock provider started and targeted `127.0.0.1:55555`.
- Kit Manager started from source after `npm install` and listened on port `3090`.
- `someipd`, `gatewayd`, both publishers, and the KUKSA bridge ran together.
- Tire-pressure and headlight SOME/IP events were observed in the publisher logs.
- The bridge client was updated to KUKSA VAL v1 `Set`/`Subscribe`; the ARM64
  bridge target builds successfully.
- A fresh Pi validation with the rebuilt bridge and the bundled v1 Databroker is
  still required before declaring KUKSA writes complete.
- The bridge publishes reverse KUKSA-to-SOME/IP events on separate outbound
  service and instance IDs; a dedicated external SOME/IP subscriber is needed
  for on-Pi runtime confirmation.
