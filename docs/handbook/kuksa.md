# KUKSA Broker and mw::com Provider

The composed broker hosts KUKSA gRPC services and an in-process middleware provider. It seeds signal metadata from a mapping file, translates middleware values into broker datapoints, and forwards command-capable writes through the matching Tx bindings.

## Components and non-responsibilities

The [Cargo workspace](../../kuksa-databroker/Cargo.toml) contains `databroker`, `databroker-proto`, `databroker-cli`, `databroker-mw-com` and `mw_com_provider`. The composed binary is not the standalone `databroker` executable: its CLI, authentication setup and metadata initialization differ.

Key locations:

| Source | Responsibility |
| --- | --- |
| [composition main](../../kuksa-databroker/databroker-mw-com/src/main.rs) | Args, seed IDs, worker/server lifecycle |
| [config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs) | Mapping schema and validation |
| [provider.rs](../../kuksa-databroker/mw_com_provider/src/provider.rs) | Broker registration, queues, command forwarding |
| [mapper.rs](../../kuksa-databroker/mw_com_provider/src/mapper.rs) | Quality/range/type/scaling conversion |
| [score_bindings.rs](../../kuksa-databroker/mw_com_provider/src/score_bindings.rs) | Generated-binding validation and transport adapter boundary |
| [gateway_adapter.rs](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs) | Live gateway-compatible LoLa producer/subscribers |
| [gateway_samples.rs](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs) | Native sample layouts and payload codecs |
| [generated sources](../../kuksa-databroker/mw_com_provider/generated) | Gateway and standalone BCM binding profiles |

## Startup and implementation

`main` loads the provider config, optionally filters mappings, validates bindings, creates `DataBroker`, registers metadata and replaces generated signal IDs with actual broker IDs. `start_provider_worker` isolates native transport work on a named thread and dedicated Tokio runtime; `run_provider_worker` selects `GatewayScoreRuntimeAdapter` when the mapping set matches gateway metadata, otherwise the standalone adapter.

The composition explicitly enables:

```rust
let apis = [
    grpc::server::Api::KuksaValV1,
    grpc::server::Api::KuksaValV2,
    grpc::server::Api::SdvDatabrokerV1,
];
```

Source: [composition main](../../kuksa-databroker/databroker-mw-com/src/main.rs). It serves with `Authorization::Disabled`; standalone broker JWT/TLS flags are not implicitly available here.

### State and command paths

`MwComMapper::message_to_update` selects the exact service/instance/member, checks quality/age, converts datatypes/scaling and produces a broker update. `actuation_to_message` uses an optional separate `actuation_binding` and reverses the value conversion ([mapper.rs](../../kuksa-databroker/mw_com_provider/src/mapper.rs)).

`MwComProviderWorker::register_with_broker` registers signal providers and actuation callbacks. `start_command_forwarder` subscribes to both actuator target and current datapoint fields, skips the initial snapshot, ignores `provider_feedback`, prefers an explicit target in a combined write, and queues mapped messages. This supports legacy VAL v1 writes without turning incoming middleware feedback into an infinite command loop ([provider.rs](../../kuksa-databroker/mw_com_provider/src/provider.rs)).

## Interfaces and configuration

The default demo mapping has 45 entries: 37 bidirectional, seven sensor datapoints and one actuator. `Vehicle.Speed` is currently mapped as **`double`**, unit km/h, from `VehicleDynamicsService/network_rx/speed` ([gateway_provider_config.json](../../sdv-hack-demo/config/gateway_provider_config.json)). This differs from older float-oriented prose in the root README.

Body booleans arrive as native Boolean samples; body numeric/text values use pre-serialized containers. The adapter translates dynamics quality codes 0..3 to invalid/stale/degraded/valid and rejects other codes ([gateway_adapter.rs](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs), `SubscriptionEntry::poll`).

Configuration defaults include queue capacity 256, stale threshold 1000 ms, cycle time 100 ms and reconnect delays 100..5000 ms with multiplier 2.0 ([config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs), [lifecycle.rs](../../kuksa-databroker/mw_com_provider/src/lifecycle.rs)). See the full [configuration table](configuration.md).

Setting `KUKSA_HIGH_BEAM_ACTUATION=0` removes separate body actuation bindings and makes the adapter decline the entire body Tx offer. The name understates its scope because all body events share an instance ([composition mode logic](../../kuksa-databroker/databroker-mw-com/src/main.rs), [adapter](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs)).

## Errors and edge cases

Config validation rejects empty mappings, empty paths/bindings, duplicate IDs/bindings, zero cycles, invalid array bounds, nonfinite scales/ranges and reversed min/max. Provider registration also checks broker metadata compatibility ([config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs), [provider.rs](../../kuksa-databroker/mw_com_provider/src/provider.rs), `validate_mapping_metadata`).

Malformed payloads become transport errors; unacceptable samples can be rejected without treating every bad value as a permanent worker failure. Command subscription lag logs possible lost updates; the initial snapshot is deliberately not replayed as a startup command ([provider.rs](../../kuksa-databroker/mw_com_provider/src/provider.rs)).

## Dependencies, testing and extension

The provider depends on the local broker/protobuf crates, async-trait, serde, Tokio, tracing and optional `score_com`; `score-lola` enables the native transport and default `mock-transport` enables a software test surface ([Cargo.toml](../../kuksa-databroker/mw_com_provider/Cargo.toml)).

```bash
# Unverified: run inside kuksa-databroker/; dependencies/build scripts may run.
cargo test --locked -p mw_com_provider
```

Tests exist in module sources and [tests](../../kuksa-databroker/mw_com_provider/tests), including gateway compatibility, stubbed end-to-end mapping, command forwarding, feedback suppression and startup-snapshot behavior. For new signals, regenerate bindings rather than hand-editing generated Rust; for a new native type, update sample representation, binding metadata and conversion tests together.

## Limitations / debt

Native integration spans Cargo and Bazel link artifacts, so a successful mock test does not establish a correct live LoLa link. There is no verified remote-command correlation or production authorization configuration for this composition. Standalone BCM and gateway-compatible profiles coexist; using the wrong profile can parse successfully while naming incompatible middleware instances.

## Related pages

[Signals](signals.md) | [S-CORE](score.md) | [Configuration](configuration.md) | [SDV Runtime](runtime.md)
