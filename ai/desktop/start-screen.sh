#!/bin/sh
# Start a foot terminal on the VM's on-screen display (requires VM_DISPLAY=cocoa).
# Software rendering only: the virtio GPU has no usable GL/EGL driver yet.
# Input devices are not wired into sway yet (WLR_LIBINPUT_NO_DEVICES=1).
set -eu
RT="/tmp/xdg-$(id -u)"
CONF="${1:-/tmp/sway-screen.conf}"
mkdir -p "$RT"; chmod 700 "$RT"
[ -f "$CONF" ] || printf 'exec foot\n' > "$CONF"
pkill -x sway 2>/dev/null || true
sleep 1
(XDG_RUNTIME_DIR="$RT" WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 LIBSEAT_BACKEND=seatd \
  timeout 3600 sway -c "$CONF" >/tmp/sway-screen.log 2>&1 &)
sleep 8
pgrep -x sway >/dev/null && echo "SCREEN_OK" || { echo "sway failed"; tail -5 /tmp/sway-screen.log; exit 1; }
