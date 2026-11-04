#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist="${root}/dist"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

package="${staging}/pi-deployment-server"
mkdir -p "$package/deploy" "$dist"
cp "$root/server.py" "$root/runner.py" "$root/config.example.json" "$package/"
cp "$root/README.md" "$package/README.md"
cp "$root/deploy/install.sh" "$root/deploy/uninstall.sh" "$root/deploy/sdv-deployer.service" "$package/deploy/"
chmod +x "$package/deploy/install.sh" "$package/deploy/uninstall.sh"
tar -czf "$dist/pi-deployment-server.tar.gz" -C "$staging" pi-deployment-server
printf 'Pi-only package created: %s\n' "$dist/pi-deployment-server.tar.gz"
