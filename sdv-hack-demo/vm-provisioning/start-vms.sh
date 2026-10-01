#!/usr/bin/env bash
set -euo pipefail

# Start two ARM64 VMs using qemu-system-aarch64. Requires the bridge and taps created by setup-bridge.sh
# Adjust AAVMF firmware path if needed (UEFI). If you don't have UEFI, try without -bios.

WORKDIR="$(pwd)"
IMGDIR="$WORKDIR/images"
VM1_IMG="$IMGDIR/vm1.qcow2"
VM2_IMG="$IMGDIR/vm2.qcow2"
CI1="$WORKDIR/cloud-init-vm1.iso"
CI2="$WORKDIR/cloud-init-vm2.iso"

TAP1=tap-vm1
TAP2=tap-vm2
BR=br0

UEFI="/usr/share/qemu-efi-aarch64/QEMU_EFI.fd"
UEFI_OPT=""
if [ -f "$UEFI" ]; then
  UEFI_OPT="-bios $UEFI"
fi

if [ ! -f "$VM1_IMG" ] || [ ! -f "$VM2_IMG" ]; then
  echo "VM images not found. Run ./create-vms.sh first."; exit 1
fi

echo "Starting VM1 (console on this terminal)..."
qemu-system-aarch64 \
  -M virt -cpu cortex-a57 -smp 4 -m 2048 $UEFI_OPT \
  -drive file="$VM1_IMG",if=virtio,format=qcow2 \
  -drive file="$CI1",if=virtio,format=raw \
  -netdev tap,id=net0,ifname=$TAP1,script=no,downscript=no \
  -device virtio-net-device,netdev=net0 \
  -nographic &
PID1=$!

echo "Starting VM2 (background)..."
qemu-system-aarch64 \
  -M virt -cpu cortex-a57 -smp 4 -m 2048 $UEFI_OPT \
  -drive file="$VM2_IMG",if=virtio,format=qcow2 \
  -drive file="$CI2",if=virtio,format=raw \
  -netdev tap,id=net1,ifname=$TAP2,script=no,downscript=no \
  -device virtio-net-device,netdev=net1 \
  -nographic &
PID2=$!

echo "VM1 PID=$PID1 VM2 PID=$PID2"
echo "Use 'tail -f /proc/$PID1/fd/1' to view VM1 output, or attach a serial console." 
