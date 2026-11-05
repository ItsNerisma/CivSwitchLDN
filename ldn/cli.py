"""Command-line arguments for LDN diagnostics, discovery and injection."""

import argparse
import math
from pathlib import Path

import connection


def build_parser():
    cli = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = cli.add_subparsers(dest="command", required=True)

    for name in ("doctor", "scan", "join"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--keys", type=Path, default="prod.keys")
        cmd.add_argument("--phy", help="Wi-Fi radio (auto-detected when only one is available)")
        cmd.add_argument("--ifname", default="civ7-ldn")

        if name == "doctor":
            continue

        cmd.add_argument("--channels", type=_channels, default=list(connection.CHANNELS))
        cmd.add_argument(
            "--protocols",
            type=lambda v: [int(x) for x in v.split(",")],
            default=[1, 3],
        )
        cmd.add_argument("--dwell", type=_positive, default=0.3)
        cmd.add_argument("--rounds", type=int, default=3)

        if name == "scan":
            continue

        cmd.add_argument(
            "--host",
            type=_mac,
            help="host MAC from scan; auto-detected if only one network",
        )
        cmd.add_argument("--name", default="Civ7-PC")
        cmd.add_argument("--connect-timeout", type=_positive, default=10)
        cmd.add_argument("--duration", type=_positive, default=30)
        cmd.add_argument(
            "--chat-stdin",
            action="store_true",
            help="read chat lines from stdin (used by run.js)",
        )
        cmd.add_argument("--chat", help="single chat message to send")
        cmd.add_argument("--chat-file", type=Path, help="file with one chat line per line")
        cmd.add_argument("--chat-delay", type=_positive, default=0.5)
        cmd.add_argument("--chat-sender", choices=("host", "self"), default="self")
        cmd.add_argument("--ip-order", choices=("network", "reversed"), default="reversed")
        cmd.add_argument("--lobby-pad", type=int, default=4)

    return cli


def _positive(value):
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise argparse.ArgumentTypeError("positive number expected")
    return n


def _mac(value):
    import re
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
        raise argparse.ArgumentTypeError("MAC expected, e.g. aa:bb:cc:dd:ee:ff")
    return value.lower()


def _channels(value):
    nums = [int(x) for x in value.split(",")]
    valid = set(connection.CHANNELS)
    if not nums or any(n not in valid for n in nums):
        raise argparse.ArgumentTypeError(f"valid channels: {', '.join(map(str, valid))}")
    return list(dict.fromkeys(nums))


