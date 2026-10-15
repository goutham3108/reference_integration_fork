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
scp dist/pi-deployment-server.tar.gz <pi-user>@<pi-ip>:/tmp/
ssh <pi-user>@<pi-ip>
cd /tmp
tar -xzf pi-deployment-server.tar.gz
cd pi-deployment-server
sudo bash deploy/install.sh
```

Run the installer with `sudo` from the regular user that should own the deployment (or set `SDV_USER=<user>`). The archive contains the API, auth/user tools, app runner, the systemd unit, and installer only. It contains no browser UI files. The installer:

- creates `/home/<user>/sdv-apps` (the deployment directory) and installs the API under `/opt/sdv-deployer`;
- installs `sdv-deployer.service`, which runs as `<user>` with `MemoryMax` and `CPUQuota` limits (default `512M` and `100%`; override with `SDV_MEMORY_MAX` and `SDV_CPU_QUOTA`, for example `sudo SDV_MEMORY_MAX=768M SDV_CPU_QUOTA=150% bash deploy/install.sh`);
- enables the service at boot and starts it, bound to `127.0.0.1:8443`.

Deployed applications are not separate services. The deployer starts each one as a normal process from `/home/<user>/sdv-apps/<app-id>/current/`, running as `<user>`, and writes its output to `/var/log/sdv-deployer/<app-id>.log`. `KillMode=process` lets running apps survive a restart of the deployer service. The service's CPU and memory limits apply to the deployer and the apps it starts together.

## Create browser users

On the Pi, create a browser account with:

```bash
python3 /opt/sdv-deployer/manage_users.py \
  --config /etc/sdv-deployer/config.json add developer@example.com
sudo systemctl restart sdv-deployer.service
```

Run the first command as the deployment user. The password is prompted interactively and stored only as a salted PBKDF2-HMAC-SHA256 hash in `/etc/sdv-deployer/config.json`, which is mode `0600`. The email is the account identifier. The browser receives only an HttpOnly session cookie.

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

- `POST /api/v1/login`, `GET /api/v1/session`, `POST /api/v1/logout`
- `GET /api/v1/environment` returns live data collected on the Pi
- `POST /api/v1/apps/upload` accepts application bundles
- `GET /api/v1/apps`, `GET /api/v1/apps/<id>`
- `POST /api/v1/apps/<id>/{start,stop,restart,rollback}`
- `DELETE /api/v1/apps/<id>`
- `GET /api/v1/apps/<id>/logs?lines=100` returns the last lines of the app's log file.

While the laptop UI's Logs view is open, it polls the selected app's log endpoint every two seconds and updates the log panel.

For CI, API clients may use the configured Bearer token. Browser sessions use email/password login and cookies.

Each upload request installs or updates one `app_id`. Multiple distinct IDs can be installed and run concurrently; uploading another version under an existing ID updates that app. The laptop UI sends selected bundles one at a time. Its Logs view can fetch one app or combine recent logs from all installed apps by requesting each app's log endpoint.

## Pi-side storage

- Configuration/accounts: `/etc/sdv-deployer/config.json`
- Application staging and state: `/var/lib/sdv-deployer/`
- Deployed applications and their versions: `/home/<user>/sdv-apps/<app-id>/`
- Service logs: systemd journal (`journalctl -u sdv-deployer.service`)
- Application logs: `/var/log/sdv-deployer/<app-id>.log`
