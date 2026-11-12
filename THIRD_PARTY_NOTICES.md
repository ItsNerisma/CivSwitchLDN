# Third-party notices

CivSwitchLDN as a combined application is distributed under GNU GPL version 3
only; see [LICENSE](LICENSE). The original code contributed by ItsNerisma is
also under `GPL-3.0-only`, copyright (c) 2026 ItsNerisma. The components below
retain their upstream licenses and copyright notices.

## CivSwitch — Gezine — MIT

- Upstream: [Gezine/CivSwitch](https://github.com/Gezine/CivSwitch).
- Source revision: [`3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f`](https://github.com/Gezine/CivSwitch/tree/3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f).
- Copyright (c) 2026 Gezine.
- Full notice: [LICENSES/Gezine-MIT.txt](LICENSES/Gezine-MIT.txt).

Paths in the upstream column are relative to that source revision. These files
are copied or adapted from CivSwitch and remain available separately under MIT:

| Repository file | Upstream file |
| --- | --- |
| `compress.js` | `PicoSwitch/compress.js` |
| `payloads/core.js` | `core.js` |
| `payloads/helloworld.js` | `payloads/helloworld.js` |
| `installer/install.py` | `installer-creator/install.py` |
| `installer/compress_stage.js` | `installer-creator/compress_stage.js` |
| `installer/save_template.bin` | `installer-creator/save_template.bin` |

Local adaptations include a reusable compressor for LDN chat delivery, the
repository's default installer payload path, Wi-Fi reconnection status messages
in `payloads/core.js`, and source/license annotations.
The exploit, Remote JS Loader and persistent installer originate from Gezine.
Preserve Gezine's full MIT notice when redistributing these files or substantial
portions of them, including compressed or generated copies.

## UDP installer transfer — SeanHeuc's ESP32 CivSwitch port

- Reference implementation: [SeanHeuc/CivSwitch `esp32-ldn-civ7`](https://github.com/SeanHeuc/CivSwitch/tree/main/esp32-ldn-civ7), especially [`tools/udp_loader.js`](https://github.com/SeanHeuc/CivSwitch/blob/main/esp32-ldn-civ7/tools/udp_loader.js) and [`main/installer.c`](https://github.com/SeanHeuc/CivSwitch/blob/main/esp32-ldn-civ7/main/installer.c).
- `installer/udp_loader.js` adapts its UDP-over-LDN transfer approach: indexed template/script chunks, requests for missing chunks, and installation before switching to the TCP loader.
- SeanHeuc's project carries the CivSwitch MIT license and retains Gezine's copyright notice; the full MIT notice above applies to the reused/adapted CivSwitch portions.

The adaptation for this repository adds the PC-side UDP sender and an explicit
installation result acknowledgement. The transfer design is credited to
SeanHeuc; the exploit and save installer remain from Gezine.

## LDN — Kinnay (Yannik Marchand) — GPLv3

- Upstream: [kinnay/LDN](https://github.com/kinnay/LDN).
- Package: `ldn==0.0.21`, declared in [ldn/requirements.txt](ldn/requirements.txt).
- Upstream license declaration: [setup.py](https://github.com/kinnay/LDN/blob/master/setup.py) (`GPLv3`).
- Full license: [LICENSES/LDN-GPL-3.0.txt](LICENSES/LDN-GPL-3.0.txt).

LDN is installed as a Python dependency. The application imports it directly;
the combined application is distributed under GPLv3. In particular,
`ldn/connection.py` installs a runtime fallback for a missing host IP
announcement. This application-side behavior is a local adaptation and should
not be attributed to the upstream library.

If distributing a binary or bundle containing LDN, provide its corresponding
source for the exact distributed version, including any changes, together with
the application's corresponding source and the necessary build/install scripts,
as required by GPLv3 section 6. Keep upstream notices and mark modifications
with their relevant dates. A dependency declaration alone does not provide the
corresponding source for a binary release.

## Other installed dependencies

Other npm and Python packages retain their own licenses. npm dependency versions
and available license metadata are recorded in `package-lock.json`; Python
dependencies are declared in `ldn/requirements.txt`. When bundling installed
dependencies, preserve their applicable license texts and notices as well.
