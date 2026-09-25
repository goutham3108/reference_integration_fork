# Vehicle High-Beam mw::com Showcase

This application publishes and consumes only the VSS signal
`Vehicle.Body.Lights.Beam.High.IsOn` through the SOME/IP gateway. Service,
instance, and member identifiers are transport configuration owned by `mw::com`
and the gateway; they are not part of the application signal interface.

The wire payload is exactly one byte: `0x00` for `false` and `0x01` for `true`.
The application rejects every other payload length or value.

The two directions use separate services so a received network state is never
republished back to the network:

| Direction | Service | Event | Instance |
| --- | --- | --- | --- |
| Vehicle app to network | `vehicle_high_beam_tx` (`0x4300`) | `0x8430` | `0x1000` |
| Network to Vehicle app | `vehicle_high_beam_rx` (`0x4300`) | `0x8431` | `0x1001` |

`gatewayd` consumes the Tx service through a `mw::com::GenericProxy` and exposes
the Rx service through a `mw::com::GenericSkeleton`. `someipd` owns the local
vSomeIP network stack.

The shared-memory binding is resolved as `service / instance / member`:
`/vehicle_high_beam_tx` or `/vehicle_high_beam_rx` / their configured instance
specifier / `high_beam_state`.

## Build

```bash
cd sdv-hack-demo
bash build-aarch64.sh
```

## Deployment

Use the packaged two-RPi workflow in the parent [SDV High-Beam Demo README](../README.md).
It builds the gateway components, creates both deployment archives, and starts
the vehicle and remote applications with the correct library paths and IP
configuration.

The Vehicle app publishes either boolean value. The bridge forwards it to the
remote sensor over UDP, and the sensor sends its latest value back through the
bridge, SOME/IP, and mw::com.