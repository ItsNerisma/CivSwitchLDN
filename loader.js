// Find and verify the Remote JS Loader on the restored Wi-Fi network.
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");

const PORT = 9026;
const CONNECT_TIMEOUT = 450;
const RESPONSE_TIMEOUT = 1000;
const PROBE_TIMEOUT = CONNECT_TIMEOUT + RESPONSE_TIMEOUT;
const SCAN_CONCURRENCY = 256;

async function discoverLoader(phy, deadline = Infinity) {
  const candidates = localCandidates(phy);
  if (!candidates.length) return [];

  let next = 0;
  let found = null;
  const controller = new AbortController();
  const workers = Math.min(SCAN_CONCURRENCY, candidates.length);

  await Promise.all(Array.from({ length: workers }, async () => {
    while (!found && next < candidates.length && Date.now() < deadline) {
      const ip = candidates[next++];
      const timeout = Math.min(PROBE_TIMEOUT, deadline - Date.now());
      if (await probeLoader(ip, timeout, controller.signal)) {
        if (!found) {
          found = ip;
          controller.abort();
        }
        return;
      }
    }
  }));

  return found ? [found] : [];
}

function probeLoader(ip, timeout = PROBE_TIMEOUT, signal) {
  if (timeout <= 0 || signal?.aborted) return Promise.resolve(false);
  return new Promise((resolve) => {
    let response = "";
    let settled = false;
    let timer;
    const probeDeadline = Date.now() + timeout;
    const sock = net.createConnection({ host: ip, port: PORT });
    const finish = (found) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      sock.destroy();
      resolve(found);
    };
    const abort = () => finish(false);
    const armTimeout = (limit) => {
      clearTimeout(timer);
      const remaining = probeDeadline - Date.now();
      if (remaining <= 0) return finish(false);
      timer = setTimeout(() => finish(false), Math.min(limit, remaining));
    };

    // Closed or filtered hosts get a short connect budget; a connected loader
    // gets a separate response budget to execute the harmless probe expression.
    signal?.addEventListener("abort", abort, { once: true });
    armTimeout(CONNECT_TIMEOUT);
    sock.once("connect", () => {
      armTimeout(RESPONSE_TIMEOUT);
      sock.end("1");
    });
    sock.on("data", (chunk) => {
      response += chunk;
      if (response.includes("Executed successfully")) finish(true);
      else if (response.length > 4096) finish(false);
    });
    sock.once("error", () => finish(false));
    sock.once("close", () => finish(false));
  });
}

function localCandidates(phy) {
  const targets = new Set();
  for (const [name, addresses] of Object.entries(os.networkInterfaces())) {
    let radio;
    try {
      radio = path.basename(fs.realpathSync(`/sys/class/net/${name}/phy80211`));
    } catch {
      continue;
    }
    if (radio !== phy) continue;

    for (const address of addresses) {
      if (address.family !== "IPv4" || address.internal || !address.netmask) continue;
      const mask = addressNumber(address.netmask);
      const count = (~mask >>> 0) + 1;
      if (count < 4 || count > 512) continue;

      const network = addressNumber(address.address) & mask;
      for (let offset = 1; offset < count - 1; offset++) {
        const value = (network + offset) >>> 0;
        const ip = [24, 16, 8, 0].map((shift) => (value >>> shift) & 255).join(".");
        if (ip !== address.address) targets.add(ip);
      }
    }
  }
  return [...targets];
}

function addressNumber(ip) {
  return ip.split(".").reduce((value, part) => (value << 8) | Number(part), 0) >>> 0;
}

module.exports = { PORT, probeLoader, discoverLoader };
