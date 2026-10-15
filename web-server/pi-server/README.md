# Raspberry Pi Deployment API Server

API-only service for the Raspberry Pi. It does not include or serve the browser UI.

## Requirements

- Raspberry Pi OS or another supported Linux image with Python 3.10 or newer.
- systemd for application supervision.
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

The archive contains the API, auth/user tools, app runner, systemd units, and installer only. It contains no browser UI files. The installer creates separate `sdv-deployer` and `sdv-apps` accounts, installs the API under `/opt/sdv-deployer`, and starts the API bound to `127.0.0.1:8443`.

The API process runs as `sdv-deployer`. A root-owned helper and narrow sudoers rule allow only lifecycle actions on `sdv-app@<id>.service` units. Uploaded applications run as the non-root `sdv-apps` user. The Pi package contains the API and deployment assets only; it does not contain the laptop UI.

## Create browser users

On the Pi, create a browser account with:

```bash
sudo -u sdv-deployer python3 /opt/sdv-deployer/manage_users.py \
  --config /etc/sdv-deployer/config.json add developer@example.com
sudo systemctl restart sdv-deployer.service
```

The password is prompted interactively and stored only as a salted PBKDF2-HMAC-SHA256 hash in `/etc/sdv-deployer/config.json`, which is mode `0600`. The email is the account identifier. The browser receives only an HttpOnly session cookie.

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
- `GET /api/v1/apps/<id>/logs?lines=100` returns recent journal entries, falling back to the process-runner log file when no journal entries exist.

While the laptop UI's Logs view is open, it polls the selected app's log endpoint every two seconds and updates the log panel.

For CI, API clients may use the configured Bearer token. Browser sessions use email/password login and cookies.

Each upload request installs or updates one `app_id`. Multiple distinct IDs can be installed and run concurrently; uploading another version under an existing ID updates that app. The laptop UI sends selected bundles one at a time. Its Logs view can fetch one app or combine recent logs from all installed apps by requesting each app's log endpoint.

## Pi-side storage

- Configuration/accounts: `/etc/sdv-deployer/config.json`
- Application staging, versions, and state: `/var/lib/sdv-deployer/`
- Service logs: systemd journal (`journalctl -u sdv-deployer.service`)
- Application logs: systemd journal units `sdv-app@<app-id>.service`
