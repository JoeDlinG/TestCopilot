#!/usr/bin/env bash
# One-time setup for PEAK-System PCAN-USB adapters over SocketCAN on Linux.
#
# Fixes "DEV-002 cannot connect even after replugging": the USB adapter is seen
# but `peak_usb` is not loaded and no can* link is UP, so python-can has nothing
# to open. Loading a kernel module and configuring a CAN link both need root,
# hence this one-time installer plus a udev rule for every future plug-in.
#
# Usage:  sudo bash backend/install/install_peakcan_rules.sh [bitrate]
#         (default bitrate 500000; then unplug and replug the PCAN-USB cable)
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
RULES_SRC="$HERE/99-peakcan-socketcan.rules"
RULES_DST="/etc/udev/rules.d/99-peakcan-socketcan.rules"
MODULES_DST="/etc/modules-load.d/testcopilot-peakcan.conf"
BITRATE="${1:-500000}"

if [ "$(id -u)" -ne 0 ]; then
    echo "需要 root 权限，请用: sudo bash $0" >&2
    exit 1
fi

install -m 0644 "$RULES_SRC" "$RULES_DST"
echo "已安装 $RULES_DST"

# Also load the driver at boot, so an adapter plugged in before udev starts is
# picked up without any manual step.
echo "peak_usb" > "$MODULES_DST"
echo "已写入 $MODULES_DST"

modprobe peak_usb 2>/dev/null || true
udevadm control --reload-rules
udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=0c72 || true
udevadm settle 2>/dev/null || true

# Configure interfaces that already exist right now (no replug needed).
found=0
for path in /sys/class/net/can*; do
    [ -e "$path" ] || continue
    found=1
    ch="$(basename "$path")"
    state="$(cat "$path/operstate" 2>/dev/null || echo unknown)"
    if [ "$state" != "up" ]; then
        /sbin/ip link set "$ch" up type can bitrate "$BITRATE" 2>/dev/null || true
    fi
    echo "已配置 $ch (原状态: $state, 目标波特率: $BITRATE)"
done

echo
if [ "$found" -eq 0 ]; then
    echo "当前没有 can* 接口。请重新插拔一次 PCAN-USB；udev 会自动加载 peak_usb 并启用接口。"
else
    /sbin/ip -details link show type can 2>/dev/null || true
fi
echo
echo "完成。回到设备管理页点击连接即可；也可在调试终端发送 {\"action\": \"diagnose\"} 查看诊断。"
