# Glossary

This glossary defines the domain and tooling vocabulary used in the handbook. Project-specific meanings are tied to the cited interfaces; the expansions do not imply that every named standard or platform has been fully implemented or qualified by this fork.

## Vehicle and middleware terms

| Term | Meaning in this repository | Evidence / context |
| --- | --- | --- |
| S-CORE / SCORE | Eclipse automotive middleware/library ecosystem integrated here; spelling varies in identifiers | [MODULE.bazel](../../MODULE.bazel) |
| SDV | Software-defined vehicle; this demo's signal-oriented software integration context | [demo README](../../sdv-hack-demo/README.md) |
| ECU | Electronic control unit; here a conceptual vehicle endpoint, not proof of an automotive-qualified device | [gateway docs](../../inc_someip_gateway/docs) |
| BCM | Body control module; standalone provider model/profile name | [BCM_Config.json](../../kuksa-databroker/mw_com_provider/models/BCM_Config.json) |
| ECM | Engine control module; used in branch commit wording for added engine/powertrain signals | [fork history](fork-changes.md) |
| VSS | Vehicle Signal Specification; hierarchical names such as `Vehicle.Speed` | [provider mapping](../../sdv-hack-demo/config/gateway_provider_config.json) |
| KUKSA | Vehicle-data broker/API project vendored here | [broker README](../../kuksa-databroker/README.md) |
| VAL | Vehicle Abstraction Layer; KUKSA API namespaces v1/v2 | [protobuf APIs](../../kuksa-databroker/proto/kuksa/val) |
| VISS | Vehicle Information Service Specification; optional standalone broker service | [broker main](../../kuksa-databroker/databroker/src/main.rs) |
| mw::com / MW::COM | S-CORE middleware communication API | [public headers](../../communication/score/mw/com) |
| LoLa | Name of the local shared-memory communication binding/runtime; no expansion assumed | [LoLa implementation](../../communication/score/mw/com/impl/bindings/lola) |
| SOME/IP | Scalable service-oriented middleware over IP; network event/service boundary used by the gateway | [someipd](../../inc_someip_gateway/score/someipd) |
| vsomeip | SOME/IP implementation/library consumed by gateway and bridge | [bridge BUILD](../../sdv-hack-demo/bridge/BUILD.bazel) |
| SOCom / socom | Gateway service/connector runtime abstraction; no undocumented expansion assumed | [socom](../../inc_someip_gateway/score/socom) |
| Proxy | Consumer-side middleware service handle | [vehicle subscription code](../../sdv-hack-demo/vehicle_app/main.cc) |
| Skeleton | Producer-side middleware service handle | [vehicle OfferLocalService](../../sdv-hack-demo/vehicle_app/main.cc) |
| Service type | Interface definition shared by service instances | [middleware manifest](../../inc_someip_gateway/score/gatewayd/etc/mw_com_config.json) |
| Instance specifier | Path-like identity used to discover/offer a middleware instance | [generated bindings](../../kuksa-databroker/mw_com_provider/generated/gateway_bindings.rs) |
| Event / event group | SOME/IP notification member and subscription grouping identity | [route registration](../../sdv-hack-demo/bridge/service_registration.h) |
| Tx / Rx | Transmit / receive, relative to the named local endpoint | [signal generator](../../sdv-hack-demo/configure_signals.py) |
| Datapoint / current value | Broker's current sample/state, distinct from an actuator target | [provider.rs](../../kuksa-databroker/mw_com_provider/src/provider.rs) |
| Actuator target | Requested command value; not confirmation of physical application | [provider actuation](../../kuksa-databroker/mw_com_provider/src/provider.rs) |
| Bidirectional mapping | Receives datapoints and accepts actuation, optionally through distinct bindings | [Direction](../../kuksa-databroker/mw_com_provider/src/config.rs) |
| Provider feedback | Broker update marked as arriving from the provider, skipped by the command forwarder | [start_command_forwarder](../../kuksa-databroker/mw_com_provider/src/provider.rs) |
| Quality | Ordered invalid/stale/degraded/valid signal status | [quality.rs](../../kuksa-databroker/mw_com_provider/src/quality.rs) |
| ACK / NACK | Positive / negative subscription acknowledgement in bridge logs | [subscription handler](../../sdv-hack-demo/bridge/main.cpp) |
| Wire format | Bytes carried across a transport, distinct from native memory layout | [speed codec](../../sdv-hack-demo/include/speed_payload.h) |
| Big-endian | Most significant byte first, used for frame IDs and numeric wire encodings | [protocol](../../sdv-hack-demo/include/high_beam_udp_protocol.h) |
| GPIO | General-purpose input/output; Linux character-device pins used by the remote | [remote GPIO code](../../sdv-hack-demo/remote_app/main.cpp) |
| Debounce | Wait for input stability before accepting a switch-state change | [MonitorGpio](../../sdv-hack-demo/remote_app/main.cpp) |
| KVS | Key-value store; persists remote high-beam state | [remote KvsBuilder](../../sdv-hack-demo/remote_app/main.cpp) |
| SHM | Shared memory; native LoLa samples and gateway resources | [Communication shared-memory code](../../communication/score/memory/shared) |
| IPC | Inter-process communication; specifically daemon transport between gatewayd and someipd | [gateway IPC binding](../../inc_someip_gateway/score/gateway_ipc_binding) |
| UDP / TCP | Datagram / stream Internet transports; demo peer transport versus gRPC listener | [bridge](../../sdv-hack-demo/bridge/main.cpp), [composition](../../kuksa-databroker/databroker-mw-com/src/main.rs) |
| IP | Internet Protocol address context for configured endpoints | [network.env](../../sdv-hack-demo/deploy/network.env) |
| gRPC | RPC framework used by KUKSA APIs and vehicle commands | [root client target](../../BUILD) |
| API / ABI | Application programming / application binary interface; call contract versus native representation/link boundary | [serializer.h](../../inc_someip_gateway/score/serializer/serializer.h) |
| FFI | Foreign-function interface between Rust and native components | [score_com_cargo](../../kuksa-databroker/mw_com_provider/score_com_cargo) |
| CDR | Common Data Representation; not assumed for the demo's compact raw payloads | [serializer implementations](../../inc_someip_gateway/score/serializer) |
| IEEE-754 | Floating-point representation used by the numeric wire codecs | [payload codec](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs) |
| UTF-8 / NUL | Text encoding / zero byte; string payloads are bounded UTF-8 without a terminator | [BodySignalText](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs) |

## Build, platform and verification terms

| Term | Meaning / context | Evidence |
| --- | --- | --- |
| Bazel / Bzlmod / Starlark | Build engine / module system / build-definition language | [MODULE.bazel](../../MODULE.bazel) |
| Target / label | Named build/test output such as `//sdv-hack-demo:gateway_config` | [demo BUILD](../../sdv-hack-demo/BUILD.bazel) |
| Runfiles | Runtime data/library tree emitted beside Bazel binaries | [packager copy_target](../../sdv-hack-demo/package-aarch64.sh) |
| Cargo / crate | Rust package/build tooling / package unit | [Cargo workspace](../../kuksa-databroker/Cargo.toml) |
| Feature | Cargo compile-time option such as `score-lola`; not necessarily an end-user product feature | [provider Cargo.toml](../../kuksa-databroker/mw_com_provider/Cargo.toml) |
| Tokio / tonic / prost | Async Rust runtime / gRPC library / protobuf support | [workspace dependencies](../../kuksa-databroker/Cargo.toml) |
| Protobuf | Protocol Buffers schemas/code generation for KUKSA RPC messages | [proto](../../kuksa-databroker/proto) |
| FlatBuffers | Schema/binary representation used for gateway configuration | [gateway config](../../inc_someip_gateway/score/config) |
| JSON / YAML / TOML / RST | Configuration/data/document formats present in the workspace | [file inventory](configuration-files.md), [Sphinx index](../../docs/index.rst) |
| CMake | Native build tooling used by dependency/toolchain workflows; not the root build system | [toolchain helper](../../inc_someip_gateway/tools/make_local_aarch64_toolchain.sh) |
| Lockfile | Recorded dependency resolution, not a guarantee of build success | [MODULE lock](../../MODULE.bazel.lock), [Cargo lock](../../kuksa-databroker/Cargo.lock) |
| Sysroot | Target headers/libraries used by a cross-compiler | [toolchain helper](../../inc_someip_gateway/tools/make_local_aarch64_toolchain.sh) |
| SDK / SSH | Software development kit / Secure Shell; build prerequisites and remote sysroot acquisition context | [toolchain helper](../../inc_someip_gateway/tools/make_local_aarch64_toolchain.sh) |
| AArch64 / ARM64 | 64-bit ARM target architecture used by demo packaging | [build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh) |
| x86_64 / AMD64 | 64-bit x86 build-host/platform architecture | [platform dispatcher](../../score_starter) |
| Pi / RPi | Raspberry Pi; intended Linux demo host/device context | [demo README](../../sdv-hack-demo/README.md) |
| POSIX / PAL / OSAL | Portable OS interface context / platform abstraction / OS abstraction layer | [baselibs instructions](../../baselibs/AGENTS.md), [score/os](../../baselibs/score/os) |
| QNX / SDP | QNX operating system / Software Development Platform toolchain context | [QNX config](../../.bazelrc) |
| QEMU | Emulator used by platform runners | [runners](../../runners) |
| AutoSD | Named automotive Linux platform integration | [AutoSD image](../../images/autosd/BUILD.bazel) |
| Docker / Podman | Container engines named by platform/runtime workflows | [Docker runner](../../runners/docker_x86_64), [runtime patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch) |
| CI/CD | Continuous integration/delivery automation; configured workflows are not observed successes | [workflows](../../.github/workflows) |
| FIT / ITF | Feature integration tests / integration test framework | [test README](../../feature_integration_tests/README.md) |
| UT | Unit test | [quality runner](../../scripts/quality_runners.py) |
| ASLR / ASan / ThreadSanitizer | Address-space layout randomization / address sanitizer / thread sanitizer | [configure_aslr_for_sanitizers](../../scripts/quality_runners.py) |
| SBOM / SPDX | Software bill of materials / output/license metadata standard | [root SBOM targets](../../BUILD) |
| DLT | Diagnostic Log and Trace protocol context for remote logging | [FIT configs](../../feature_integration_tests/configs/datarouter) |
| JWT / TLS | JSON Web Token / Transport Layer Security; standalone broker options, not composed-server defaults | [broker main](../../kuksa-databroker/databroker/src/main.rs) |
| OTel | OpenTelemetry; feature-gated telemetry/log initialization | [broker lib](../../kuksa-databroker/databroker/src/lib.rs) |
| ASIL / QM | Automotive Safety Integrity Level / quality-management context in library metadata; not demo qualification claims | [baselibs instructions](../../baselibs/AGENTS.md) |
| MSRV | Minimum supported Rust version; edition alone does not determine it | [cross-build version check](../../kuksa-databroker/scripts/build-rpi-aarch64.sh) |
| SIGINT / SIGTERM / SIGABRT | Interrupt / termination / abort signals | [daemon handlers](../../inc_someip_gateway/score/gatewayd/main.cpp), [FIT result codes](../../feature_integration_tests/test_cases/fit_scenario.py) |
| CDN | Content delivery network; possible source for browser Mermaid assets | [site setup](build-run-deploy.md) |
| MkDocs / Material / Sphinx | New handbook generator/theme / existing repository docs generator | [MkDocs config](../mkdocs.yml), [Sphinx config](../../docs/conf.py) |
| Mermaid | Diagram syntax embedded in handbook architecture pages | [Architecture](architecture.md) |
| Shared ancestor / three-dot diff | Git comparison base versus branch-tip changes, not direct latest-main subtraction | [fork comparison](fork-changes.md) |

## Related pages

[Overview](overview.md) | [Architecture](architecture.md) | [Configuration](configuration.md) | [FAQ](faq.md)
