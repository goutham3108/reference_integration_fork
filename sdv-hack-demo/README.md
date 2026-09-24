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
its latest state every two seconds. Separate SOME/IP domains prevent either
event direction from looping back to its publisher.

```text
Vehicle app publisher
	-> mw::com SHM -> gatewayd GenericProxy -> someipd
	-> SOME/IP service 0x4300 / event 0x8430
	-> vehicle_high_beam_bridge -> remote vSomeIP sensor

Remote vSomeIP sensor
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

Then start it from the demo folder:

```bash
./sdv-hack-demo/remote_app/run_remote_app.sh
```

## Run Locally

The demo runs five long-lived processes. Open five terminals and keep each
process running while starting the next one.

### 1. Stop a Previous Run

Run this from any directory before starting the demo:

```bash
sudo pkill -9 -f 'someipd|gatewayd|vehicle_high_beam' 2>/dev/null
rm -f /tmp/vsomeip*.lck
```

### 2. Build the Binaries

From the reference-integration root, set a shell variable used by the remaining
commands:

```bash
export REPO_ROOT="$PWD"

bazel build //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com

cd "$REPO_ROOT/inc_someip_gateway"
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
cd "$REPO_ROOT/inc_someip_gateway"
VSOMEIP_CONFIGURATION="$PWD/tests/integration/vsomeip-gateway-services.json" \
bazel run //score/someipd -- \
	--configuration "$PWD/bazel-bin/score/config/mw_someip_config.bin"
```

### 4. Start the Gateway

In terminal 2:

```bash
cd "$REPO_ROOT/inc_someip_gateway"
bazel run //score/gatewayd -- \
	--configuration "$PWD/bazel-bin/score/config/mw_someip_config.bin" \
	--service_instance_manifest "$PWD/score/gatewayd/etc/mw_com_config.json"
```

Wait for `Gateway started, waiting for shutdown signal...`.

### 5. Start the SOME/IP Domain Bridge

In terminal 3:

```bash
cd "$REPO_ROOT/inc_someip_gateway"
VEHICLE_DOMAIN_CONFIG="$PWD/tests/integration/vsomeip-gateway-services.json" \
REMOTE_DOMAIN_CONFIG="$PWD/tests/integration/vsomeip-remote-domain.json" \
bazel run //tests/integration/vehicle_high_beam_bridge:vehicle_high_beam_bridge
```

Wait for both bridge legs and subscriptions to become ready:

```text
Bridge vehicle-side leg ready [4300.1000/1001]
Bridge remote-side leg ready [4300.1000/1001]
Bridge subscribed to vehicle high-beam updates
```

### 6. Start the Remote Sensor

In terminal 4:

```bash
cd "$REPO_ROOT/inc_someip_gateway"
VSOMEIP_CONFIGURATION="$PWD/tests/integration/vsomeip-remote-domain.json" \
bazel run //tests/integration/vehicle_high_beam_remote_app:vehicle_high_beam_remote_app
```

The remote sensor begins by publishing `false`, then publishes its current
state every two seconds. The bridge prints `Bridge subscribed to remote
high-beam updates` after the remote service is available.

### 7. Start the Vehicle Application

In terminal 5:

```bash
cd "$REPO_ROOT"
bazel run //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com -- \
	--configuration "$PWD/inc_someip_gateway/score/gatewayd/etc/mw_com_config.json"
```

Enter `true` or `false` in the Vehicle application terminal. For example,
entering `true` should produce this flow:

```text
Vehicle app published Vehicle.Body.Lights.Beam.High.IsOn=true
Bridge forwarded vehicle-to-remote High.IsOn=true
Remote app received Vehicle.Body.Lights.Beam.High.IsOn=true
Remote sensor published Vehicle.Body.Lights.Beam.High.IsOn=true
Bridge forwarded remote-to-vehicle High.IsOn=true
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