#!/bin/sh
# Install the desktop core in the guest, run as the ai user inside the VM:
#   emulation/vm.sh exec 'sh /ai/desktop/setup.sh'
set -eu
sudo apk add --no-cache sway foot grim seatd eudev wtype font-dejavu
sudo rc-update add udev default >/dev/null 2>&1 || true
sudo rc-update add udev-trigger sysinit >/dev/null 2>&1 || true
sudo rc-service udev start >/dev/null 2>&1 || true
sudo rc-update add seatd default >/dev/null 2>&1 || true
sudo rc-service seatd start >/dev/null 2>&1 || true
sudo addgroup ai seat 2>/dev/null || true
sudo addgroup ai video 2>/dev/null || true
sudo addgroup ai input 2>/dev/null || true
