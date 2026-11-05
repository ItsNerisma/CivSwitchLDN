"""Discover a host and keep LDN connected throughout chat delivery."""

import math

import ldn
import trio

import connection
import lobby


async def run(args):
    """Scan first, then keep the selected LDN connection open for the lobby."""
    keys = connection.load_keys(args.keys, args.protocols)
    found = await connection.scan(
        keys,
        phy=args.phy,
        ifname=args.ifname,
        channels=args.channels,
        protocols=args.protocols,
        dwell=args.dwell,
        rounds=args.rounds,
    )

    if args.command == "scan":
        return 0 if found else 1

    # Auto-selection is safe only when exactly one network was found.
    if args.host is None:
        if len(found) != 1:
            raise RuntimeError(f"{len(found)} networks found; specify --host MAC.")
        args.host = next(iter(found))
        print(f"Auto-selected host: {args.host}", flush=True)

    if args.host not in found:
        raise RuntimeError("Host not found. Check MAC, channels, keys.")

    info = found[args.host]
    param = connection.build_connect_params(
        info,
        keys,
        name=args.name,
        passphrase_hex=connection.CIV7_PASSPHRASE_HEX,
        phy=args.phy,
        ifname=args.ifname,
    )

    print(f"\nConnecting to {args.host}, name={args.name!r}", flush=True)

    with trio.fail_after(args.connect_timeout) as timeout:
        async with ldn.connect(param) as network_obj:
            # The deadline covers association, not the chat session.
            timeout.deadline = math.inf
            print(f"[LDN connected] PC LDN IP={network_obj.participant().ip_address}", flush=True)
            return await lobby.run(args, network_obj)


