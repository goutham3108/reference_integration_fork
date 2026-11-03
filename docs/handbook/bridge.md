# UDP Bridge and Frame Protocol

The bridge connects configured SOME/IP events on the vehicle host to a compact UDP protocol used by the remote demo application. Payload bytes are forwarded rather than converted to VSS values; interpretation happens at the endpoint/provider boundaries.

## Purpose and location

[bridge/main.cpp](../../sdv-hack-demo/bridge/main.cpp), `main`, creates one vsomeip application, registers configured services/events, receives local SOME/IP events and runs a UDP receive thread. [service_registration.h](../../sdv-hack-demo/bridge/service_registration.h), `RegisterServices`, centralizes event/service registration order and deduplicates service pairs.

Non-responsibilities: GPIO access, broker authentication, model generation and native LoLa serialization. The build target is `//sdv-hack-demo/bridge:vehicle_high_beam_bridge` ([BUILD.bazel](../../sdv-hack-demo/bridge/BUILD.bazel)).

## Frame layout

The codec in [high_beam_udp_protocol.h](../../sdv-hack-demo/include/high_beam_udp_protocol.h), `Encode`/`Decode`, uses a **46-byte datagram**:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 4 | Magic `0x48424731` |
| 4 | 1 | Version `1` |
| 5 | 1 | Reserved, encoder zero-initializes |
| 6 | 2 | Service ID, big-endian |
| 8 | 2 | Instance ID, big-endian |
| 10 | 2 | Event ID, big-endian |
| 12 | 1 | Actual payload length, 0..32 |
| 13 | 1 | Reserved, encoder zero-initializes |
| 14 | 32 | Payload storage, zero-filled beyond written bytes |

```cpp
constexpr std::uint32_t kMagic = 0x48424731U;
constexpr std::uint8_t kVersion = 1U;
constexpr std::size_t kHeaderSize = 14U;
constexpr std::size_t kMaxPayloadSize = 32U;
constexpr std::size_t kFrameSize = kHeaderSize + kMaxPayloadSize;
```

Source: [protocol header](../../sdv-hack-demo/include/high_beam_udp_protocol.h). Decode rejects wrong length, magic, version or payload length; it does not require reserved bytes to be zero. `Encode` assumes the caller respects the payload bound.

There are separate copies in [bridge](../../sdv-hack-demo/bridge/high_beam_udp_protocol.h), [include](../../sdv-hack-demo/include/high_beam_udp_protocol.h) and an extended [remote header](../../sdv-hack-demo/remote_app/high_beam_udp_protocol.h). Do not assume modifying one updates the others.

## Control flow and interfaces

`LoadRoutes` reads service, vehicle/remote instance and vehicle/remote event IDs. On vsomeip registration, `RegisterServices` offers remote events/services and requests vehicle services. Availability callbacks subscribe to vehicle events. A vehicle-event handler bounds payload size, encodes the vehicle IDs and sends to the remote; the UDP thread decodes remote IDs, matches a route and calls `notify` ([main.cpp](../../sdv-hack-demo/bridge/main.cpp)).

Configuration: `SIGNAL_ROUTE_CONFIG` defaults to `signal_routes.json`; `VEHICLE_DOMAIN_CONFIG` falls back to `VSOMEIP_CONFIGURATION`, then the integration example path. UDP defaults are bind `0.0.0.0:35000` and destination `127.0.0.1:35001` ([resolver functions](../../sdv-hack-demo/bridge/main.cpp)).

Dependencies are vsomeip, nlohmann JSON, logging/lifecycle and the speed codec; the bridge is consumed by someipd and the remote app ([BUILD.bazel](../../sdv-hack-demo/bridge/BUILD.bazel)).

## Error behavior and limitations

Config/open/initialization/bind errors terminate startup; malformed incoming frames and unknown route IDs are logged and skipped. Some `sendto` results are ignored, and the UDP receive loop continues on receive failures. Its loop has no explicit stop flag, unlike the remote application ([main.cpp](../../sdv-hack-demo/bridge/main.cpp)).

**Unverified:** delivery guarantees, congestion behavior and sender authenticity. The frame has no sequence number, cryptographic integrity field or replay detection. A successful send/log statement is not proof of receipt.

## Testing and extension

[service_registration_test.cpp](../../sdv-hack-demo/bridge/service_registration_test.cpp) tests registration ordering/deduplication against a fake application and reversed route order; its synthetic fixture has 38 events, not the production 45-route inventory. It was compiled and executed natively successfully.

```bash
# Unverified Bazel form; standalone native form was executed.
bazel test --lockfile_mode=error --config=sdv-demo \
  //sdv-hack-demo/bridge:service_registration_test
```

Add routes through the generator. A protocol change requires matching codecs on both endpoints and tests for malformed lengths, unknown versions and maximum payloads; it cannot safely be deployed to one endpoint alone.

## Related pages

[Signals](signals.md) | [Remote App](remote.md) | [Gateway](gateway.md) | [Testing and CI](testing-ci.md)
