# Build, Run and Deploy

There are three distinct workflows: preview this handbook, build the two-endpoint demo, and build inherited platform images. Only documentation builds and narrowly scoped non-actuating checks were executed here; other commands below are explicitly marked **Unverified**.

## Documentation preview

From the repository root, create a local virtual environment and install the isolated documentation dependency:

```bash
python3 -m venv docs/.venv-handbook
docs/.venv-handbook/bin/python -m pip install -r docs/requirements-handbook.txt
npm ci --prefix docs --ignore-scripts --no-audit --no-fund
python3 -B docs/tools/handbook.py check
docs/.venv-handbook/bin/python -m mkdocs serve -f docs/mkdocs.yml -a 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/`. The dependency installation and site build were verified using the docs-local virtual environment above. No global installation is needed.

```bash
# Build only, including internal-site link validation.
docs/.venv-handbook/bin/python -m mkdocs build --strict -f docs/mkdocs.yml
python3 -B docs/tools/handbook.py site

# After editing chapter sources, regenerate the consolidated document/appendices.
python3 -B docs/tools/handbook.py generate
```

Configuration: [mkdocs.yml](../mkdocs.yml), [requirements-handbook.txt](../requirements-handbook.txt), [package.json](../package.json), [handbook.py](../tools/handbook.py). Output is `docs/_handbook_site`; this new output directory is ignored by [docs/.gitignore](../.gitignore). Existing Sphinx configuration and targets are unchanged.

The top tabs persist during scrolling and have purpose tooltips; the sidebar integrates page sections, breadcrumbs precede the page, and search is local. Mermaid source is embedded in the pages; [site_hooks.py](../tools/site_hooks.py), `on_files`, copies the pinned local renderer and its license into site assets so rendering does not require the default Mermaid CDN. Building the site requires Node/npm for the docs-local dependency installation. The license is published at `assets/mermaid-LICENSE.txt`, and upstream bundled dependency notices remain in the unmodified browser script.

## Demo prerequisites

| Requirement | Source-defined expectation |
| --- | --- |
| Build host | x86_64 Linux for the KUKSA cross-build helper |
| Bazel | Root and gateway selectors: 8.6.0; Communication selector: 8.7.0 |
| Rust | Stable 1.96+ checked by the KUKSA script; AArch64 GNU target |
| Native tools | Bash, `file`, GNU cross C/C++ compiler and archiver; scripts also use common Linux utilities |
| Toolchain/sysroot | Executable `AARCH64_CC`, `AARCH64_CXX`, `AARCH64_AR` or helper defaults |
| Sources | Local gateway, Communication, baselibs and KUKSA trees |
| Devices | Compatible AArch64 Linux environment for packaged binaries; GPIO is optional in the remote app |

Evidence: [version selectors](../../.bazelversion), [gateway selector](../../inc_someip_gateway/.bazelversion), [Communication selector](../../communication/.bazelversion), [KUKSA cross-build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh), [remote GPIO fallback](../../sdv-hack-demo/remote_app/main.cpp).

**Unverified:** installed cross-toolchain/sysroot suitability, Rust target availability, full external dependency resolution, target OS/libc compatibility and hardware connectivity. The helper's toolchain creation instructions involve downloads, SSH and installing prerequisites; they were not run.

## Build the demo

**Unverified; not executed because it regenerates existing source/configuration files and may download build dependencies.** Review your worktree before using this documented build:

```bash
bash sdv-hack-demo/build-aarch64.sh
```

Actual steps in [build-aarch64.sh](../../sdv-hack-demo/build-aarch64.sh):

1. Run `configure_signals.py --write`.
2. In the gateway workspace, build `//score/gatewayd` and `//score/someipd` with `--config=aarch64-linux`.
3. In the root workspace, build gateway config, both serializers, vehicle menu, signal tester, bridge and remote app with `aarch64-linux` and `sdv-demo`.
4. Run [build-rpi-aarch64.sh](../../kuksa-databroker/scripts/build-rpi-aarch64.sh).

The KUKSA helper builds the Communication vehicle-dynamics target, exports Bazel link-artifact locations to Cargo, builds broker/protobuf/CLI/provider/composition binaries and checks executable architecture using `file`. Its final expected line is:

```text
All requested Raspberry Pi targets built successfully.
```

This is a **source-derived expected output**, not an observed full-build success. Both helpers use `set -euo pipefail`.

## Package and deploy

**Unverified; not executed.**

```bash
bash sdv-hack-demo/package-aarch64.sh
```

The [packager](../../sdv-hack-demo/package-aarch64.sh) requires existing AArch64 Bazel binaries/runfiles and Cargo release artifacts. It creates `sdv-hack-demo/dist/vehicle-aarch64.tar.gz` and `remote-aarch64.tar.gz`, including matched routes/network defaults and libraries. Its staging cleanup removes its temporary directory; review the script before execution.

On two **dedicated, isolated test hosts**, extract each archive into its own empty deployment directory using a non-overwriting extraction policy, then edit the extracted `network.env`. File transfer, extraction and device paths are **Unverified** because no hosts were accessed.

The packaged vehicle launcher expects `${root}/databroker-mw-com-demo`, but the current packager copies `databroker-mw-com` under its original name. **This is a source-visible deployment mismatch, not a verified working command.** Compare [package-aarch64.sh](../../sdv-hack-demo/package-aarch64.sh) and [start-vehicle.sh](../../sdv-hack-demo/deploy/start-vehicle.sh), `start_kuksa`; reconcile the package/launcher contract in a separate code change before combined-mode deployment.

### Launcher side effects

The launchers are **not safe validation commands for a shared development host**:

- [start-vehicle.sh](../../sdv-hack-demo/deploy/start-vehicle.sh) kills processes by name/pattern, removes vsomeip lock/socket artifacts and LoLa shared-memory files, rewrites an extracted vsomeip config and starts background daemons.
- [start-remote.sh](../../sdv-hack-demo/deploy/start-remote.sh) kills matching remote app processes and starts an app that may access GPIO and persist state.
- `VEHICLE_APP_MODE=signals` publishes horn/lighting/lock/window/wiper and other test values. It is not a read-only smoke test ([tester source](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp)).

After reviewing those side effects and fixing the package mismatch, the intended installed commands are:

```bash
# Unverified: run only on the dedicated remote test host.
./run/start-remote.sh

# Unverified: run only on the dedicated vehicle test host.
./run/start-vehicle.sh
```

The vehicle launcher binds the broker to all interfaces on TCP 55555 with authorization disabled in the composed server. Restrict connectivity to the test network; do not infer production access controls exist ([composition](../../kuksa-databroker/databroker-mw-com/src/main.rs)).

## Expected observation and common failures

| Symptom | Check and action | Source |
| --- | --- | --- |
| Missing ARM compiler | Check executable toolchain environment paths; prepare a compatible sysroot separately | [cross-build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh) |
| Rust version rejected | Use the helper's required stable version/target; do not assume the provider's Rust edition establishes the whole workspace MSRV | [version guard](../../kuksa-databroker/scripts/build-rpi-aarch64.sh) |
| Missing package artifact/runfiles | Build the exact targets and architecture before packaging | [copy_target](../../sdv-hack-demo/package-aarch64.sh) |
| Broker launcher says binary missing | Check the `databroker-mw-com` versus `databroker-mw-com-demo` mismatch | [packager](../../sdv-hack-demo/package-aarch64.sh), [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh) |
| Duplicate publisher/service failures | Ensure one owner per body Tx instance; use consistent command mode | [vehicle Run](../../sdv-hack-demo/vehicle_app/main.cc), [adapter](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs) |
| Broker listening but no datapoints | Check gateway IPC, service discovery, shared-memory readiness, mapping profile and remote routes—not only the TCP port | [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh), [provider](../../kuksa-databroker/mw_com_provider/src/provider.rs) |
| Serializer load failure | Keep both libraries together; inspect loader paths and stderr | [serializer Base](../../sdv-hack-demo/serializer/serializer_shim.cpp) |
| GPIO unavailable off-Pi | Expected logged fallback; menu/network can still run | [remote main](../../sdv-hack-demo/remote_app/main.cpp) |
| Signal round-trip timeout | Check matching routes/event IDs and remote process; service subscription alone is insufficient | [tester](../../sdv-hack-demo/vehicle_app/body_signal_test_app.cpp) |

## Related pages

[Configuration](configuration.md) | [Testing and CI](testing-ci.md) | [Contributing and Debugging](contributing-debugging.md) | [Verification](verification.md)
