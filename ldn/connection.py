"""LDN network discovery and joining using kinnay/LDN.

Handles key loading, scanning for Civ VII wireless networks, building
connection parameters, and fallback addressing when a host announcement is missing.
"""

import importlib
import importlib.metadata
import os
from pathlib import Path
import platform
import re
import sys

CHANNELS = (1, 6, 11, 36, 40, 44, 48)
KEY_NAMES = ("aes_kek_generation_source", "aes_key_generation_source")
MASTER_KEYS = {1: "master_key_00", 3: "master_key_12"}
CIV7_PASSPHRASE_HEX = "cb964487b449f4208b1eabee6e927f8947fad3d88c37"


async def scan(keys, phy=None, ifname="civ7-ldn", channels=None, protocols=(1, 3),
               dwell=0.3, rounds=3, local_id=None):
    """Scan for LDN networks. Returns {mac: network_info}."""
    ldn = importlib.import_module("ldn")
    channels = channels or list(CHANNELS)
    found = {}

    # A host may advertise between channel visits, so repeat the scan.
    for i in range(rounds):
        print(
            f"Scan {i + 1}/{rounds}: channels {channels}, protocols {list(protocols)}",
            flush=True,
        )
        networks = await ldn.scan(
            keys,
            ifname=ifname,
            phyname=phy,
            channels=channels,
            dwell_time=dwell,
            protocols=protocols,
        )
        for info in networks:
            if local_id is None or info.local_communication_id == local_id:
                found[str(info.address).lower()] = info

    for info in found.values():
        _show_network(info)

    print(f"\n{len(found)} LDN network(s) found.", flush=True)
    return found


def build_connect_params(info, keys, name="Civ7-PC", passphrase_hex=CIV7_PASSPHRASE_HEX,
                         app_version=None, phy=None, ifname="civ7-ldn", nx_platform=True):
    """Build ConnectNetworkParam from a scanned network."""
    ldn = importlib.import_module("ldn")
    if info.accept_policy == ldn.ACCEPT_NONE:
        raise RuntimeError("Host is not accepting new participants.")
    if info.num_participants >= info.max_participants:
        raise RuntimeError("Network is full.")

    # Preserve the version advertised by the host unless explicitly overridden.
    param = ldn.ConnectNetworkParam()
    param.keys = keys
    param.network = info
    param.phyname = phy
    param.ifname = ifname
    param.name = name.encode("utf-8")
    param.app_version = info.app_version if app_version is None else app_version
    param.platform = ldn.PLATFORM_NX if nx_platform else ldn.PLATFORM_OUNCE
    param.password = bytes.fromhex(passphrase_hex) if passphrase_hex else b""
    return param


def load_keys(path, protocols=(1, 3)):
    """Load prod.keys and validate required entries for the given protocols."""
    ldn = importlib.import_module("ldn")
    path = Path(path).expanduser()
    try:
        keys = ldn.load_keys(str(path))
    except OSError as e:
        raise RuntimeError(f"Cannot read key file {path}: {e.strerror}") from e
    except (ValueError, UnicodeError) as e:
        raise RuntimeError("Malformed key file.") from e

    # LDN needs different key entries for each selected protocol version.
    required = (*KEY_NAMES, *(MASTER_KEYS[p] for p in protocols))
    missing = [n for n in required if n not in keys]
    if missing:
        raise RuntimeError("Missing keys: " + ", ".join(missing))
    if any(len(keys[n]) != 16 for n in required):
        raise RuntimeError("AES keys must be exactly 16 bytes.")
    return keys


def doctor(phy=None, ifname="civ7-ldn", keys_path=None):
    """Run a read-only diagnostic check. Returns exit code."""
    print(f"Python: {sys.version.split()[0]} ; platform: {sys.platform}")
    errors = hardware_check(phy, ifname)
    for pkg in ("ldn", "trio", "python-netlink", "pycryptodome"):
        try:
            print(f"{pkg}: {importlib.metadata.version(pkg)}")
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing dependency: {pkg}")

    if keys_path:
        if Path(keys_path).expanduser().is_file():
            print("Key file present (not read by doctor).")
        else:
            errors.append(f"Key file not found: {keys_path}")

    for e in errors:
        print(f"[!] {e}")
    print("Read-only diagnostic; no scan or network change performed.")
    return 1 if errors else 0


def install_ip_fallback():
    """Monkey-patch LDN to handle missing host announcement after auth.

    If the host announcement is missing after authentication, the IP
    follows the LDN slot: 169.254.<network>.<slot+1>.
    """
    ldn = importlib.import_module("ldn")
    original = ldn.STANetwork._initialize_network

    async def _initialize(self):
        try:
            await original(self)
            return
        except ConnectionError as e:
            if "IP address" not in str(e):
                raise

        # Authentication succeeded; only the host's IP announcement is absent.
        network = self._network
        host = network.participants[0]
        free = [i for i, p in enumerate(network.participants) if not p.connected]
        if not free:
            raise ConnectionError("No free LDN slot to deduce our IP")

        self._network_id = int(host.ip_address.split(".")[2])
        self._participant_id = free[0]
        me = ldn.ParticipantInfo(
            ip_address=f"169.254.{self._network_id}.{free[0] + 1}",
            connected=True, mac_address=self._interface.address(),
            name=self._param.name, app_version=self._param.app_version,
            platform=self._param.platform,
        )
        network.participants[free[0]] = me
        print(
            f"[LDN] No host announcement; deduced IP: {me.ip_address} (slot {free[0]})",
            flush=True,
        )
        await self._interface.add_address(me.ip_address, f"169.254.{self._network_id}.255")
        await self._interface.add_neighbor(host.ip_address, host.mac_address)

    ldn.STANetwork._initialize_network = _initialize


def select_phy(phy=None):
    """Select the only available radio, or require an explicit choice."""
    if phy is not None:
        return phy

    root = Path("/sys/class/ieee80211")
    radios = sorted(p.name for p in root.iterdir()) if root.exists() else []
    if len(radios) != 1:
        raise RuntimeError(
            f"Available Wi-Fi radios: {', '.join(radios) or 'none'}. "
            "Select one with --phy."
        )
    return radios[0]


def hardware_check(phy=None, ifname="civ7-ldn"):
    """Return a list of hardware/environment problems (empty = OK)."""
    errors = []
    if sys.platform != "linux":
        errors.append("LDN requires Linux with direct Wi-Fi hardware access.")
    if sys.version_info < (3, 12):
        errors.append("Python 3.12+ is required.")

    # The requested radio must exist before the library creates its interface.
    radios = Path("/sys/class/ieee80211")
    available = sorted(p.name for p in radios.iterdir()) if radios.exists() else []
    if phy not in available:
        errors.append(f"Radio {phy} not found. Available: {', '.join(available) or 'none'}.")
        if "microsoft" in platform.release().lower():
            errors.append("WSL does not provide the Wi-Fi access LDN requires.")

    # LDN creates this interface on connect, so an existing name would collide.
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", ifname):
        errors.append("Invalid interface name (1-15 alphanumeric, - or _).")
    elif (Path("/sys/class/net") / ifname).exists():
        errors.append(f"Interface {ifname} already exists; pick a different name.")

    # A copied Python helper can satisfy these permissions without running as root.
    if sys.platform == "linux" and os.geteuid() != 0:
        status = Path("/proc/self/status").read_text()
        match = re.search(r"^CapEff:\s*([0-9a-fA-F]+)$", status, re.M)
        caps = int(match[1], 16) if match else 0
        required = (1 << 12) | (1 << 13)
        if caps & required != required:
            errors.append("Needs root or CAP_NET_ADMIN + CAP_NET_RAW.")
    return errors


def _show_network(info):
    print(
        f"\nHost {info.address} | local_id=0x{info.local_communication_id:016x} "
        f"| scene={info.scene_id}"
    )
    print(
        f"  channel={info.channel} | protocol={info.protocol} "
        f"| ldn_version={info.version} | app_version={info.app_version}"
    )
    print(
        f"  participants={info.num_participants}/{info.max_participants} "
        f"| accept={info.accept_policy} | security={info.security_mode}"
    )
    for p in info.participants:
        if p.connected:
            name = p.name.decode("utf-8", "replace")
            print(f"  participant={name!r} | IP={p.ip_address} | MAC={p.mac_address}")
