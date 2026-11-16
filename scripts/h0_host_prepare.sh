#!/usr/bin/env bash
# Operator-run prerequisites only: packages, DC1 access and the known Piper CAN.
# Does not run an arm SDK, enable motors, reset, home, or send CAN commands.
set -euo pipefail
if [[ ${EUID} -ne 0 || -z ${SUDO_USER:-} ]]; then
    echo 'Run from your local terminal: sudo bash scripts/h0_host_prepare.sh' >&2
    exit 1
fi
udevadm info --query=property --path=/sys/class/net/can0 | \
    grep -qx 'ID_SERIAL_SHORT=004F00374548570120353731'
missing=()
for pkg in libuvc-dev libgoogle-glog-dev libgflags-dev \
    ros-humble-camera-info-manager ros-humble-image-publisher; do
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -qx 'install ok installed'; then
        missing+=("$pkg")
    fi
done
if ((${#missing[@]})); then
    apt-get install --no-upgrade -y "${missing[@]}"
fi
# Narrow permissions to the two actual DC1 USB functions.
cat > /etc/udev/rules.d/70-dog-and-arm-dc1.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="2bc5", ATTR{idProduct}=="0557", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2bc5", ATTR{idProduct}=="0657", MODE="0660", GROUP="plugdev", TAG+="uaccess"
EOF
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=2bc5
udevadm settle
# Grant this operator access immediately, without unplugging the wrist camera.
for dev in /sys/bus/usb/devices/*; do
    [[ -r "$dev/idVendor" && -r "$dev/idProduct" ]] || continue
    [[ $(cat "$dev/idVendor") == 2bc5 ]] || continue
    case "$(cat "$dev/idProduct")" in 0557|0657) ;; *) continue ;; esac
    printf -v node '/dev/bus/usb/%03d/%03d' "$(cat "$dev/busnum")" "$(cat "$dev/devnum")"
    setfacl -m "u:${SUDO_USER}:rw" "$node"
done
if ! ip -o link show can0 | grep -q '<[^>]*UP'; then
    ip link set can0 up type can bitrate 1000000
fi
ip -details -statistics link show can0
echo 'H0 host prerequisites finished. No motor commands sent.'
