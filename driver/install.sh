#!/usr/bin/env bash
# Builds and installs the linuwu_sense kernel module (with the AN517-54 patch)
# through DKMS, so it is rebuilt automatically on every kernel update.
set -euo pipefail

REPO=https://github.com/0x7375646F/Linuwu-Sense.git
COMMIT=73a25ec243a44ba2b1703e8d0a76fa2735062506
NAME=linuwu_sense
VERSION=git${COMMIT:0:7}
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=$HERE/build
SRC=/usr/src/$NAME-$VERSION
KVER=$(uname -r)
USER_NAME=${SUDO_USER:-$(whoami)}
SYSFS=/sys/module/$NAME/drivers/platform:acer-wmi/acer-wmi/nitro_sense

if [ ! -d "/lib/modules/$KVER/build" ]; then
    MAJOR=$(echo "$KVER" | cut -d. -f1,2 | tr -d .)
    echo "Kernel headers for $KVER not found. Install them first" >&2
    echo "(Manjaro: sudo pacman -S --needed linux$MAJOR-headers dkms)." >&2
    exit 1
fi
command -v dkms >/dev/null || { echo "dkms not found (sudo pacman -S dkms)." >&2; exit 1; }

# 1. Fetch and patch the source.
rm -rf "$BUILD"
git clone "$REPO" "$BUILD"
git -C "$BUILD" checkout "$COMMIT"
git -C "$BUILD" apply "$HERE"/0001-add-nitro-an517-54.patch
# Kernel 7.x removed strncpy(); memcpy() is equivalent here (copies exactly len bytes).
sed -i 's/\bstrncpy(/memcpy(/g' "$BUILD/src/$NAME.c"

# 2. Remove any previous install (DKMS or the upstream `make install` copy).
for v in $(dkms status -m "$NAME" 2>/dev/null | sed -n "s|^$NAME/\([^,:]*\).*|\1|p" | sort -u); do
    sudo dkms remove -m "$NAME" -v "$v" --all || true
done
sudo find /lib/modules -path '*/kernel/drivers/platform/x86/linuwu_sense.ko*' -delete
sudo rm -rf /usr/src/"$NAME"-*

# 3. Register with DKMS, build and install for the running kernel.
sudo install -d "$SRC"
sudo install -m 644 "$BUILD/src/$NAME.c" "$SRC/"
echo "obj-m := $NAME.o" | sudo tee "$SRC/Makefile" >/dev/null
sudo tee "$SRC/dkms.conf" >/dev/null <<CONF
PACKAGE_NAME="$NAME"
PACKAGE_VERSION="$VERSION"
BUILT_MODULE_NAME[0]="$NAME"
DEST_MODULE_LOCATION[0]="/kernel/drivers/platform/x86"
MAKE[0]="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build modules"
CLEAN="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build clean"
AUTOINSTALL="yes"
CONF
sudo dkms install -m "$NAME" -v "$VERSION" -k "$KVER"

# 4. Replace acer_wmi and load at boot.
echo "blacklist acer_wmi" | sudo tee /etc/modprobe.d/blacklist-acer_wmi.conf >/dev/null
echo "$NAME" | sudo tee /etc/modules-load.d/$NAME.conf >/dev/null
sudo install -m 644 "$BUILD/$NAME.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$NAME.service"
sudo rmmod acer_wmi 2>/dev/null || true
sudo modprobe "$NAME"
sudo systemctl start "$NAME.service"

# 5. Let the linuwu_sense group write the sysfs files without root.
getent group "$NAME" >/dev/null || sudo groupadd "$NAME"
sudo usermod -aG "$NAME" "$USER_NAME"
for f in fan_speed battery_limiter battery_calibration usb_charging; do
    echo "f $SYSFS/$f 0660 root $NAME"
done | sudo tee /etc/tmpfiles.d/$NAME.conf >/dev/null
sudo systemd-tmpfiles --create /etc/tmpfiles.d/$NAME.conf

dkms status -m "$NAME"
echo "Done. Log out and back in if this is the first install (new group)."
