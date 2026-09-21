# KUKSA to `mw::com` sample

This sample demonstrates the S-CORE side of a KUKSA adapter:

```text
KUKSA Vehicle.Speed -> adapter boundary -> mw::com provider -> local event
```

KUKSA is not currently a dependency of the Reference Integration, so the
adapter boundary is represented by `read_kuksa_speed_kph()`. The executable
accepts a speed in km/h as its first argument and publishes it using the
existing generated `VehicleInterface.left_tire` event. The event payload is a
temporary reuse of the upstream communication example's `Tire.pressure` field;
a production version should add a `VehicleState.SpeedChanged` service contract.

Run it with:

```bash
bazel run --config=linux-x86_64 //showcases/kuksa_to_com:kuksa_to_com -- 52.4
```

The runtime uses `feature_integration_tests/configs/etc/mw_com_config.json`.
Set `MW_COM_CONFIG_FILE` to use another compatible manifest.
