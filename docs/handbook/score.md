# S-CORE Libraries and Communication

This integration consumes S-CORE foundations, shared-memory communication and several externally resolved modules. The locally visible source trees explain concrete middleware/sample contracts; the presence of a module name in dependency metadata is not evidence that every module feature is exercised by this demo.

## Purpose, boundaries and locations

- [baselibs/score](../../baselibs/score) supplies reusable C++/Rust libraries; it is not the application entry point.
- [communication/score/mw/com](../../communication/score/mw/com) supplies middleware service APIs and LoLa bindings; it is not a network gateway.
- [target module include](../../bazel_common/score_modules_target_sw.MODULE.bazel) declares persistency, kyron, lifecycle, logging, time and configuration-management dependencies; their full root-level source trees are not checked in here.

## Public contracts used here

The vehicle application's [main.cc](../../sdv-hack-demo/vehicle_app/main.cc) uses:

```cpp
score::mw::com::runtime::InitializeRuntime(
    score::mw::com::runtime::RuntimeConfiguration{manifest});
```

It then constructs `InstanceSpecifier`, `GenericSkeleton`, `GenericProxy`, event metadata and subscriptions. The underlying public entry headers are [runtime.h](../../communication/score/mw/com/runtime.h) and [types.h](../../communication/score/mw/com/types.h); implementation is under [impl](../../communication/score/mw/com/impl).

The Rust adapter uses `score_com` traits including `RuntimeBuilder`, `Producer`, `Subscriber`, `Subscription` and `SampleContainer`. Its concrete runtime is `LolaRuntimeImpl`; typed interfaces are generated in [gateway_runtime.rs](../../kuksa-databroker/mw_com_provider/generated/gateway_runtime.rs) and consumed by [gateway_adapter.rs](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs).

## Why native layout matters

LoLa shares native sample storage rather than treating every sample as a generic byte stream. [gateway_samples.rs](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs) uses `#[repr(C)]`, explicit 16-byte alignment for pre-serialized payload containers, and types corresponding to gateway serializer layouts.

The checked-in [generated metadata](../../kuksa-databroker/mw_com_provider/generated/gateway_bindings.rs) records sample size and alignment. The [vehicle C++ app](../../sdv-hack-demo/vehicle_app/main.cc) asserts pre-serialized-data alignment/data offset; the root [module override](../../bazel_common/score_modules_target_sw.MODULE.bazel) and [gateway user configuration](../../inc_someip_gateway/user.bazelrc) explain the need to use the same Communication layout.

The reason for each individual underlying allocator/concurrency implementation is outside this integration trace. **Unverified:** design rationale not established merely from their directory names; consult each module's requirements/design docs.

## Dependencies and use sites

| Module | Observable integration use |
| --- | --- |
| Communication | Vehicle/gateway services; Rust provider transport |
| Baselibs | Middleware/support dependencies; local Rust logging path in KUKSA build |
| Persistency | Remote high-beam KVS through `KvsBuilder` |
| Logging | C++ `score::mw::log` calls throughout demo |
| Lifecycle | `report_running()` when `PROCESSIDENTIFIER` exists |
| Kyron, Time, Config Management | Packaged standalone showcases and aggregate build/test metadata |

Evidence: [remote BUILD](../../sdv-hack-demo/remote_app/BUILD.bazel), [bridge BUILD](../../sdv-hack-demo/bridge/BUILD.bazel), [vehicle BUILD](../../sdv-hack-demo/vehicle_app/BUILD), [showcases BUILD](../../showcases/BUILD), [standalone BUILD](../../showcases/standalone/BUILD).

## Configuration and error handling

The LoLa JSON manifest contains service types, bindings, event IDs, sample slots/subscriber limits and instance specifiers ([gateway manifest](../../inc_someip_gateway/score/gatewayd/etc/mw_com_config.json)). Generated body events use ten sample slots and three maximum subscribers in [configure_signals.py](../../sdv-hack-demo/configure_signals.py), `configure`.

Most demo middleware calls return `score::Result`; the app checks `has_value()` rather than assuming success. Runtime discovery may race resource readiness, which is why the [vehicle proxy retry helper](../../sdv-hack-demo/vehicle_app/main.cc) exists.

## Testing and modification

```bash
# Unverified: run inside baselibs/.
bazel test --config=bl-x86_64-linux //score/...

# Unverified: run inside communication/.
bazel build --config=linux_aarch64_score_gcc_12_2_0_posix \
  //score/mw/com/example/vehicle-dynamics-example:vehicle-dynamics-example
```

The baselibs config is required by its [module instructions](../../baselibs/AGENTS.md); the Communication command is taken from the [KUKSA cross-build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh). Do not transpose root config names into module-local commands.

When modifying shared sample metadata, rebuild all consuming processes and test both Tx/Rx directions with a coordinated deployment. Do not repair a layout mismatch by casting an incompatible sample to a convenient type.

## Limitations / debt

The vendored Communication refresh is much larger than the demo change itself. Module-level safety/conformance claims and full library behavior remain **Unverified** in this handbook; it documents integration use, not a substitute for thousands of library unit tests and module design documents.

## Related pages

[Workspace](workspace.md) | [Gateway](gateway.md) | [KUKSA](kuksa.md) | [Repository Tour](repository-tour.md)
