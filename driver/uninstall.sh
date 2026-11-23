#!/usr/bin/env bash
# Removes linuwu_sense and restores the stock acer_wmi module.
set -euo pipefail

NAME=linuwu_sense
USER_NAME=${SUDO_USER:-$(whoami)}

for v in $(dkms status -m "$NAME" 2>/dev/null | sed -n "s|^$NAME/\([^,:]*\).*|\1|p" | sort -u); do
    sudo dkms remove -m "$NAME" -v "$v" --all || true
done
sudo rm -rf /usr/src/"$NAME"-*
sudo find /lib/modules -path '*/kernel/drivers/platform/x86/linuwu_sense.ko*' -delete

sudo systemctl disable --now "$NAME.service" 2>/dev/null || true
sudo rm -f /etc/systemd/system/$NAME.service \
    /etc/modules-load.d/$NAME.conf \
    /etc/modprobe.d/blacklist-acer_wmi.conf \
    /etc/tmpfiles.d/$NAME.conf
sudo systemctl daemon-reload
sudo depmod -a
sudo rmmod "$NAME" 2>/dev/null || true
sudo modprobe acer_wmi || true

if getent group "$NAME" >/dev/null; then
    sudo gpasswd -d "$USER_NAME" "$NAME" || true
    sudo groupdel "$NAME" || true
fi
echo "Removed $NAME; acer_wmi restored."
