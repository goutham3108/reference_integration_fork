# Repository Tour

The repository is an integration workspace containing complete vendored source trees, build metadata, tests and a fork-specific demonstration. Treat the top-level build graph and each vendored module's own workspace as separate build contexts; similarly named targets and configuration names are not interchangeable.

## Annotated top-level tree

```text
reference_integration_fork/
  .devcontainer/              Development-container setup
  .github/                   CI, CodeQL configuration, helper tools, agent material
  .llm_tmp/                  Checked-in/local experimental artifacts, not runtime entry points
  .vscode/                   Editor settings and formatting helper
  baselibs/                  Vendored C++/Rust foundational libraries
  bazel/toolchains/          Integration-specific toolchain registration
  bazel_common/             Module includes, bundles, packaging helpers
  ci/                        Showcase target list
  communication/             Vendored middleware, shared memory, Rust/C++ bindings
  docs/                      Existing Sphinx docs plus this additive handbook
  feature_integration_tests/ Python orchestration and C++/Rust scenarios
  images/                    Platform image assembly
  inc_someip_gateway/        Gateway daemons, serializer, IPC, configs and tests
  kuksa-databroker/           Rust broker workspace and mw::com provider
  patches/                   Patches applied to externally resolved modules
  platform_integration_tests/Reserved placeholder, not an implemented test suite
  runners/                   Docker/QEMU launch rules and scripts
  rust_coverage/             Rust coverage support target
  scripts/                   Pin management, tooling CLI, build/report automation
  sdv-hack-demo/             Two-endpoint signal demonstration
  showcases/                Packaged CLI, lifecycle and standalone examples
```

Evidence: each location is present locally; entry definitions are [MODULE.bazel](../../MODULE.bazel), [BUILD](../../BUILD), [showcases/BUILD](../../showcases/BUILD), and [tooling BUILD](../../scripts/tooling/BUILD). The [platform test placeholder](../../platform_integration_tests/.gitkeep) is empty. Generated `bazel-*` symlinks are outputs/cache entry points, not source directories.

## Demo directories

| Folder | What belongs here | Evidence |
| --- | --- | --- |
| [bridge](../../sdv-hack-demo/bridge) | vsomeip/UDP relay and registration-order test | `main.cpp`, `service_registration.h`, `BUILD.bazel` |
| [config](../../sdv-hack-demo/config) | Source signal manifest plus gateway/provider snapshots | `body_signals.json`, `mw_someip_config.json`, `gateway_provider_config.json` |
| [deploy](../../sdv-hack-demo/deploy) | Installed launchers and network defaults | `start-vehicle.sh`, `start-remote.sh`, `network.env` |
| [include](../../sdv-hack-demo/include) | UDP framing and speed codec | `high_beam_udp_protocol.h`, `speed_payload.h` |
| [remote_app](../../sdv-hack-demo/remote_app) | Remote menu/GPIO/state and protocol helpers | `main.cpp`, local protocol header |
| [serializer](../../sdv-hack-demo/serializer) | Forwarding shim and exported ABI | `serializer_shim.cpp`, `exported_symbols.lds` |
| [vehicle_app](../../sdv-hack-demo/vehicle_app) | Vehicle menu and all-signal tester | `main.cc`, `body_signal_test_app.cpp`, `signal_test_values.h` |
| [sdv-runtime](../../sdv-hack-demo/sdv-runtime) | Tracked patch for another runtime repository | `sdv-runtime-mw-com.patch`; nested checkout and backup are untracked |

The root-level demo scripts build/package the above; [signal_routes.json](../../sdv-hack-demo/signal_routes.json) is a synchronized runtime snapshot. [architecture.drawio](../../sdv-hack-demo/architecture.drawio) is an existing diagram asset, not the authority when it disagrees with executable code.

## Vendored library organization

**Baselibs:** [score](../../baselibs/score) contains allocator, analysis/tracing, bit manipulation, concurrency, containers, Rust containers, datetime conversion, filesystem, FlatBuffers, hash, JSON, language support, Rust logging, memory, middleware helpers, network, OS/PAL wrappers, quality, result, scope exit, static reflection/serialization, strings, synchronization, testing macros, threads and utilities. [src](../../baselibs/src) retains compatibility aliases; [examples](../../baselibs/examples), [third_party](../../baselibs/third_party), [tools](../../baselibs/tools), [patches](../../baselibs/patches), [docs](../../baselibs/docs), [licenses](../../baselibs/licenses), and [bazel](../../baselibs/bazel) serve the named module-local concerns. See [AGENTS.md](../../baselibs/AGENTS.md), “Repository Layout,” and the corresponding subdirectory BUILD files.

**Communication:** [score](../../communication/score) separates shared memory, message passing and middleware; [score/mw/com](../../communication/score/mw/com) holds public APIs, implementation, Rust bindings and examples. [bazel](../../communication/bazel), [third_party](../../communication/third_party), [quality](../../communication/quality), [module_integration_test](../../communication/module_integration_test), [tools](../../communication/tools), and [docs](../../communication/docs) contain module build infrastructure, dependencies, verification and design material. Evidence: [MODULE.bazel](../../communication/MODULE.bazel), [BUILD](../../communication/BUILD).

**Gateway:** [score](../../inc_someip_gateway/score) contains `config`, `gateway_ipc_binding`, `gatewayd`, `serializer`, `socom`, `someip`, and `someipd`. [config](../../inc_someip_gateway/config) and [deployment](../../inc_someip_gateway/deployment) contain deployment inputs; [tests](../../inc_someip_gateway/tests) includes integration, benchmarks and TC8 material; [quality](../../inc_someip_gateway/quality), [bazel](../../inc_someip_gateway/bazel), [third_party](../../inc_someip_gateway/third_party), [tools](../../inc_someip_gateway/tools), [docs](../../inc_someip_gateway/docs), and [LICENSES](../../inc_someip_gateway/LICENSES) provide supporting infrastructure. See [gateway instructions](../../inc_someip_gateway/AGENTS.md).

**KUKSA:** [databroker](../../kuksa-databroker/databroker), [databroker-cli](../../kuksa-databroker/databroker-cli), [databroker-proto](../../kuksa-databroker/databroker-proto), [databroker-mw-com](../../kuksa-databroker/databroker-mw-com), and [mw_com_provider](../../kuksa-databroker/mw_com_provider) are Cargo workspace members. [proto](../../kuksa-databroker/proto), [lib](../../kuksa-databroker/lib), [data](../../kuksa-databroker/data), [integration_test](../../kuksa-databroker/integration_test), [scripts](../../kuksa-databroker/scripts), [doc](../../kuksa-databroker/doc), [certificates](../../kuksa-databroker/certificates), and [jwt](../../kuksa-databroker/jwt) support APIs, examples, tests and standalone broker operation. Membership/exclusions are defined in [Cargo.toml](../../kuksa-databroker/Cargo.toml).

## Integration infrastructure

- [feature_integration_tests](../../feature_integration_tests) separates `configs`, `itf`, `test_cases`, and `test_scenarios/{cpp,rust}`; see [README](../../feature_integration_tests/README.md).
- [images](../../images) contains AutoSD, Elektrobit corbos Linux for Safety Applications, Linux x86_64, QNX AArch64 and QNX x86_64 image definitions. [runners](../../runners) supplies Docker x86_64 and QEMU AArch64/x86_64 support. See each image BUILD and [score_starter](../../score_starter).
- [patches](../../patches) groups baselibs, communication, configuration-management, kyron, logging, persistency, platform, time and tooling patches. A patch file's presence does not mean it is applied; inspect the matching [bazel_common module include](../../bazel_common).
- [scripts/known_good](../../scripts/known_good) owns dependency models/generation/tests; [scripts/tooling](../../scripts/tooling) owns CLI/library/tests; [scripts/models](../../scripts/models) contains build configuration data structures.
- Existing [Sphinx documentation](../../docs/index.rst) groups integration process, modules, process/tools, S-CORE version-one roadmap/releases, verification reports and assets. This handbook has independent [MkDocs configuration](../mkdocs.yml).

## Root files and hidden support

| Files | Meaning |
| --- | --- |
| [MODULE.bazel](../../MODULE.bazel), [lockfile](../../MODULE.bazel.lock), [BUILD](../../BUILD) | Dependency graph, resolved versions, aggregate targets |
| [.bazelrc](../../.bazelrc), [.bazelversion](../../.bazelversion), [.bazelignore](../../.bazelignore) | Platform/config flags, Bazel version, package exclusions |
| [known_good.json](../../known_good.json) | Module pins, patches, documentation/test metadata |
| [pyproject.toml](../../pyproject.toml), [.pre-commit-config.yaml](../../.pre-commit-config.yaml) | Python test/lint rules and copyright hook |
| [README.md](../../README.md), [LICENSE](../../LICENSE), [NOTICE](../../NOTICE) | Existing guide and legal metadata |
| [inc_someip_gateway.patch](../../inc_someip_gateway.patch) | Standalone gateway patch artifact; not automatically applied by the demo build |
| [.gitignore](../../.gitignore), [.devcontainer](../../.devcontainer), [.vscode](../../.vscode), [.github](../../.github) | Ignore rules, development environment, editor and automation |

**Unverified:** this annotated tour is not a hand-audit of every nested vendored directory. The [configuration inventory](configuration-files.md) and [branch file inventory](changed-files.md) supply exact deep paths; component chapters identify the modification surfaces used by this integration.

## Related pages

[Component Map](index.md) | [Workspace](workspace.md) | [Configuration File Inventory](configuration-files.md) | [Changes in this Fork](fork-changes.md)
