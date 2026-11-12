// SPDX-License-Identifier: MIT
// See LICENSES/Gezine-MIT.txt for the preserved upstream MIT notice.
// UDP receiver and transfer approach adapted from SeanHeuc's LDN installer channel:
// https://github.com/SeanHeuc/CivSwitch/tree/main/esp32-ldn-civ7/tools/udp_loader.js
// The PC sends A<header>, J/T<index>:<base64>, then G; the console returns
// D when all chunks arrive, or t/j indexes for retransmission. I:OK/I:ERR
// reports the installer result before the normal TCP loader starts.

function udp_fast_str(addr, len) {
    const codes = new Array(len);
    let i = 0;
    for (; i + 8 <= len; i += 8) {
        const v = read64(addr + BigInt(i));
        codes[i] = Number(v & 0xffn);
        codes[i + 1] = Number((v >> 8n) & 0xffn);
        codes[i + 2] = Number((v >> 16n) & 0xffn);
        codes[i + 3] = Number((v >> 24n) & 0xffn);
        codes[i + 4] = Number((v >> 32n) & 0xffn);
        codes[i + 5] = Number((v >> 40n) & 0xffn);
        codes[i + 6] = Number((v >> 48n) & 0xffn);
        codes[i + 7] = Number((v >> 56n) & 0xffn);
    }
    for (; i < len; i++) codes[i] = Number(read8(addr + BigInt(i)));
    let value = "";
    for (let k = 0; k < len; k += 4096) {
        value += String.fromCharCode.apply(null, codes.slice(k, k + 4096));
    }
    return value;
}

function udp_base64_decode(value) {
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const map = {};
    for (let i = 0; i < 64; i++) map[alphabet[i]] = i;
    const bytes = [];
    for (let i = 0; i + 3 < value.length; i += 4) {
        const c0 = map[value[i]], c1 = map[value[i + 1]];
        const p2 = value[i + 2] === "=", p3 = value[i + 3] === "=";
        const c2 = p2 ? 0 : map[value[i + 2]];
        const c3 = p3 ? 0 : map[value[i + 3]];
        const n = (c0 << 18) | (c1 << 12) | (c2 << 6) | c3;
        bytes.push((n >> 16) & 255);
        if (!p2) bytes.push((n >> 8) & 255);
        if (!p2 && !p3) bytes.push(n & 255);
    }
    let decoded = "";
    for (let i = 0; i < bytes.length; i++) decoded += String.fromCharCode(bytes[i]);
    return decoded;
}

async function core_udp_loader() {
    const UDP_PORT = 9027;
    const CHUNK_SIZE = 1100;
    const fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd === -1n) {
        await log("UDP socket failed");
        return;
    }

    const receiveSize = malloc(4);
    write32(receiveSize, 512 * 1024);
    setsockopt(fd, SOL_SOCKET, 0x1002, receiveSize, 4); // SO_RCVBUF

    for (let i = 0; i < 16; i++) write8(sockaddr_in + BigInt(i), 0);
    write8(sockaddr_in, 16n);
    write8(sockaddr_in + 1n, 2n);
    write16(sockaddr_in + 2n, BigInt(((UDP_PORT & 0xff) << 8) | (UDP_PORT >> 8)));
    write32(sockaddr_in + 4n, 0n);
    if (bind(fd, sockaddr_in, 16) === -1n) {
        await log("UDP bind failed on 9027");
        return;
    }

    await log("UDP PAYLOAD CHANNEL :9027");
    const buffer = malloc(2048);
    const tx = malloc(64);
    const template = [], apply = [];
    let needTemplate = 0, needApply = 0, received = 0;
    let gotTemplate = 0, gotApply = 0, connected = false, finished = false;

    function udp_tx(text) {
        for (let i = 0; i < text.length; i++) {
            write8(tx + BigInt(i), BigInt(text.charCodeAt(i)));
        }
        send(fd, tx, text.length, 0);
    }

    async function finish_install() {
        if (finished) return;
        finished = true;
        for (let i = 0; i < 3; i++) udp_tx("D");

        window.__tpl = template.slice(0, needTemplate);
        const source = udp_base64_decode(apply.slice(0, needApply).join(""));
        await log("RUNNING INSTALLER (" + source.length + " bytes)");
        window.__civswitchPersistOK = false;
        try {
            await eval(source);
        } catch (e) {
            await log("E: " + e.message);
            await log(e.stack);
        }

        const installed = window.__civswitchPersistOK === true;
        udp_tx(installed ? "I:OK" : "I:ERR");
        await log(installed ? "INSTALLER RETURNED" : "INSTALLER FAILED");
        await log("leaving ldn network.");
        await log("switching to TCP loader :9026");
        await remote_js_loader();
    }

    async function try_finish() {
        if (!finished && needTemplate && needApply &&
            gotTemplate >= needTemplate && gotApply >= needApply) {
            await finish_install();
        }
    }

    function request_missing() {
        let requested = 0;
        for (let i = 0; i < needTemplate && requested < 96; i++) {
            if (!template[i]) { udp_tx("t" + i); requested++; }
        }
        for (let i = 0; i < needApply && requested < 96; i++) {
            if (!apply[i]) { udp_tx("j" + i); requested++; }
        }
        return requested;
    }

    for (;;) {
        const length = Number(recv(fd, buffer, 2048, 0));
        if (length <= 0) continue;
        received++;
        if (finished) continue;

        let message;
        try { message = udp_fast_str(buffer, length); }
        catch (e) { message = ""; }
        if (!message) continue;

        try {
            const type = message[0];
            const colon = message.indexOf(":");
            if (type === "T" || type === "J") {
                const chunks = type === "T" ? template : apply;
                const count = type === "T" ? needTemplate : needApply;
                const index = Number(message.slice(1, colon));
                const data = message.slice(colon + 1);
                if (!Number.isInteger(index) || index < 0 || index >= count || colon < 0 ||
                    data.length < 1 || data.length > CHUNK_SIZE) continue;
                if (!chunks[index]) {
                    chunks[index] = data;
                    if (type === "T") gotTemplate++;
                    else gotApply++;
                }
                await try_finish();
            } else if (type === "A") {
                const secondColon = message.indexOf(":", colon + 1);
                if (colon < 0 || secondColon < 0) continue;
                needTemplate = Number(message.slice(1, colon));
                needApply = Number(message.slice(colon + 1, secondColon));
                if (!Number.isInteger(needTemplate) || needTemplate < 1 || needTemplate > 4000 ||
                    !Number.isInteger(needApply) || needApply < 1 || needApply > 1000) {
                    await log("Invalid UDP installer header");
                    continue;
                }
                if (secondColon > 0 && !connected) {
                    const ip = message.slice(secondColon + 1).split(".").map(Number);
                    if (ip.length === 4 && ip.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)) {
                        for (let i = 0; i < 16; i++) write8(sockaddr_in + BigInt(i), 0);
                        write8(sockaddr_in, 16n);
                        write8(sockaddr_in + 1n, 2n);
                        write16(sockaddr_in + 2n, BigInt(((UDP_PORT & 0xff) << 8) | (UDP_PORT >> 8)));
                        write32(sockaddr_in + 4n,
                            BigInt(ip[0]) | (BigInt(ip[1]) << 8n) |
                            (BigInt(ip[2]) << 16n) | (BigInt(ip[3]) << 24n));
                        connected = connect(fd, sockaddr_in, 16) === 0n;
                    }
                }
                await log("UDP header tpl=" + needTemplate + " js=" + needApply + (connected ? " (nak)" : ""));
                await try_finish();
            } else if (type === "G") {
                if (!connected) {
                    await log("UDP has no return path for chunk repairs");
                    continue;
                }
                const missing = request_missing();
                if (missing) await log("UDP repairing " + missing + " chunk(s), rx=" + received);
                else await try_finish();
            }
        } catch (e) {
            await log("UDP receiver: " + e.message);
        }
    }
}

core_udp_loader();
