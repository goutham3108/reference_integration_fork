# SDV Hack Demo

This folder contains the Vehicle-side artifact for the bidirectional
`Vehicle.Body.Lights.Beam.High.IsOn` SOME/IP demonstration.

| Artifact | Role |
| --- | --- |
| [vehicle_app](vehicle_app) | Vehicle-side `mw::com` publisher and subscriber. |
| [remote_app](remote_app) | Source artifact for the remote vSomeIP publisher and subscriber. Build its native runner from `inc_someip_gateway`. |
| [architecture.drawio](architecture.drawio) | Editable end-to-end architecture diagram. |

Shared gateway infrastructure remains in `inc_someip_gateway`: `gatewayd`,
`someipd`, their shared-memory manifest, gateway IPC implementation, and SOME/IP
configuration are not demo endpoint artifacts.

The boolean payload is one byte: `0x01` for `true` and `0x00` for `false`.

## Data Flow

Both endpoint applications accept `true` or `false` on standard input. Each
input follows a separate service direction, so neither event loops back to the
publisher.

```text
Vehicle app publisher
	-> mw::com SHM -> gatewayd GenericProxy -> someipd
	-> SOME/IP service 0x4300 / event 0x8430
	-> Remote vSomeIP subscriber

Remote vSomeIP publisher
	-> SOME/IP service 0x4301 / event 0x8431
	-> someipd -> gatewayd GenericSkeleton -> mw::com SHM
	-> Vehicle GenericProxy subscriber
```

There is no TCP transport or network bridge. The existing headlight publisher
and consumer remain a separate one-way example.

## Build

```bash
bazel build //sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com
```

Build the remote runner once from the gateway workspace, which owns the vSomeIP
toolchain:

```bash
cd inc_someip_gateway
bazel build //tests/integration/vehicle_high_beam_remote_app:vehicle_high_beam_remote_app
```

Then start it from the demo folder:

```bash
./sdv-hack-demo/remote_app/run_remote_app.sh
```