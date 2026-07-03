#!/bin/bash
set -e

echo "[aimilivpn] Docker container starting..."

# 1. Check TUN device
if [ ! -c /dev/net/tun ]; then
    echo "[ERROR] /dev/net/tun not found. Run with: --device=/dev/net/tun"
    echo "If tun module is not loaded on host, run: modprobe tun"
    exit 1
fi
if [ ! -r /dev/net/tun ] || [ ! -w /dev/net/tun ]; then
    echo "[WARN] /dev/net/tun permission issue, trying to fix..."
    chmod 666 /dev/net/tun 2>/dev/null || true
fi

# 2. Enable IP forwarding (may fail if not privileged, that's ok)
echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo "[WARN] Cannot enable ip_forward via proc, use sysctl in compose"

# 3. Set rp_filter to loose mode
for iface in all default; do
    echo 2 > /proc/sys/net/ipv4/conf/${iface}/rp_filter 2>/dev/null || true
done

# 4. Verify openvpn
if ! command -v openvpn &>/dev/null; then
    echo "[ERROR] openvpn not found in PATH"
    exit 1
fi
echo "[aimilivpn] openvpn version: $(openvpn --version 2>&1 | head -1)"

# 5. Verify python3
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found in PATH"
    exit 1
fi

echo "[aimilivpn] Environment check passed, starting manager..."
exec python3 /opt/aimilivpn/vpngate_manager.py
