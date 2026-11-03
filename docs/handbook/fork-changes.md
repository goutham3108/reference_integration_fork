# Changes in this Fork — sdv-hackathon

This chapter separates the earlier integration/fork baseline from branch-only changes using local Git history. It does not label all vendored source as original hackathon work, and it does not claim an exact pristine upstream comparison that the available remotes cannot establish.

## Comparison method

Observed local refs during authoring:

| Ref / comparison | Value |
| --- | --- |
| Branch HEAD | `0842972` |
| Local `origin/main` | `2460f06` |
| Shared ancestor | `2e786d61244a66d35227fad9b117c7d1c8958673` |
| Branch-only commits | 17 |
| Three-dot tracked diff | 1,654 files, 114,523 insertions, 28,279 deletions |
| Upstream remote | Absent |

Commands used: `git merge-base origin/main HEAD`, `git log origin/main..HEAD`, `git diff --stat origin/main...HEAD`, and local file/diff reads. A three-dot diff compares the shared ancestor to this branch, **not** a direct latest-main-to-HEAD content subtraction.

## What is inherited

- The reference-integration structure, root dependency metadata, image/runners, tests, Sphinx docs and engineering tooling predate these 17 branch commits.
- The basic high-beam demo, gateway/KUKSA/Communication/baselibs directories and earlier speed/high-beam work also existed at the shared ancestor.
- Local history has earlier demo commits such as `2e786d6`, `bd42489`, `af73011` and `e78a4b6`. Therefore “present in the fork” does not mean “introduced on sdv-hackathon.”

Evidence: local `git ls-tree origin/main`, shared-ancestor tree, and history affecting [the root README](../../README.md), [demo](../../sdv-hack-demo), [module selections](../../bazel_common/score_modules_target_sw.MODULE.bazel). **Unverified:** exact upstream commit attribution for every baseline file.

## Branch changes and reasons

| Added/modified files | Branch change | Visible reason / confidence |
| --- | --- | --- |
| [Communication source tree](../../communication) | Large refresh, recorded by `9f314a1` | Commit says verified/working; [module override](../../bazel_common/score_modules_target_sw.MODULE.bazel) explains layout compatibility. Individual upstream algorithm rationale Unverified. |
| [gateway source tree](../../inc_someip_gateway) | Gateway update, recorded by `f6f27c0` | Commit says verified/working; two-daemon IPC/config/serializer behavior visible in source. Individual refresh rationale Unverified. |
| [gateway user.bazelrc](../../inc_someip_gateway/user.bazelrc), [target module include](../../bazel_common/score_modules_target_sw.MODULE.bazel) | Local Communication dependency alignment | Comments explicitly require consistent LoLa layout across processes |
| [body_signals.json](../../sdv-hack-demo/config/body_signals.json), [configure_signals.py](../../sdv-hack-demo/configure_signals.py), [generator tests](../../sdv-hack-demo/configure_signals_test.py) | Body/door/engine/powertrain model and synchronized configuration | Keep routes, middleware config and generated interfaces consistent |
| [gateway_provider_codegen.py](../../sdv-hack-demo/gateway_provider_codegen.py), [provider JSON](../../sdv-hack-demo/config/gateway_provider_config.json), [generated Rust](../../kuksa-databroker/mw_com_provider/generated) | Gateway-specific provider bindings alongside standalone BCM profile | Gateway contract differs from standalone profile; explicit sample metadata |
| [body_signal_test_app.cpp](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp), [signal_test_values.h](../../sdv-hack-demo/vehicle_app/signal_test_values.h), [tests](../../sdv-hack-demo/vehicle_app/signal_test_values_test.cpp) | All-signal payload sweep | Verify matching application-level Tx/Rx values |
| [service_registration.h](../../sdv-hack-demo/bridge/service_registration.h), [test](../../sdv-hack-demo/bridge/service_registration_test.cpp), [bridge main](../../sdv-hack-demo/bridge/main.cpp) | Registration helper/order and bridge updates | Test enforces events before offers/requests and deduplicated services |
| [serializer_shim.cpp](../../sdv-hack-demo/serializer/serializer_shim.cpp), [serializer BUILD](../../sdv-hack-demo/serializer/BUILD.bazel) | New forwarding shim/base packaging | Source comment explains service-type name collision and Rx alias |
| [vehicle main](../../sdv-hack-demo/vehicle_app/main.cc), [root BUILD](../../BUILD), [MODULE.bazel](../../MODULE.bazel) | gRPC client generation and broker high-beam command mode | Route commands through sole provider Tx owner rather than competing skeleton |
| [remote main](../../sdv-hack-demo/remote_app/main.cpp), [remote protocol](../../sdv-hack-demo/remote_app/high_beam_udp_protocol.h), [helper test](../../sdv-hack-demo/remote_app/high_beam_command_test.cpp) | GPIO/output/reporting and test payload changes | State reporting and helper validation visible in code; not proof of hardware operation |
| [databroker-mw-com](../../kuksa-databroker/databroker-mw-com) | Added composition crate | Host broker and provider in one process with coordinated lifecycle |
| [gateway_adapter.rs](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs), [gateway_samples.rs](../../kuksa-databroker/mw_com_provider/src/gateway_samples.rs), [compatibility tests](../../kuksa-databroker/mw_com_provider/tests/gateway_compatibility.rs) | Live native gateway profile | Match actual gateway sample layout and generated binding contract |
| [provider.rs](../../kuksa-databroker/mw_com_provider/src/provider.rs), broker update sources | Legacy/current-value command forwarding (`2723d0a`, `91d2f50`) | Accept target/current writes without re-forwarding provider feedback |
| [build-aarch64.sh](../../sdv-hack-demo/build-aarch64.sh), [package-aarch64.sh](../../sdv-hack-demo/package-aarch64.sh), [vehicle launcher](../../sdv-hack-demo/deploy/start-vehicle.sh) | Updated artifact/config packaging and startup modes | Keep generated config and processes aligned; current binary-name mismatch remains |
| [runtime patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch) | Added/updated runtime Docker/syncer/supervisor changes | External-broker runtime and VAL v1 write integration |
| [.bazelrc](../../.bazelrc), [.vscode/settings.json](../../.vscode/settings.json), lockfiles, [root README](../../README.md) | Build/environment/docs updates | Specific changes visible in diff; not all design reasons recorded |
| [.llm_tmp](../../.llm_tmp), [gateway patch artifact](../../inc_someip_gateway.patch) | Checked-in experimental/patch artifacts | Individual rationale and regeneration contract Unverified |

This table groups changes by coherent contract. The [complete per-file table](changed-files.md) enumerates **every tracked destination/status** in the branch diff, with the latest branch commit subject and an explicit confidence limitation. Renames retain their original path; deletions are shown without dead current-file links.

## Chronological branch history

```text
ee994fb  check
5f999e7  e2e commit
da31f97  build issue is fixed
f6f27c0  inc_someip commit verified and working
9f314a1  communication verified and working
cebbb36  Record gateway dependency config and restore vendored modes
c9b1317  New BCM signals added
525caf3  Latest signal for ECM app is added
932552f  New Signal Engine ON-OFF is added
7c59343  Remove unnecessary cd command from script
a2b367c  Power Train mode signal is added
52af8f2  Latest changes
2723d0a  Legacy version of KUKSA-V1 is supported
91d2f50  added publish for actuator
c125277  sdv-runtime patch is added
b048870  sdv-runtime support for amd86
0842972  updated patch with syner for kuksa_val_v1
```

These are recorded commit subjects, including their original terminology/spelling, not independently validated release claims.

## Untracked content and this documentation

At orientation an empty root `DOCUMENT.md`, the runtime checkout and runtime backup were untracked. The root file was no longer present at validation; this task did not delete it. The runtime trees were not edited. This handbook is additive work under [docs](../../docs), separate from the compared committed branch.

## Related pages

[Complete Branch File Changes](changed-files.md) | [Overview](overview.md) | [Repository Tour](repository-tour.md) | [Verification](verification.md)
