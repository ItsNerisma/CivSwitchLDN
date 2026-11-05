"""Arguments passed by run.js to the LDN injection client."""

import argparse
from pathlib import Path
import re


def build_parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--keys", type=Path, default="prod.keys")
    cli.add_argument("--phy", required=True, help="Wi-Fi radio selected by run.js")
    cli.add_argument("--ifname", default="civ7-ldn")
    cli.add_argument(
        "--host",
        type=_mac,
        help="host MAC; auto-selected when only one network is found",
    )
    return cli


def _mac(value):
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
        raise argparse.ArgumentTypeError("MAC expected, e.g. aa:bb:cc:dd:ee:ff")
    return value.lower()
