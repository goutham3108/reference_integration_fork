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
| Network to Vehicle app | `vehicle_high_beam_rx` (`0x4301`) | `0x8431` | `0x1000` |

`gatewayd` consumes the Tx service through a `mw::com::GenericProxy` and exposes
the Rx service through a `mw::com::GenericSkeleton`. `someipd` owns the local
vSomeIP network stack.

The shared-memory binding is resolved as `service / instance / member`:
`/vehicle_high_beam_tx` or `/vehicle_high_beam_rx` / their configured instance
specifier / `high_beam_state`.

## Build

```bash
bazel build //showcases/vehicle_high_beam_mw_com:vehicle_high_beam_mw_com
```

## Local Demonstration

Build the gateway configuration and binaries in `inc_someip_gateway`, then start
the processes in this order:

1. `someipd`, with `tests/integration/vsomeip-gateway-services.json` in
   `VSOMEIP_CONFIGURATION`.
2. `gatewayd`, with `score/config/mw_someip_config.bin` and
   `score/gatewayd/etc/mw_com_config.json`.
3. `vehicle_high_beam_remote_app`, which listens for TCP on port `35000`.
4. `vehicle_high_beam_network_bridge`, which bridges SOME/IP to the TCP remote app.
5. This application, passing the gateway `mw_com_config.json` through
   `--configuration` when it is not already available at the default path.

The Vehicle app publishes `true`; the network bridge forwards it over TCP to the
remote app. The remote app returns `false` over TCP; the bridge publishes that
value through SOME/IP and the Vehicle app prints
`Vehicle.Body.Lights.Beam.High.IsOn=false`.