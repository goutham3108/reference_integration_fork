#!/usr/bin/env bash
set -euo pipefail

# Creates a bridge (br0) and two TAP devices (tap-vm1, tap-vm2).
# Run with sudo.

BR=br0
TAP1=tap-vm1
TAP2=tap-vm2
BR_IP=192.168.100.1/24
DNSMASQ_CONF="/tmp/dnsmasq-br0.conf"
DNSMASQ_LEASES="/tmp/dnsmasq-br0.leases"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo $0"; exit 1
fi

modprobe tun

# Ensure bridge exists and is up first
ip link add name "$BR" type bridge 2>/dev/null || true
ip link set dev "$BR" up || true

create_tap() {
  local tap="$1"
  if ip link show "$tap" >/dev/null 2>&1; then
    echo "Tap $tap already exists"
    return 0
  fi

  # Try portable tuntap command first, then fall back to newer ip link syntax
  if ip tuntap add mode tap name "$tap" 2>/dev/null; then
    echo "Created tap $tap via ip tuntap"
  elif ip link add name "$tap" type tap 2>/dev/null; then
    echo "Created tap $tap via ip link add type tap"
  else
    echo "Failed to create tap device $tap: no supported ip/tuntap method" >&2
    return 1
  fi

  ip link set dev "$tap" mtu 1500
  ip link set dev "$tap" up
  ip link set dev "$tap" master "$BR"
}

create_tap "$TAP1"
create_tap "$TAP2"

ip addr add "$BR_IP" dev "$BR" 2>/dev/null || true

echo 1 > /proc/sys/net/ipv4/ip_forward

# NAT outbound traffic from br0 to main interface

MAIN_IF=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="dev") print $(i+1); exit}')
if [ -n "$MAIN_IF" ]; then
  iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o "$MAIN_IF" -j MASQUERADE || true
else
  echo "Warning: could not determine main interface for NAT; skipping MASQUERADE rule" >&2
fi

if [ "${1:-}" = "--dhcp" ]; then
  if ! command -v dnsmasq >/dev/null 2>&1; then
    echo "dnsmasq not installed; please install it to enable DHCP (sudo apt install dnsmasq)" >&2
    exit 1
  fi

  # Kill any previous instance bound to this conf so leases start fresh
  pkill -f "dnsmasq --conf-file=$DNSMASQ_CONF" 2>/dev/null || true

  cat > "$DNSMASQ_CONF" <<EOF
interface=$BR
bind-interfaces
except-interface=lo
dhcp-range=192.168.100.100,192.168.100.200,12h
dhcp-leasefile=$DNSMASQ_LEASES
dhcp-option=option:dns-server,8.8.8.8,1.1.1.1
log-dhcp
port=0
EOF

  # Start dnsmasq detached so it survives this script exiting
  echo "Starting dnsmasq for $BR (leases: $DNSMASQ_LEASES)"
  setsid dnsmasq --conf-file="$DNSMASQ_CONF" --no-daemon >/tmp/dnsmasq-br0.log 2>&1 < /dev/null &
  disown
  sleep 1
  if pgrep -f "dnsmasq --conf-file=$DNSMASQ_CONF" >/dev/null; then
    echo "dnsmasq running. Check leases with: cat $DNSMASQ_LEASES"
  else
    echo "dnsmasq failed to start; see /tmp/dnsmasq-br0.log" >&2
  fi
fi

echo "Bridge $BR and taps $TAP1,$TAP2 created. Bridge IP: $BR_IP"
echo "To persist across reboots, create appropriate systemd/network or netplan configs." 
