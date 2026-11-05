#!/usr/bin/env bash
# Temporarily release the selected Wi-Fi radio for an LDN command.
# Usage: bash network.sh --phy <radio> <command> [args...]
set -uo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
python_ldn="$root/ldn/.venv/bin/python-ldn"

if [[ $# -lt 3 || "$1" != --phy ]]; then
    echo "Usage: bash network.sh --phy <radio> <command> [args...]" >&2
    exit 1
fi
phy="$2"
shift 2
[[ -d "/sys/class/ieee80211/$phy" ]] || { echo "[net] Radio not found: $phy" >&2; exit 1; }
[[ -x "$python_ldn" ]] || { echo "[net] Run setup first: npm install" >&2; exit 1; }
command -v nmcli >/dev/null || { echo "[net] NetworkManager (nmcli) is required." >&2; exit 1; }

# Discover interfaces belonging to this radio, without a machine-specific name.
interfaces=()
connections=()
was_up=()
for radio in /sys/class/net/*/phy80211; do
    [[ "$(basename -- "$(readlink -f -- "$radio")")" == "$phy" ]] || continue
    device="$(basename -- "$(dirname -- "$radio")")"
    interfaces+=("$device")
    connections+=("$(nmcli -g GENERAL.CON-UUID device show "$device" 2>/dev/null || true)")
    flags="$(cat "/sys/class/net/$device/flags")"
    was_up+=("$((flags & 1))")
done
networking="$(nmcli networking)" || exit 1
[[ "$networking" == enabled || "$networking" == disabled ]] || exit 1

link() {
    "$python_ldn" -c '
import fcntl, socket, struct, sys
name, up = sys.argv[1].encode(), sys.argv[2] == "up"
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    flags = struct.unpack("16sH14x", fcntl.ioctl(s, 0x8913, struct.pack("16sH14x", name, 0)))[1]
    flags = flags | 1 if up else flags & ~1
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14x", name, flags))
' "$1" "$2"
}

restore() {
    local status=$? failed=0 i conn
    trap - EXIT INT TERM
    echo "[net] Restoring networking..."
    for i in "${!interfaces[@]}"; do
        if [[ "${was_up[i]}" == 1 ]]; then
            link "${interfaces[i]}" up || failed=1
        else
            link "${interfaces[i]}" down || failed=1
        fi
    done
    if [[ "$networking" == enabled ]]; then
        nmcli networking on || failed=1
        for i in "${!interfaces[@]}"; do
            conn="${connections[i]}"
            if [[ -n "$conn" && "$conn" != -- ]]; then
                nmcli --wait 30 connection up uuid "$conn" || failed=1
            fi
        done
    fi
    if (( failed )); then
        echo "[net] Networking could not be fully restored. Reconnect before running the installer." >&2
        (( status == 0 )) && status=1
    fi
    exit "$status"
}
child=""
interrupt() {
    if [[ -n "$child" ]]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
    fi
    exit "$1"
}
trap restore EXIT
trap 'interrupt 130' INT
trap 'interrupt 143' TERM

echo "[net] Suspending NetworkManager for LDN on $phy."
nmcli networking off || exit 1
for device in "${interfaces[@]}"; do
    link "$device" down || exit 1
done

"$@" <&0 &
child=$!
wait "$child"
exit $?
