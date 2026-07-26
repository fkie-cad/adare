#!/bin/bash
# provision + recompress a genuine desktop disk to ADARE-ready, in place.
#   ready_vm.sh <disk.qcow2> <ubuntu|kubuntu|fedora>
set -eu
DISK="${1:?usage: ready_vm.sh <disk.qcow2> <ubuntu|kubuntu|fedora>}"
FAMILY="${2:?family required}"
HERE="$(cd "$(dirname "$0")" && pwd)"
"$HERE/provision_adare.sh" "$DISK" "$FAMILY"
"$HERE/recompress.sh" "$DISK"
echo "READY_VM_OK: $DISK ($FAMILY)"
