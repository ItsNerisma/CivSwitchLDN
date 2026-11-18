Persistent installer adapted from [Gezine/CivSwitch](https://github.com/Gezine/CivSwitch/blob/3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f/installer-creator), commit `3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f`.

`install.py` prepares the installer assets for this repository's automatic LDN flow. `compress_stage.js` and [save_template.bin](https://github.com/Gezine/CivSwitch/blob/3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f/installer-creator/save_template.bin) are included from the same version. Gezine's original MIT license is preserved in [LICENSES/Gezine-MIT.txt](../LICENSES/Gezine-MIT.txt).

For the automatic LDN flow, [install.py](install.py) prepares the Base64 save template and installer script. [run.js](../run.js) injects the receiver through lobby chat and sends both assets in indexed chunks over UDP port 9027. The receiver requests missing chunks, then confirms when it has them all. The PC closes LDN and restores Wi-Fi while the console installs the save from memory. The console reports `INSTALL DONE` when installation finishes and starts the TCP Remote JS Loader on port 9026.

The installer replaces the game's single-player saves. Run it with `npm start` and keep the game open until `INSTALL DONE` appears. Restart the game and select **Load Game** to start the loader again.

The UDP transfer approach is adapted from [SeanHeuc's ESP32 CivSwitch port](https://github.com/SeanHeuc/CivSwitch/tree/main/esp32-ldn-civ7); see [the third-party notices](../THIRD_PARTY_NOTICES.md).
