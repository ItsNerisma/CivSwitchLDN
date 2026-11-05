# CivSwitchLDN

> [!IMPORTANT]
> **[CivSwitch](https://github.com/Gezine/CivSwitch) is an exploit by [Gezine](https://github.com/Gezine).** This project delivers it through local wireless (LDN) :heart:.

## Requirements

- The **physical Switch 1 edition of Civilization VII, version 1.0.0**. See [CivSwitch](https://github.com/Gezine/CivSwitch#readme) for console firmware compatibility.
- A real Linux system (*WSL isn't supported yet*).
- Node.js 18+, Python 3.12+ with `venv`, and `setcap` (`libcap2-bin` on Debian/Ubuntu).
- A Switch 2, **on the same Wi-Fi network as the Linux system**.
- **Your own `prod.keys`, dumped from your own Switch.** Place it at the repository root before running.

## Usage

### 1. Install dependencies once.

```sh
npm install
```

Setup may ask for `sudo` to grant the Python helper its network permissions.

### 2. Setup the game

On the Switch, open Civilization VII and go to **MULTIPLAYER > WIRELESS > CREATE GAME (R stick press) > HOST LOBBY (+)**

### 3. Run the thing

> [!IMPORTANT]
> Wi-Fi will be **temporarily disabled** while the payload is being sent. It's a requirement for the LDN stuff. Once the exploit is triggered (or an error occurs), it will be re-enabled automatically.

Leave the lobby open, then run:

```sh
npm start
```

### 4. Persist the exploit (optional)

Once the Remote JS Loader is running on the console, you will be prompted on the Linux system to launch the persistent installer: type **`y`** to continue, or **`n`** to finish.

It will replace the game's single-player saves. Keep the game open until it prints **`INSTALL DONE`**. Afterwards, restart the game and select **Load Game** to start the loader again :tada:.

## How it works

`run.js` handles the sequence:

1. Compress `payloads/core.js` into 20 chat messages.
2. Temporarily release Wi-Fi for LDN, find a lobby, join it and send the messages.
3. Close LDN and restore networking, including on failure or interruption.
4. Offer Gezine's persistent installer after networking is restored, using the console's displayed IP.

## Project structure

```text
run.js              # Main flow and installer prompt
compress.js         # Payload compression for chat delivery
network.sh          # Temporary network suspension and restoration
setup.sh            # Dependency and permission setup
send_payload.js     # Optional JS payload sender
payloads/           # Gezine's exploit and an example payload
installer/          # Persistent installer and save template
ldn/                # LDN relative stuff
```

## Send a JS payload

Once the Remote JS Loader is running, send a JS file to the console IP shown on screen:

```sh
node send_payload.js <console-ip> payloads/helloworld.js
```

## Credits

- **[Gezine](https://github.com/Gezine)** for [CivSwitch](https://github.com/Gezine/CivSwitch), the exploit, Remote JS Loader and persistent installer. Reused files link to [their source version](https://github.com/Gezine/CivSwitch/tree/3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f). The original [MIT license](LICENSE) is included.
- **[Kinnay](https://github.com/kinnay)** for the [LDN library](https://github.com/kinnay/LDN), used as a Python dependency under GPL-3.0.
