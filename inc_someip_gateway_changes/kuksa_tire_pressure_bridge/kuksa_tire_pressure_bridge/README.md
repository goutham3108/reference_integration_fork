# KUKSA tire-pressure bridge

This directory contains a bidirectional bridge:

    SOME/IP -> mw::com proxy -> TirePressureBridge -> KUKSA Databroker

and:

    KUKSA subscription -> mw::com skeleton/provider -> gatewayd -> SOME/IP

The bridge uses KUKSA VAL v1. The Databroker must implement the v1 `Set` and
`Subscribe` RPCs.

The reverse path offers separate mw::com instances so it does not conflict
with gatewayd's inbound SOME/IP instances:

| KUKSA signal | mw::com instance | SOME/IP service / instance / event | Payload |
| --- | --- | --- | --- |
| Tire pressure | `kuksa/tire_pressure` | `0x4101` / `0x1002` / `0x8411` | Four uint8 pressures: FL, FR, RL, RR |
| Headlight | `kuksa/headlight` | `0x4201` / `0x1003` / `0x8421` | One byte: `0` off, `1` on |

## Runtime order

Start `someipd`, then `gatewayd`, then the bridge. `gatewayd` discovers the
two KUKSA-owned mw::com skeletons and forwards their events to SOME/IP.

```bash
bazel run //kuksa_tire_pressure_bridge/kuksa_tire_pressure_bridge:kuksa_tire_pressure_bridge -- \
  127.0.0.1:55555
```

The forward direction starts after the bridge discovers the existing
`gatewayd/tire_pressure` and `gatewayd/headlight` services. The reverse
direction starts after the bridge offers `kuksa/tire_pressure` and
`kuksa/headlight`.

## Databroker paths

Default endpoint expected by the binary:

    127.0.0.1:55555

The bridge uses:

    Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure
    Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire.Pressure
    Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.Pressure
    Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire.Pressure

The paths must be present in the VSS metadata loaded into the Databroker.
