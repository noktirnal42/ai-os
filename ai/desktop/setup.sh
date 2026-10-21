#!/bin/sh
# Install the desktop and default apps in the guest, run as the ai user inside the VM:
#   emulation/vm.sh exec 'sh /ai/desktop/setup.sh'
set -eu
# Desktop core: compositor, terminal, screenshot, launcher, input test helper, seat and udev.
sudo apk add --no-cache sway foot grim seatd eudev wtype fuzzel gtk4.0 py3-gobject3 font-dejavu
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
# Terminal font default, read by foot for every new terminal (settings font changes it).
mkdir -p "$HOME/.config/foot"
[ -f "$HOME/.config/foot/foot.ini" ] || printf '[main]\nfont=monospace:size=12\n' > "$HOME/.config/foot/foot.ini"

# Launcher and menu look: a readable size for the virtual display.
mkdir -p "$HOME/.config/fuzzel"
[ -f "$HOME/.config/fuzzel/fuzzel.ini" ] || printf '[main]\nfont=monospace:size=12\nwidth=40\nlines=12\n' > "$HOME/.config/fuzzel/fuzzel.ini"

# Install the desktop helper commands (welcome, tutorial) into /ai/bin when they are present.
if [ -d /ai/desktop/bin ]; then
  for f in /ai/desktop/bin/*; do sudo install -m 755 "$f" "/ai/bin/$(basename "$f")"; done
fi

# Freedom policy: the default file narrows nothing. It can only remove write roots (see docs/19).
[ -f /ai/policy.json ] || cp /ai/desktop/policy/policy.json /ai/policy.json

# Kernel staging: the tool and the example module source. Building needs linux-virt-dev for the
# running kernel; this script does not install it, because a mismatched header package cannot build.
sudo install -m 755 /ai/kernel/bin/kstage /ai/bin/kstage 2>/dev/null || true

# Boot straight into the desktop: autologin on tty1 for the ai user, and start the session from the
# profile. The profile line is added once, guarded by a marker.
if ! grep -q '^tty1::respawn:/bin/login -f ai' /etc/inittab 2>/dev/null; then
  sudo sed -i 's#^tty1::respawn:/sbin/getty 38400 tty1#tty1::respawn:/bin/login -f ai#' /etc/inittab
fi
if ! grep -q 'AI OS desktop autostart' "$HOME/.profile" 2>/dev/null; then
  printf '%s\n' '# AI OS desktop autostart' 'if [ "$(tty)" = /dev/tty1 ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then exec /ai/bin/desktop-session; fi' >> "$HOME/.profile"
fi

