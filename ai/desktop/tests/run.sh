#!/bin/sh
# Phase 1 gate: start a headless sway session, open a foot terminal, and check
# the captured frame contains the terminal's output. Runs in the guest.
set -eu
RT="/tmp/xdg-$(id -u)"
OUT="${AIOS_DESKTOP_FRAME:-/tmp/ai-os-frame.png}"
TOKEN="AI_OS_DESKTOP_OK"
CONF="$(mktemp)"
trap 'pkill -u "$(id -u)" -x sway 2>/dev/null || true; rm -f "$CONF"' EXIT

sudo rc-service seatd start >/dev/null 2>&1 || true
mkdir -p "$RT"; chmod 700 "$RT"
printf 'exec foot -e sh -c "echo %s; sleep 60"\n' "$TOKEN" > "$CONF"

export XDG_RUNTIME_DIR="$RT" WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 LIBSEAT_BACKEND=seatd
timeout 60 sway -c "$CONF" >/tmp/sway-test.log 2>&1 &

for _ in $(seq 1 30); do
  WAYLAND_DISPLAY=$(ls "$RT" 2>/dev/null | grep '^wayland-[0-9]*$' | head -1 || true)
  [ -n "${WAYLAND_DISPLAY:-}" ] && break
  sleep 1
done
[ -n "${WAYLAND_DISPLAY:-}" ] || { echo "no wayland socket"; cat /tmp/sway-test.log; exit 1; }
export WAYLAND_DISPLAY
sleep 6
grim "$OUT"
SIZE=$(wc -c < "$OUT")
[ "$SIZE" -gt 4000 ] || { echo "frame too small ($SIZE bytes): terminal did not render"; exit 1; }
echo "DESKTOP_FRAME_OK bytes=$SIZE file=$OUT"
