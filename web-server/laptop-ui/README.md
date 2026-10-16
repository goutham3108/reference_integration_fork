# Laptop Deployment UI

This folder is the browser client only. The deployment API runs on the Raspberry Pi.

1. Start the Pi API and keep an SSH local-forward open:
   `ssh -N -L 18443:127.0.0.1:8443 <pi-user>@<pi-ip>`
2. From the workspace root, serve this folder on the laptop:
   `python3 -m http.server 8080 --bind 127.0.0.1 --directory web-server/laptop-ui`
3. Open `http://localhost:8080`. There is no sign-in; access is controlled by the SSH login to the Pi.

Set `apiBaseUrl` in `config.js` if the local forwarded port changes. UI API calls, including environment, uploads, lifecycle actions, and logs, are sent to that API URL.

The upload picker accepts multiple `.tar.gz`/`.tgz` bundles and deploys them sequentially. Give each separate application a unique `app_id`; uploading another version with the same ID updates that application. The Deployed Applications view lists all installed IDs.

In Application Logs, choose one application from the selector. Its recent logs load immediately and refresh every two seconds while the Logs view is open. Choosing another application switches the live log feed.
