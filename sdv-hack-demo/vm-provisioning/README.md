VM Provisioning (QEMU) for Raspberry Pi / ARM64 VMs
=================================================

This folder contains scripts and templates to create two ARM64 VMs (Raspberry-Pi-like) using QEMU + Ubuntu cloud images, with bridged networking so the VMs can talk to each other and your host/WSL.

Requirements (host)
- A native Linux host with sudo access.
- Packages: `qemu-system-aarch64`, `qemu-img`, `cloud-image-utils` (cloud-localds), `iproute2`, `bridge-utils`, `dnsmasq`.

```bash
sudo apt update
sudo apt install -y qemu-system-arm qemu-system-aarch64 qemu-utils cloud-image-utils iproute2 bridge-utils dnsmasq
```

First-time setup
----------------

```bash
cd sdv-hack-demo/vm-provisioning
chmod +x create-vms.sh setup-bridge.sh vm1-launch.sh vm2-launch.sh start-vms.sh

# downloads base image, creates vm1.qcow2/vm2.qcow2 and cloud-init ISOs
./create-vms.sh
```

Start everything (bridge + DHCP + both VMs)
--------------------------------------------

```bash
cd sdv-hack-demo/vm-provisioning

# 1. create br0 + taps and start dnsmasq (DHCP-only, range 192.168.100.100-200)
sudo ./setup-bridge.sh --dhcp

# 2. boot both VMs in background; each prints its IP once DHCP completes (~30-60s)
BACKGROUND=1 nohup ./vm1-launch.sh > /tmp/vm1-launch.log 2>&1 &
disown
BACKGROUND=1 nohup ./vm2-launch.sh > /tmp/vm2-launch.log 2>&1 &
disown

# 3. after ~45s, check assigned IPs
cat /tmp/dnsmasq-br0.leases
```

Each line in the leases file is: `<timestamp> <mac> <ip> <hostname> <client-id>`.
- VM1 MAC: `52:54:00:12:34:01`
- VM2 MAC: `52:54:00:12:34:02`

Verified working example IPs (yours may differ — always check the leases file):
- VM1: `192.168.100.175`
- VM2: `192.168.100.176`

SSH in (password: `ubuntu`, user: `ubuntu`):

```bash
ssh ubuntu@192.168.100.175   # VM1 (use your actual leased IP)
ssh ubuntu@192.168.100.176   # VM2 (use your actual leased IP)
```

Checking status
----------------

```bash
# qemu processes
ps aux | grep qemu-system-aarch64 | grep -v grep

# bridge / taps
ip addr show br0
ip neigh show dev br0

# dnsmasq process + logs
pgrep -af dnsmasq
tail -f /tmp/dnsmasq-br0.log

# reachability
ping -c 3 192.168.100.173
nc -zv 192.168.100.173 22
```

Stopping / killing the VMs
---------------------------

```bash
# stop both VMs
pkill -f qemu-system-aarch64

# stop dnsmasq (DHCP server for br0)
sudo pkill -f "dnsmasq --conf-file=/tmp/dnsmasq-br0.conf"

# optional: tear down the bridge and taps entirely
sudo ip link set br0 down 2>/dev/null
sudo ip link del br0 2>/dev/null
sudo ip link del tap-vm1 2>/dev/null
sudo ip link del tap-vm2 2>/dev/null
```

Restart later: just re-run the "Start everything" commands above (no need to re-run `create-vms.sh` unless you want a clean disk).

Reset a VM to a clean state
----------------------------

If a VM's disk gets into a bad state (e.g. broken network config baked in after first boot), recreate its qcow2 from the base image instead of editing a running VM:

```bash
pkill -f qemu-system-aarch64
IMG="$(pwd)/images/ubuntu-22.04-server-cloudimg-arm64.img"
rm -f images/vm1.qcow2
qemu-img create -f qcow2 -b "$IMG" -F qcow2 images/vm1.qcow2 10G
# repeat for vm2.qcow2 as needed
```

Alternate access: host port-forwarding (useful from WSL, no bridge needed)
---------------------------------------------------------------------------

```bash
USE_USERNET=1 ./vm1-launch.sh &   # VM1 SSH -> localhost:2222
USE_USERNET=1 ./vm2-launch.sh &   # VM2 SSH -> localhost:2223

ssh -p 2222 ubuntu@localhost   # VM1
ssh -p 2223 ubuntu@localhost   # VM2
```

Install and run your vehicle/remote apps inside the VMs
------------------------------------------------------

1. Install runtime packages on each VM:

```bash
sudo apt update
sudo apt install -y openssh-server tar iproute2 net-tools libc6 libstdc++6 libgcc-s1 libatomic1 ca-certificates rsync
```

2. Copy the prebuilt ARM64 tarballs from the host into each VM:

```bash
scp dist/high-beam-vehicle-aarch64.tar.gz ubuntu@192.168.100.175:/tmp/   # VM1
scp dist/high-beam-remote-aarch64.tar.gz  ubuntu@192.168.100.176:/tmp/   # VM2
```

3. Extract and run on each VM. Run one command at a time (do not paste the whole block at once — some shells mangle multi-line pastes):

On the vehicle VM (VM1):
```bash
rm -rf ~/high-beam
mkdir -p ~/high-beam
tar -xzf /tmp/high-beam-vehicle-aarch64.tar.gz -C ~/high-beam
ls ~/high-beam/run
```
```bash
cd ~/high-beam/run
./start-vehicle.sh 2>&1 | tee ~/high-beam/vehicle_app.log
```

On the remote VM (VM2):
```bash
rm -rf ~/high-beam
mkdir -p ~/high-beam
tar -xzf /tmp/high-beam-remote-aarch64.tar.gz -C ~/high-beam
ls ~/high-beam/run
```
```bash
cd ~/high-beam/run
./start-remote.sh 2>&1 | tee ~/high-beam/remote_app.log
```

Note: use `~/high-beam` (not `/opt/high-beam`) — the extracted `network.env` and launcher scripts assume this path, matching [sdv-hack-demo/README.md](../README.md).


Known issues already fixed in these scripts
--------------------------------------------

- Cloud-init previously set a static IP on `eth0`, but virtio NICs in these images don't always come up as `eth0` — switched to DHCP with an `en*` wildcard match.
- `setup-bridge.sh --dhcp` previously used the wrong dnsmasq option (`leasefile-ro`) and also tried to serve DNS on port 53 (conflicting with `systemd-resolved`) — fixed with `dhcp-leasefile=...` and `port=0` (DHCP only).
- If a VM booted once with the old broken static config, its disk has stale netplan state; recreate its qcow2 (see "Reset a VM to a clean state") rather than just rebooting.

Files in this folder
--------------------

- `create-vms.sh` — download/prepare cloud images and per-VM qcow2 files
- `setup-bridge.sh` — create bridge/taps and start `dnsmasq` for DHCP (`--dhcp`)
- `vm1-launch.sh`, `vm2-launch.sh` — per-VM launch scripts (deterministic MACs, `BACKGROUND=1` to daemonize + print IP, `USE_USERNET=1` for host port-forwarding)
- `start-vms.sh` — convenience script to start both VMs (legacy, tap mode only)
- `cloud-init-vm1.yaml`, `cloud-init-vm2.yaml` — cloud-init templates (DHCP networking, user `ubuntu`/`ubuntu`)

Security
--------

- Default VM account: `ubuntu` / password `ubuntu`. For production-like use, add your SSH public key to the `cloud-init` templates under `ssh_authorized_keys` and regenerate the ISOs:

```bash
cloud-localds -v cloud-init-vm1.iso cloud-init-vm1.yaml
cloud-localds -v cloud-init-vm2.iso cloud-init-vm2.yaml
```

Then recreate the qcow2 disks (see "Reset a VM to a clean state") so the new cloud-init applies on first boot.
