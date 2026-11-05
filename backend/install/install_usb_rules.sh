#!/usr/bin/env bash
# One-time setup for Mini Gateway 100 over USB on Linux.
#
# Fixes "USB is plugged in but the app cannot connect": the cdc_acm driver is
# often not bound on embedded/Jetson kernels, so no /dev/ttyACM* node exists,
# and the raw USB node is not writable by a normal user.
#
# Usage:  sudo bash backend/install/install_usb_rules.sh
#         (then unplug and replug the MG100 USB cable)
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
RULES_SRC="$HERE/99-mg100-usb.rules"
RULES_DST="/etc/udev/rules.d/99-mg100-usb.rules"

if [ "$(id -u)" -ne 0 ]; then
    echo "需要 root 权限，请用: sudo bash $0" >&2
    exit 1
fi

install -m 0644 "$RULES_SRC" "$RULES_DST"
echo "已安装 $RULES_DST"

modprobe cdc_acm 2>/dev/null || true
udevadm control --reload-rules
udevadm trigger --action=add --attr-match=idVendor=0483 --attr-match=idProduct=5740 || true
# Also bind any already-enumerated device right now (no replug needed).
if [ -w /sys/bus/usb/drivers/cdc_acm/new_id ]; then
    echo "0483 5740" > /sys/bus/usb/drivers/cdc_acm/new_id || true
fi
udevadm settle 2>/dev/null || true

echo
echo "完成。当前串口节点："
ls -1 /dev/ttyACM* 2>/dev/null || echo "  (暂无 — 请重新插拔一次 MG100 USB 线；"
echo "   插件的 transport=usb 也可在无串口节点时直接工作)"
echo
echo "USB 节点权限："
ls -l /dev/bus/usb/*/* 2>/dev/null | grep -i "" | head -5 || true
