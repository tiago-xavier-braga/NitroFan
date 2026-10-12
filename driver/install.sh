#!/usr/bin/env bash
# Builds and installs the linuwu_sense kernel module with the AN517-54 patch.
set -euo pipefail

REPO=https://github.com/0x7375646F/Linuwu-Sense.git
COMMIT=73a25ec243a44ba2b1703e8d0a76fa2735062506
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=$HERE/build

if [ ! -d "/lib/modules/$(uname -r)/build" ]; then
    echo "Kernel headers for $(uname -r) not found. Install them first" >&2
    echo "(Manjaro: sudo pacman -S linux<version>-headers dkms)." >&2
    exit 1
fi

rm -rf "$BUILD"
git clone "$REPO" "$BUILD"
git -C "$BUILD" checkout "$COMMIT"
git -C "$BUILD" apply "$HERE"/0001-add-nitro-an517-54.patch

# Replaces acer_wmi with linuwu_sense, installs the service and group.
make -C "$BUILD" install
echo "Done. Log out and back in so the linuwu_sense group takes effect."
