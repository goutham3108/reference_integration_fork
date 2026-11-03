# Integration Workspace

The root Bazel workspace assembles modules rather than containing one monolithic application. Its dependency declarations, generated includes and configuration flags determine which implementations are actually compiled; a nearby vendored folder is not automatically selected.

## Purpose and boundaries

Responsibilities are module selection, common toolchain/platform configuration, aggregate documentation/SBOM targets and demo gRPC code generation. Runtime signal handling belongs to apps and libraries, not this layer ([MODULE.bazel](../../MODULE.bazel), [BUILD](../../BUILD)).

Locations: [bazel_common](../../bazel_common), [bazel/toolchains](../../bazel/toolchains), [patches](../../patches), [known_good.json](../../known_good.json).

## Implementation

The root module selects the local gateway explicitly:

```starlark
bazel_dep(name = "score_someip_gateway", version = "0.0.0")
local_path_override(
    module_name = "score_someip_gateway",
    path = "inc_someip_gateway",
)
```

Source: [MODULE.bazel](../../MODULE.bazel). The target-software include similarly selects local Communication but resolves baselibs, persistency, kyron, lifecycle, logging, time and configuration management through `git_override` declarations ([score_modules_target_sw.MODULE.bazel](../../bazel_common/score_modules_target_sw.MODULE.bazel)).

This distinction matters: the local [baselibs tree](../../baselibs) is used by Cargo path dependencies in the KUKSA build, while the root Bazel graph declares a pinned baselibs dependency. Do not assume both builds consume identical paths; inspect [the KUKSA build helper](../../kuksa-databroker/scripts/build-rpi-aarch64.sh) and the target-software include.

Key root targets in [BUILD](../../BUILD):

| Target | Role |
| --- | --- |
| `//:kuksa_val_types_proto`, `//:kuksa_val_proto` | VAL v2 protobuf inputs |
| `//:kuksa_val_grpc_codegen`, `//:kuksa_val_client` | Generate/build C++ gRPC client |
| `//:docs`, `//:docs_shim` | Existing Sphinx/docs-as-code build and stable alias |
| `//:sbom`, `//:product_sbom` | Product software bill of materials |
| `//:build_tools_sbom` | Separate qualification inventory for build tools |
| `//:starpls_server` | Starlark editor tooling |

The SBOM split is intentional: build-time Python/Java dependencies are not treated as product/runtime dependencies (comments in [BUILD](../../BUILD)).

## Inputs, configuration and dependencies

[MODULE.bazel](../../MODULE.bazel) includes common basic rules, GCC/QNX/Rust/LLVM/Python support, tooling, target software, images and test-artifact versions. It also declares nlohmann JSON, gRPC, protobuf and Rust crate-universe inputs for the demo.

[.bazelrc](../../.bazelrc) defines `linux-x86_64`, `aarch64-linux`, `sdv-demo`, QNX, AutoSD, Elektrobit, coverage and integration-test configurations. `sdv-demo` adds a GNU C11 host-tool flag; it is not itself a target-platform selector. Optional root `user.bazelrc` is imported with `try-import`.

The [pin generator](../../scripts/known_good/update_module_from_known_good.py) derives common includes and documentation bundle metadata from [known_good.json](../../known_good.json). **Branch caveat:** the Communication local override is hand-adapted relative to the generated header; regeneration can replace the intentional integration choice.

## Errors and edge cases

- Module visibility and transitive repository resolution can fail before source compilation; the [pre-commit configuration](../../.pre-commit-config.yaml) explains why copyright checking bypasses one problematic aggregate Bazel graph.
- The root [MODULE.bazel](../../MODULE.bazel) references a JSON-schema validator build label whose availability was not verified through a full build.
- Pin metadata and the active local override are different sources of information; a stale pinned Communication hash in [known_good.json](../../known_good.json) does not identify the active local source tree.

## Testing and modification

Use the tooling/pin tests named in [internal_tests.yml](../../.github/workflows/internal_tests.yml):

```bash
bazel test --lockfile_mode=error \
  //scripts/tooling:tooling_tests //scripts/known_good:known_good_tests
```

**Unverified:** command not run; it may resolve/download module dependencies. Add a module through the [existing integration process](../../docs/integration_process/step_1_add_module.rst), update the metadata and generated includes together, and inspect overrides before rebuilding.

## Limitations

Several external module implementations are absent as first-class source directories; this handbook can document their integration contracts, not unseen internals. Exact toolchain availability and a clean full-workspace build remain **Unverified**.

## Related pages

[Repository Tour](repository-tour.md) | [Build, Run and Deploy](build-run-deploy.md) | [Configuration](configuration.md) | [Platforms](platforms.md)
