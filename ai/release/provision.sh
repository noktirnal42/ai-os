#!/bin/sh
# Provision an AI OS guest from one source tree. Run inside the VM as the ai user:
#   sh /ai/source/release/provision.sh
# The host packs the repo's ai/ directory and pushes it to /ai/source first (see RELEASE.md).
# Steps: harness and apps, kernel (upgrade and initramfs), desktop and kernel tools, policy, manifest.
set -eu
SRC=/ai/source
[ -f "$SRC/aios.py" ] || { echo "provision: $SRC/aios.py missing; push the repo's ai/ tree first" >&2; exit 1; }

echo "== harness"
sudo mkdir -p /ai/bin /ai/apps /ai/state /ai/tmp /ai/out /ai/lib
sudo install -m 755 "$SRC/aios.py" /ai/bin/aios.py
sudo install -m 755 "$SRC/aios_tui.py" /ai/bin/aios_tui.py
sudo install -m 755 "$SRC/aiosd" /ai/bin/aiosd
printf '#!/bin/sh\nexec python3 /ai/bin/aios.py "$@"\n' > /tmp/aios-wrapper
sudo install -m 755 /tmp/aios-wrapper /ai/bin/aios
for f in "$SRC"/bin/*; do sudo install -m 755 "$f" "/ai/bin/$(basename "$f")"; done

echo "== apps"
sudo cp -R "$SRC/apps/." /ai/apps/
sudo chown -R ai:ai /ai/apps /ai/state /ai/tmp /ai/out

echo "== kernel"
sudo apk upgrade --no-cache linux-virt linux-virt-dev
KV=$(ls /lib/modules | sort -V | tail -1)
sudo mkinitfs -o /boot/initramfs-virt "$KV"
echo "kernel $KV, initramfs regenerated"

echo "== desktop and kernel tools"
sudo rm -rf /ai/desktop /ai/kernel /ai/release
sudo cp -R "$SRC/desktop" /ai/desktop
sudo cp -R "$SRC/kernel" /ai/kernel
sudo cp -R "$SRC/release" /ai/release
sudo chown -R ai:ai /ai/desktop /ai/kernel /ai/release
sh /ai/desktop/setup.sh

echo "== manifest"
sh /ai/release/manifest.sh /ai/release/manifest.json
echo PROVISION_DONE
