# KUKSA to `score::mw::com` (ARA::COM) Demo

Note: `score::mw::com` is the S-CORE name for the middleware component
commonly referred to as ARA::COM (AUTOSAR Runtime for Applications Communication).
This demo uses the `score::mw::com` APIs and a Lola SHM binding that
implements the ARA::COM-style shared-memory event exchange.

This demo proves out one vertical slice of the pub/sub vehicle middleware
architecture: KUKSA vehicle signals flowing into an S-CORE `mw::com` (ARA::COM)
publisher, and out to an S-CORE `mw::com` (ARA::COM) subscriber. It does **not** yet
include the SOME/IP gateway, REST bus simulator, or digital.auto — those are
later, separate integration steps.

## Watching every VSS signal automatically (current and future)

`kuksa_to_com` auto-discovers which VSS paths to poll/publish, in this order:

1. `KUKSA_VSS_PATHS_FILE` — explicit newline-separated file of paths.
2. `KUKSA_VSS_PATHS` — explicit comma-separated list.
3. **Auto-discovery from a VSS json tree** — [demo/mw_com_setup/etc/vss.json](etc/vss.json)
   (or `KUKSA_VSS_JSON_FILE` if set). Every leaf signal in this file (any node
   whose `type` isn't `branch`) is watched automatically — no code change, no
   regenerating a path list, and any signal added to the file in the future
   is picked up on the next run.
4. A small hardcoded `DEFAULT_VSS_PATHS` fallback if none of the above apply.

The checked-in `etc/vss.json` is a sample containing the signals used in this
demo. **Replace it with your full VSS export** (e.g. the file used to seed
your KUKSA Databroker) to have every signal in it flow through automatically:

```bash
cp /path/to/your/vss.json demo/mw_com_setup/etc/vss.json
bazel run --config=linux-x86_64 //demo/mw_com_setup/kuksa_to_com:kuksa_to_com
```

## What this is about

```text
KUKSA Databroker (external, via Docker)
        |
        | kuksa-databroker-cli "get <path>" (real gRPC client, polled)
        v
kuksa_to_com  (Rust, S-CORE mw::com PROVIDER)
        |
        | score::mw::com event "vss_signal" (shared memory, Lola binding)
        v
mw_com_receiver  (Rust, S-CORE mw::com CONSUMER)
        |
        v
stdout (prints "<VSS path> = <value>")
```

## Artifacts in this folder

| Path | Role |
|---|---|
| [kuksa_to_com/main.rs](kuksa_to_com/main.rs) | Polls KUKSA, offers the `mw::com` service, publishes changed signals |
| [kuksa_to_com/gen/vehicle_gen.h](kuksa_to_com/gen/vehicle_gen.h) / [.cpp](kuksa_to_com/gen/vehicle_gen.cpp) | Local C++ FFI export of the `VehicleInterface` service and its `VssSignal` event type |
| [kuksa_to_com/gen/com_api_gen.rs](kuksa_to_com/gen/com_api_gen.rs) | Rust side of the same interface (generated via `score_com::interface!`), plus the pack/unpack helpers for `VssSignal` |
| [kuksa_to_com/etc/mw_com_config.json](kuksa_to_com/etc/mw_com_config.json) | Lola runtime manifest: service type, instance, and the single `vss_signal` event binding |
| [mw_com_receiver/main.rs](mw_com_receiver/main.rs) | Discovers the offered instance, subscribes to `vss_signal`, prints every update |

Both binaries load the same `mw_com_config.json` and connect through the same
instance specifier `/Vehicle/Service1/Instance`, which is how they rendezvous.

## Why one generic event instead of many typed ones

Earlier iterations used one typed `mw::com` event per VSS signal
(`vehicle_speed`, `engine_speed`, ...), which meant adding a new KUKSA signal
required editing the interface and rebuilding. This version instead defines a
single event, `vss_signal`, whose payload is a generic `(path, value)` pair of
UTF-8 text (fixed-size buffers, no heap allocation, consistent with `mw::com`'s
zero-copy design). Any VSS path can flow through without touching the
interface — see `watched_vss_paths()` in `kuksa_to_com/main.rs`.

## Signal flow, artifact by artifact

1. **You publish a signal** in the KUKSA CLI, e.g. `publish Vehicle.Speed 88.8`.
   This writes the value into the running KUKSA Databroker over gRPC
   (`kuksa.val.v1`).

2. **`kuksa_to_com` polls KUKSA.** Every 500 ms, for each path in its watch
   list (`watched_vss_paths()`), it shells out to the official
   `kuksa-databroker-cli` Docker image (`get <path>`) — a real gRPC client
   call against the real Databroker, not a simulation. `kuksa_get()` parses
   the CLI's `<path>: <value>` output line.

3. **Change detection.** `kuksa_to_com` keeps a `HashMap` of the last value
   seen per path. It only proceeds to step 4 when the value actually changed
   since the previous poll, so unchanged signals are silent instead of
   flooding the log/channel every cycle.

4. **`kuksa_to_com` publishes over `mw::com` (ARA::COM).** It builds a
   `VssSignal { path, value }` (packed into fixed byte buffers via
   `VssSignal::new`), allocates a sample on the `vss_signal` event, writes it,
   and calls `.send()`. This writes into the Lola shared-memory binding
   configured in `mw_com_config.json` — this is the actual `score::mw::com`
   (ARA::COM) **provider** side.

5. **`mw_com_receiver` discovers and subscribes.** On startup it calls
   `find_service::<VehicleInterface>` for `/Vehicle/Service1/Instance`, polls
   `get_available_instances()` until `kuksa_to_com` has offered the service,
   builds a consumer, and subscribes to `vss_signal`.

6. **`mw_com_receiver` receives and prints.** Its main loop calls
   `try_receive()` every 200 ms; for every sample it unpacks `path_str()` /
   `value_str()` from the `VssSignal` and prints `"<path> = <value>"`. This is
   the `score::mw::com` (ARA::COM) **consumer** side — it has no knowledge of
   KUKSA, Docker, or gRPC; it only understands `mw::com` events.

## Commands to run this demo

### 1. KUKSA network + Databroker

```bash
docker network create kuksa   # skip if it already exists

docker run -d --rm --name Server --network kuksa \
  ghcr.io/eclipse-kuksa/kuksa-databroker:main --insecure
```

### 2. KUKSA CLI (interactive, to publish signals)

```bash
docker run -it --rm --network kuksa \
  ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main --server Server:55555
```

```text
publish Vehicle.Speed 88.8
publish Vehicle.Powertrain.CombustionEngine.Speed 2500
publish Vehicle.Cabin.Door.Row1.Left.IsOpen true
publish Vehicle.Powertrain.TractionBattery.StateOfCharge.Current 75
```

### 3. Build

```bash
cd /home/goutham/Gitrepos/SDV-Hackathon/reference_integration_fork

bazel build --config=linux-x86_64 \
  //demo/mw_com_setup/kuksa_to_com:kuksa_to_com \
  //demo/mw_com_setup/mw_com_receiver:mw_com_receiver
```

### 4. Run the receiver

```bash
bazel run --config=linux-x86_64 //demo/mw_com_setup/mw_com_receiver:mw_com_receiver
```

Or use the helper script to run receiver + producer together (generates
paths from a VSS JSON):

```bash
demo/mw_com_setup/scripts/run_full_demo.sh /path/to/SDV-Hack_vss.json
```

### 5. Run the KUKSA adapter (producer)

Default watched paths (`Vehicle.Speed`, `Vehicle.Powertrain.CombustionEngine.Speed`,
`Vehicle.Cabin.Door.Row1.Left.IsOpen`, `Vehicle.Powertrain.TractionBattery.StateOfCharge.Current`):

```bash
bazel run --config=linux-x86_64 //demo/mw_com_setup/kuksa_to_com:kuksa_to_com
```

Or watch any VSS paths, without changing code:

```bash
KUKSA_VSS_PATHS="Vehicle.Speed,Vehicle.VehicleIdentification.VIN,Vehicle.CurrentLocation.Latitude" \
bazel run --config=linux-x86_64 //demo/mw_com_setup/kuksa_to_com:kuksa_to_com
```

Or generate a full list of VSS leaf paths from a VSS JSON and point the
adapter at that file (recommended if you want to forward every defined
signal):

```bash
# generate a newline-separated list from your VSS JSON
python3 demo/mw_com_setup/scripts/extract_vss_paths.py /path/to/SDV-Hack_vss.json > /tmp/vss_paths.txt

# run the adapter reading paths from the file
KUKSA_VSS_PATHS_FILE=/tmp/vss_paths.txt \
bazel run --config=linux-x86_64 //demo/mw_com_setup/kuksa_to_com:kuksa_to_com
```

### Expected output

`kuksa_to_com`:

```text
offering VehicleInterface at /Vehicle/Service1/Instance; polling 4 KUKSA path(s) at Server:55555 via ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main every 500ms (Ctrl+C to stop)
Vehicle.Speed not available
published Vehicle.Speed = 88.80 km/h
```

`mw_com_receiver`:

```text
waiting for the KUKSA adapter to offer VehicleInterface...
subscribed to VehicleInterface.vss_signal (any VSS path), waiting for samples (Ctrl+C to stop)
Vehicle.Speed = 88.80 km/h
```

### Cleanup

```bash
docker stop Server
```

## Configuration knobs (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `KUKSA_VSS_PATHS` | the 4 defaults above | Comma-separated VSS paths to poll and publish |
| `KUKSA_SERVER` | `Server:55555` | KUKSA Databroker gRPC address, as seen from the CLI container |
| `KUKSA_DOCKER_NETWORK` | `kuksa` | Docker network the CLI container joins to reach the Databroker |
| `KUKSA_DATABROKER_CLI_IMAGE` | `ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main` | CLI image used for polling |
| `MW_COM_CONFIG_FILE` | `demo/mw_com_setup/kuksa_to_com/etc/mw_com_config.json` | Lola runtime manifest path (must match between both binaries) |

## Known limitations

- **Polling, not push.** `kuksa_to_com` spawns a Docker container per watched
  path per poll cycle (via the official CLI's `get` command) — this is a real
  gRPC client, but not a persistent subscription. It does not scale to
  watching hundreds of VSS paths at once. A future iteration should replace
  this with a native `tonic`/`prost` gRPC client using KUKSA's `Subscribe` RPC
  (push-based), which requires adding a Rust protobuf/gRPC codegen toolchain
  to this Bazel workspace — not yet set up here.
- **The Databroker must stay running.** If the `Server` container stops,
  every watched path reports "not available" until it is restarted.
- **Local only.** This demo does not yet include the SOME/IP gateway,
  `gatewayd`/`someipd`, or any external (REST/digital.auto) consumer. It
  proves the KUKSA → `mw::com` provider → `mw::com` → consumer path only.
