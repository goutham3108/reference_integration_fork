# Web-Based Application Deployment Plan

## Objective

Build an API-only application deployment server for Vehicle Pi A and a separate browser UI for the developer laptop. The laptop UI sends requests to the Pi over an SSH local port forward.

The server and its deployment artifacts remain isolated from the already-working S-CORE integration. The implementation lives in separate `pi-server/` and `laptop-ui/` folders.

## Existing Workspace Context

The current vehicle demo builds fixed Raspberry Pi archives and starts the gateway, bridge, KUKSA broker, and vehicle app through existing scripts. It has no general web upload or application deployment service.

The deployment manager is a separate tool with its own source, configuration, accounts, ports, storage, logs, service, and release archive. It will not be added to or alter the existing vehicle package, launchers, Bazel configuration, S-CORE repositories, or S-CORE service configuration. Uploaded applications may optionally communicate with S-CORE through existing interfaces, but the manager itself does not manage S-CORE.

## Proposed Architecture

- `pi-server/`: Python standard-library REST API, account tooling, restricted systemd controller, systemd units, and installer. No HTML, CSS, or JavaScript is shipped to the Pi.
- `laptop-ui/`: static HTML/CSS/JavaScript client with a configurable API base URL. The UI is served on the laptop and calls the Pi API through SSH local forwarding.
- Pi API binds to `127.0.0.1:8443`; the laptop SSH tunnel maps `localhost:18443` to that endpoint. CORS permits only the configured laptop UI origin and supports the HttpOnly session cookie.
- Package only the Pi server as `pi-server/dist/pi-deployment-server.tar.gz`. Python 3 and systemd are required; no native compilation step is needed.
- Dedicated `sdv-deployer` API account, `sdv-apps` workload account, protected account configuration, upload staging, deployed app/version storage, state, and logs.
- A root-owned helper can manage only deployment-owned app units. Uploaded workloads run as `sdv-apps`, not as root.
- Native AArch64 binaries and Python applications are supported in this implementation. Container/OCI packages are not yet accepted; they require a later runtime integration.

## Application Types Supported

1. **S-CORE Native Applications (`runtime: "native"`)**:
   - Compiled AArch64 C++ or Rust binaries interacting with S-CORE middleware.
   - Accesses `/dev/shm` to talk directly over `mw::com` (LoLa) shared-memory to `gatewayd` and local S-CORE services.
   - Includes binary, shared library runfiles, and local JSON configurations (such as `mw_com_config.json`).
2. **SDV Python Applications (`runtime: "python"`)**:
   - Python scripts/packages using the KUKSA client, gRPC, or vehicle abstraction libraries.
   - Connects to the local KUKSA Databroker over TCP/gRPC (`127.0.0.1:55555`) to read or actuate vehicle signals (e.g. `Vehicle.Speed`, `Vehicle.Body.Lights.Beam.High.IsOn`).
   - Runs in a managed Python virtual environment or system Python on the Pi.

## Target Environment & Capability Display in Web UI

To allow developers to verify version compatibility before uploading, the Web UI provides a live **Environment & Compatibility** panel:
- **Hardware & OS**: Target architecture (`aarch64`), kernel version (`uname -r`), OS distribution (`/etc/os-release`).
- **C/C++ Toolchain Baseline**: Target `glibc` version (`ldd --version`), available C++ standard library (`libstdc++.so.6`).
- **Python Environment**: Target Python version (`python3 --version`), installed packages and SDV client libraries.
- **Available S-CORE & SDV Middleware Services**:
   - KUKSA Databroker endpoint (`127.0.0.1:55555`) TCP reachability.
   - S-CORE `mw::com` / LoLa shared-memory status based on visible `/dev/shm` segments.
  - Runtime supervisors: `systemd` version and container runtime (`podman`) availability.

## Application State & Real-Time Logs in Web UI

After deployment, the Web UI provides an active management console:
- **Status Overview**: Real-time lifecycle state (`Active (Running)`, `Inactive (Stopped)`, or `Failed (Exited)`), process PID, uptime, and restart counts.
- **Version Tracking**: Currently running version, deployment timestamp, and previous known-good version available for rollback.
- **Logs**: Fetch recent stdout/stderr journal output for the selected application on request, including startup errors.
- **Control Actions**: Start, Stop, Restart, Roll Back, and Remove.

## Validation Benchmarks Before Activation

Every package uploaded must pass a 5-stage benchmark before it is promoted and executed:

1. **Archive Safety & Format**:
   - File format verified as valid `.tar.gz`.
   - File size enforced under max upload threshold (default 100 MB).
   - Strict archive traversal check: rejects any entry containing `../`, absolute paths (`/`), or symlinks resolving outside the staging folder.
2. **Manifest & Checksum Benchmark**:
   - `manifest.json` present and conforms to the bundle schema.
   - All required fields valid: `app_id` (alphanumeric/hyphen), `version` (semver), `runtime` (`native` | `python` | `container`), `entrypoint`.
   - SHA-256 checksums verified for every file in the package against manifest hashes.
3. **Architecture & Binary Compatibility Benchmark**:
   - For `native`: ELF header verification confirms `ELF 64-bit LSB` executable and machine type `EM_AARCH64`. Binaries for x86_64 or 32-bit ARM are rejected immediately. Dynamic dependencies checked against target `glibc` compatibility.
   - For `python`: Entrypoint syntax checked (`python3 -m py_compile`). Package dependencies checked against target Python version.
4. **Execution Permissions & Security Benchmark**:
   - Entrypoint confirmed to exist inside the bundle.
   - Executable permissions verified or set (`chmod +x`).
   - No `setuid`/`setgid` bits allowed.
5. **Startup Smoke Benchmark**:
   - Application is launched from staging as the non-root app user.
   - The process must survive the initial grace period (e.g. 3–5 seconds) without crashing or exiting nonzero.
   - If the startup smoke test fails, the deployment aborts, logs are captured for the developer in the UI, and the previous known-good version remains active.

## Features and Implementation Steps

1. **Define the bundle contract.** Specify the manifest schema, package layout, native/Python runtimes, size limits, and versioning rules. Include a sample bundle and manifest.
2. **Build the Pi API and laptop client separately.** The API handles login, upload/validation, environment inspection, app versions/status, logs, lifecycle, and rollback. The static laptop UI uses a configurable API base URL and the SSH tunnel; it is not served from the Pi package.
3. **Make uploads resilient.** Stream each upload into a unique staging path. Keep incomplete or invalid uploads inactive. Promote only validated packages using an atomic filesystem operation; report upload and validation errors clearly.
4. **Install and supervise applications.** Store versions in separate directories. Run the API as `sdv-deployer`; run app units as `sdv-apps`. A root-owned helper permits only deployment-owned unit operations. Install supplied runtime configuration with explicit permissions, expose lifecycle status and startup errors, and retain a previous known-good version for rollback if activation or smoke checks fail.
5. **Create separate deliverables.** Keep the laptop UI under `laptop-ui/`. Package only the API, auth/user tools, restricted controller, installer/uninstaller, config example, and systemd units from `pi-server/` into `pi-deployment-server.tar.gz`. No cross-compilation is required; Pi needs Python 3 and systemd. Do not alter existing workspace build/package/launch files.
6. **Document operation and automation.** Document Pi installation, SSH tunneling, account provisioning, package structure, browser workflow, REST API, CI/CD usage, security model, and troubleshooting.
7. **Verify in isolation.** Test locally, then install the separate archive on Pi A. Upload a sample app, exercise lifecycle and rollback, and prove that installing, stopping, restarting, or upgrading the manager does not change or restart any existing S-CORE process.

## API Capabilities

The authenticated REST API should support:

- Upload a bundle and retrieve validation/deployment results.
- List applications, versions, and current state.
- Retrieve application logs and startup/health-check errors.
- Start, stop, restart, remove, replace, and roll back applications.
- Upload or update runtime configuration alongside an application.

The separate laptop UI should expose the same essential workflows and display upload progress, validation errors, deployed version, running/stopped/failed status, and fetched logs.

## Security and Isolation Requirements

- Keep TLS keys and authentication tokens on the device, outside application bundles. Do not ship default production credentials.
- Authenticate deployment requests, authorize supported actions, and restrict network exposure to the intended interface.
- Do not run the HTTP server as root. Do not let uploaded manifests request arbitrary shell commands, arbitrary systemd units, or unrestricted host paths.
- Restrict the privileged lifecycle controller, if needed, to deployment-owned unit names and directories. It must not control S-CORE units.
- Use separate users and filesystem paths for the manager and uploaded workloads. Apply safe file permissions and avoid sharing S-CORE state or configuration.
- Manager installation, removal, restart, and upgrade must leave S-CORE processes, configuration, and existing demo packages untouched.
- Handle incomplete uploads, corrupted archives, checksum failures, disk-full conditions, invalid metadata, failed startup, and interrupted deployment without replacing the active known-good version.

## Repository Scope

All deployment project source and assets live under the workspace-root `web-server/` directory. The coworker handoff is `pi-server/`; the browser client stays separate in `laptop-ui/`. Do not modify existing S-CORE sources or demo launch/package files.

## Verification Checklist

- Validate manifest parsing, required fields, filenames, formats, versions, architecture, checksums, and metadata.
- Test archive traversal/link rejection, corrupted packages, oversized files, incomplete uploads, and concurrent uploads.
- Test authentication, authorization, HTTPS behavior, and error responses.
- Test start/stop/restart/remove, status/log retrieval, failed startup, version replacement, health checks, and rollback.
- Verify the Pi archive contains backend/service assets only and no laptop UI files.
- Install and upgrade the manager on Vehicle Pi A without reinstalling the vehicle demo archive.
- Verify existing gateway, broker, bridge, vehicle app, and KUKSA processes continue running through manager install, stop, restart, and upgrade.
- Confirm a sample application can be managed independently. Any optional connection from that app to S-CORE must use existing interfaces and require no S-CORE modifications.
