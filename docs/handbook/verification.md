# Verification, Open Questions and Improvements

This page records the limits of the handbook's evidence rather than presenting plausible build commands as successful results. All implementation descriptions come from local files/history; no repository cloning, fetching, GitHub browsing or service deployment was used.

## Executed checks

| Check | Result | What it does not prove |
| --- | --- | --- |
| Orientation: pwd, listing, Git status/branches/remotes/history, three-dot diff and directory tree | `sdv-hackathon`, HEAD `0842972`, no upstream remote | Pristine upstream provenance |
| JSON/model inspection | 44 manifest signals, 45 routes/mappings; 37 bidirectional, seven datapoints, one actuator | Runtime registration/delivery |
| `python3 -B sdv-hack-demo/configure_signals.py` | Passed | Generated binary config matches a deployed image |
| `python3 -B sdv-hack-demo/configure_signals_test.py` | Six tests passed | Actual transport/physical output |
| Native standalone speed codec test | Passed | Target-platform ABI or full Bazel graph |
| Native standalone service-registration test | Passed | Live vsomeip discovery |
| Native standalone high-beam helper test | Passed | Full remote receive loop, GPIO or persistence |
| `bash -n` on build/package/two launchers/KUKSA helper | Passed | Runtime behavior or safe side effects |
| Isolated docs dependency install | Passed; no global packages installed | Existing Sphinx dependency environment |
| Local Mermaid lockfile restore | `npm ci --prefix docs --ignore-scripts --no-audit --no-fund` passed | Application/container build |
| Source citation checks | All repository-relative Markdown targets exist; source line references checked | Remote GitHub URL availability |
| MkDocs Material `--strict` build | Passed with all 26 handbook chapters | Existing Sphinx build/CI |
| Rendered-site check | All local HTML links, assets and fragment targets passed | External websites |
| Handbook helper tests | Four tests passed; navigation JavaScript syntax check passed | Arbitrary future helper changes |
| Browser checks | Search returned matching documents for keyboard-entered `actuation`; all 13 top tabs have purpose tooltips; sticky tabs/breadcrumbs verified at 390px mobile width; eight in-page section links present in the desktop KUKSA sidebar | Every browser/device |
| Mermaid rendering | Diagram sources rendered to SVG using local Mermaid; architecture component/data-flow/sequence sources all rendered successfully with no external asset requests | Domain behavior at runtime |

Material places rendered diagrams in closed shadow roots, so a plain DOM query for `.mermaid svg` is not a valid rendering test. Verification used the bundled renderer's SVG output and rendered-element dimensions, in addition to the local asset/network checks.

## Unverified items

1. **Upstream provenance:** exact pristine Eclipse baselines and upstream contribution attribution for every vendored file. Checked local remotes/history/tree; only `origin` is configured.
2. **Full build:** root/gateway/Communication Bazel graph, Cargo native link, proprietary SDKs, target Rust/cross-compilers/sysroot and all external dependencies. Checked manifests/helpers/selectors, not full compilation.
3. **Runtime:** two-host networking, native LoLa interoperability at runtime, discovery races, IPC recovery and clean shutdown. Checked entry points/launchers and mapping/sample code; did not launch.
4. **Physical behavior:** GPIO detection/wiring, restored output state, debounce timing and actual actuators. Checked remote source/helper tests; no hardware accessed.
5. **Delivery guarantees:** loss/reordering/congestion, duplicates, latency/performance and command correlation. Checked frame/receive loops; no stress or network-fault testing performed.
6. **Security/conformance/safety:** full SOME/IP conformance, authorization deployment and safety qualification. Checked relevant code/defaults and test locations; no audit/certification claim is made.
7. **Full test suites/CI:** Rust/provider/library/integration/platform tests and CI outcomes. Read targets/workflows; did not query CI or run broad suites.
8. **Runtime patch:** clean application against a pinned external base, image builds and patch-target regression tests. Checked committed patch; excluded untracked runtime checkouts.
9. **Configuration exhaustiveness:** computed environment names, third-party implicit settings and all semantics of vendored/test fixture configs. Checked operational paths and scanner-visible literal declarations; dynamic paths remain explicit limits.
10. **Remote source links:** site source URLs are generated from locally existing paths and pinned revision; no GitHub request checked them.
11. **Broader browser support:** diagrams are served using the pinned local Mermaid asset rather than Material's default CDN. Browser smoke results are recorded below; compatibility across every browser/device remains Unverified.
12. **All library internals:** a complete hand-audit of thousands of vendored files, APIs and subfolders is outside the verified integration trace. The tour and inventories identify locations; module-specific design documents remain necessary for deep library changes.

## Confusing or underdocumented code

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Packager/launcher broker filename mismatch | [packager](../../sdv-hack-demo/package-aarch64.sh) versus [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh) | Default combined launch cannot use the copied binary name without reconciliation |
| Speed prose says float while active mapping says double | [root README](../../README.md), [mapping](../../sdv-hack-demo/config/gateway_provider_config.json) | Engineers may select the wrong wire/native representation |
| GPIO comments and generic echo can be mistaken for actuator coverage | [remote source](../../sdv-hack-demo/remote_app/main.cpp) | A successful value round trip is not physical validation |
| Launcher cleanup/recovery is broad and process-name based | [launchers](../../sdv-hack-demo/deploy) | Unsafe to use as an unreviewed shared-host smoke test |
| Model generation edits multiple vendored trees | [configure_signals.py](../../sdv-hack-demo/configure_signals.py) | Build command can dirty source/configuration unexpectedly |
| `known_good.json` pins coexist with active local override | [metadata](../../known_good.json), [include](../../bazel_common/score_modules_target_sw.MODULE.bazel) | Metadata hash does not identify active Communication source |
| Historic variable name affects whole body Tx instance | [gateway adapter](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs) | “Disable high beam” has wider ownership implications |
| Protocol has multiple local copies | [bridge header](../../sdv-hack-demo/bridge/high_beam_udp_protocol.h), [shared header](../../sdv-hack-demo/include/high_beam_udp_protocol.h), [remote header](../../sdv-hack-demo/remote_app/high_beam_udp_protocol.h) | One-sided edits can drift |
| Runtime patch lacks a recorded exact base | [patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch) | Reproducibility and application remain uncertain |
| Platform-test directory is a placeholder | [platform_integration_tests](../../platform_integration_tests) | Do not assume a platform suite exists there; active ITF tests are elsewhere |
| Some checked-in tooling README target spelling differs from BUILD | [README](../../scripts/tooling/README.md) versus [BUILD](../../scripts/tooling/BUILD) | Use `//scripts/tooling:tooling_tests`, as CI does |

## Suggested improvements — not implemented

1. Fix package/launcher artifact-name agreement and add a non-actuating package-contract test.
2. Add a README “build contexts” table showing root/gateway/Communication versions, selected dependency paths and exact target names.
3. Separate generation from compilation so builds can check snapshots without rewriting tracked source.
4. Replace broad launcher cleanup with explicit process ownership and scoped resource lifetimes.
5. Deduplicate frame definitions and add protocol/version compatibility tests.
6. Add a dedicated isolated demo CI job covering generated config, codecs, provider mapping and a software-only round trip.
7. Pin and record external runtime patch bases; distinguish patches, generated files, vendored revisions and local checkouts.
8. Correct stale README datatype/profile descriptions and clearly distinguish generic echo from hardware support.
9. Keep historical coverage reports separate from current-run verification; make disabled jobs visible in contributor docs.
10. Expand this handbook's inventories into schema-aware references if comprehensive vendored-module configuration semantics become a requirement.

These are recommendations, not new components or behavior.

## Related pages

[Testing and CI](testing-ci.md) | [Changes in this Fork](fork-changes.md) | [Build, Run and Deploy](build-run-deploy.md) | [FAQ](faq.md)
