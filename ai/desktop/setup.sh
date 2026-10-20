#!/bin/sh
# Install the desktop core packages in the guest. Run as the ai user inside the VM:
#   emulation/vm.sh exec 'sh /ai/desktop/setup.sh'
set -eu
sudo apk add --no-cache sway foot grim seatd font-dejavu
