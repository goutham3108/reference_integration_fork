# Overview

This repository combines an S-CORE reference-integration workspace with a two-endpoint vehicle-signal demonstration and a KUKSA middleware provider. The branch extends an earlier fork demo with more signals, compatible shared-memory bindings, broker command forwarding and an optional container-runtime patch; it is not a production deployment specification.

## Problem and boundary

The concrete problem is to move typed vehicle signals between local shared-memory middleware, SOME/IP gateway processes, a remote UDP endpoint and gRPC clients. The implementation is visible in the [vehicle application](../../sdv-hack-demo/vehicle_app/main.cc), [bridge](../../sdv-hack-demo/bridge/main.cpp), [remote application](../../sdv-hack-demo/remote_app/main.cpp), and [broker composition](../../kuksa-databroker/databroker-mw-com/src/main.rs).

The inherited reference-integration layer also builds platform images, packages showcases, selects compatible module revisions and runs integration checks. Its entry points are [MODULE.bazel](../../MODULE.bazel), [known_good.json](../../known_good.json), [showcases/BUILD](../../showcases/BUILD), and [score_starter](../../score_starter), `main`.

**Not established by this code:** production safety qualification of this demo, authenticated UDP transport, guaranteed end-to-end command delivery, physical actuation for all listed signals, or deployment to a real vehicle. In particular, the [remote receive loop](../../sdv-hack-demo/remote_app/main.cpp) echoes most non-high-beam payloads rather than driving matching hardware.

## Five-minute mental model

1. **A model is not a live signal.** [body_signals.json](../../sdv-hack-demo/config/body_signals.json) lists 44 body/door/powertrain signals. [configure_signals.py](../../sdv-hack-demo/configure_signals.py), `configure`, derives route and middleware snapshots; [gateway_provider_codegen.py](../../sdv-hack-demo/gateway_provider_codegen.py) derives provider mappings and Rust bindings.
2. **Local data is shared memory.** Apps use `GenericSkeleton` to offer events and `GenericProxy` to subscribe. The provider uses Rust `score_com`; see [vehicle source](../../sdv-hack-demo/vehicle_app/main.cc), `OfferLocalService`, and [gateway adapter](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs).
3. **Two daemons split the gateway boundary.** [gatewayd](../../inc_someip_gateway/score/gatewayd/main.cpp) owns the middleware side; [someipd](../../inc_someip_gateway/score/someipd/main.cpp) owns network-facing routing. They exchange messages through gateway IPC.
4. **The bridge is another process.** [bridge `main`](../../sdv-hack-demo/bridge/main.cpp) subscribes/offers SOME/IP events using vsomeip and relays their payloads in fixed-size UDP frames. It is not the remote GPIO driver.
5. **Current value and command are different concepts.** [provider `start_command_forwarder`](../../kuksa-databroker/mw_com_provider/src/provider.rs) forwards broker target/current-value writes for command-capable mappings, ignores provider feedback to prevent loops, and skips the initial state snapshot.
6. **One publisher owns the body Tx instance.** In default combined mode KUKSA owns it; direct mode selects the legacy vehicle publisher and disables the provider's body Tx offer. See [launcher](../../sdv-hack-demo/deploy/start-vehicle.sh) and [gateway adapter](../../kuksa-databroker/mw_com_provider/src/gateway_adapter.rs).

## What this branch changes

Local history identifies a communication-source refresh (`9f314a1`), gateway-source update (`f6f27c0`), body and engine/powertrain additions (`c9b1317`, `525caf3`, `932552f`, `a2b367c`), legacy VAL v1 support (`2723d0a`), current-value command forwarding (`91d2f50`), and runtime patch updates (`c125277`, `b048870`, `0842972`). See the complete generated [file table](changed-files.md) and the evidence-based [interpretation](fork-changes.md).

**Unverified:** an exact pristine Eclipse upstream baseline. Only the local `origin/main` history and shared ancestor were available. Earlier fork additions already include the basic demo and vendored trees, as shown by `git ls-tree origin/main` and the shared-ancestor history.

## Why these choices exist

| Choice | Visible reason | Evidence |
| --- | --- | --- |
| Same Communication checkout for LoLa users | All processes must agree on shared-memory layout | [module override comments](../../bazel_common/score_modules_target_sw.MODULE.bazel), [gateway override](../../inc_someip_gateway/user.bazelrc) |
| Separate Rx and Tx mappings | Receive current state without making competing body Tx publishers | [provider generator](../../sdv-hack-demo/gateway_provider_codegen.py), [composition mode logic](../../kuksa-databroker/databroker-mw-com/src/main.rs) |
| Serializer shim | Gateway service-type naming collision requires a distinct dynamics Rx name, while base serializer knows the canonical name | [serializer_shim.cpp](../../sdv-hack-demo/serializer/serializer_shim.cpp), leading design comment |
| Dedicated provider worker runtime | Native LoLa state/calls are isolated from the main broker runtime | [start_provider_worker](../../kuksa-databroker/databroker-mw-com/src/main.rs) |
| Compact UDP remote transport | Code implements a 32-byte payload bound; why UDP was selected over a complete remote SOME/IP endpoint is not established | [protocol](../../sdv-hack-demo/include/high_beam_udp_protocol.h), `kMaxPayloadSize`; **Unverified: transport selection rationale** |

## Related pages

[Component Map](index.md) | [Architecture](architecture.md) | [Changes in this Fork](fork-changes.md) | [Glossary](glossary.md)
