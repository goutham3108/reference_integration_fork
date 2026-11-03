# Optional SDV Runtime Patch

The committed runtime integration is a patch for another repository, not a tracked application checkout in this branch. This chapter documents only what its hunks establish; the local untracked runtime checkout and backup are not treated as delivered source.

## Purpose, location and boundaries

[sdv-runtime-mw-com.patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch) changes container defaults, syncer signal writes, broker selection and service supervision. It connects a containerized playground/kit runtime to the externally running broker; it does not replace gatewayd, the UDP bridge or remote hardware handling.

The patch modifies Dockerfile, README, `kuksa-syncer/syncer.py`, middleware/provider configuration snapshots, `start_services.sh`, and `test/test_signal_writes.py`. These are **patch target paths**, not independent tracked runtime source files.

## Implementation and visible rationale

The patch adds broker host/port configuration to the syncer:

```python
BORKER_IP = os.environ.get('KUKSA_DATABROKER_HOST', '127.0.0.1')
BROKER_PORT = int(os.environ.get('KUKSA_DATABROKER_PORT', '55555'))
```

Source: [runtime patch](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch), `kuksa-syncer/syncer.py` hunk. The spelling `BORKER_IP` is preserved from the code; it is not a separate user environment variable.

`writeSignalsValue` and associated command handling publish current values for writable signal types. With `MOCK_SIGNAL` empty, signal-watch writes go directly to the broker rather than starting mock behavior; with a mock file configured, mock configuration remains available. The added regression tests cover successful writes and failure replies.

Dockerfile hunks disable the bundled broker by default for the patched external-broker use case. `start_services.sh` selects `databroker` or `databroker-mw-com` (legacy alias `mw-com-dem-bin`) and reports/terminates sibling processes when a required child exits. Why: avoid leaving a superficially running container after its kit/broker process fails, as explained in the patch's README/supervision changes.

## Inputs, outputs and configuration

| Setting | Patch-defined role |
| --- | --- |
| `KUKSA_DATABROKER_HOST`, `KUKSA_DATABROKER_PORT` | External syncer broker destination |
| `DATABROKER_BACKEND` | Ordinary broker or composed middleware broker |
| `DISABLE_DATABROKER` | Skip bundled broker |
| `DATABROKER_ARGS` | Selected broker argument string |
| `KUKSA_DATABROKER_ADDR` | Bind address when building composed-broker default arguments |
| `MOCK_SIGNAL` | Empty means direct signal writes; filename retains mock mode |
| `RUNTIME_NAME`, `RUNTIME_PREFIX` | Runtime identification described by README hunks |
| `SYNCER_SERVER_URL` | Kit service destination described by README hunks |

Evidence: [Dockerfile, syncer, supervisor and README patch hunks](../../sdv-hack-demo/sdv-runtime/sdv-runtime-mw-com.patch). The **full unchanged base runtime environment/configuration is Unverified** because an exact tracked base revision is not recorded here.

## Dependencies and users

The patch assumes a compatible SDV runtime tree, Python KUKSA client dependencies, container tooling and reachable broker/API. The downstream KUKSA provider must support forwarding command-capable current-value writes; that behavior exists in [provider `start_command_forwarder`](../../kuksa-databroker/mw_com_provider/src/provider.rs).

The patch is not applied or built by [the demo ARM64 build script](../../sdv-hack-demo/build-aarch64.sh). The untracked runtime directories should not be mistaken for automatic build inputs.

## Testing and extension

**Unverified:** patch applicability against a clean upstream revision, container builds, syncer networking and the patch's Python test execution. Do not apply it blindly to the main integration worktree.

On a separately prepared matching runtime tree, inspect/apply the patch with a reviewable workflow, then run its new test:

```bash
# Unverified: only in the matching external runtime checkout after applying the patch.
python3 -m unittest discover -s test -p test_signal_writes.py
```

Add write-path tests whenever changing sensor/actuator semantics. Preserve explicit failure replies for invalid paths/values instead of acknowledging a command that the broker rejected.

## Limitations / debt

A patch without a pinned base is not a reproducible vendored component. The branch also carries provider/config snapshots in that patch, so runtime compatibility must be reviewed separately from the active demo snapshots.

## Related pages

[KUKSA](kuksa.md) | [Configuration](configuration.md) | [Changes in this Fork](fork-changes.md) | [Verification](verification.md)
