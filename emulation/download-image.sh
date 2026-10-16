#!/bin/zsh
# Fetch a cloud-init image and require its upstream SHA-512 before use.
set -euo pipefail
source "$(dirname "$0")/env.sh"
ensure_artifacts
OUT="$BASE_IMAGE_FILE"
if [ -s "$OUT" ] && [ -s "$OUT.sha512" ]; then
  got="$(shasum -a 512 "$OUT" | awk '{print $1}')"
  [ "$got" = "$(cat "$OUT.sha512")" ] || die 'cached image checksum mismatch; cache left untouched' 4
  log 'cached image SHA-512 verified'; exit 0
fi
[ ! -e "$OUT" ] || die 'existing image has no checksum; left untouched; choose a new BASE_IMAGE_FILE' 4
URL="$IMAGE_URL"
if [ -z "$URL" ]; then
  idx="$ALPINE_MIRROR/$ALPINE_BRANCH/releases/cloud/"
  html="$(curl -fsSL --connect-timeout 10 --max-time 60 "$idx")"
  name="$(print -r -- "$html" | grep -oE "alpine-[0-9.]+-aarch64-${IMAGE_VARIANT}-cloudinit-r[0-9]+\\.qcow2" | sort -uV | tail -1)"
  [ -n "$name" ] || die "no matching cloud image in $idx" 4
  URL="$idx$name"
fi
curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 -o "$OUT.part.sha512" "$URL.sha512"
want="$(awk '{print $1}' "$OUT.part.sha512" | tr 'A-F' 'a-f')"
[[ "$want" =~ ^[0-9a-f]{128}$ ]] || die 'invalid upstream SHA-512' 4
log "downloading $URL"
curl -fL --retry 3 --connect-timeout 10 -o "$OUT.part" "$URL"
got="$(shasum -a 512 "$OUT.part" | awk '{print $1}')"
[ "$want" = "$got" ] || die 'SHA-512 mismatch; refusing to install' 4
mv "$OUT.part" "$OUT"
print -r -- "$got" > "$OUT.sha512"
print -r -- "$URL" > "$OUT.url"
rm -f "$OUT.part.sha512"
log "SHA-512 verified; image ready: $OUT"
