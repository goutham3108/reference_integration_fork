# Signal Model and Generation

The demo has one primary 44-signal manifest and several synchronized runtime views of it. Change the model first, then regenerate and test the views together; changing one JSON file by hand can create a configuration that parses but does not communicate.

## Purpose, location and boundaries

[body_signals.json](../../sdv-hack-demo/config/body_signals.json) records names, VSS paths, wire event IDs, datatypes and optional sensor/actuator metadata. [configure_signals.py](../../sdv-hack-demo/configure_signals.py) and [gateway_provider_codegen.py](../../sdv-hack-demo/gateway_provider_codegen.py) synchronize integration snapshots; they do not compile binaries or operate the network.

## Implementation and outputs

`configure` preserves unrelated services, removes old body routes and reconstructs body event entries. Its route construction includes:

```python
route = {
    "name": signal["name"],
    "apiName": signal["apiName"],
    "ackApiName": signal["apiName"],
    "datatype": signal["datatype"],
    "eventName": event_name,
    "maxPayloadSize": payload_size,
    "service": 17152,
    "vehicleInstance": 4096,
    "remoteInstance": 4097,
    "vehicleEvent": event_id,
    "remoteEvent": event_id + 1,
}
```

Source: [configure_signals.py](../../sdv-hack-demo/configure_signals.py), `configure`.

| Output | Consumer |
| --- | --- |
| [signal_routes.json](../../sdv-hack-demo/signal_routes.json) | Bridge, remote app and signal tester |
| [demo gateway JSON](../../sdv-hack-demo/config/mw_someip_config.json) | `//sdv-hack-demo:gateway_config` produces binary config |
| [gateway source JSON](../../inc_someip_gateway/score/config/mw_someip_config.json) | Gateway module configuration |
| [gateway LoLa manifest](../../inc_someip_gateway/score/gatewayd/etc/mw_com_config.json) | gatewayd and demo apps/provider |
| [vsomeip snapshot](../../inc_someip_gateway/tests/integration/vsomeip-gateway-services.json) | Network event/service declarations |
| [Communication example manifest](../../communication/score/mw/com/example/vehicle-dynamics-example/etc/mw_com_config.json) | Shared integration example |
| [provider mapping](../../sdv-hack-demo/config/gateway_provider_config.json) | Composed broker |
| [gateway_bindings.rs](../../kuksa-databroker/mw_com_provider/generated/gateway_bindings.rs), [gateway_runtime.rs](../../kuksa-databroker/mw_com_provider/generated/gateway_runtime.rs) | Rust gateway adapter |

`body_signal_declarations` also emits the Communication example's body-event declaration include; its destination is constructed in [generator `main`](../../sdv-hack-demo/configure_signals.py). Why synchronize across repositories? The same logical event must agree on service instance, event ID and native sample layout before it can traverse the transport.

## Interfaces and payload types

There are **45 routes and provider mappings**: 44 model signals plus the dynamics speed route. The generated mapping classifies 37 as bidirectional, seven as datapoints and one as actuator ([provider mapping](../../sdv-hack-demo/config/gateway_provider_config.json)).

| Model datatype | Transport payload | Middleware representation |
| --- | --- | --- |
| `boolean` | One byte, `0`/`1` | Tx pre-serialized; Rx native boolean |
| `uint8` | One byte | Pre-serialized; generated percent bounds 0..100 |
| `int16` | Two bytes, big-endian | Pre-serialized |
| `float` | IEEE-754 float32, big-endian | Pre-serialized |
| `float_array` | At most eight big-endian float32 values | Up to 32 bytes |
| `string` | UTF-8 bytes, no terminating NUL | Up to 32 bytes |

Evidence: [generator payload-size/type selection](../../sdv-hack-demo/configure_signals.py), [gateway samples encode/decode](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs), [signal test values](../../sdv-hack-demo/vehicle_app/signal_test_values.h). Dynamics speed is a separate **double plus quality byte** wire contract, not the four-byte model `float` ([speed_payload.h](../../sdv-hack-demo/include/speed_payload.h)).

## Configuration and errors

Default invocation checks snapshots; `--write` modifies them. Parse errors and missing dictionary fields propagate, while stale snapshots make the check fail. The [six generator tests](../../sdv-hack-demo/configure_signals_test.py), `SignalConfigurationTest`, check cardinality, uniqueness, manifest alignment and generated provider contracts.

```bash
python3 -B sdv-hack-demo/configure_signals.py
python3 -B sdv-hack-demo/configure_signals_test.py
```

Both passed during documentation preparation. The following is **Unverified and intentionally not executed**, because it edits existing tracked files:

```bash
python3 -B sdv-hack-demo/configure_signals.py --write
```

## Extending the signal set

1. Select the datatype, VSS path, Tx event ID, event name and direction in [the manifest](../../sdv-hack-demo/config/body_signals.json).
2. Verify uniqueness and paired remote IDs; add actual hardware handling if echo is insufficient.
3. Regenerate on a development branch, review **all** changed snapshots and bindings, run the generator tests and relevant codec/provider tests.
4. Rebuild gateway config, apps and provider; deploy matching route/config snapshots to both endpoints ([build script](../../sdv-hack-demo/build-aarch64.sh), [packager](../../sdv-hack-demo/package-aarch64.sh)).

## Limitations and debt

Signal counts and interface declarations are repeated in tests/output messages. A new datatype needs coordinated changes to generator type maps, codec, Rust samples, metadata and test-value generation; it is not only a JSON edit. **Unverified:** enum/domain semantics beyond the values explicitly encoded in the model and test helpers.

## Related pages

[Configuration](configuration.md) | [Vehicle Apps](vehicle.md) | [KUKSA](kuksa.md) | [UDP Bridge](bridge.md)
