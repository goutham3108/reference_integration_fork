# S-CORE KUKSA High-Beam Demo

This workspace integrates S-CORE modules. Remote values cross the existing
UDP bridge and SOME/IP gateway, then reach both the vehicle app and KUKSA
Databroker on Pi A through mw::com.

```text
KUKSA client          vehicle app
    ^                     ^
    |                     |
Databroker + mw_com_provider (Pi A)
    ^
    | mw::com / LoLa
gatewayd <- someipd <- vehicle_high_beam_bridge
                            ^
                            | UDP across the network
                       remote app (Pi B)
```

KUKSA receives `Vehicle.Speed` (`float`, km/h) from `/Vehicle/Service2/Instance`
and `Vehicle.Body.Lights.Beam.High.IsOn` (`bool`) from
`/vehicle_high_beam/network_rx`. The vehicle app subscribes to the same
instances. Speed is not rescaled, so the value entered on the remote is shown
unchanged.

The provider now converts the LoLa double speed payload to the VSS float type.
High.IsOn supports separate Rx input and Tx actuation bindings. In default
combined mode the vehicle menu submits VAL v2 actuation commands to KUKSA,
which owns the high-beam Tx instance. Remote hardware mode reads GPIO 17 and
independently drives a command LED on GPIO 27. See the hardware and command-mode
instructions in [the demo guide](sdv-hack-demo/README.md).

## Current Status

The build compiles the gateway, bridge, legacy vehicle app, remote app, and
KUKSA runtime. `start-vehicle.sh` starts the gateway and bridge, starts KUKSA in
the background on `0.0.0.0:55555`, and then runs the vehicle app in the
foreground. KUKSA subscribes only to the remote-fed speed and high-beam signals.

## 1. Prepare Pi A for Toolchain Creation

The cross-toolchain script downloads the ARM GNU compiler and copies the
sysroot from a live Raspberry Pi over SSH. Pi A can provide that sysroot. On
Pi A, install SSH and rsync and check its architecture:

```bash
sudo apt update
sudo apt install -y openssh-server rsync
sudo systemctl enable --now ssh
uname -m
```

Use a 64-bit Linux image; `uname -m` should print `aarch64`. Note Pi A's IP
address and SSH username.

## 2. Create the AArch64 Toolchain on the Build Host

On an x86_64 Linux build host, install the toolchain script prerequisites:

```bash
sudo apt update
sudo apt install -y bash curl xz-utils tar rsync openssh-client build-essential cmake file
```

Verify SSH access to Pi A:

```bash
ssh <pi-user>@<pi-a-ip>
```

Edit `inc_someip_gateway/tools/make_local_aarch64_toolchain.sh` and set
`PI_USER`, `PI_HOST`, and `OUTDIR`. The script downloads the ARM GNU toolchain,
copies the Pi's headers and libraries into a sysroot, creates compiler
wrappers, and archives the result. Its default output directory is
`$HOME/aarch64_toolchain`.

Run it from the integration workspace root:

```bash
bash inc_someip_gateway/tools/make_local_aarch64_toolchain.sh
```

Check the generated compiler and configure the environment in the same build
host terminal:

```bash
$HOME/aarch64_toolchain/local/bin/aarch64-linux-gnu-gcc --version
$HOME/aarch64_toolchain/local/bin/aarch64-linux-gnu-g++ --version

export AARCH64_TOOLCHAIN_ROOT="$HOME/aarch64_toolchain"
export AARCH64_CC="$AARCH64_TOOLCHAIN_ROOT/local/bin/aarch64-linux-gnu-gcc"
export AARCH64_CXX="$AARCH64_TOOLCHAIN_ROOT/local/bin/aarch64-linux-gnu-g++"
export AARCH64_AR="$AARCH64_TOOLCHAIN_ROOT/toolchain/bin/aarch64-none-linux-gnu-ar"
```

These variables select the AArch64 C compiler, C++ linker, and archiver for
the Cargo native dependencies. Keep the toolchain on the build host; do not
copy it to either Pi.

## 3. Install the Build Tools

Install Bazelisk or the Bazel version selected by `.bazelversion`, and install
Rustup with Rust stable 1.96 or newer. The build also requires the `file`
utility. The KUKSA build helper installs the Rust target when run, or it can be
installed manually:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
rustup toolchain install stable
rustup update stable
rustup target add --toolchain stable aarch64-unknown-linux-gnu
rustup run stable rustc --version
bazel --version
```

The build host also needs the `baselibs/`, `communication/`,
`inc_someip_gateway/`, and `kuksa-databroker/` source checkouts at the workspace
root. If Communication is elsewhere, set `COMMUNICATION_ROOT` to its path.

## 4. Configure KUKSA to Replace the Vehicle Publisher

The old vehicle app publishes a `high_beam_state` event from
`vehicle_high_beam/local_tx`; `gatewayd`, `someipd`, and the bridge consume
that event. KUKSA must replace that publisher, not the remote app.

The high-beam mapping is bidirectional: its primary binding receives remote
input, and `actuation_binding` sends commands through the local transmit service.
The demo seeds one actuator entry, keeping input/current value independent of
command delivery. The provider owns high-beam Tx in combined mode; the vehicle
menu uses VAL v2 `Actuate` rather than offering another Tx skeleton. Use
`HIGH_BEAM_COMMAND_MODE=direct` only for the legacy vehicle-publisher mode;
the launcher disables KUKSA high-beam actuation in that mode.

## 5. Build ARM64 Artifacts on the Host

The build command compiles these ARM64 outputs:

- KUKSA `databroker`, `databroker-cli`, `mw_com_provider`, and
  `databroker-mw-com-demo`.
- The existing `gatewayd`, `someipd`, serializer, UDP bridge, remote
  application, and legacy `vehicle_high_beam_mw_com` app.
- Communication vehicle-dynamics Bazel artifacts used while building the
  KUKSA mw::com integration.

Run the build on the x86_64 Linux build host:

```sh
bash sdv-hack-demo/build-aarch64.sh
```

The command builds gateway targets from `inc_someip_gateway/`, builds the
legacy vehicle app, bridge, and remote app from the workspace root, then runs
`kuksa-databroker/scripts/build-rpi-aarch64.sh`. The KUKSA helper builds the
Communication dependency and Rust targets, then verifies that its executables
are AArch64. Both scripts stop on the first failed command. A successful run
ends with `All requested Raspberry Pi targets built successfully.` and exits
with status 0; if a command fails, the script exits nonzero and reports the
failed step.

The build outputs are left in their project build directories; this command
does not package them or run `scp`:

```text
inc_someip_gateway/bazel-bin/score/gatewayd/gatewayd
inc_someip_gateway/bazel-bin/score/someipd/someipd
inc_someip_gateway/bazel-bin/score/serializer/score_com_serializer.so
bazel-bin/sdv-hack-demo/vehicle_app/vehicle_high_beam_mw_com
bazel-bin/sdv-hack-demo/bridge/vehicle_high_beam_bridge
bazel-bin/sdv-hack-demo/remote_app/vehicle_high_beam_remote_app
kuksa-databroker/target/aarch64-unknown-linux-gnu/release/databroker
kuksa-databroker/target/aarch64-unknown-linux-gnu/release/databroker-cli
kuksa-databroker/target/aarch64-unknown-linux-gnu/release/mw_com_provider
kuksa-databroker/target/aarch64-unknown-linux-gnu/release/databroker-mw-com-demo
communication/bazel-bin/score/mw/com/example/vehicle-dynamics-example/
```

The Communication output is a build-time dependency, not an additional demo
process to copy to a Pi. If Communication is outside this workspace, its
Bazel outputs are under the configured `COMMUNICATION_ROOT` instead. The
KUKSA helper itself runs `file` checks on `databroker`, `databroker-cli`,
`mw_com_provider`, and `databroker-mw-com-demo`. You can also check the main
demo and remote executables manually:

```sh
file kuksa-databroker/target/aarch64-unknown-linux-gnu/release/databroker-mw-com-demo
file bazel-bin/sdv-hack-demo/remote_app/vehicle_high_beam_remote_app
```

Both should report AArch64 executables. The Bazel outputs also include their
runfiles; they are not copied into deployment archives by the build command.

## 6. Package and Copy to the Pis

Package on the build host; packaging and transfer are separate from the build:

```sh
bash sdv-hack-demo/package-aarch64.sh
```

The package step creates `vehicle-aarch64.tar.gz` and `remote-aarch64.tar.gz`.
The vehicle archive includes the gateway daemons, bridge, KUKSA
`databroker-mw-com-demo`, `databroker-cli`, both provider JSON configs, and the
legacy `vehicle_high_beam_mw_com` app with its runfiles. It excludes
`kuksa_high_beam_udp_provider`, which is a separate adapter and is not needed
for the KUKSA-to-mw::com bridge path. The remote archive and app are unchanged.
`scp` only transfers the completed archives:

```sh
scp sdv-hack-demo/dist/vehicle-aarch64.tar.gz \
  <pi-user>@<pi-a-ip>:/tmp/
scp sdv-hack-demo/dist/remote-aarch64.tar.gz \
  <pi-user>@<pi-b-ip>:/tmp/
```

## 7. Start and Test the Demo

The steps below assume the vehicle and remote archives have been packaged and
copied to the Pis.

Pi 1 is the vehicle side (Pi A); Pi 2 is the remote side (Pi B). On **both**
Pis, extract the appropriate archive first:

```bash
mkdir -p ~/sdv-demo
tar -xzf /tmp/vehicle-aarch64.tar.gz -C ~/sdv-demo
```

Run that command on Pi 1 with the vehicle archive. On Pi 2, use the remote
archive instead:

```bash
mkdir -p ~/sdv-demo
tar -xzf /tmp/remote-aarch64.tar.gz -C ~/sdv-demo
```

Then edit `~/sdv-demo/network.env` on **both** Pis. Set the same vehicle and
remote LAN addresses on each Pi; do not leave the loopback defaults
(`127.0.1.1`) when the devices are separate:

```bash
nano ~/sdv-demo/network.env
```

Use the actual addresses assigned by your network:

```bash
export HIGH_BEAM_VEHICLE_IP=<Pi-1-LAN-IP>
export HIGH_BEAM_REMOTE_IP=<Pi-2-LAN-IP>
export HIGH_BEAM_BRIDGE_UDP_PORT=35000
export HIGH_BEAM_REMOTE_UDP_PORT=35001
```

On **Pi 2 (remote)**, start its service first:

```bash
~/sdv-demo/run/start-remote.sh
```

The remote application stays in the foreground. Keep the terminal open to see
its output. Then, on **Pi 1 (vehicle)**, start the vehicle services:

```bash
~/sdv-demo/run/start-vehicle.sh
```

The vehicle launcher keeps `someipd`, `gatewayd`, the bridge, and KUKSA
running in the background; the vehicle app runs in the foreground. Logs are
written under `~/sdv-demo/`, including `someipd.log`, `gatewayd.log`,
`bridge.log`, and `kuksa.log`.

On Pi 1, run the CLI from the extracted demo directory to read or subscribe to
values sent from the remote menu:

```sh
cd ~/sdv-demo
./databroker-cli --server http://127.0.0.1:55555 \
  get Vehicle.Speed Vehicle.Body.Lights.Beam.High.IsOn
./databroker-cli --server http://127.0.0.1:55555 \
  subscribe Vehicle.Speed
```

for cli 

```sh
cd ~/sdv-demo
./databroker-cli
```

The same values appear in the vehicle app as `Vehicle app received ...`. Use
the remote log and network checks in [the legacy demo guide](sdv-hack-demo/README.md)
if needed.

## Verified Data Paths

- Remote `Vehicle.speed` and high-beam input reach the vehicle app and KUKSA
  with the same values.
- Vehicle `Vehicle.speed` input is forwarded to the remote app with the same
  value.
- If no remote updates arrive, check that `~/sdv-demo/network.env` on both Pis
  contains the real vehicle and remote LAN IPs, not `127.0.1.1`.