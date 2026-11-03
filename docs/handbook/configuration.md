# Configuration Reference

Configuration is split between build selection, generated signal contracts and process-launch settings. The table below defines the operational integration surfaces; the generated appendices separately inventory recognized tracked configuration files and literal environment/flag references across vendored code.

## Precedence and scope

- The launchers **source `network.env`**, which assigns the network defaults, then export additional process settings. An inherited shell value is not necessarily preserved ([vehicle launcher](../../sdv-hack-demo/deploy/start-vehicle.sh), [remote launcher](../../sdv-hack-demo/deploy/start-remote.sh), [network.env](../../sdv-hack-demo/deploy/network.env)).
- Bare binary defaults can differ from launcher defaults, particularly command mode, broker profile, bind address and state directory.
- “Default” means source fallback, not proof of effective configuration on a deployed host.
- Standalone `databroker` flags do not automatically apply to `databroker-mw-com`. Runtime-patch settings below describe patch target behavior, not a tracked runtime checkout.

## Operational configuration table

| Kind / scope | Name or file | Default / allowed values | Meaning and evidence |
| --- | --- | --- | --- |
| File / build | [MODULE.bazel](../../MODULE.bazel) | Root module `score_ref_int` | Includes rules/toolchains/dependencies and local gateway |
| File / build | [MODULE.bazel.lock](../../MODULE.bazel.lock) | Checked-in resolved graph | Dependency lock; do not regenerate incidentally |
| File / build | [.bazelversion](../../.bazelversion) | `8.6.0` | Root Bazel version |
| File / build | [.bazelrc](../../.bazelrc) | Platform/test/coverage configs | Root Bazel settings and optional `user.bazelrc` import |
| File / build | [.bazelignore](../../.bazelignore) | File contents | Bazel package exclusion list |
| File / build | [bazel_common](../../bazel_common) module includes | Generated/pinned metadata plus local overrides | Rules, toolchains, modules, images |
| File / build | [known_good.json](../../known_good.json) | Target/tooling module groups | Hashes, patch lists, test exclusions, docs metadata |
| File / gateway build | [user.bazelrc](../../inc_someip_gateway/user.bazelrc) | Communication `../communication`; lockfile mode off | Align gateway LoLa with local build |
| File / Cargo | [Cargo.toml](../../kuksa-databroker/Cargo.toml), [Cargo.lock](../../kuksa-databroker/Cargo.lock) | Workspace members and resolved crates | Rust dependency/profile selection |
| File / Python | [pyproject.toml](../../pyproject.toml) | Pytest/Ruff settings | Test roots, Python paths, markers, lint rules |
| File / tooling Python | [requirements.in](../../scripts/tooling/requirements.in), [requirements.txt](../../scripts/tooling/requirements.txt) | Declared and locked requirements | Tooling dependencies |
| File / model | [body_signals.json](../../sdv-hack-demo/config/body_signals.json) | 44 signals | Primary body/door/powertrain model |
| File / routes | [signal_routes.json](../../sdv-hack-demo/signal_routes.json) | 45 routes | IDs/names/datatype/payload limits |
| File / gateway | [demo mw_someip_config.json](../../sdv-hack-demo/config/mw_someip_config.json) | Generated snapshot | Compiled by `gateway_config` |
| File / gateway | [gateway source config](../../inc_someip_gateway/score/config/mw_someip_config.json) | Synchronized body events | Module-side gateway configuration |
| File / middleware | [gateway mw_com_config.json](../../inc_someip_gateway/score/gatewayd/etc/mw_com_config.json) | Service types/bindings/instances | Native middleware instance contract |
| File / network | [vsomeip-gateway-services.json](../../inc_someip_gateway/tests/integration/vsomeip-gateway-services.json) | Service/event/group definitions | Launcher makes an installed unicast-adjusted copy |
| File / provider | [gateway_provider_config.json](../../sdv-hack-demo/config/gateway_provider_config.json) | 45 demo mappings | Gateway-compatible profile |
| File / provider | [standalone provider config](../../kuksa-databroker/mw_com_provider/generated/mw_com_provider_config.json) | Generated BCM profile | Composition's bare default, not demo launcher mapping |
| File / provider | [bcm_config_lola_config.json](../../kuksa-databroker/mw_com_provider/generated/bcm_config_lola_config.json) | Standalone LoLa profile | Bare composition SCORE default |
| File / example | [Communication example manifest](../../communication/score/mw/com/example/vehicle-dynamics-example/etc/mw_com_config.json) | Generated body additions | Cross-build/sample contract |
| File / deploy | [network.env](../../sdv-hack-demo/deploy/network.env) | Two test-host IPs and UDP ports | Edit installed copy for the test network |
| Env / network | `HIGH_BEAM_VEHICLE_IP` | Launcher file: `10.56.121.101` | Vehicle address/unicast and remote bridge destination ([network file](../../sdv-hack-demo/deploy/network.env)) |
| Env / network | `HIGH_BEAM_REMOTE_IP` | Launcher file: `10.56.121.79`; bare bridge `127.0.0.1` | Remote UDP destination ([bridge](../../sdv-hack-demo/bridge/main.cpp)) |
| Env / network | `HIGH_BEAM_BIND_IP` | Bare `0.0.0.0`; launchers force `0.0.0.0` | UDP bind address ([bridge](../../sdv-hack-demo/bridge/main.cpp), [remote](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / network | `HIGH_BEAM_BRIDGE_IP` | Bare remote `127.0.0.1`; launcher uses vehicle IP | Remote report destination ([remote](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / network | `HIGH_BEAM_BRIDGE_UDP_PORT` | `35000` | Bridge bind/remote destination ([bridge](../../sdv-hack-demo/bridge/main.cpp)) |
| Env / network | `HIGH_BEAM_REMOTE_UDP_PORT` | `35001` | Remote bind/bridge destination ([remote](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / routes | `SIGNAL_ROUTE_CONFIG` | `signal_routes.json`; launchers use package absolute path | Route snapshot path ([bridge](../../sdv-hack-demo/bridge/main.cpp), [tester](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)) |
| Env / network | `VEHICLE_DOMAIN_CONFIG` | `VSOMEIP_CONFIGURATION`, then `tests/integration/vsomeip-gateway-services.json` | Bridge vsomeip domain config ([ResolveConfigPath](../../sdv-hack-demo/bridge/main.cpp)) |
| Env / network | `VSOMEIP_CONFIGURATION` | Set to installed `vsomeip-vehicle.json` | Network library config ([launcher](../../sdv-hack-demo/deploy/start-vehicle.sh)) |
| Env / modes | `VEHICLE_APP_MODE` | `combined` or `signals` | Vehicle launcher case selection ([launcher](../../sdv-hack-demo/deploy/start-vehicle.sh)) |
| Env / modes | `HIGH_BEAM_COMMAND_MODE` | Launcher `kuksa`; allowed `kuksa`/`direct`; bare app defaults direct | Publisher ownership ([vehicle Run](../../sdv-hack-demo/vehicle_app/main.cc)) |
| Env / modes | `KUKSA_HIGH_BEAM_ACTUATION` | Launcher `1`; direct sets `0` | Disables body actuation/Tx offer when exactly `0` ([composition](../../kuksa-databroker/databroker-mw-com/src/main.rs)) |
| Env / broker client | `VDB_ADDRESS` | `127.0.0.1:55555` | Menu gRPC target and readiness probe; does not change launcher's broker bind ([vehicle](../../sdv-hack-demo/vehicle_app/main.cc), [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh)) |
| Env / remote state | `HIGH_BEAM_KVS_DIR` | Bare `/tmp/score_high_beam_sensor`; launcher package `state` | Persistent high-beam state ([remote main](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / GPIO | `HIGH_BEAM_GPIO_CHIP` | Autodetection | Input chip and fallback output chip ([OpenGpioInput](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / GPIO | `HIGH_BEAM_GPIO_LINE` | `17` | Pull-up input line ([OpenGpioInput](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / GPIO | `HIGH_BEAM_GPIO_OUTPUT_CHIP` | Input chip/autodetection | Output device ([GpioOutput::Open](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / GPIO | `HIGH_BEAM_GPIO_OUTPUT_LINE` | `27` | Output line; cannot equal input line on same chip ([GpioOutput::Open](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / lifecycle | `PROCESSIDENTIFIER` | Unset | Presence enables lifecycle `report_running` ([vehicle](../../sdv-hack-demo/vehicle_app/main.cc), [bridge](../../sdv-hack-demo/bridge/main.cpp), [remote](../../sdv-hack-demo/remote_app/main.cpp)) |
| Env / loader | `LD_LIBRARY_PATH` | Launcher prepends package/runfiles library dirs | vsomeip and serializer discovery ([launchers](../../sdv-hack-demo/deploy)) |
| Env / Bazel runfiles | `TEST_SRCDIR`, `RUNFILES_DIR` | Runtime/test environment | Vehicle manifest fallback lookup ([ResolveConfigurationPath](../../sdv-hack-demo/vehicle_app/main.cc)) |
| Env / logging | `RUST_LOG` | Logging initializer's environment filter | Rust diagnostics ([databroker lib](../../kuksa-databroker/databroker/src/lib.rs), `init_logging`) |
| Env / example logging | `MW_LOG_CONFIG_FILE` | Communication target's `etc/logging.json` | Rust example logger ([example BUILD](../../communication/score/mw/com/example/vehicle-dynamics-example/BUILD)) |
| Env / cross-build | `COMMUNICATION_ROOT` | Workspace Communication, fallback `$HOME/communication` | KUKSA build source location ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / cross-build | `AARCH64_TOOLCHAIN_ROOT` | `$HOME/aarch64_toolchain` | Compiler root ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / cross-build | `AARCH64_CC`, `AARCH64_CXX`, `AARCH64_AR` | Root's `toolchain/bin/aarch64-none-linux-gnu-*` | Compiler/linker/archiver override ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / native link | `SCORE_COM_BAZEL_BIN`, `SCORE_COM_LINK_PARAMS` | Exported by cross-build helper; build-script fallbacks exist | Bazel native link artifact paths ([composition build.rs](../../kuksa-databroker/databroker-mw-com/build.rs)) |
| Env / native link | `SCORE_COM_VEHICLE_GEN_LIB_DIR` | Generated example `com-api-gen` directory | Native generated library path ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / native link | `SCORE_COM_LINK_OWNER` | Composition build invocation sets `databroker-mw-com` | Native link ownership ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / native link | `SCORE_COM_BAZEL_CACHE_ROOTS`, `XDG_CACHE_HOME`, `HOME` | Explicit roots or home/cache fallbacks | Build-script cache discovery ([build.rs](../../kuksa-databroker/databroker-mw-com/build.rs)) |
| Env / cross-build | `CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER`, `CC_aarch64_unknown_linux_gnu`, `AR_aarch64_unknown_linux_gnu` | Exported compiler selections | Cargo/native toolchain wiring ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / build host | `PATH` | Helper prepends `$HOME/.cargo/bin` | Rust tooling discovery ([build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh)) |
| Env / Bazel repo | `ANDROID_HOME` | Root .bazelrc forces empty | Avoid incomplete transitive Android SDK discovery ([.bazelrc](../../.bazelrc)) |
| CLI / generator | `--write` | Off | Update existing snapshots rather than check ([main](../../sdv-hack-demo/configure_signals.py)) |
| CLI / gatewayd | `-c`, `--configuration` | Required | Compiled binary config ([gatewayd main](../../inc_someip_gateway/score/gatewayd/main.cpp)) |
| CLI / gatewayd | `-s`, `--service_instance_manifest` | Required | Middleware manifest ([gatewayd main](../../inc_someip_gateway/score/gatewayd/main.cpp)) |
| CLI / daemons | `-i`, `--ipc_channel` | `someipd_gatewayd_ipc` | Matching channel on both daemons ([constants](../../inc_someip_gateway/score/someip/constants.h)) |
| CLI / someipd | `-c`, `--configuration` | Required | Binary config ([someipd main](../../inc_someip_gateway/score/someipd/main.cpp)) |
| CLI / daemons | `-h`, `--help` | Off | Usage and exit ([gatewayd](../../inc_someip_gateway/score/gatewayd/main.cpp), [someipd](../../inc_someip_gateway/score/someipd/main.cpp)) |
| CLI / vehicle menu | `--configuration` | `score/gatewayd/etc/mw_com_config.json` | Runtime manifest ([main.cc](../../sdv-hack-demo/vehicle_app/main.cc)) |
| CLI / signal tester | `--configuration` | `mw_com_config.json` | Runtime manifest ([Options](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)) |
| CLI / signal tester | `--routes` | `SIGNAL_ROUTE_CONFIG` or `signal_routes.json` | Route manifest ([tester main](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)) |
| CLI / signal tester | `--timeout-ms` | `3000`; 1..60000 | Per-value timeout ([tester main](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)) |
| CLI / signal tester | `--startup-timeout-ms` | `20000`; 1..60000 | Discovery/subscription timeout ([tester main](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)) |
| CLI / signal tester | `--list`, `--help` | Off | List routes without publishing, or usage ([tester main](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)) |
| CLI / composition | `--address`, `--addr` | `127.0.0.1:55555`; launcher `0.0.0.0:55555` | Socket address including port ([DemoArgs](../../kuksa-databroker/databroker-mw-com/src/main.rs)) |
| CLI / composition | `--provider-config` | `mw_com_provider/generated/mw_com_provider_config.json` | Mapping JSON; launcher selects gateway profile ([DemoArgs](../../kuksa-databroker/databroker-mw-com/src/main.rs)) |
| CLI / composition | `--score-config` | `mw_com_provider/generated/bcm_config_lola_config.json` | LoLa config; launcher selects gateway manifest ([DemoArgs](../../kuksa-databroker/databroker-mw-com/src/main.rs)) |
| CLI / composition | `--include-vss-path` | All mappings; repeatable | Filter before assigning runtime IDs; empty result fails ([DemoArgs](../../kuksa-databroker/databroker-mw-com/src/main.rs)) |
| CLI / composition | `-h`, `--help` | Off | Usage and exit ([DemoArgs](../../kuksa-databroker/databroker-mw-com/src/main.rs)) |
| CLI / provider executable | `--provider-config`, `--score-config`, `--provider-name`, `--seed-databroker-metadata`, `-h`/`--help` | Provider JSON default; optional SCORE path; name `mw_com_provider`; seed off | Separate standalone provider CLI ([RuntimeArgs](../../kuksa-databroker/mw_com_provider/src/bin/mw_com_provider.rs)) |
| Env / standalone provider | `SCORE_CONFIG_PATH` | Used if score config argument absent | LoLa manifest fallback ([provider executable](../../kuksa-databroker/mw_com_provider/src/bin/mw_com_provider.rs)) |
| JSON / provider | `provider_name`, `queue_capacity`, `stale_after_ms` | `mw_com_provider`, `256`, `1000` | Provider identity, queue size, freshness threshold ([config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs)) |
| JSON / provider | `reconnect.initial_delay_ms`, `max_delay_ms`, `backoff_multiplier` | `100`, `5000`, `2.0` | Reconnection backoff ([lifecycle.rs](../../kuksa-databroker/mw_com_provider/src/lifecycle.rs)) |
| JSON / mapping | `signal_id`, `vss_path`, `datatype`, `service`, `instance`, `member` | Required | Model ID and exact broker/middleware binding ([SignalMapping](../../kuksa-databroker/mw_com_provider/src/config.rs)) |
| JSON / mapping | `direction` | `datapoint`; supports `actuator`, `bidirectional` | Read/write capability ([Direction](../../kuksa-databroker/mw_com_provider/src/config.rs)) |
| JSON / mapping | `actuation_binding` | None | Optional separate service/instance/member for commands ([ActuationBinding](../../kuksa-databroker/mw_com_provider/src/config.rs)) |
| JSON / mapping | `scale`, `offset` | `1.0`, `0.0` | Numeric conversion ([config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs), [mapper.rs](../../kuksa-databroker/mw_com_provider/src/mapper.rs)) |
| JSON / mapping | `min`, `max`, `unit`, `field` | None | Bounds/unit and optional generated field mapping ([SignalMapping](../../kuksa-databroker/mw_com_provider/src/config.rs)) |
| JSON / mapping | `max_elements` | None; float arrays require 1..8 | Bound arrays ([validate](../../kuksa-databroker/mw_com_provider/src/config.rs)) |
| JSON / mapping | `cycle_time_ms`, `required_quality` | `100`, `valid` | Subscription interval and quality floor ([config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs), [quality.rs](../../kuksa-databroker/mw_com_provider/src/quality.rs)) |
| JSON / LoLa body events | `numberOfSampleSlots`, `maxSubscribers` | Generated `10`, `3` | Sample storage/subscriber capacity ([configure](../../sdv-hack-demo/configure_signals.py)) |
| CLI+env / standalone broker | `--address`/`--addr`, `KUKSA_DATABROKER_ADDR` | `127.0.0.1` | IP only, unlike composition CLI ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI+env / standalone broker | `--port`, `KUKSA_DATABROKER_PORT` | `55555` | TCP port ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI+env / standalone broker | `--enable-unix-socket`, `KUKSA_DATABROKER_ENABLE_UNIX_SOCKET` | Off | Enable Unix-domain socket ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI+env / standalone broker | `--unix-socket`, `KUKSA_DATABROKER_UNIX_SOCKET` | `/run/kuksa/databroker.sock` when enabled | Socket path ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI+env / standalone broker | `--vss`/`--metadata`, `KUKSA_DATABROKER_METADATA_FILE` | None | Comma-separated metadata files ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI / standalone broker | `--jwt-public-key`, `--disable-authorization` | No key; disable flag off | Authorization initialization ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI / standalone broker | `--insecure`, `--tls-cert`, `--tls-private-key` | Feature-dependent; no TLS if unconfigured | TLS behavior only with compiled support ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI+env / standalone broker | `--worker-threads`, `KUKSA_WORKER_THREADS` | Available core count | Tokio workers ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI+env / standalone broker | `--enable-viss`, `--viss-address`, `--viss-port`; `KUKSA_DATABROKER_VISS_ADDR`, `KUKSA_DATABROKER_VISS_PORT` | Feature-dependent; address follows main bind; port `8090` | Optional VISS server ([broker main](../../kuksa-databroker/databroker/src/main.rs)) |
| CLI / platform dispatcher | `-r`, `--run` | Interactive if absent | Select platform name from `mEntries` ([score_starter](../../score_starter)) |
| Env / runtime patch | `DATABROKER_BACKEND`, `DISABLE_DATABROKER` | Dockerfile `databroker`, `1` | External-broker image defaults ([patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch)) |
| Env / runtime patch | `KUKSA_DATABROKER_HOST`, `KUKSA_DATABROKER_PORT` | `127.0.0.1`, `55555` | Syncer broker destination ([patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch)) |
| Env / runtime patch | `DATABROKER_ARGS`, `KUKSA_DATABROKER_ADDR` | Ordinary broker empty args; composed backend synthesizes bind/profile args with address `0.0.0.0` | Child broker launch ([patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch)) |
| Env / runtime patch | `MOCK_SIGNAL` | Dockerfile empty; supervisor fallback depends on backend | Empty selects direct writes ([patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch)) |
| Env / runtime patch | `SITE_PACKAGES_DIR`, `GEN_MODEL_DIR`, `PYTHONPATH` | `/home/dev/python-packages`; model dir follows it; paths prepended | Python runtime package/model lookup ([patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch)) |
| Env / runtime patch | `RUNTIME_NAME`, `RUNTIME_PREFIX`, `SYNCER_SERVER_URL` | Name user-supplied; prefix/server described in README hunks | Kit runtime identity/server; unchanged base details Unverified ([patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch)) |
| File / handbook | [mkdocs.yml](../mkdocs.yml), [requirements-handbook.txt](../requirements-handbook.txt) | Separate docs root/output and Material pin | This site only |
| File / handbook diagrams | [package.json](../package.json), [package-lock.json](../package-lock.json) | Pinned Mermaid and resolved package dependencies | Docs-local renderer, copied into static site |
| CLI / handbook | `handbook.py generate` / `check` / `site` | Required explicit command | Generate book/inventories, validate source links, or validate rendered links/assets/anchors ([helper](../tools/handbook.py)) |

## Limits of exhaustiveness

The [configuration file inventory](configuration-files.md) enumerates recognized tracked manifests/configuration/data/schema/tool files. The [static variable/flag index](environment-flags.md) includes module examples and test references, not just active demo settings.

**Unverified:** computed variable names, implicit third-party flags, all semantics of vendored/test fixture configuration, and untracked local settings. The scanner records its exact rules; it is not evidence that every arbitrary string in every library is a supported public option. Do not treat these inventories as a substitute for source review when enabling a new subsystem.

## Related pages

[Signals](signals.md) | [Build, Run and Deploy](build-run-deploy.md) | [Configuration File Inventory](configuration-files.md) | [Static Environment and Flag Inventory](environment-flags.md)
