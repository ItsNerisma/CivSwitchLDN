#!/usr/bin/env bash
# Temporarily release the selected Wi-Fi radio for an LDN command.
# Usage: bash bash/network.sh --phy <radio> <command> [args...]

# Handle failures explicitly so cleanup can preserve the command's exit status.
set -uo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
python_ldn="$root/ldn/.venv/bin/python-ldn"

if [[ $# -lt 3 || "$1" != --phy ]]; then
    echo "Usage: bash bash/network.sh --phy <radio> <command> [args...]" >&2
    exit 1
fi

phy="$2"
shift 2

if [[ ! -d "/sys/class/ieee80211/$phy" ]]; then
    echo "[net] Radio not found: $phy" >&2
    exit 1
fi

if [[ ! -x "$python_ldn" ]]; then
    echo "[net] Run setup first: npm install" >&2
    exit 1
fi

if ! command -v nmcli >/dev/null; then
    echo "[net] NetworkManager (nmcli) is required." >&2
    exit 1
fi

if ! command -v sudo >/dev/null; then
    echo "[net] sudo is required to control NetworkManager." >&2
    exit 1
fi

# Save each interface's connection and link state before releasing the radio.
# These arrays share the same index for each interface.
interfaces=()
connections=()
was_up=()

for radio in /sys/class/net/*/phy80211; do
    if [[ "$(basename -- "$(readlink -f -- "$radio")")" != "$phy" ]]; then
        continue
    fi

    device="$(basename -- "$(dirname -- "$radio")")"
    interfaces+=("$device")
    connections+=("$(nmcli -g GENERAL.CON-UUID device show "$device" 2>/dev/null || true)")

    # The lowest bit of the interface flags is IFF_UP.
    flags="$(cat "/sys/class/net/$device/flags")"
    was_up+=("$((flags & 1))")
done

networking="$(nmcli networking)" || exit 1
[[ "$networking" == enabled || "$networking" == disabled ]] || exit 1

# Use the Python helper's network capabilities to change the link state.
link() {
    "$python_ldn" -c '
import fcntl
import socket
import struct
import sys

SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 1

name, up = sys.argv[1].encode(), sys.argv[2] == "up"
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    request = struct.pack("16sH14x", name, 0)
    response = fcntl.ioctl(s, SIOCGIFFLAGS, request)
    flags = struct.unpack("16sH14x", response)[1]
    flags = flags | IFF_UP if up else flags & ~IFF_UP
    fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sH14x", name, flags))
' "$1" "$2"
}

# Wait for the original connection and an IPv4 address before LAN discovery.
restore_connection() {
    local device="$1" conn="$2"
    local state current address
    local deadline=$((SECONDS + 60))

    while (( SECONDS < deadline )); do
        state="$(nmcli -g GENERAL.STATE device show "$device" 2>/dev/null || true)"
        # nmcli returns a numeric state followed by a human-readable label.
        state="${state%% *}"

        current="$(nmcli -g GENERAL.CON-UUID device show "$device" 2>/dev/null || true)"
        address="$(nmcli -g IP4.ADDRESS device show "$device" 2>/dev/null || true)"

        # State 100 means connected; state 30 means disconnected.
        if [[ "$state" == 100 && "$current" == "$conn" && -n "$address" ]]; then
            return 0
        fi

        if [[ "$state" == 30 || ( "$state" == 100 && "$current" != "$conn" ) ]]; then
            sudo nmcli --wait 10 connection up uuid "$conn" ifname "$device" || true
        fi

        sleep 1
    done

    echo "[net] $device did not reconnect to $conn with an IPv4 address." >&2
    return 1
}

restore() {
    local status=$?
    local failed=0 i conn

    # Disable traps to avoid re-entering cleanup while restoring the network.
    trap - EXIT INT TERM
    echo "[net] Restoring networking..."

    for i in "${!interfaces[@]}"; do
        if [[ "${was_up[i]}" == 1 ]]; then
            link "${interfaces[i]}" up || failed=1
        else
            link "${interfaces[i]}" down || failed=1
        fi
    done

    # Only re-enable NetworkManager if networking was enabled originally.
    if [[ "$networking" == enabled ]]; then
        if sudo nmcli networking on; then
            for i in "${!interfaces[@]}"; do
                conn="${connections[i]}"
                if [[ -n "$conn" && "$conn" != -- ]]; then
                    restore_connection "${interfaces[i]}" "$conn" || failed=1
                fi
            done
        else
            failed=1
        fi
    fi

    if (( failed )); then
        echo "[net] Networking could not be fully restored. Reconnect before running the installer." >&2
        (( status == 0 )) && status=1
    fi

    exit "$status"
}

child=""

interrupt() {
    # Stop the LDN command before restoring the radio it was using.
    if [[ -n "$child" ]]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
    fi

    exit "$1"
}

# Restore the saved state on normal exit, failure, or interruption.
trap restore EXIT
trap 'interrupt 130' INT
trap 'interrupt 143' TERM

echo "[net] Suspending NetworkManager for LDN on $phy."
# NetworkManager is disabled globally, even though LDN uses one radio.
sudo nmcli networking off || exit 1

for device in "${interfaces[@]}"; do
    link "$device" down || exit 1
done

# Forward stdin to LDN and wait asynchronously so signal traps can run.
"$@" <&0 &
child=$!
wait "$child"
exit $?
