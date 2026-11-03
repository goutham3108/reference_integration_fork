# Platform Images, Runners and Showcases

The inherited platform integration packages examples into Linux/QNX-oriented images and supplies Docker/QEMU launchers. It is a parallel integration surface to the Raspberry Pi demo, not an automatic production deployment path for that demo.

## Purpose and location

[images](../../images) contains image assembly definitions; [runners](../../runners) contains execution helpers; [showcases](../../showcases) contains packaged applications/configuration. [score_starter](../../score_starter), `main`, is an interactive or `--run` dispatcher into the platform `:run` targets.

These components do not manage the demo's route-generation model or broker command ownership.

## Implementation and entry points

The dispatcher stores description/command/name triples:

```python
(
    "Run Linux x86_64 Docker",
    "bazel --output_base=build/linux-x86_64 run --config linux-x86_64  //images/linux_x86_64:run",
    "linux-x86_64",
),
```

Source: [score_starter](../../score_starter), `mEntries`. `run_entry` executes the selected command and returns its exit status; the interactive loop restores terminal state after key reads.

| Platform | Target/config source | Runner |
| --- | --- | --- |
| Linux x86_64 | [images/linux_x86_64/BUILD](../../images/linux_x86_64/BUILD) | [Docker runner](../../runners/docker_x86_64) |
| AutoSD x86_64 | [images/autosd/BUILD.bazel](../../images/autosd/BUILD.bazel) | Docker-oriented image run target |
| QNX x86_64 | [images/qnx_x86_64/BUILD](../../images/qnx_x86_64/BUILD) | [QEMU x86_64](../../runners/qemu_x86_64) |
| QNX AArch64 | [images/qnx_aarch64/BUILD](../../images/qnx_aarch64/BUILD) | [QEMU AArch64](../../runners/qemu_aarch64) |
| Elektrobit corbos Linux for Safety Applications AArch64 | [images/ebclfsa_aarch64/BUILD](../../images/ebclfsa_aarch64/BUILD) | AArch64 QEMU/image helper scripts |

The [showcases bundle](../../showcases/BUILD), `showcases`, includes CLI, demo vehicle app and standalone communication/kyron/time/logging/config-management/lifecycle package inputs. Example configuration and lifecycle signal scripts live alongside the corresponding [simple_lifecycle](../../showcases/simple_lifecycle) and [standalone](../../showcases/standalone) targets.

## Inputs, dependencies and outputs

Inputs include external platform modules, OS image/toolchain artifacts, packaged binaries and configuration overlays. Outputs and runtime commands are defined per-image BUILD; runners use Docker/QEMU and platform networking helpers rather than the two-Pi UDP launcher ([image definitions](../../images), [runner scripts](../../runners)).

Configuration comes from root [.bazelrc](../../.bazelrc), platform-specific image configs and optional SDK credentials/toolchain setup. QNX-specific credential helper wiring is present in `.bazelrc`; credentials are not documented or printed here.

## Error behavior and edge cases

`score_starter` requires terminal behavior for interactive mode and exits with the subprocess status. SDK/image resolution, container privileges and QEMU networking can fail before an app starts. **Unverified:** actual platform image buildability or host prerequisites beyond source-defined tool/config references.

Why separate output bases? The dispatcher explicitly uses one `build/<platform>` path per selected platform. Isolation is observable; a stronger performance/correctness rationale is **Unverified** because the dispatcher does not explain it.

## Testing and modification

```bash
# Unverified: may build/download artifacts and start containers.
./score_starter --run linux-x86_64
```

Do not execute platform launch commands in a shared host without reviewing network/privilege effects. For a new platform, follow [the existing platform integration process](../../docs/integration_process/step_4_platforms.rst), add image and runner rules, wire the dispatcher/CI, and test the resulting packaged showcase rather than only compiling its source.

The [feature integration framework](../../feature_integration_tests/README.md) includes QEMU-based tests and remote-logging/SSH/showcase checks; they were not run for this documentation task.

## Limitations / debt

Platform targets mix proprietary SDK requirements and public dependencies. The exact platform/container images were not executed; do not treat an existing `:run` target or historical verification report as evidence of this branch passing on that platform.

## Related pages

[Workspace](workspace.md) | [Repository Tour](repository-tour.md) | [Build, Run and Deploy](build-run-deploy.md) | [Testing and CI](testing-ci.md)
