"""Civ VII lobby handshake and chat delivery, running on Trio."""

from collections import deque
from pathlib import Path
import socket
import struct
import sys
import time

import trio

import protocol
import transport


async def run(args, network):
    """Send the lobby handshake and chat while the LDN link is open."""
    host_ip = str(network.info().participants[0].ip_address)
    local_ip = str(network.participant().ip_address)
    session = LobbySession(args, local_ip, host_ip, read_chat_lines(args))

    await warmup_arp(args.ifname, local_ip, host_ip)

    # Bind game traffic to LDN so the normal network cannot receive it.
    with trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, args.ifname.encode() + b"\0")
        await sock.bind((local_ip, protocol.PORT))
        return await session.run(sock)


class LobbySession:
    """Own the handshake state, transport and scheduled chat messages."""

    def __init__(self, args, local_ip, host_ip, chat_lines):
        self.args = args
        self.host_ip = host_ip
        self.chat_lines = chat_lines

        # FireCONN carries the game's introduction inside an LDN F packet.
        intro = protocol.introduction(identity=args.name, name=args.name)
        body = protocol.connection_payload(host_ip, intro, ip_order=args.ip_order, pad=args.lobby_pad)
        self.initial = protocol.ip_bytes(host_ip, args.ip_order) + b"F" + body
        self.transport = transport.Transport(local_ip, host_ip, self.initial, ip_order=args.ip_order)

        self.follow = deque()
        self.last_sent = None
        self.joined = False
        self.received = 0

    async def run(self, sock):
        # Allow every chat line plus the handshake and final linger to complete.
        duration = max(self.args.duration, 15 + self.args.chat_delay * len(self.chat_lines))
        start = next_attempt = time.monotonic()
        attempts = 0

        while time.monotonic() - start < duration:
            now = time.monotonic()

            # Retry the introduction until the host acknowledges the join.
            if not self.joined and attempts < 3 and now >= next_attempt:
                attempts += 1
                await self.send(sock, self.initial, f"FireCONN attempt {attempts}/3")
                next_attempt = now + 3.0

            if not await self.receive(sock):
                return 2

            await self.send_pending(sock)

            # Keep the link open briefly after the last message for host replies.
            linger_done = (
                self.last_sent is not None
                and not self.follow
                and time.monotonic() - self.last_sent >= 5.0
            )
            if linger_done:
                print("All messages sent; linger timeout reached.", flush=True)
                break

        print(f"Lobby done: {self.received} message(s) received.", flush=True)
        if not self.joined or self.follow or self.last_sent is None:
            print("Lobby handshake or chat delivery did not complete.", flush=True)
            return 3
        return 0

    async def receive(self, sock):
        """Process one datagram. Return False if the host refuses or closes."""
        data = None
        with trio.move_on_after(0.1):
            data, addr = await sock.recvfrom(65535)

        if data is None or addr != (self.host_ip, protocol.PORT):
            return True

        # The transport handles ordering and retransmissions before game parsing.
        bodies, responses, detail = self.transport.receive(data)
        print(f"RX {detail}", flush=True)

        if self.transport.learned_order:
            print(f"[info] host uses {self.transport.learned_order} byte order", flush=True)
            self.transport.learned_order = None

        for response in responses:
            await self.send(sock, response, "transport response")

        for body in bodies:
            self.received += 1
            description = protocol.describe(body)
            print(f"[msg] {description}", flush=True)

            refused = body.startswith((protocol.REFUSED, protocol.CLOSE))
            rejected = description.startswith(("NetJoinRefused", "NetKicked"))
            if refused or rejected:
                print("Refused/closed by host.", flush=True)
                return False

            welcome = body.startswith(protocol.REPLY) or description.startswith("NetWelcome")
            if not self.joined and welcome:
                self.schedule_messages(body)

        return True

    async def send_pending(self, sock):
        # Transport sequence numbers are assigned when a message is sent.
        while self.follow and time.monotonic() >= self.follow[0][0]:
            _, name, build = self.follow.popleft()
            packet = self.transport.queue(build(len(self.transport.sent)))
            await self.send(sock, packet, f"{name} (seq {self.transport.next_seq - 1})")
            self.last_sent = time.monotonic()

        for packet in self.transport.timers(time.monotonic()):
            await self.send(sock, packet, "keepalive R/V")

    def schedule_messages(self, welcome):
        slot = struct.unpack_from("<I", welcome, 40)[0] if len(welcome) >= 44 else 1
        print(f"[info] assigned slot: {slot}", flush=True)
        sender = 0 if self.args.chat_sender == "host" else slot
        now = time.monotonic()

        # Register with the game before injecting any chat messages.
        self.follow.extend([
            (now + 0.3, "NetRegister", protocol.net_register),
            (now + 0.6, "NetAppRegister", lambda n: protocol.net_app_register(n, slot)),
            (now + 1.0, "NetSnapshotProcessed", protocol.net_snapshot_processed),
        ])

        for i, line in enumerate(self.chat_lines):
            self.follow.append((
                now + 2.0 + self.args.chat_delay * i,
                f"NetChat[{i + 1}/{len(self.chat_lines)}]",
                lambda n, text=line: protocol.net_chat_public(n, text, sender),
            ))
        self.joined = True

    async def send(self, sock, data, reason):
        await sock.sendto(data, (self.host_ip, protocol.PORT))
        print(f"TX {reason} ({len(data)}B)", flush=True)


def read_chat_lines(args):
    if args.chat_stdin:
        lines = sys.stdin.read().splitlines()
    elif args.chat_file:
        lines = args.chat_file.read_text(encoding="utf-8").splitlines()
    elif args.chat:
        lines = [args.chat]
    else:
        lines = []

    return [line for line in lines if line.strip()]


async def warmup_arp(device, local_ip, host_ip):
    """Prime address resolution before starting the UDP handshake."""
    try:
        address = Path(f"/sys/class/net/{device}/address").read_text().strip()
        mac = bytes.fromhex(address.replace(":", ""))
        frame = transport.arp_request(mac, local_ip, transport.neighbor_mac(device, host_ip), host_ip)

        with socket.socket(socket.AF_PACKET, socket.SOCK_RAW) as raw:
            raw.bind((device, 0))
            for _ in range(2):
                raw.send(frame)
                await trio.sleep(0.1)

        print("[ARP] warmup sent", flush=True)
    except (OSError, ValueError) as e:
        print(f"[ARP] warmup failed: {e}", flush=True)
    await trio.sleep(0.3)
