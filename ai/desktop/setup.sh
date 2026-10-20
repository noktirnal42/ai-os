#!/bin/sh
# Install the desktop and default apps in the guest, run as the ai user inside the VM:
#   emulation/vm.sh exec 'sh /ai/desktop/setup.sh'
set -eu
# Desktop core: compositor, terminal, screenshot, launcher, input test helper, seat and udev.
sudo apk add --no-cache sway foot grim seatd eudev wtype fuzzel font-dejavu
# Default apps: text editor, file browser, and a plain-text fallback editor.
sudo apk add --no-cache micro ranger nano
sudo rc-update add udev default >/dev/null 2>&1 || true
sudo rc-update add udev-trigger sysinit >/dev/null 2>&1 || true
sudo rc-service udev start >/dev/null 2>&1 || true
sudo rc-update add seatd default >/dev/null 2>&1 || true
sudo rc-service seatd start >/dev/null 2>&1 || true
sudo addgroup ai seat 2>/dev/null || true
sudo addgroup ai video 2>/dev/null || true
sudo addgroup ai input 2>/dev/null || true
# Install the desktop helper commands (welcome, tutorial) into /ai/bin when they are present.
if [ -d /ai/desktop/bin ]; then
  for f in /ai/desktop/bin/*; do sudo install -m 755 "$f" "/ai/bin/$(basename "$f")"; done
fi
