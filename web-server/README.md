# SDV Web-Based Application Deployment Server

A two-part, isolated application deployment tool for **Eclipse S-CORE** and **Software-Defined Vehicle (SDV)** targets. The API-only server runs on Raspberry Pi A; the browser UI runs on the developer laptop.

The laptop UI sends requests through an SSH local port forward to the Pi. The Pi reads its own environment, stages and validates uploaded packages, manages application services, and returns status and logs. The integration stack is not modified.

The coworker handoff is [`pi-server/`](pi-server/), which contains no UI assets. The laptop client is in [`laptop-ui/`](laptop-ui/).

---

## 🌟 Key Features

1. **Pi API Service**:
   Runs as an independent daemon (`sdv-deployer.service`), listening only on `127.0.0.1:8443` on Vehicle Pi A. Use the SSH tunnel for laptop access.
2. **Supported Application Types**:
   - **1] S-CORE Native Applications (`runtime: "native"`)**: AArch64 C++/Rust binaries that communicate over `mw::com` (LoLa shared memory in `/dev/shm`) directly to `gatewayd` and local S-CORE middleware.
   - **2] SDV Python Applications (`runtime: "python"`)**: Python scripts/packages that interact with the KUKSA Databroker (`127.0.0.1:55555`) via VAL v2 gRPC to read and actuate vehicle signals (e.g. `Vehicle.Speed`, `Vehicle.Body.Lights.Beam.High.IsOn`).
3. **Live Environment & Dependency Display**:
   The UI calls the Pi's environment API only when the user selects **Get info**. Architecture, OS, kernel, `glibc`, `g++` version, Python, supervisor, and visible LoLa segments are inspected by the server at request time. KUKSA running status is detected from local Databroker processes. If the request fails, old values are cleared and the UI shows the error.
4. **Active Application State & Real-Time Logs**:
   Dashboard showing running status (`active`, `stopped`, `failed`), PID, uptime, version tracking, startup error capture, live rolling `journald` log output, and one-click rollback to the previous known-good version.
5. **5-Stage Pre-Activation Benchmark Pipeline**:
   Every uploaded package is statically and dynamically benchmarked before it is permitted to run.

---

## 🛡️ 5-Stage Pre-Deployment Benchmarks

Before any application package is promoted or executed on the Raspberry Pi, it must pass five automated benchmarks:

```
  ┌─────────────────────────────────────────────────────────────┐
  │ 1. Archive Safety Benchmark                                 │
  │    - Valid .tar.gz format & size under 100 MB               │
  │    - Rejection of path traversal (../), leading /, symlinks │
  └──────────────────────────────┬──────────────────────────────┘
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 2. Manifest & Checksum Benchmark                            │
  │    - Schema validation (app_id, version, runtime, entry)    │
  │    - SHA-256 verification of every packaged file            │
  └──────────────────────────────┬──────────────────────────────┘
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 3. Architecture & Compatibility Benchmark                   │
  │    - Native: ELF header validation (EM_AARCH64 64-bit LSB)  │
  │    - Python: Syntax compilation (py_compile) & deps check   │
  └──────────────────────────────┬──────────────────────────────┘
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 4. Execution Permissions & Security Benchmark               │
  │    - No setuid / setgid bits allowed                        │
  │    - Entrypoint existence & chmod +x applied                │
  └──────────────────────────────┬──────────────────────────────┘
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 5. Startup Smoke Benchmark                                  │
  │    - Staging launch with 3-second grace window              │
  │    - Immediate crash detection, stderr capture & abort      │
  │    - Retention of previous known-good version on failure    │
  └─────────────────────────────────────────────────────────────┘
```

---

## 📦 Package Bundle Specification

Applications are packaged as standard `.tar.gz` archives with a root `manifest.json`:

```json
{
  "app_id": "vehicle-speed-reader",
  "name": "S-CORE Vehicle Speed Reader",
  "version": "1.0.0",
  "description": "Reads vehicle speed from S-CORE mw::com shared memory",
  "runtime": "native",
  "entrypoint": "vehicle_speed_reader",
  "target_architecture": "aarch64",
  "author": "Eclipse S-CORE SDV Team",
  "checksums": {
    "vehicle_speed_reader": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}
```

### Example Packages Provided

- [examples/sample_score_app](examples/sample_score_app/): S-CORE native C binary reading `/dev/shm` dynamics.
- [examples/sample_sdv_python_app](examples/sample_sdv_python_app/): Python application reading `Vehicle.Speed` and toggling `Vehicle.Body.Lights.Beam.High.IsOn` on KUKSA (`127.0.0.1:55555`).
- [examples/hello-app](examples/hello-app/): independent Python heartbeat app for multi-app deployment and per-app live-log testing. Build it with `bash web-server/examples/hello-app/build_bundle.sh`.

---

## Quick Start: Pi Server and Laptop UI

### Test the UI locally before the Pi is available

This starts a local copy of the API on port `18443` and the laptop UI on port `8080`. It exercises login, navigation, upload, and API behavior, but **Get info reports the development machine (for example WSL), not the Pi**.

In terminal 1:

```bash
cp web-server/pi-server/config.example.json /tmp/sdv-deployer-local.json
python3 web-server/pi-server/manage_users.py \
   --config /tmp/sdv-deployer-local.json add demo@example.com
SDV_DEPLOYER_PORT=18443 python3 web-server/pi-server/server.py /tmp/sdv-deployer-local.json
```

In terminal 2:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory web-server/laptop-ui
```

Open `http://localhost:8080`. Use the email and password created by the account command. The existing Python sample bundle is at `web-server/examples/sample_sdv_python_app/kuksa-high-beam-controller-1.0.0.tar.gz`.

Stop each local process with `Ctrl+C` in its terminal. To see real Pi environment and logs, use the Pi installation and SSH tunnel instructions below instead.

### Package and install the Pi-only server

On the build/workspace host:

```bash
cd web-server/pi-server
bash package.sh
scp dist/pi-deployment-server.tar.gz <pi-user>@<pi-ip>:/tmp/
ssh <pi-user>@<pi-ip>
tar -xzf /tmp/pi-deployment-server.tar.gz
sudo bash pi-deployment-server/deploy/install.sh
```

This installs the API, account tool, runner, and systemd units on the Pi. The server binds to `127.0.0.1:8443`; it does not include or serve the laptop UI and does not modify S-CORE source or launch configuration.

### Create a browser account on the Pi

```bash
sudo python3 /opt/sdv-deployer/manage_users.py \
   --config /etc/sdv-deployer/config.json add developer@example.com
```

Enter a password when prompted, then restart the service:

```bash
sudo systemctl restart sdv-deployer.service
```

The email is stored as the account identifier. The password is stored only as a salted PBKDF2-HMAC-SHA256 hash in `/etc/sdv-deployer/config.json` (mode `0600`); plaintext is not saved. CI Bearer credentials are stored separately in that Pi-side config.

### Open the laptop UI through SSH

Keep this tunnel running on the laptop:

```bash
ssh -N -L 18443:127.0.0.1:8443 <pi-user>@<pi-ip>
```

In a second laptop terminal, from the workspace root:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory web-server/laptop-ui
```

Open `http://localhost:8080` and sign in with the account provisioned on the Pi. `laptop-ui/config.js` points the client to `http://localhost:18443`; update both that setting and the Pi's `allowed_origins` if you use different local ports.

The four menu sections are Target Environment & Compatibility, Upload & Validate Application Package, Application Logs & Diagnostics, and Deployed Applications. **Get info** explicitly requests live data from the Pi. Uploads go to the Pi for staging, validation, extraction, and launch; the selected application's logs refresh every two seconds while its Logs view is open.

---

## 📡 REST API Reference (for CI/CD & Automation)

REST automation requests require `Authorization: Bearer <token>`. Browser users instead sign in with a provisioned email/password account; passwords are stored as salted PBKDF2 hashes.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/environment` | Returns live target hardware, kernel, glibc, Python, KUKSA, and LoLa SHM status |
| `POST` | `/api/v1/apps/upload` | Upload `.tar.gz` package (multipart or raw stream), executes 5 benchmarks, and activates |
| `GET` | `/api/v1/apps` | List all deployed applications with status, active version, uptime, PID |
| `GET` | `/api/v1/apps/:id` | Get details and metadata for a specific application |
| `POST` | `/api/v1/apps/:id/start` | Start application |
| `POST` | `/api/v1/apps/:id/stop` | Stop application |
| `POST` | `/api/v1/apps/:id/restart` | Restart application |
| `POST` | `/api/v1/apps/:id/rollback` | Roll back to previous known-good version |
| `DELETE` | `/api/v1/apps/:id` | Stop and completely remove application |
| `GET` | `/api/v1/apps/:id/logs?lines=100` | Stream application stdout/stderr and journald logs |

### Example: Upload from CI/CD Pipeline

```bash
curl -X POST http://localhost:18443/api/v1/apps/upload \
   -H "Authorization: Bearer <ci-api-token>" \
  -F "package=@kuksa-high-beam-controller-1.0.0.tar.gz"
```


---

## 🧪 Running the Test Suite

From the `web-server` directory:

```bash
bash tests/run_tests.sh
```

Validates:
- Traversal attack rejection
- Corrupt archive rejection
- Checksum integrity matching
- ELF architecture matching
- Python syntax compilation
- Startup smoke test crash detection
- REST API lifecycle, environment, authentication, and rollback
