#!/bin/bash
# zstd-recompress a disk in place (virt-customize leaves clusters uncompressed).
#   recompress.sh <disk.qcow2>
set -eu
DISK="${1:?usage: recompress.sh <disk.qcow2>}"
TMP="${DISK%.qcow2}.zstd.qcow2"; rm -f "$TMP"
before=$(du -h "$DISK" | cut -f1)
qemu-img convert -O qcow2 -c -o compression_type=zstd "$DISK" "$TMP"
qemu-img check "$TMP" >/dev/null
mv -f "$TMP" "$DISK"
echo "RECOMPRESSED: $DISK  $before -> $(du -h "$DISK" | cut -f1)"
