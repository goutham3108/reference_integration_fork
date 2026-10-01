#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(pwd)"
IMAGES_DIR="$WORKDIR/images"
IMG_URL="https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-arm64.img"
BASE_IMG="$IMAGES_DIR/ubuntu-22.04-server-cloudimg-arm64.img"

VM1_IMG="$IMAGES_DIR/vm1.qcow2"
VM2_IMG="$IMAGES_DIR/vm2.qcow2"
CI1="$WORKDIR/cloud-init-vm1.iso"
CI2="$WORKDIR/cloud-init-vm2.iso"

mkdir -p "$IMAGES_DIR"

echo "Checking required tools..."
for tool in qemu-img cloud-localds qemu-system-aarch64; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Please install $tool"; exit 1; }
done

if [ ! -f "$BASE_IMG" ]; then
  echo "Downloading base cloud image..."
  wget -O "$BASE_IMG" "$IMG_URL"
fi

echo "Creating VM qcow2 images (thin clones)..."
qemu-img create -f qcow2 -b "$BASE_IMG" -F qcow2 "$VM1_IMG" 10G
qemu-img create -f qcow2 -b "$BASE_IMG" -F qcow2 "$VM2_IMG" 10G

echo "Creating cloud-init ISOs..."
if [ ! -f "$WORKDIR/cloud-init-vm1.yaml" ] || [ ! -f "$WORKDIR/cloud-init-vm2.yaml" ]; then
  echo "Missing cloud-init yaml templates in $WORKDIR; please edit them as needed." >&2
  exit 1
fi

cloud-localds -v "$CI1" "$WORKDIR/cloud-init-vm1.yaml"
cloud-localds -v "$CI2" "$WORKDIR/cloud-init-vm2.yaml"

echo "VM images and cloud-init ISOs created in: $WORKDIR"
echo "VM1 image: $VM1_IMG"
echo "VM2 image: $VM2_IMG"
echo "Cloud-init ISOs: $CI1, $CI2"
echo "Next: run sudo ./setup-bridge.sh then ./start-vms.sh to boot the VMs."
