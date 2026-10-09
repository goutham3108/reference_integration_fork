# SDV High-Beam Demo

## Overview

This project demonstrates a bidirectional vehicle high-beam signal across two
Edge Devices. It uses Eclipse S-CORE `mw::com` shared memory on the Rpi
side, a SOME/IP gateway, and a compact UDP transport between the vehicle and
remote device(now we are using RPi need to change to Ardino).

The KUKSA signals are:

```text
Vehicle.Body.Lights.Beam.High.IsOn  GPIO17 switch/software state (bidirectional)
Vehicle.Body.Lights.Beam.Low.IsOn   GPIO27 LED applied state (bidirectional)
Vehicle.Speed                     speed input (float, km/h)
```

The demo also carries the initial vehicle-dynamics signals from the LoLa
example:

```text
Vehicle.speed
Vehicle.speedAck
```

The vehicle application provides a menu for commanding low-beam LED booleans or
publishing speed values. By default its LED commands go through KUKSA VAL v2
actuation; the KUKSA provider is the sole lighting MW::COM Tx publisher.
Speed continues to use the existing vehicle publisher. The remote endpoint acknowledges configured non-high-beam
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
Vehicle app actuates Low.IsOn through KUKSA
  -> provider mw::com producer and SHM
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
dist/vehicle-aarch64.tar.gz
dist/remote-aarch64.tar.gz
```

The vehicle archive includes the gateway executables and runfiles, bridge,
`databroker-mw-com-demo`, `databroker-cli`, the KUKSA provider configuration
files, legacy `vehicle_high_beam_mw_com` app and its runfiles, serializer, and
launch/configuration files. It excludes `kuksa_high_beam_udp_provider`, which
is separate from the bridge and unnecessary for the KUKSA-to-mw::com path. The
remote archive includes the remote app and its runfiles and
launch/configuration files. `start-vehicle.sh` runs KUKSA in the background
and the vehicle app in the foreground; both receive remote speed and high-beam
updates from the gateway.

Important build note:

- The `bash build-aarch64.sh` step performs cross-compilation using Bazel and
  requires the full workspace (not just the `sdv-hack-demo` folder) plus a
  configured aarch64 cross-toolchain on the build host. The build host must
  have the workspace root accessible so Bazel can build `someipd`, `gatewayd`,
  and other dependencies. By default this workspace expects a local toolchain
  at `$HOME/aarch64_toolchain` to satisfy cross-compilation.

- After `package-aarch64.sh` completes, the produced archives are self-contained
  for runtime on the RPis — you only need to extract the appropriate archive
  on each Pi and run the scripts in `~/sdv-demo/run/` (no Bazel or toolchain is
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
scp dist/vehicle-aarch64.tar.gz <user>@10.56.121.101:/tmp/
scp dist/remote-aarch64.tar.gz <user>@10.56.121.79:/tmp/
```

On the Vehicle RPi:

```bash
rm -rf ~/sdv-demo
mkdir -p ~/sdv-demo
tar -xzf /tmp/vehicle-aarch64.tar.gz -C ~/sdv-demo
```

On the Remote RPi:

```bash
rm -rf ~/sdv-demo
mkdir -p ~/sdv-demo
tar -xzf /tmp/remote-aarch64.tar.gz -C ~/sdv-demo
```

Both archives include `~/sdv-demo/network.env`. Edit that file on either RPi
when the devices receive new IP addresses:

```bash
nano ~/sdv-demo/network.env
```

```bash
export HIGH_BEAM_VEHICLE_IP=10.56.121.101
export HIGH_BEAM_REMOTE_IP=10.56.121.79
export HIGH_BEAM_BRIDGE_UDP_PORT=35000
export HIGH_BEAM_REMOTE_UDP_PORT=35001
```

Verify that required libraries were extracted:

```bash
find ~/sdv-demo -name 'libvsomeip3.so.3' -type f -print
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
~/sdv-demo/run/start-remote.sh
```

The remote app listens on UDP port `35001` and sends sensor frames to
`10.56.121.101:35000`.

GPIO is initialized once at program startup, before the software menu appears;
there is no hardware/software selection prompt. Hardware reads high-beam state
from BCM GPIO 17. Connect a momentary switch between physical
pin 11 (GPIO 17) and a ground pin such as physical pin 6. The GPIO uses its
internal pull-up, so pressing the switch means `High.IsOn=true` and releasing
it means `false`. Do not connect 5 V to a GPIO pin. The input is debounced,
and a changed state is sent to the vehicle immediately over the existing UDP
route. The keyboard menu always accepts software high-beam and `Vehicle.speed`.

After hardware initialization the remote menu is shown immediately; GPIO
monitoring and LED command reception continue in background workers while the
menu accepts input. Option 1 sends a software high-beam value, and option 2
sends speed; both return to the menu without reinitializing GPIO. GPIO switch
changes and software high-beam entries share one outbound value: the latest
input event wins, and a stable switch does not repeatedly overwrite software
input. `q` exits the remote app and stops its GPIO workers.

```text
Remote menu
1  High-beam (true/false)
2  Vehicle.speed (number)
q  Quit remote app
```

Startup also configures BCM GPIO 27 (physical pin 13) as an active-high
LED output for commands received from the vehicle side. Wire GPIO 27 through
a 330-1000 ohm resistor and LED to GND (LED cathode to GND). Do not connect a
headlight, motor, or relay coil directly to GPIO. The output starts OFF and is
set OFF on normal exit, Ctrl-C, or SIGTERM; SIGKILL cannot perform cleanup.
`HIGH_BEAM_GPIO_OUTPUT_CHIP` and `HIGH_BEAM_GPIO_OUTPUT_LINE` override its
controller/line. Input and output must not share a GPIO line.

GPIO 17 and GPIO 27 are independent. Both High.IsOn and Low.IsOn support
commands and remote-to-KUKSA current-value updates:

- GPIO17 switch changes and remote menu option 1 update High.IsOn. A KUKSA
  High.IsOn command updates that same remote software state and reports it
  back, without changing GPIO27 or driving GPIO17 as an output. The next
  debounced switch change or menu entry overrides the software command;
  a stable switch does not repeatedly overwrite it.
- A KUKSA Low.IsOn command writes GPIO27 and reports the applied value back
  only after the write succeeds. High state is unchanged. This confirms the
  GPIO write, not whether the physical LED illuminated.
- Both values are periodically republished so the vehicle can recover after
  reconnecting. Low starts OFF and reports OFF on normal shutdown; UDP remains
  best-effort. In software mode Low feedback represents simulated output.

Reading High.IsOn does not acknowledge or gate the LED command. Read Low.IsOn
for the latest reported applied LED output state, rather than the command target.

For a runtime Velocitas application that turns the LED on at 110 km/h and off
below 110 km/h, use this logic inside its polling loop:

```python
speed = (await self.Vehicle.Speed.get()).value
await self.Vehicle.Body.Lights.Beam.Low.IsOn.set(speed >= 110)
```

The application must explicitly send both True and False. Do not condition
the OFF command on High.IsOn or Low.IsOn current values. With the application
running, remote menu speed 111 commands GPIO27 ON and speed 100 commands it
OFF; GPIO17 remains an independent switch input.

For development on hosts without GPIO devices, `HIGH_BEAM_INPUT=software`
disables GPIO initialization. It retains the same software menu and logs
received commands without accessing GPIO. GPIO is enabled by default.

The app detects Raspberry Pi pin-controller chips by name or label (including
`pinctrl-rp1`). If startup reports a GPIO permission error, grant the runtime
user access to that device. The GPIO chip and line can be changed with
`HIGH_BEAM_GPIO_CHIP` and `HIGH_BEAM_GPIO_LINE` if the Pi exposes them
differently.

### 2. Start the Vehicle Stack

On `10.56.121.101`:

```bash
~/sdv-demo/run/start-vehicle.sh
```

This launcher:

1. Creates a vehicle SOME/IP configuration with unicast address `10.56.121.101`.
2. Starts `someipd` in the background.
3. Starts `gatewayd` in the background.
4. Starts the UDP bridge in the background.
5. Starts KUKSA and waits for its gRPC port in combined command mode.
6. Starts the vehicle application in the foreground.

Default `HIGH_BEAM_COMMAND_MODE=kuksa` routes vehicle low-beam LED menu commands
to the local KUKSA broker (`VDB_ADDRESS=127.0.0.1:55555`). The provider publishes
them on `/vehicle_high_beam/local_tx`; the vehicle app does not offer a competing
high-beam Tx instance. `HIGH_BEAM_COMMAND_MODE=direct` restores the legacy
vehicle publisher and disables KUKSA High.IsOn and Low.IsOn actuation. Never mix the two Tx
owners. `VEHICLE_APP_MODE=kuksa` runs just KUKSA after the gateway/bridge startup.

KUKSA clients must use VAL v2 `Actuate` or Velocitas VDB `SetDatapoints` for
commands. Writing a VAL v1 current value is not an actuator command. The broker
contains separate bidirectional High.IsOn and Low.IsOn actuator entries, each
with its own Rx feedback and Tx actuation event. High uses `high_beam_state`
(SOME/IP Tx 33840, Rx 33841); Low uses `low_beam_state` (Tx 33842, Rx 33843).
Both share the existing `/vehicle_high_beam` service instances. API acceptance means queued for dispatch,
not confirmed physical output. UDP remains best-effort.

The vehicle application accepts:

```text
true
false
```

It also accepts this menu:

```text
1   Select low-beam LED and enter true or false
2   Select speed and enter a numeric value
q   Quit
```

The speed payload is the vehicle-dynamics example representation: an 8-byte
`double` followed by a 1-byte quality value (currently `3`).

When the remote app is started with `HIGH_BEAM_INPUT=menu`, it provides a keyboard menu:

```text
1   Select high-beam and enter true or false
2   Send Vehicle.speedAck to the vehicle (enter a numeric value)
q   Quit the remote app
```

The remote endpoint acknowledges incoming `Vehicle.speed` payloads as
`Vehicle.speedAck`. If you enter `12345` in the remote menu, it sends that
number on the reverse event; expect `Remote sent Vehicle.speedAck to
vehicle=12345` remotely and `Vehicle app received Vehicle.speedAck =
12345.000000` on the vehicle. Its high-beam state continues to send a UDP
update every two seconds.

## Expected Logs

In default combined mode the forward-command logs are:

```text
Vehicle menu requested Low.IsOn=1 through KUKSA
KUKSA accepted vehicle command Low.IsOn=1 (not remote output acknowledgement)
Command transmitted through mw::com Tx service=/vehicle_high_beam_tx value=Bool(true)
Remote received vehicle-side command Low.IsOn=1
Remote GPIO output applied Low.IsOn=1 line=27
Remote published feedback low_beam=1
```

The remote UDP frame cannot distinguish a KUKSA client from the vehicle menu;
both are logged as vehicle-side commands. In software mode the GPIO-apply line
is absent. Independent input changes are logged as `Remote GPIO BCM 17 input
set High.IsOn=...` or `Remote menu input set High.IsOn=...`, then received by the
vehicle app and KUKSA. The legacy logs below apply to direct publisher mode.

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
~/sdv-demo/someipd.log
~/sdv-demo/gatewayd.log
~/sdv-demo/bridge.log
```

## Watch Logs Live

Run these on the Vehicle RPi while the demo is running to follow each
process's output as it happens.

Follow a single log:

```bash
tail -f ~/sdv-demo/someipd.log
tail -f ~/sdv-demo/gatewayd.log
tail -f ~/sdv-demo/bridge.log
```

Follow all three vehicle-side logs at once, each line prefixed with its source:

```bash
tail -f ~/sdv-demo/someipd.log ~/sdv-demo/gatewayd.log ~/sdv-demo/bridge.log
```

Follow only High.IsOn state changes across all logs:

```bash
tail -f ~/sdv-demo/someipd.log ~/sdv-demo/gatewayd.log ~/sdv-demo/bridge.log | grep --line-buffered 'High.IsOn'
```

The vehicle application and the remote sensor run in the foreground, so their
output appears directly in the terminal where you launched
`~/sdv-demo/run/start-vehicle.sh` or `~/sdv-demo/run/start-remote.sh`. To
capture that output to a file as well while still seeing it live, restart with
`tee`:

```bash
~/sdv-demo/run/start-vehicle.sh 2>&1 | tee ~/sdv-demo/vehicle_app.log
```

```bash
~/sdv-demo/run/start-remote.sh 2>&1 | tee ~/sdv-demo/remote_app.log
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
find ~/sdv-demo -name 'libvsomeip3.so.3' -type f -print
find ~/sdv-demo -name 'score_com_serializer.so' -type f -print
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
