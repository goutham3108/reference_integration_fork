# FAQ and Gotchas

Most surprising behavior comes from mismatched ownership, native-layout assumptions or confusing a configured target with a working deployment. These answers point to executable contracts and distinguish source-visible behavior from untested runtime expectations.

## Why are there 44 signals but 45 mappings?

The body/door/powertrain manifest has 44 entries; the provider generator appends `Vehicle.Speed`. Routes retain the separate dynamics route as well ([body model](../../sdv-hack-demo/config/body_signals.json), [gateway_provider_documents](../../sdv-hack-demo/gateway_provider_codegen.py)).

## Is speed a float or a double?

The active gateway-provider mapping says `double`; its native sample is an `f64`/double plus quality, and the UDP speed payload is nine bytes. Older root README float statements do not describe the active mapping ([provider config](../../sdv-hack-demo/config/gateway_provider_config.json), [gateway_samples.rs](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs), [speed codec](../../sdv-hack-demo/include/speed_payload.h)).

Also distinguish VSS `Vehicle.Speed` from the legacy menu label `Vehicle.speed`; identifiers and case are not freely interchangeable ([vehicle constants](../../sdv-hack-demo/vehicle_app/main.cc)).

## Can I build only one LoLa process from a different Communication version?

Not safely assumed. The integration explicitly selects one Communication tree because native shared-memory layout must agree. Update/rebuild/deploy all consumers together ([root override](../../bazel_common/score_modules_target_sw.MODULE.bazel), [gateway override](../../inc_someip_gateway/user.bazelrc)).

## Why not run every app simultaneously?

The body Tx instance has one intended publisher: KUKSA in combined broker mode, the menu in direct mode, or the standalone tester in signals mode. Competing skeletons violate that ownership model ([vehicle Run](../../sdv-hack-demo/vehicle_app/main.cc), [launcher cases](../../sdv-hack-demo/deploy/start-vehicle.sh)).

## Does disabling “high-beam actuation” affect only high beam?

No. `KUKSA_HIGH_BEAM_ACTUATION=0` affects the shared body Tx offer and associated command mappings. The variable name is historical/narrower than its actual integration scope ([composition](../../kuksa-databroker/databroker-mw-com/src/main.rs), [gateway adapter](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs)).

## Why does a current-value write sometimes become a command?

The provider subscribes to datapoint and actuator-target updates for command-capable mappings to support legacy clients. It ignores startup state and provider feedback to avoid re-sending existing/received values ([start_command_forwarder](../../kuksa-databroker/mw_com_provider/src/provider.rs)). Sensor-only mappings are not automatically command-capable.

## Is `PASS 44/44` proof that hardware worked?

No. The tester checks matching application payloads; the remote echoes most non-high-beam routes. There is no unique command correlation, and GPIO output may be unavailable ([SignalTestApplication](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp), [remote receive loop](../../sdv-hack-demo/remote_app/main.cpp)).

## Is the remote firmware for an Arduino?

No. The tracked implementation uses Linux sockets, threads, files and GPIO ioctls. Comments/README future plans do not establish another implementation ([remote source](../../sdv-hack-demo/remote_app/main.cpp)).

## Is `build-aarch64.sh` read-only?

No. It starts with `configure_signals.py --write` and can install a Rust target through its helper. Packaging and deployment have additional filesystem/process side effects ([build script](../../sdv-hack-demo/build-aarch64.sh), [cross-build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh), [launchers](../../sdv-hack-demo/deploy)).

## Why does the freshly packaged vehicle launcher fail to find the broker?

The packager copies `databroker-mw-com`, but the launcher calls `databroker-mw-com-demo`. That inconsistency is source-visible and was left unfixed because this task forbids existing source changes ([packager](../../sdv-hack-demo/package-aarch64.sh), [start_kuksa](../../sdv-hack-demo/deploy/start-vehicle.sh)).

## Is TCP port 55555 enough to prove the system is ready?

No. It proves at most that a listener exists. Provider registration, gateway IPC, LoLa resources, remote routes and feedback are separate checks ([composition worker startup](../../kuksa-databroker/databroker-mw-com/src/main.rs), [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh)).

## Do standalone broker security flags secure the demo composition?

No. The composition uses its own argument parser and `Authorization::Disabled`; the launcher binds all interfaces. Standalone TLS/JWT options belong to a different executable ([composition](../../kuksa-databroker/databroker-mw-com/src/main.rs), [standalone broker](../../kuksa-databroker/databroker/src/main.rs)).

## Does the root build use every local library folder?

No. Explicit module overrides and Cargo path dependencies determine selection. In particular root Bazel pins baselibs while the KUKSA build references local baselibs paths ([target module include](../../bazel_common/score_modules_target_sw.MODULE.bazel), [KUKSA helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)).

## Why is there both MkDocs and Sphinx?

The repository already had Sphinx/Bazel documentation. The requested handbook is additive and isolated, with its own dependencies/config/output; it does not replace existing CI documentation ([Sphinx config](../../docs/conf.py), [MkDocs config](../mkdocs.yml)).

## Does the committed runtime patch mean the runtime checkout is tracked?

No. The patch is tracked, while the local runtime and backup were untracked at orientation. An exact upstream patch base and reproducible application remain **Unverified** ([runtime patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch), [runtime chapter](runtime.md)).

## Related pages

[Build, Run and Deploy](build-run-deploy.md) | [Architecture](architecture.md) | [Verification](verification.md) | [Glossary](glossary.md)
