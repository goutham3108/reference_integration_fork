# Contributing and Debugging

Start a change at the contract that owns the behavior: model for signal identity, provider for broker mapping, bridge for framing, and endpoint for physical/software state. Debug one boundary at a time rather than restarting an entire shared machine or treating a listening TCP port as proof of end-to-end success.

## Add a component or module

1. Follow [the existing module integration process](../../docs/integration_process/step_1_add_module.rst).
2. Declare the module/version/patch/docs/test metadata in [known_good.json](../../known_good.json); inspect [the pin generator](../../scripts/known_good/update_module_from_known_good.py) before regenerating includes.
3. Preserve deliberate local overrides in [the target-software include](../../bazel_common/score_modules_target_sw.MODULE.bazel) and [gateway user.bazelrc](../../inc_someip_gateway/user.bazelrc).
4. Add exact build/test targets and package inputs; wire image/showcase targets only if the new component is actually deployed there.
5. Add focused tests and documentation describing inputs, outputs, failure behavior and ownership. Do not claim a new dependency is exercised merely because it resolves.

For a signal rather than a module, use the [signal-specific workflow](signals.md); metadata changes can affect native sample layout, not only routes.

## Logging and observability

| Where | Output / mechanism | Evidence |
| --- | --- | --- |
| Installed vehicle package | `someipd.log`, `gatewayd.log`, `bridge.log`, `kuksa.log` | [vehicle launcher redirections](../../sdv-hack-demo/deploy/start-vehicle.sh) |
| Vehicle foreground app | Menu plus middleware log calls; input may use `/dev/tty` | [vehicle Run](../../sdv-hack-demo/vehicle_app/main.cc) |
| Remote foreground app | Console/log output; menu attempts terminal output separately | [remote Say/main](../../sdv-hack-demo/remote_app/main.cpp) |
| Serializer shim | stderr with `[serializer shim]` | [serializer Base](../../sdv-hack-demo/serializer/serializer_shim.cpp) |
| Rust broker/provider | tracing subscriber; non-OTel default `info`, configurable by `RUST_LOG` | [init_logging](../../kuksa-databroker/databroker/src/lib.rs) |
| Integration builds | `_logs` artifacts and generated summaries | [reusable build workflow](../../.github/workflows/reusable_integration-build.yml), [integration_test.py](../../scripts/integration_test.py) |
| Bazel tests | Test logs under Bazel output symlinks | Targets in [test BUILD](../../feature_integration_tests/test_cases/BUILD) and [CI](../../.github/workflows/test_and_docs.yml) |

Do not print secrets, access tokens or environment dumps when sharing diagnostics. These log locations are source-defined, not proof that any launcher was run during handbook authoring.

## Non-actuating troubleshooting checklist

1. **Identify the build context.** Root, gateway and Communication have separate Bazel versions/config names ([selectors](../../.bazelversion), [gateway selector](../../inc_someip_gateway/.bazelversion), [Communication selector](../../communication/.bazelversion)).
2. **Check generated alignment.** Run the read-only generator check and its tests; do not jump directly to `--write`.
3. **Check package contracts.** Confirm the broker filename expected by the launcher actually exists; current packaging and launcher names differ ([build/deploy guide](build-run-deploy.md)).
4. **Inspect configured listeners.** On an authorized test host, `ss -Hltnp 'sport = :55555'` and `ss -Hlun` are observational commands; they do not prove a usable provider.
5. **Inspect daemon IPC.** The launcher expects `someipd_gatewayd_ipc`; inspect logs and `/proc/net/unix` before changing anything ([launcher](../../sdv-hack-demo/deploy/start-vehicle.sh)).
6. **Check service identity/layout.** Match instance specifiers, event names, sample sizes/alignment and the active provider profile ([gateway metadata](../../kuksa-databroker/mw_com_provider/generated/gateway_bindings.rs)).
7. **Trace an existing sample.** Compare remote/bridge/gateway/provider logs without issuing commands. Service discovery, notification arrival and broker datapoint update are different observations.
8. **Separate UI from hardware.** GPIO errors are nonfatal; generic route echo is not physical output ([remote source](../../sdv-hack-demo/remote_app/main.cpp)).

**Unverified:** the observational commands against a deployed host were not executed here. Never use broad process-kill or shared-memory deletion commands as a generic troubleshooting step on a shared system.

## Extension recipes

### Change broker mapping or add a datatype

Update the source manifest/generator, Rust sample codec, mapper and generated metadata together. Test rejected quality, stale data, range/array bounds, command direction and provider feedback suppression ([config.rs](../../kuksa-databroker/mw_com_provider/src/config.rs), [mapper.rs](../../kuksa-databroker/mw_com_provider/src/mapper.rs), [provider tests](../../kuksa-databroker/mw_com_provider/src/provider.rs)).

### Change UDP framing

Change both active endpoint codecs and the shared copy; version the frame contract and add malformed-frame/maximum-payload tests. The three copies are documented in [UDP Bridge](bridge.md). Rebuild/deploy both peers together.

### Change startup behavior

Preserve one body Tx publisher, explicit failure reporting and consistent broker/profile paths. Test lock contention, occupied ports, missing artifacts, failed daemons and unavailable remote state—not only successful startup ([launchers](../../sdv-hack-demo/deploy)).

## Documentation maintenance

Edit the chapter sources listed in [the Component Map](index.md), regenerate [document.md](../document.md) with `python3 -B docs/tools/handbook.py generate`, run its `check`, build MkDocs with `--strict`, then run `python3 -B docs/tools/handbook.py site`. New major components need a navigation entry and purpose tooltip in [navigation.js](assets/navigation.js); a page not in navigation is not discoverable merely because it exists.

The handbook helper tests run with `docs/.venv-handbook/bin/python -B -m unittest discover -s docs/tools -p 'test_*.py'`. They exercise link extraction, missing-anchor rejection, consolidated chapter/source-link rewriting and pinned citation generation ([test_handbook.py](../tools/test_handbook.py)).

The existing Sphinx documentation is independent. This handbook is not automatically included in the repository's Sphinx CI target ([root BUILD](../../BUILD), [MkDocs config](../mkdocs.yml)).

## Related pages

[Signals](signals.md) | [Testing and CI](testing-ci.md) | [Build, Run and Deploy](build-run-deploy.md) | [FAQ](faq.md)
