# Serializer Adapter

The demo serializer is a small ABI-preserving forwarding library, not a second implementation of every codec. It translates one dynamics Rx service-type name and delegates to a separately packaged gateway serializer.

## Purpose and source

[serializer_shim.cpp](../../sdv-hack-demo/serializer/serializer_shim.cpp) explains the reason: gateway connectors are keyed by service type name, so local and remote instances can collide. The demo gives the Rx type a distinct name; the base serializer still expects its canonical name.

Location: [serializer directory](../../sdv-hack-demo/serializer). Targets `serializer_shim` and `base_serializer`, shared-library filenames and export handling are in [BUILD.bazel](../../sdv-hack-demo/serializer/BUILD.bazel) and [exported_symbols.lds](../../sdv-hack-demo/serializer/exported_symbols.lds).

## Implementation

```cpp
constexpr std::array<std::pair<std::string_view, std::string_view>, 1> kNameAliases{{
    {"vehicle::VehicleDynamicsService_rx", "vehicle::VehicleDynamicsService"},
}};

constexpr char kBaseLibraryName[] = "score_com_serializer_base.so";
```

Source: [serializer_shim.cpp](../../sdv-hack-demo/serializer/serializer_shim.cpp). `OpenBaseLibrary` first uses `dladdr` to locate the shim's directory and tries the base library next to it, then falls back to the dynamic loader's search path. `Base` caches the resolved function table; `CanonicalName` applies the alias before `score_com_serializer_get`.

## Interfaces and dependencies

Exported functions cover initialization/deinitialization, serializer lookup, serialize/deserialize, maximum serialized size, native type size and alignment. The signatures are inherited from [serializer.h](../../inc_someip_gateway/score/serializer/serializer.h).

Dependency direction is **gatewayd → shim → base library**. The shim uses `dlopen`/`dlsym`; the [packager](../../sdv-hack-demo/package-aarch64.sh) ships `score_com_serializer.so` and `score_com_serializer_base.so` together, and the [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh) adds the package directory to `LD_LIBRARY_PATH`.

There are no shim-specific environment settings or CLI flags. Configuration consists of the hard-coded alias table, library filename and process loader path ([source](../../sdv-hack-demo/serializer/serializer_shim.cpp)).

## Errors and edge cases

Missing library/symbol errors are printed to stderr with `[serializer shim]`. Forwarding functions return a general failure or zero metadata size if the base API is invalid; a null service-type pointer is rejected by lookup ([`Base` and exported functions](../../sdv-hack-demo/serializer/serializer_shim.cpp)).

The fallback lookup is useful when the libraries are not adjacent, but also makes loader-path correctness important. A new alias must be compatible with the original service's serialized and native data contracts; renaming alone cannot make unrelated layouts safe.

## Testing and modification

**Unverified:** no dedicated shim test target was identified in [its BUILD](../../sdv-hack-demo/serializer/BUILD.bazel), and no runtime load test was executed. Validate changes by building both libraries, inspecting exported symbols and running a dedicated gateway integration rig with both speed directions.

```bash
# Unverified: root-workspace build.
bazel build --lockfile_mode=error --config=sdv-demo \
  //sdv-hack-demo/serializer:serializer_shim \
  //sdv-hack-demo/serializer:base_serializer
```

Keep the ABI header authoritative; do not independently change a function signature. Limitations include the single hard-coded alias and integration dependence on dynamic loading rather than a statically enforced package relationship.

## Related pages

[Gateway](gateway.md) | [Signals](signals.md) | [Configuration](configuration.md) | [FAQ](faq.md)
