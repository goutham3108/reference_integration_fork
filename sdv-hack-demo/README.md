# SDV Hack Demo

This folder contains the Vehicle-side artifact for the bidirectional
`Vehicle.Body.Lights.Beam.High.IsOn` SOME/IP demonstration.

| Artifact | Role |
| --- | --- |
| [vehicle_app](vehicle_app) | Vehicle-side `mw::com` publisher and subscriber. |
| [remote_app](remote_app) | Launcher for the remote vSomeIP sensor runner built from `inc_someip_gateway`. |
| [architecture.drawio](architecture.drawio) | Editable end-to-end architecture diagram. |

Shared gateway infrastructure remains in `inc_someip_gateway`: `gatewayd`,
`someipd`, their shared-memory manifest, gateway IPC implementation, and SOME/IP
configuration are not demo endpoint artifacts.

The boolean payload is one byte: `0x01` for `true` and `0x00` for `false`.

## Data Flow

The vehicle application accepts `true` or `false` on standard input. The remote
sensor starts at `false`, updates its state from vehicle events, and publishes
its latest state every two seconds. The vehicle-side bridge converts SOME/IP
events to UDP for the remote app and converts remote UDP events back to
vehicle-side SOME/IP.

```text
Vehicle app publisher
	-> mw::com SHM -> gatewayd GenericProxy -> someipd
	-> SOME/IP service 0x4300 / event 0x8430
	-> vehicle_high_beam_bridge -> UDP 127.0.0.1:35001
	-> remote sensor app -> decoded SOME/IP event

Remote sensor app
	-> UDP 127.0.0.1:35000
	-> vehicle_high_beam_bridge -> SOME/IP service 0x4300 / event 0x8431
	-> someipd -> gatewayd GenericSkeleton -> mw::com SHM
	-> Vehicle GenericProxy subscriber
```

The existing headlight publisher and consumer remain a separate one-way example.

## Build

```bash
bazel build //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com
```

Build the remote runner once from the gateway workspace, which owns the vSomeIP
toolchain:

```bash
cd inc_someip_gateway
bazel build \
	//score/config:config_file \
	//score/someipd \
	//score/gatewayd \
	//tests/integration/vehicle_high_beam_bridge:vehicle_high_beam_bridge \
	//tests/integration/vehicle_high_beam_remote_app:vehicle_high_beam_remote_app
```

The remote runner uses UDP and does not require a remote vSomeIP configuration
file. Start it from the demo folder:

```bash
./sdv-hack-demo/remote_app/run_remote_app.sh
```

## Run Locally

The demo runs five long-lived processes. Open five terminals and keep each
process running while starting the next one.

Before running the commands, use these working directories:

- Terminals 1-4: `inc_someip_gateway`
- Terminal 5: the reference-integration root

For example, from the reference-integration root:

```bash
cd inc_someip_gateway
```

Run that once in terminals 1-4. In terminal 5, use the reference-integration
root directory.

### 1. Stop a Previous Run

Run this from any directory before starting the demo:

```bash
sudo pkill -9 -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null
rm -f /tmp/vsomeip*.lck
ss -lunp | grep -E ':35000|:35001' || true
```

### 2. Build the Binaries

From the reference-integration root:

```bash
bazel build //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com

cd inc_someip_gateway
bazel build \
	//score/config:config_file \
	//score/someipd \
	//score/gatewayd \
	//tests/integration/vehicle_high_beam_bridge:vehicle_high_beam_bridge \
	//tests/integration/vehicle_high_beam_remote_app:vehicle_high_beam_remote_app
```

### 3. Start the Vehicle SOME/IP Router

In terminal 1:

```bash
VSOMEIP_CONFIGURATION="$PWD/tests/integration/vsomeip-gateway-services.json" \
bazel run //score/someipd -- \
	--configuration "$PWD/bazel-bin/score/config/mw_someip_config.bin"
```

### 4. Start the Gateway

In terminal 2:

```bash
bazel run //score/gatewayd -- \
	--configuration "$PWD/bazel-bin/score/config/mw_someip_config.bin" \
	--service_instance_manifest "$PWD/score/gatewayd/etc/mw_com_config.json"
```

Wait for `Gateway started, waiting for shutdown signal...`.

### 5. Start the SOME/IP-to-UDP Bridge

In terminal 3:

```bash
VSOMEIP_CONFIGURATION="$PWD/tests/integration/vsomeip-gateway-services.json" \
bazel run //tests/integration/vehicle_high_beam_bridge:vehicle_high_beam_bridge
```

The bridge listens for remote UDP frames on port `35000` and sends vehicle
events to the remote app on port `35001`. Wait for:

```text
Bridge vehicle-side leg ready [4300.1000/1001]
Bridge subscribed to vehicle high-beam updates
```

### 6. Start the Remote Sensor

In terminal 4:

```bash
bazel run //tests/integration/vehicle_high_beam_remote_app:vehicle_high_beam_remote_app
```

The remote sensor receives vehicle events over UDP on port `35001`, converts
them into decoded SOME/IP event payloads, and publishes its sensor state over
UDP on port `35000` every two seconds. It starts with `false`.

You can also enter `true` or `false` in the remote sensor terminal. This
manually changes the sensor state and the next UDP update is sent back to the
vehicle through the bridge.

The remote sensor persists its latest state with SCORE Persistency. By default
its KVS files are stored in `/tmp/score_high_beam_sensor`; set
`HIGH_BEAM_KVS_DIR` before starting the remote app to choose another directory.
When a process is started by SCORE Lifecycle, set `PROCESSIDENTIFIER` so the
application reports its running state to the Launch Manager.

### 7. Start the Vehicle Application

In terminal 5, use the reference-integration root:

```bash
bazel run //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com -- \
	--configuration "$PWD/inc_someip_gateway/score/gatewayd/etc/mw_com_config.json"
```

If terminal 5 is currently in `inc_someip_gateway`, run this instead:

```bash
cd ..
bazel run //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com -- \
	--configuration "$PWD/inc_someip_gateway/score/gatewayd/etc/mw_com_config.json"
```

If port `35000` is already in use, stop the previous bridge and remote app
before restarting them:

```bash
sudo pkill -9 -f 'vehicle_high_beam_bridge|vehicle_high_beam_remote_app' 2>/dev/null
```

Enter `true` or `false` in the Vehicle application terminal. For example,
entering `true` should produce this flow:

```text
Vehicle app published Vehicle.Body.Lights.Beam.High.IsOn=true
Bridge forwarded vehicle-to-remote High.IsOn=true
Remote app converted UDP to SOME/IP High.IsOn=true
Remote sensor converted SOME/IP to UDP High.IsOn=true
Bridge converted UDP to SOME/IP High.IsOn=true
Vehicle app received Vehicle.Body.Lights.Beam.High.IsOn=true
```

### 8. Stop the Demo

Press `Ctrl+C` in each terminal, then clean any remaining processes and vSomeIP
lock files:

```bash
sudo pkill -9 -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null
rm -f /tmp/vsomeip*.lck
pgrep -af 'someipd|gatewayd|vehicle_high_beam' || echo "All demo processes stopped"
```