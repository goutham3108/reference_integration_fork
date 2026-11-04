# Raspberry Pi Deployment API Server

API-only service for the Raspberry Pi. It does not include or serve the browser UI.

## Requirements

- Raspberry Pi OS or another supported Linux image with Python 3.10 or newer.
- systemd to run the deployer as a service.
- SSH access from the developer laptop.

The server uses the Python standard library; no Python package installation or compilation is required.

## Build and install the server-only package

On the build host, from this folder:

```bash
bash package.sh
target="<pi-user>@<pi-ip>"
work="$(ssh "$target" 'mktemp -d /tmp/sdv-deployer.XXXXXXXXXX')"
scp dist/pi-deployment-server.tar.gz "$target:$work/"
ssh -t "$target" "cd '$work' && tar -xzf pi-deployment-server.tar.gz && cd pi-deployment-server && sudo bash deploy/install.sh"
```

Copy and extraction use a private remote directory rather than predictable shared `/tmp` paths. Remove that specific temporary directory after installation.

Run the installer with `sudo` from the regular user that should own the deployment (or set `SDV_USER=<user>`). The archive contains the API, auth/user tools, app runner, the systemd unit, and installer only. It contains no browser UI files. The installer:

- creates `/home/<user>/sdv-apps` (the deployment directory) and installs the API under `/opt/sdv-deployer`;
- installs `sdv-deployer.service`, which runs as `<user>` with `MemoryMax` and `CPUQuota` limits (default `512M` and `100%`; override with `SDV_MEMORY_MAX` and `SDV_CPU_QUOTA`, for example `sudo SDV_MEMORY_MAX=768M SDV_CPU_QUOTA=150% bash deploy/install.sh`);
- enables the service at boot and starts it, bound to `127.0.0.1:8443`.

The installer keeps an existing configured `apps_dir` on upgrades, provided it is inside the service user's home or `/var/lib/sdv-deployer`; it does not switch existing installations to a new empty directory. Configuration is updated atomically with explicit root/group-readable permissions, independent of the caller's umask. Both the configuration and data parent directories are root-owned; staging and log directories are opened without following symlinks before applying ownership and permissions.

Deployed applications are not separate services. The deployer starts each one from `<apps_dir>/<app-id>/current/`, running as `<user>`, and writes its output to `/var/log/sdv-deployer/<app-id>.log`. App process groups are recorded per application so Stop and Remove target the app and its descendants without matching unrelated processes. `KillMode=process` lets installed apps survive a service restart. Smoke-test groups are separately recorded, cleaned on service stop, and recovered at the next startup. The service's CPU and memory limits apply to the deployer and the apps it starts together.

## Laptop connection using SSH

Keep the tunnel open in one laptop terminal:

```bash
ssh -N -L 18443:127.0.0.1:8443 <pi-user>@<pi-ip>
```

In another laptop terminal, serve the browser UI from the workspace's `web-server/laptop-ui/` directory:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory web-server/laptop-ui
```

Open `http://localhost:8080`. The UI calls the Pi API through `http://localhost:18443`. Do not expose port 8443 on the Pi's network interface; the SSH tunnel provides the encrypted laptop-to-Pi connection.

## API endpoints

- `GET /api/v1/environment` returns live data collected on the Pi
- `POST /api/v1/apps/upload` accepts application bundles
- `GET /api/v1/apps`, `GET /api/v1/apps/<id>`
- `POST /api/v1/apps/<id>/{start,stop,restart,rollback}`
- `DELETE /api/v1/apps/<id>`
- `GET /api/v1/apps/<id>/logs?lines=100` returns the last lines of the app's log file.

While the laptop UI's Logs view is open, it polls the selected app's log endpoint every two seconds and updates the log panel.

There is no sign-in. The API accepts requests from the configured UI origins (`allowed_origins`) or with the configured Bearer token (`Authorization: Bearer <auth_token>`), and reaches only through the SSH tunnel.

Each upload request installs or updates one `app_id`. Multiple distinct IDs can be installed and run concurrently; uploading a new version under an existing ID keeps the previous version for Rollback. Installed version directories are immutable, so uploading an already-installed version is rejected. Archives are limited to 100 MB compressed, 512 MB expanded, and 10,000 regular-file/directory members. The laptop UI sends selected bundles one at a time. Its Logs view can fetch one app or combine recent logs from all installed apps by requesting each app's log endpoint.

## Pi-side storage

- Configuration: `/etc/sdv-deployer/config.json`
- Application staging and state: `/var/lib/sdv-deployer/`
- Deployed applications and their versions: `<apps_dir>/<app-id>/` (new installs default to `/home/<user>/sdv-apps/`)
- Service logs: systemd journal (`journalctl -u sdv-deployer.service`)
- Application logs: `/var/log/sdv-deployer/<app-id>.log`
