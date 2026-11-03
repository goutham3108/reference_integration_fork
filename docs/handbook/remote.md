# Remote Application

The remote endpoint is a Linux C++ application that maintains high-beam state, optionally reads/writes GPIO, and communicates with the bridge over UDP. Most other configured signals are echoed for application-level testing rather than connected to physical actuators.

## Purpose and location

[remote_app/main.cpp](../../sdv-hack-demo/remote_app/main.cpp) owns the menu, GPIO I/O, persistence and receive/report loops. The extended [protocol header](../../sdv-hack-demo/remote_app/high_beam_udp_protocol.h) supplies command/test-payload helpers; [BUILD.bazel](../../sdv-hack-demo/remote_app/BUILD.bazel) declares `vehicle_high_beam_remote_app` and `high_beam_command_test`.

Non-responsibilities: providing a complete remote SOME/IP ECU stack, hosting KUKSA, validating all VSS semantics, or driving every modeled actuator.

## Implementation and state

At startup `main` loads routes, requires a `high_beam` route, creates a Persistency KVS instance and restores a Boolean `high_beam_state` if present:

```cpp
const auto stored_command = sensor_store->get_value(kSensorStateKey);
if (stored_command.has_value() &&
    stored_command.value().getType() == score::mw::per::kvs::KvsValue::Type::Boolean) {
    initial_output = std::get<bool>(stored_command.value().getValue());
}
std::atomic<bool> outbound_state{initial_output};
```

Source: [main.cpp](../../sdv-hack-demo/remote_app/main.cpp), `main`.

The app then creates separate input, receive and optional GPIO-monitor threads. `SetOutboundState` coordinates persistence/output/state changes and wakes reporting; the main reporting loop sends when the state generation changes and otherwise at a two-second period. SIGINT/SIGTERM set a lock-free atomic stop flag; the UDP receive timeout is 200 ms ([main.cpp](../../sdv-hack-demo/remote_app/main.cpp)).

GPIO input uses a pull-up request, five-millisecond sampling and 30-millisecond debounce. `GpioOutput` initializes the output from restored state and attempts to turn it off on destruction. GPIO setup failure is logged but nonfatal so menu/network operation can continue off-device ([OpenGpioInput, MonitorGpio, GpioOutput](../../sdv-hack-demo/remote_app/main.cpp)).

## Interfaces and defaults

| Input/output | Default / behavior |
| --- | --- |
| UDP listen | `HIGH_BEAM_BIND_IP=0.0.0.0`, port 35001 |
| Bridge destination | `HIGH_BEAM_BRIDGE_IP=127.0.0.1`, port 35000 |
| Routes | `SIGNAL_ROUTE_CONFIG`, else `signal_routes.json` |
| Persistent state | `HIGH_BEAM_KVS_DIR`, else `/tmp/score_high_beam_sensor` |
| GPIO input | Detected chip, line 17 |
| GPIO output | Output chip override or input chip, line 27 |
| Terminal menu | High beam, speed, parking lights, all-signal sample sweep, quit |

Evidence: [main.cpp](../../sdv-hack-demo/remote_app/main.cpp), resolver functions, `OpenGpioInput`, `GpioOutput::Open`, `PrintRemoteMenu`. The [installed launcher](../../sdv-hack-demo/deploy/start-remote.sh) changes persistence to package-local `state`, destination to the configured vehicle IP and library search paths.

The receive loop matches IDs against vehicle-side routes. High beam requires exactly one byte with value 0 or 1; parking lights has a similar check. Other routes produce an acknowledgement with remote instance/event IDs and unchanged payload. Parking state, once known, is also periodically reported ([receive and reporting loops](../../sdv-hack-demo/remote_app/main.cpp)).

## Dependencies and consumers

The app depends on Persistency's C++ KVS API, logging, lifecycle reporting, JSON, socket/GPIO APIs and the demo speed codec. The bridge consumes remote reports; the operator and GPIO input can also change the remote state ([BUILD.bazel](../../sdv-hack-demo/remote_app/BUILD.bazel)).

## Errors and edge cases

Missing routes, persistence-directory/KVS setup failure, socket bind failure and invalid destination IP fail startup. GPIO errors degrade to software operation. Output and input cannot use the same line on the same chip. Some reporting/echo sends ignore return values; restored state is not proof of actual output success ([main.cpp](../../sdv-hack-demo/remote_app/main.cpp)).

**Unverified:** actual pin mapping, electrical setup and physical state. This documentation does not recommend wiring actuators or running an all-signal sweep on a vehicle.

## Testing and modification

The native [high_beam_command_test.cpp](../../sdv-hack-demo/remote_app/high_beam_command_test.cpp) passed. It covers helper command application, malformed Boolean payloads, unavailable output, failed output callback, frame round trips and test-payload generation. It does **not** exercise the full threaded `main` or real GPIO.

To extend hardware behavior, add explicit per-route handling and failure reporting rather than interpreting the existing generic echo as actuation. Preserve synchronization between persistence, GPIO state and outbound generation, and add tests for GPIO-unavailable operation.

## Limitations

Linux GPIO character-device APIs make this a Linux endpoint, not an Arduino firmware implementation. Header duplication, unchecked UDP sends, generic echo semantics and limited integration tests remain modification risks.

## Related pages

[UDP Bridge](bridge.md) | [Vehicle Apps](vehicle.md) | [Configuration](configuration.md) | [FAQ](faq.md)
