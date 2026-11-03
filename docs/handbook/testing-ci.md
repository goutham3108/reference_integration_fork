# Testing and CI

Tests exist at codec, model-generation, provider, library and integration-framework levels. A passed unit test establishes only its own contract; it does not demonstrate two-host operation, actual GPIO output or a passing CI run on this branch.

## Engineering tooling responsibilities

[scripts](../../scripts) manages dependency metadata, tooling commands, builds and report generation; [.github/workflows](../../.github/workflows) defines automation. These tools consume [known_good.json](../../known_good.json), Bazel target lists and test results, and produce generated includes, build logs, coverage and documentation reports—not runtime vehicle events.

The [tooling BUILD](../../scripts/tooling/BUILD) separates `lib`, `cli`, `tooling`, workflow executables and `tooling_tests`. [quality_runners.py](../../scripts/quality_runners.py), `run_unit_test_with_coverage`, invokes Bazel coverage with module-specific code roots/configuration/exclusions; `cpp_coverage` and `rust_coverage` build reports.

## Tests and exact targets

| Layer | Location / target | What it checks | Authoring result |
| --- | --- | --- | --- |
| Signal snapshots | [configure_signals.py](../../sdv-hack-demo/configure_signals.py), default check | Generated views match committed snapshots | Passed |
| Generator contracts | [configure_signals_test.py](../../sdv-hack-demo/configure_signals_test.py) | Six tests for signal/route/provider consistency | 6 passed |
| Speed codec | [speed_payload_test.cpp](../../sdv-hack-demo/include/speed_payload_test.cpp), `//sdv-hack-demo:speed_payload_test` | Endian encoding and positive/zero/negative double round trips | Native standalone passed |
| Service registration | [service_registration_test.cpp](../../sdv-hack-demo/bridge/service_registration_test.cpp), `//sdv-hack-demo/bridge:service_registration_test` | Event-first ordering and service deduplication | Native standalone passed |
| Remote helpers | [high_beam_command_test.cpp](../../sdv-hack-demo/remote_app/high_beam_command_test.cpp), `//sdv-hack-demo/remote_app:high_beam_command_test` | Command validation, output callbacks, codec/test samples | Native standalone passed |
| Signal test values | [signal_test_values_test.cpp](../../sdv-hack-demo/vehicle_app/signal_test_values_test.cpp), `//sdv-hack-demo/vehicle_app:signal_test_values_test` | 44 routes, payload bounds, malformed model rejection | Unverified: not run |
| Provider | [provider source](../../kuksa-databroker/mw_com_provider/src/provider.rs), [tests](../../kuksa-databroker/mw_com_provider/tests) | Mapping/quality/metadata/command/feedback contracts | Unverified: not run |
| Tooling/pins | [tooling tests](../../scripts/tooling/tests), [pin tests](../../scripts/known_good/tests) | CLI/model/generation/report behavior | Unverified: not run |
| Feature integration | [test_cases](../../feature_integration_tests/test_cases), [scenarios](../../feature_integration_tests/test_scenarios) | Python assertions over C++/Rust scenarios | Unverified: not run |
| Gateway | [gateway tests](../../inc_someip_gateway/tests), module-local tests | IPC, network and gateway behaviors | Unverified: not run |
| Platform integration | [ITF tests](../../feature_integration_tests/itf) | QEMU showcase/logging/SSH checks | Unverified: not run |
| Shell scripts | Five demo/cross-build scripts | `bash -n` parsing only | Passed; no launch/build execution |

## Reproduce the safe subset

```bash
python3 -B sdv-hack-demo/configure_signals.py
python3 -B sdv-hack-demo/configure_signals_test.py
bash -n sdv-hack-demo/build-aarch64.sh sdv-hack-demo/package-aarch64.sh \
  sdv-hack-demo/deploy/start-vehicle.sh sdv-hack-demo/deploy/start-remote.sh \
  kuksa-databroker/scripts/build-rpi-aarch64.sh
```

The three C++ tests were built with `g++ -std=c++17 -Wall -Wextra -pedantic -I.` and executed from session storage outside the repository. This avoids Bazel dependency downloads but does **not** validate the Bazel graph or target toolchain.

For normal development, use their actual Bazel targets together:

```bash
# Unverified: Bazel execution may resolve/download dependencies.
bazel test --lockfile_mode=error --config=sdv-demo \
  //sdv-hack-demo:speed_payload_test \
  //sdv-hack-demo/bridge:service_registration_test \
  //sdv-hack-demo/remote_app:high_beam_command_test \
  //sdv-hack-demo/vehicle_app:signal_test_values_test
```

## Feature integration framework

[FitScenario](../../feature_integration_tests/test_cases/fit_scenario.py) wraps subprocess results and rejects unexpected success/failure/hangs. C++ and Rust scenario binaries have their own entry points, and Python fixtures provide build/run/log assertions. Pytest roots, language markers and Python paths are configured in [pyproject.toml](../../pyproject.toml).

```bash
# Unverified: root-workspace scenario suite.
bazel test --lockfile_mode=error --config=linux-x86_64 \
  //feature_integration_tests/test_cases:fit
```

The real all-signal test is different: it publishes values and waits for feedback. Its matching-value success criterion has no packet correlation or physical-output verification ([SignalTestApplication](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)). Run it only on an isolated rig with explicit ownership of the body Tx instance.

## What CI declares

| Workflow | Source-visible behavior |
| --- | --- |
| [test_and_docs.yml](../../.github/workflows/test_and_docs.yml) | Docs preflight, module coverage, feature integration, build-tool SBOM, reports, documentation artifacts/deployment |
| [internal_tests.yml](../../.github/workflows/internal_tests.yml) | Reusable tests workflow for tooling/pin test targets |
| [build_and_test_linux.yml](../../.github/workflows/build_and_test_linux.yml) | Linux platform workflow |
| [build_and_test_qnx.yml](../../.github/workflows/build_and_test_qnx.yml) | QNX platform workflow |
| [build_and_test_autosd.yml](../../.github/workflows/build_and_test_autosd.yml) | AutoSD platform workflow |
| [build_and_test_ebclfsa.yml](../../.github/workflows/build_and_test_ebclfsa.yml) | Elektrobit platform workflow |
| [reusable_integration-build.yml](../../.github/workflows/reusable_integration-build.yml) | Generate supplied known-good metadata, invoke integration build, upload `_logs` |
| [test_integration.yml](../../.github/workflows/test_integration.yml) | Latest-main integration job explicitly disabled with `if: false` |
| [format.yml](../../.github/workflows/format.yml), [copyright.yml](../../.github/workflows/copyright.yml) | Formatting/legal-header automation |
| [known_good_correct.yml](../../.github/workflows/known_good_correct.yml), [bzlmod-lock.yml](../../.github/workflows/bzlmod-lock.yml) | Dependency metadata/lock maintenance |
| [check_release_approvals.yml](../../.github/workflows/check_release_approvals.yml) | Release-approval workflow |
| [codeql-multiple-repo-scan.yml](../../.github/workflows/codeql-multiple-repo-scan.yml) | Static-analysis workflow |
| [docs_cleanup.yml](../../.github/workflows/docs_cleanup.yml), [reusable_smoke-test.yml](../../.github/workflows/reusable_smoke-test.yml) | Documentation cleanup and reusable smoke-test infrastructure |

These are configured jobs, **not observed CI outcomes**. No GitHub status/logs were accessed.

## Side effects, errors and modification

Do not run [quality_runners.py](../../scripts/quality_runners.py) as an innocent read-only check: `configure_aslr_for_sanitizers` attempts `sudo sysctl -w vm.mmap_rnd_bits=28`, and report generation writes existing documentation/report paths. The source explains a sanitizer-shadow-memory workaround; changing a host kernel setting is still a shared-environment side effect.

Add focused tests beside the changed helper/module, then run the nearest target before broad suites. For new metadata formats, extend [pin tests](../../scripts/known_good/tests); for new application behavior, test serialization, mapping and the actual delivery/ownership scenario rather than just a JSON count.

## Limitations

The demo has no verified dedicated CI job covering its full two-endpoint flow. Existing report files are historical artifacts; all full builds, Rust suites, platform tests and hardware tests remain **Unverified** here.

## Related pages

[Build, Run and Deploy](build-run-deploy.md) | [Vehicle Apps](vehicle.md) | [KUKSA](kuksa.md) | [Verification](verification.md)
