# SDV Application Deployment Manager

Deploy and run applications on a Raspberry Pi from a browser. The Pi runs a small API service; the UI runs on your laptop and reaches the Pi through an SSH tunnel. Nothing in the S-CORE sources is modified.

```
 Laptop browser ──> UI (localhost:8080) ──> SSH tunnel (localhost:18443) ──> Pi API (127.0.0.1:8443)
```

| Folder | Runs on | Purpose |
|---|---|---|
| `pi-server/` | Pi | API service, installer, account tool |
| `laptop-ui/` | Laptop | Browser UI (static files) |
| `scripts/` | Both | `pi_setup.sh` (Pi), `launch_ui.sh` (laptop), `install_on_pi.sh`, `e2e_pi_test.py` |
| `examples/` | Laptop | Sample app bundles |
| `tests/` | Laptop | Unit and API tests |

**How it behaves on the Pi**

- The deployer is one systemd service, `sdv-deployer.service`. It runs as your Pi user, starts at boot, and has a memory and CPU limit (default `512M`, `100%`).
- Apps are plain processes started by the deployer, not separate services. Each app lives in `/home/<user>/sdv-apps/<app-id>/` and logs to `/var/log/sdv-deployer/<app-id>.log`.
- The service limit covers the deployer and its apps together.
- Running apps survive a restart of the deployer.
- Apps do not start by themselves after a Pi reboot. Press Start in the UI.

Requirements: Pi with Python 3.10+, `aarch64`, systemd, SSH access. Laptop with `python3` and `ssh`.

---

## 1. Build the package (laptop)

Run from the repository root.

```bash
bash web-server/pi-server/package.sh
bash web-server/examples/hello-app/build_bundle.sh
bash web-server/examples/sample_sdv_python_app/build_sample_bundle.sh
```

This creates the Pi package `web-server/pi-server/dist/pi-deployment-server.tar.gz` and two sample apps.

## 2. Install on the Pi

Copy the package and the setup script, then run it as your normal user (not root).

```bash
scp web-server/scripts/pi_setup.sh web-server/pi-server/dist/pi-deployment-server.tar.gz <pi-user>@<pi-ip>:~
ssh <pi-user>@<pi-ip>
bash pi_setup.sh
```

The script checks the Pi is `aarch64`, installs or upgrades the service, shows the status, and asks for an email and password if no login exists. Type the password at the prompt.

Other commands:

```bash
bash pi_setup.sh status      # service state, limits, apps, logins
bash pi_setup.sh adduser     # add or replace a login
bash pi_setup.sh /path/to/pi-deployment-server.tar.gz   # install from another location
```

Change the limits at install time (run from the extracted `pi-deployment-server/` folder):

```bash
sudo SDV_MEMORY_MAX=768M SDV_CPU_QUOTA=150% bash deploy/install.sh
```

Manual install, without the script:

```bash
scp web-server/pi-server/dist/pi-deployment-server.tar.gz <pi-user>@<pi-ip>:/tmp/
ssh <pi-user>@<pi-ip>
cd /tmp && tar -xzf pi-deployment-server.tar.gz && cd pi-deployment-server
sudo bash deploy/install.sh
python3 /opt/sdv-deployer/manage_users.py --config /etc/sdv-deployer/config.json add <email>
sudo systemctl restart sdv-deployer.service
```

## 3. Launch the UI (laptop)

```bash
bash web-server/scripts/launch_ui.sh <pi-user>@<pi-ip>
```

It opens the SSH tunnel, serves the UI, and tries to open `http://localhost:8080`. Press Ctrl+C to stop both. Ports 8080 and 18443 must be free. Use `localhost` or `127.0.0.1` for the UI address; other hosts are rejected by the Pi.

Manual equivalent, in two terminals:

```bash
ssh -N -L 18443:127.0.0.1:8443 <pi-user>@<pi-ip>
python3 -m http.server 8080 --bind 127.0.0.1 --directory web-server/laptop-ui
```

## 4. Use the UI

1. **Sign in** with the email and password created on the Pi.
2. **Target Environment**: click **Get info** to read the Pi's architecture, OS, kernel, glibc, `g++`, Python and KUKSA status.
3. **Upload & Validate**: choose one or more `.tar.gz` bundles and click **Validate & Deploy**. Each bundle goes through 5 checks and is started if all pass.
4. **Logs**: choose one app. The log follows new lines every 2 seconds.
5. **Deployed Applications**: Stop, Start, Restart, Rollback or Remove each app.

Each app needs a unique `app_id`. Uploading an existing ID updates that app and keeps the previous version for Rollback.

---

## Application bundle

A `.tar.gz` with a `manifest.json` at its root:

```json
{
  "app_id": "pi-heartbeat-monitor",
  "name": "Pi Heartbeat Monitor",
  "version": "1.0.0",
  "runtime": "python",
  "entrypoint": "pi_heartbeat.py",
  "target_architecture": "aarch64",
  "checksums": { "pi_heartbeat.py": "<sha256 of the file>" }
}
```

| Field | Meaning |
|---|---|
| `runtime` | `python` or `native` (an AArch64 ELF binary) |
| `entrypoint` | File to run, relative to the bundle root |
| `checksums` | SHA-256 of each listed file, verified on the Pi |

Create one:

```bash
sha256sum pi_heartbeat.py                       # put the value in manifest.json
tar -czf pi-heartbeat-monitor-1.0.0.tar.gz manifest.json pi_heartbeat.py
```

Samples: `examples/hello-app` (Python heartbeat), `examples/sample_sdv_python_app` (KUKSA demo), `examples/sample_score_app` (native, x86-64 only; it fails the Pi's architecture check).

## Validation (done by the Pi, shown by the UI)

| Stage | Checks |
|---|---|
| 1. Archive safety | Valid tar, under 100 MB, no `..`, absolute paths or unsafe links |
| 2. Manifest and checksums | Required fields, valid `app_id` and runtime, SHA-256 of every listed file |
| 3. Compatibility | Native: AArch64 ELF header. Python: syntax compiles |
| 4. Permissions and security | No setuid/setgid bits, entrypoint made executable |
| 5. Startup smoke test | App runs for 3 seconds without crashing |

If a stage fails, the UI shows the reason on that row and marks the later stages "Not run". Nothing is installed.

---

## Check the Pi by hand

```bash
systemctl status sdv-deployer.service --no-pager
systemctl show sdv-deployer -p User -p MemoryMax -p CPUQuotaPerSecUSec
journalctl -u sdv-deployer.service -n 50 --no-pager
ls /home/<pi-user>/sdv-apps/
ps -eo pid,user,args | grep -E "pi_heartbeat|high_beam" | grep -v grep
tail -f /var/log/sdv-deployer/<app-id>.log
sudo systemctl restart sdv-deployer.service
```

| Item | Location |
|---|---|
| Installed server | `/opt/sdv-deployer/` |
| Config and logins | `/etc/sdv-deployer/config.json` (mode `0600`, passwords stored as salted PBKDF2 hashes) |
| Deployed apps | `/home/<pi-user>/sdv-apps/<app-id>/` |
| Upload staging | `/var/lib/sdv-deployer/staging/` |
| App logs | `/var/log/sdv-deployer/<app-id>.log` |

Remove the server and stop its apps (config and app files are kept):

```bash
sudo bash /tmp/pi-deployment-server/deploy/uninstall.sh
```

---

## Test

Without a Pi, on the laptop (Get info then shows the laptop, not a Pi):

```bash
cp web-server/pi-server/config.example.json /tmp/sdv-local.json
python3 web-server/pi-server/manage_users.py --config /tmp/sdv-local.json add demo@example.com
SDV_DATA_DIR=/tmp/sdv-local-data SDV_DEPLOYER_PORT=18443 python3 web-server/pi-server/server.py /tmp/sdv-local.json
python3 -m http.server 8080 --bind 127.0.0.1 --directory web-server/laptop-ui     # second terminal
```

Automated tests:

```bash
bash web-server/tests/run_tests.sh
```

Against the real Pi, with the tunnel open (deploys both samples, reads logs, stops, restarts and removes them):

```bash
python3 web-server/scripts/e2e_pi_test.py --email <email>
```

---

## REST API

Browser users sign in with email and password (session cookie). Automation can use `Authorization: Bearer <auth_token>` from the Pi config.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/login`, `/api/v1/logout` | Sign in and out |
| `GET` | `/api/v1/session` | Current session |
| `GET` | `/api/v1/environment` | Live data from the Pi |
| `POST` | `/api/v1/apps/upload` | Upload, validate and start a bundle |
| `GET` | `/api/v1/apps`, `/api/v1/apps/<id>` | List apps, or one app |
| `POST` | `/api/v1/apps/<id>/{start,stop,restart,rollback}` | Control an app |
| `DELETE` | `/api/v1/apps/<id>` | Stop and remove an app |
| `GET` | `/api/v1/apps/<id>/logs?lines=100` | Last lines of the app log |

```bash
curl -X POST http://127.0.0.1:18443/api/v1/apps/upload \
  -H "Authorization: Bearer <auth_token>" \
  --data-binary @pi-heartbeat-monitor-1.0.0.tar.gz -H "Content-Type: application/gzip"
```

## Limitations

- The KUKSA status is "a Databroker process is running" on the Pi. It does not prove an app is connected to it.
- Containers are not supported; apps are Python scripts or native AArch64 binaries.
- Apps run as your Pi user, so they can access everything that user can.
- The API listens only on `127.0.0.1:8443`. Always reach it through the SSH tunnel.
