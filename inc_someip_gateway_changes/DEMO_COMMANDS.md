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

# Demo Commands

Run all commands from the repository root:

```sh
cd ~/Gitrepos/SDV-Hackathon/inc_someip_gateway
```

## Build

```sh
bazel build \
  //score/config:config_file \
  //score/gatewayd \
  //score/someipd \
  //tests/integration/tire_pressure_publisher:tire_pressure_publisher \
  //tests/integration/tire_pressure_consumer:tire_pressure_consumer \
  //tests/integration/headlight_publisher:headlight_publisher \
  //tests/integration/headlight_consumer:headlight_consumer

bazel build --config=kuksa \
  //kuksa_tire_pressure_bridge/kuksa_tire_pressure_bridge:kuksa_tire_pressure_bridge
```

## Clean Up Before Demo

```sh
sudo pkill -9 -f 'someipd|gatewayd|tire_pressure_(publisher|consumer)|headlight_(publisher|consumer)|kuksa_tire_pressure_bridge' 2>/dev/null
rm -f /tmp/vsomeip*.lck
docker rm -f kuksa-databroker 2>/dev/null
```

## Terminal 1: KUKSA Databroker

```sh
docker run -it --rm --name kuksa-databroker \
  -p 127.0.0.1:55556:55555 \
  ghcr.io/eclipse-kuksa/kuksa-databroker:main --insecure
```

Wait for:

```text
Listening on 0.0.0.0:55555
```

## Terminal 2: SOME/IP Daemon

```sh
VSOMEIP_CONFIGURATION="$(pwd)/tests/integration/vsomeip-gateway-services.json" \
bazel run //score/someipd -- \
  --configuration "$(pwd)/bazel-bin/score/config/mw_someip_config.bin"
```

## Terminal 3: Gateway Daemon

```sh
bazel run //score/gatewayd -- \
  --configuration "$(pwd)/bazel-bin/score/config/mw_someip_config.bin" \
  --service_instance_manifest "$(pwd)/score/gatewayd/etc/mw_com_config.json"
```

Wait for:

```text
Gateway started, waiting for shutdown signal...
```

## Terminal 4: Tire-Pressure Publisher

```sh
VSOMEIP_CONFIGURATION="$(pwd)/tests/integration/vsomeip-gateway-services.json" \
bazel run //tests/integration/tire_pressure_publisher:tire_pressure_publisher
```

## Terminal 5: Headlight Publisher

```sh
VSOMEIP_CONFIGURATION="$(pwd)/tests/integration/vsomeip-gateway-services.json" \
bazel run //tests/integration/headlight_publisher:headlight_publisher
```

## Terminal 6: KUKSA Bridge

```sh
bazel run --config=kuksa \
  //kuksa_tire_pressure_bridge/kuksa_tire_pressure_bridge:kuksa_tire_pressure_bridge \
  -- 127.0.0.1:55556
```

Expected bridge lines:

```text
KUKSA: connected to 127.0.0.1:55556
KUKSA bridge: subscribed to gatewayd/tire_pressure.
KUKSA bridge: subscribed to gatewayd/headlight.
KUKSA bridge: published tire pressure 36 to all four VSS wheel signals.
KUKSA bridge: published headlights=on to VSS.
KUKSA bridge: published headlights=off to VSS.
```

## Terminal 7: KUKSA CLI

```sh
docker run -it --rm --network host \
  ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main \
  --protocol kuksa.val.v1 \
  --server http://127.0.0.1:55556
```

At the `kuksa.val.v1 >` prompt, check tire pressure and headlight together:

```text
get Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire.Pressure Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.Pressure Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire.Pressure Vehicle.Body.Lights.Beam.Low.IsOn
```

Expected output shape:

```text
[get]  OK
Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure: 36 kPa
Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire.Pressure: 36 kPa
Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.Pressure: 36 kPa
Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire.Pressure: 36 kPa
Vehicle.Body.Lights.Beam.Low.IsOn: true
```

Run the same `get` command again after one second. Tire pressure should change, and headlight should alternate between `true` and `false`.

Exit the CLI:

```text
quit
```

## Optional Local Consumers

Tire-pressure consumer:

```sh
bazel run //tests/integration/tire_pressure_consumer:tire_pressure_consumer -- \
  --configuration "$(pwd)/score/gatewayd/etc/mw_com_config.json"
```

Headlight consumer:

```sh
bazel run //tests/integration/headlight_consumer:headlight_consumer -- \
  --configuration "$(pwd)/score/gatewayd/etc/mw_com_config.json"
```

## Automated Checks

```sh
bazel test //tests/integration:integration --test_output=all
```

```sh
bazel test //tests/integration:integration \
  --test_output=all \
  --test_arg=-k \
  --test_arg=concurrent_gateway_services
```

## Stop Everything

```sh
sudo pkill -9 -f 'someipd|gatewayd|tire_pressure_publisher|headlight_publisher|tire_pressure_consumer|headlight_consumer|kuksa_tire_pressure_bridge' 2>/dev/null
rm -f /tmp/vsomeip*.lck
docker rm -f kuksa-databroker 2>/dev/null
```
