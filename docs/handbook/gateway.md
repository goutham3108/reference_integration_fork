# SOME/IP Gateway

The gateway translates between middleware service instances and SOME/IP network services using two cooperating daemons. This integration builds the gateway as its own Bazel workspace and supplies demo-specific binary configuration and a serializer adapter.

## Purpose, location and non-responsibilities

[gatewayd](../../inc_someip_gateway/score/gatewayd) owns middleware-facing local/remote service instances; [someipd](../../inc_someip_gateway/score/someipd) owns network-facing services and routing. Their IPC transport lives in [gateway_ipc_binding](../../inc_someip_gateway/score/gateway_ipc_binding); they do not parse the demo's compact remote UDP frame—that belongs to the bridge.

## Implementation

`someipd` creates the server side of the daemon connection:

```cpp
message_passing::ServiceProtocolConfig const proto{ipc_channel_name, someip::kMaxIpcMessageSize,
                                                   someip::kMaxIpcMessageSize,
                                                   someip::kMaxIpcMessageSize};

auto ipc_server = message_passing::ServerFactory{}.Create(proto, {10, 1, 10});
```

Source: [someipd/main.cpp](../../inc_someip_gateway/score/someipd/main.cpp), `main`. It builds a gateway binding server, starts routing, and constructs local and remote network services from configuration. [gatewayd/main.cpp](../../inc_someip_gateway/score/gatewayd/main.cpp) creates the corresponding client and middleware-facing services.

Gateway `event_slot_size` queries the serializer for each event's maximum size and adds the SOME/IP header. If any maximum is unavailable it uses the transport maximum rather than shrinking shared-memory slots unsafely ([gatewayd `event_slot_size`](../../inc_someip_gateway/score/gatewayd/main.cpp)).

## Interfaces and configuration

| Input / output | Meaning |
| --- | --- |
| `--configuration` / `-c` | Required compiled FlatBuffers gateway config, both daemons |
| `--service_instance_manifest` / `-s` | Required LoLa manifest, gatewayd |
| `--ipc_channel` / `-i` | Optional daemon IPC channel; same name on both sides |
| `VSOMEIP_CONFIGURATION` | vsomeip network configuration supplied by launcher |
| Serializer ABI | Functions in [serializer.h](../../inc_someip_gateway/score/serializer/serializer.h) |
| IPC service constants | [constants.h](../../inc_someip_gateway/score/someip/constants.h) |

The [demo BUILD](../../sdv-hack-demo/BUILD.bazel), `gateway_config`, compiles [demo JSON](../../sdv-hack-demo/config/mw_someip_config.json) to `mw_someip_config.bin` using the gateway's generation rule. The [packager](../../sdv-hack-demo/package-aarch64.sh) combines this binary with the gateway LoLa/vsomeip snapshots and both serializer libraries.

## Dependencies and consumers

Dependencies include Communication for middleware, message-passing/IPC helpers, vsomeip through network wrappers, and the serializer ABI. Consumers are the vehicle app/provider on the middleware side and the UDP bridge on the SOME/IP side ([gateway MODULE](../../inc_someip_gateway/MODULE.bazel), [gatewayd BUILD](../../inc_someip_gateway/score/gatewayd/BUILD.bazel), [someipd BUILD](../../inc_someip_gateway/score/someipd/BUILD.bazel)).

The [gateway override](../../inc_someip_gateway/user.bazelrc) points Communication at `../communication` and disables lockfile rewriting during resolution. This deliberately aligns LoLa with the KUKSA build; it does not pin the entire vendored gateway to pristine upstream.

## Errors and shutdown

Both entry points validate required options, reject unreadable/empty binary config files, register SIGINT/SIGTERM handlers and report fatal initialization errors. SOME/IP/IPC startup can fail independently of a successful executable build ([gatewayd/main.cpp](../../inc_someip_gateway/score/gatewayd/main.cpp), [someipd/main.cpp](../../inc_someip_gateway/score/someipd/main.cpp)).

The [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh) retries a suspected stuck IPC connection by restarting both daemons. This is launcher-level recovery, not proof that the daemon connection reconnects automatically in every case.

## Testing and extension

Module-local test commands are recorded in [AGENTS.md](../../inc_someip_gateway/AGENTS.md):

```bash
# Unverified: execute from inc_someip_gateway/, not the root workspace.
bazel test //score/...
bazel test --config=qemu-integration //tests/integration_test/...
```

For new events, prefer the existing signal generator. For transport changes, add tests at the daemon/IPC boundary and in [integration tests](../../inc_someip_gateway/tests/integration_test), then check both directions and serializer metadata.

## Limitations / debt

The integration's service naming workaround and launcher retry/cleanup behavior are tightly coupled to current gateway behavior. **Unverified:** complete SOME/IP conformance, ASIL separation guarantees of this fork, and performance at the full signal rate; the presence of conformance test directories is not a passed result.

## Related pages

[Serializer](serializer.md) | [UDP Bridge](bridge.md) | [S-CORE](score.md) | [Build, Run and Deploy](build-run-deploy.md)
