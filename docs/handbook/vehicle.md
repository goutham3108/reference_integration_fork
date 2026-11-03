# Vehicle Applications

The vehicle side has an interactive demonstration application and a separate all-signal round-trip tester. They share the middleware transport but have different roles and must not compete for the same body Tx instance.

## Purpose and location

[main.cc](../../sdv-hack-demo/vehicle_app/main.cc), `VehicleHighBeamApplication`, provides a high-beam/speed menu and subscribes to returned events. [body_signal_test_app.cpp](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp), `SignalTestApplication`, sends a configured value sweep and checks matching Rx payloads; neither implements the remote hardware.

Build targets are `//sdv-hack-demo/vehicle_app:vehicle_high_beam_mw_com`, `:body_signal_test_app`, and `:signal_test_values_test` in [BUILD](../../sdv-hack-demo/vehicle_app/BUILD).

## Implementation

Publisher selection is explicit:

```cpp
const char* command_mode = std::getenv("HIGH_BEAM_COMMAND_MODE");
broker_commands_ = command_mode != nullptr && std::string_view{command_mode} == "kuksa";
if ((!broker_commands_ && !OfferLocalService()) || !SubscribeToRemoteService() || !OfferDynamicsService() ||
    !SubscribeToDynamicsService()) {
    Cleanup();
    return EXIT_FAILURE;
}
```

Source: [main.cc](../../sdv-hack-demo/vehicle_app/main.cc), `Run`. A bare binary without the launcher's environment uses direct high-beam publishing; the launcher defaults to `kuksa`. In broker mode, `PublishLocalState` builds a VAL v2 `ActuateRequest`; in direct mode it sends a one-byte pre-serialized middleware sample. Speed continues through its own dynamics skeleton.

The C++ app uses generic middleware events and native metadata. Its dynamics `SpeedSample` contains a `double` and a quality byte; the metadata uses native `sizeof`/alignment rather than the nine-byte wire size ([main.cc](../../sdv-hack-demo/vehicle_app/main.cc)).

## Inputs and outputs

| Interface | Contract |
| --- | --- |
| `/vehicle_high_beam/local_tx` | Body high-beam Tx service, direct mode only |
| `/vehicle_high_beam/network_rx` | Remote high-beam feedback |
| `/Vehicle/Service1/Instance` | Local dynamics service |
| `/Vehicle/Service2/Instance` | Remote dynamics service |
| `VDB_ADDRESS` | gRPC target used for broker commands |
| Menu | `1`: high beam, `2`: speed, `q`: exit |

Evidence: constants and `PublishLocalState` in [main.cc](../../sdv-hack-demo/vehicle_app/main.cc). Input is read from `/dev/tty` when available, falling back to stdin; logs and menu output can therefore behave differently when redirected.

The tester consumes route metadata from [signal_routes.json](../../sdv-hack-demo/signal_routes.json) and uses [signal_test_values.h](../../sdv-hack-demo/vehicle_app/signal_test_values.h), `LoadSignals`, `TestValues` and `DisplayValue`. Only its `--list` mode avoids middleware initialization and publishing.

## Configuration and edge cases

- Tester defaults: `mw_com_config.json`, `signal_routes.json`, value timeout 3000 ms, startup timeout 20000 ms; both timeout flags accept 1..60000 ms ([tester `Options` and `main`](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)).
- `CreateProxyWithRetry` retries creation up to 40 times with 300 ms delays because service discovery can precede shared-memory readiness ([main.cc](../../sdv-hack-demo/vehicle_app/main.cc)).
- Invalid menu values are logged; failed service setup exits nonzero and calls cleanup. The tester prints per-signal `PASS`/`FAIL` and fails the process if any signal fails.
- A matching feedback value does not identify a unique command: frames have no sequence/correlation field ([protocol](../../sdv-hack-demo/include/high_beam_udp_protocol.h)).

## Dependencies and modification

The menu links root `kuksa_val_client`, gRPC, Communication, lifecycle, logging and the gateway's pre-serialized-data ABI. The tester links Communication plus the signal-value helper and ABI header ([BUILD](../../sdv-hack-demo/vehicle_app/BUILD)).

For a new menu option, reuse existing parse/publish helpers and select the correct ownership path. For a new signal-test datatype, change `LoadSignals`, test-value encoding/formatting and generated sample metadata together.

```bash
# Unverified: Bazel execution not performed.
bazel test --lockfile_mode=error --config=sdv-demo \
  //sdv-hack-demo/vehicle_app:signal_test_values_test
```

Run the actuator sweep only on an isolated test rig. The [tester](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp) does not provide an interruption-safe restoration transaction.

## Limitations

The menu covers high beam and speed, not all 44 model signals. The tester establishes application-level round trips, not physical actuation or deterministic delivery; some service-setup failures return little context compared with explicit tester errors.

## Related pages

[Architecture](architecture.md) | [Signals](signals.md) | [Testing and CI](testing-ci.md) | [Remote App](remote.md)
