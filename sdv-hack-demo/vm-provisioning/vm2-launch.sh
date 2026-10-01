#!/usr/bin/env bash
set -euo pipefail

# Launch VM2 only. Defaults to using bridge/tap networking (tap-vm2 -> br0).
# If you don't have a bridge/tap, set USE_USERNET=1 to use user-mode networking and host SSH forward (port 2223).

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
IMGDIR="$WORKDIR/images"
VM_IMG="$IMGDIR/vm2.qcow2"
CI_ISO="$WORKDIR/cloud-init-vm2.iso"

# Deterministic MAC so we can map IP -> MAC from the host ARP table
MAC2="52:54:00:12:34:02"

POLL_TIMEOUT=${POLL_TIMEOUT:-60}

if [ ! -f "$VM_IMG" ]; then
  echo "VM image $VM_IMG not found. Run ./create-vms.sh first." >&2
  exit 1
fi

UEFI="/usr/share/qemu-efi-aarch64/QEMU_EFI.fd"
UEFI_OPT=""
if [ -f "$UEFI" ]; then
  UEFI_OPT="-bios $UEFI"
fi

if [ "${USE_USERNET:-0}" = "1" ]; then
  echo "Starting VM2 with user-mode networking (SSH on host:2223)"
  qemu-system-aarch64 \
    -M virt -cpu cortex-a57 -smp 4 -m 2048 $UEFI_OPT \
    -drive file="$VM_IMG",if=virtio,format=qcow2 \
    -drive file="$CI_ISO",if=virtio,format=raw \
    -netdev user,id=net1,hostfwd=tcp::2223-:22 \
    -device virtio-net-device,netdev=net1,mac=$MAC2 \
    -nographic &
  QEMU_PID=$!
  echo "VM2 PID=$QEMU_PID"
  echo "VM network (user) IP: 10.0.2.15 (use host forward port 2223)"
else
  echo "Starting VM2 with tap networking (tap-vm2 -> br0). Ensure sudo ./setup-bridge.sh was run."
  if [ "${BACKGROUND:-0}" = "1" ]; then
    qemu-system-aarch64 \
      -M virt -cpu cortex-a57 -smp 4 -m 2048 $UEFI_OPT \
      -drive file="$VM_IMG",if=virtio,format=qcow2 \
      -drive file="$CI_ISO",if=virtio,format=raw \
      -netdev tap,id=net1,ifname=tap-vm2,script=no,downscript=no \
      -device virtio-net-device,netdev=net1,mac=$MAC2 \
      -nographic &
    QEMU_PID=$!
    echo "VM2 PID=$QEMU_PID (background). Polling ARP table for MAC $MAC2 to discover IP..."
    SECONDS=0
    while [ $SECONDS -lt $POLL_TIMEOUT ]; do
      IP_LINE=$(ip neigh show dev br0 | grep -i "$MAC2" || true)
      if [ -n "$IP_LINE" ]; then
        VM_IP=$(echo "$IP_LINE" | awk '{print $1}')
        echo "Detected VM2 IP: $VM_IP"
        exit 0
      fi
      sleep 1
    done
    echo "Timed out waiting for VM2 IP (no ARP entry for $MAC2)." >&2
    echo "Check bridge/taps and DHCP (try: sudo ./setup-bridge.sh --dhcp)." >&2
    exit 2
  else
    qemu-system-aarch64 \
      -M virt -cpu cortex-a57 -smp 4 -m 2048 $UEFI_OPT \
      -drive file="$VM_IMG",if=virtio,format=qcow2 \
      -drive file="$CI_ISO",if=virtio,format=raw \
      -netdev tap,id=net1,ifname=tap-vm2,script=no,downscript=no \
      -device virtio-net-device,netdev=net1,mac=$MAC2 \
      -nographic
  fi
fi
