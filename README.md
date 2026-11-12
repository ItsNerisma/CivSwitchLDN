# CivSwitchLDN

> [!IMPORTANT]
> **[CivSwitch](https://github.com/Gezine/CivSwitch) is an exploit by [Gezine](https://github.com/Gezine).** This project delivers it through local wireless (LDN) :heart:.

## Demo (don't blink)

No capture card, sorry 🫣​​

https://github.com/user-attachments/assets/fefe32c0-e343-43c3-b716-296bd97ffa70

## Requirements

- The **physical Switch 1 edition of Civilization VII, version 1.0.0**. See [CivSwitch](https://github.com/Gezine/CivSwitch#readme) for console firmware compatibility.
- A real Linux system (*WSL isn't supported yet*).
- Node.js 18+, Python 3.12+ with `venv`, and `setcap` (`libcap2-bin` on Debian/Ubuntu).
- A Switch 2, **on the same Wi-Fi network as the Linux system**.
- **Your own `prod.keys`, dumped from your own Switch 1.** Place it at the repository root before running.

## Usage

### 1. Install dependencies once.

```sh
npm install
```

Setup may ask for `sudo` to grant the Python helper its network permissions.

### 2. Setup the game

On the Switch, open Civilization VII and 
1. Go to "MULTIPLAYER" 
2. Choose "WIRELESS" 
3. Create a game *(R stick press)*
4. Host a lobby *(+ button)*

### 3. Run the thing

> [!IMPORTANT]
> NetworkManager will **temporarily disable all managed network connections** while the payload and installer are sent over LDN. Afterwards, the script restores the previous Wi-Fi connection. In `--no-persist` mode it also waits for an IPv4 address before looking for the Remote JS Loader. If restoration fails, reconnect Wi-Fi manually before using the loader.

Leave the lobby open, then run:

```sh
npm start
```

You may be asked for your sudo password to control NetworkManager if your sudo session has expired.

The output shows connection and delivery steps, with warnings and errors when needed. For packet traces and diagnostics, run `npm start -- --verbose`.

### 4. Install persistence during injection

By default, the initial LDN payload includes a small UDP receiver. While the LDN session is still active, the PC streams the installer and save template to the console in chunks over **UDP port 9027**; missing chunks are requested again automatically. After installing persistence, the console starts the regular Remote JS Loader on **TCP port 9026**. The PC restores its Wi-Fi connection and finishes without waiting for or scanning for the loader. To skip persistence, leave the loader running, and discover its IP immediately, use `npm start -- --no-persist`.

The ports serve different stages: UDP `9027` is a temporary bulk-transfer channel over LDN, while TCP `9026` is the loader used for later JS payloads over Wi-Fi.

The installer replaces the game's single-player saves. Keep the game open until it prints **`INSTALL DONE`**. Afterwards, restart the game and select **Load Game** to start the loader again :tada:.

### Send JS payloads

Once the Remote JS Loader is running, send a JS file to the console IP shown on screen:

```sh
node send_payload.js <console-ip> payloads/helloworld.js
```

The JS file is optional (default: `payloads/helloworld.js`), as is a third port argument (default: `9026`).

## How it works

`run.js` handles the sequence:

1. Add the small UDP installer receiver to `payloads/core.js` (unless `--no-persist` was passed), then compress it into chat messages. The large save template and installer script are prepared separately.
2. Temporarily release Wi-Fi for LDN, scan nearby LDN networks, connect to the selected host, join its Civilization VII lobby and send the messages.
3. While the LDN connection remains active, send the save template and installer script over UDP `9027`; the console requests retransmission of any missing chunks and confirms the installation result.
4. Close the LDN connection and attempt to restore networking, including on failure or interruption.
5. The console starts the Remote JS Loader on TCP `9026`. In persistence mode, finish after restoring the PC's network; in `--no-persist` mode, discover the loader IP.

## Troubleshooting

Use `--verbose` to see a timestamped trace of all packets exchanged with the lobby.

```sh
npm start -- --verbose
```

If the exploit fails on your hardware, try slowing down the handshake with `--handshake-scale` (default: 1.0). For example, `3` triples the delays between registration messages:

```sh
npm start -- --handshake-scale 3
```

You can adjust the delay between chat messages (default: 10 ms):

```sh
npm start -- --chat-delay 50
```

## Project structure

```text
run.js                   # Main flow and automatic installer transfer
loader.js                # Remote JS Loader verification and LAN discovery
compress.js              # Payload compression for chat delivery
send_payload.js          # Optional JS payload sender
bash/                    # Linux scripts (setup, network stuff...)
payloads/                # Gezine's exploit and an example payload
installer/               # Persistent installer, UDP receiver and save template
ldn/                     # LDN client, game protocol and transport
LICENSES/                # Original licenses for the upstream components
THIRD_PARTY_NOTICES.md   # Reused files, sources and license scope
```

## Licenses

CivSwitchLDN as a combined application, and the original code contributed by ItsNerisma, are licensed under the **GNU GPL version 3 only (`GPL-3.0-only`)**. See [LICENSE](LICENSE). Copyright (c) 2026 ItsNerisma.

The reused CivSwitch files retain **Gezine's MIT license and copyright**; they remain available separately under MIT. The **LDN library by Kinnay (Yannik Marchand)** is a GPLv3 dependency. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for file origins, adaptations and the preserved upstream notices.

When redistributing the application, include its license and third-party notices. Binary or bundled releases must also provide access to the complete corresponding source under the GPLv3 terms, including any included GPL dependencies and the scripts needed to build and install them. The software is provided without warranty; see the license texts for the full terms.

## Credits

- **[Gezine](https://github.com/Gezine)** for [CivSwitch](https://github.com/Gezine/CivSwitch), the exploit, Remote JS Loader and persistent installer. Reused files link to [their source version](https://github.com/Gezine/CivSwitch/tree/3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f).
- **[Kinnay](https://github.com/kinnay)** for the [LDN library](https://github.com/kinnay/LDN), used as a Python dependency under GPL-3.0.
- **[SeanHeuc](https://github.com/SeanHeuc)** for the UDP-over-LDN installer-transfer method, adapted from [their ESP32 CivSwitch port](https://github.com/SeanHeuc/CivSwitch/tree/main/esp32-ldn-civ7).