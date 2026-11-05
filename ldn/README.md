# LDN client

This directory handles the local wireless part of CivSwitchLDN. `run.js` calls `main.py` to scan for a Civilization VII lobby, join it and send the compressed exploit through game chat.

The client always scans, joins a lobby and reads chat messages from stdin. Node selects the radio and manages network restoration. Scan timing and lobby settings are constants in the Python modules.

The code is split by responsibility:

- `main.py` checks the environment and starts the CLI.
- `cli.py` accepts the radio, key file, interface name and optional host MAC from Node.
- `session.py` discovers the host and keeps the LDN connection open during delivery.
- `lobby.py` performs the game handshake and schedules chat messages.
- `transport.py` handles ordered UDP packets and retransmissions.
- `protocol.py` builds and identifies Civilization VII messages.
- `connection.py` loads keys and configures the LDN library.

This client is part of CivSwitchLDN and is licensed under
[GNU GPL version 3 only](../LICENSE). It imports Kinnay's GPLv3
[`ldn==0.0.21`](https://github.com/kinnay/LDN) package, installed separately
through `requirements.txt`. The missing-host-announcement fallback in
`connection.py` is application-side behavior. See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for attribution and
redistribution details.
