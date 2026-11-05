#!/usr/bin/env node
/**
 * Compress and inject over LDN, wait for the Remote JS Loader, then offer the installer.
 *
 * Usage: npm start -- [options]
 *   --keys <file>       Your prod.keys file (default: ./prod.keys)
 *   --phy <radio>       Wi-Fi radio (auto-detected if there is only one)
 *   --ifname <name>     Temporary LDN interface (default: civ7-ldn)
 *   --host <mac>        LDN host MAC when more than one lobby is found
 *   --switch-ip <ip>    Console's Wi-Fi IP; skips LAN discovery
 *   --help              Show a short usage summary
 */
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const readline = require("readline/promises");
const { setTimeout: sleep } = require("timers/promises");
const compress = require("./compress");

const PAYLOAD_PATH = path.join(__dirname, "payloads", "core.js");
const PYTHON = path.join(__dirname, "ldn", ".venv", "bin", "python-ldn");
const INSTALLER_PYTHON = path.join(__dirname, "ldn", ".venv", "bin", "python");
const PORT = 9026;

function parseArgs(args) {
  const opts = { keys: path.join(__dirname, "prod.keys"), ifname: "civ7-ldn" };
  const values = {
    "--keys": "keys", "--phy": "phy", "--ifname": "ifname",
    "--host": "host", "--switch-ip": "switchIP",
  };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (values[arg]) {
      if (!args[i + 1] || args[i + 1].startsWith("--")) {
        throw new Error(`Missing value for ${arg}`);
      }
      opts[values[arg]] = args[++i];
    } else if (arg === "--help" || arg === "-h") {
      opts.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (opts.switchIP && !net.isIPv4(opts.switchIP)) throw new Error("Invalid --switch-ip address.");
  return opts;
}

function selectPhy(phy) {
  if (phy) return phy;
  const directory = "/sys/class/ieee80211";
  if (!fs.existsSync(directory)) throw new Error("No Wi-Fi radio found. LDN requires Linux with direct Wi-Fi access.");
  const radios = fs.readdirSync(directory);
  if (radios.length !== 1) {
    throw new Error(`Available Wi-Fi radios: ${radios.join(", ") || "none"}. Select one with --phy.`);
  }
  return radios[0];
}

function addressNumber(ip) {
  return ip.split(".").reduce((value, part) => (value << 8) | Number(part), 0) >>> 0;
}

function localCandidates(phy) {
  const interfaces = os.networkInterfaces();
  const targets = new Set();

  for (const [name, addresses] of Object.entries(interfaces)) {
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

function probeLoader(ip) {
  return new Promise((resolve) => {
    let response = "";
    const sock = net.createConnection({ host: ip, port: PORT }, () => sock.end("1"));
    sock.setTimeout(1500, () => sock.destroy());
    sock.on("data", (chunk) => {
      response += chunk;
      if (response.length > 4096) sock.destroy();
    });
    sock.once("error", () => resolve(false));
    sock.once("close", () => resolve(response.includes("Executed successfully")));
  });
}

async function discoverLoader(phy, deadline = Infinity) {
  const candidates = localCandidates(phy);
  const matches = [];
  let next = 0;
  const workers = Array.from({ length: Math.min(32, candidates.length) }, async () => {
    while (next < candidates.length && Date.now() < deadline) {
      const ip = candidates[next++];
      if (await probeLoader(ip)) matches.push(ip);
    }
  });
  await Promise.all(workers);
  return next < candidates.length ? [] : matches;
}

function runCommand(command, args, input) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: __dirname,
      stdio: [input === undefined ? "inherit" : "pipe", "inherit", "inherit"],
    });
    // Keep Node alive until bash/network.sh has restored networking on interruption.
    const interrupt = () => child.kill("SIGTERM");
    process.on("SIGINT", interrupt);
    process.on("SIGTERM", interrupt);
    const cleanup = () => {
      process.off("SIGINT", interrupt);
      process.off("SIGTERM", interrupt);
    };
    child.once("error", (error) => { cleanup(); reject(error); });
    child.once("close", (code, signal) => {
      cleanup();
      if (code === 0) resolve();
      else reject(new Error(`${path.basename(command)} exited with ${signal || `code ${code}`}`));
    });
    if (input !== undefined) {
      child.stdin.on("error", (error) => {
        if (error.code !== "EPIPE") reject(error);
      });
      child.stdin.end(input);
    }
  });
}

async function injectViaLDN(opts) {
  if (!fs.existsSync(opts.keys)) {
    throw new Error(`Place your own prod.keys, dumped from your Switch, at ${opts.keys}.`);
  }
  const phy = selectPhy(opts.phy);
  opts.phy = phy;
  const lines = await compress(fs.readFileSync(PAYLOAD_PATH, "utf8"));
  console.log(`${lines.length} chat lines ready.`);
  const args = [
    path.join(__dirname, "bash", "network.sh"), "--phy", phy,
    PYTHON, path.join(__dirname, "ldn", "main.py"),
    "--keys", path.resolve(opts.keys), "--phy", phy, "--ifname", opts.ifname,
  ];
  if (opts.host) args.push("--host", opts.host);
  await runCommand("bash", args, lines.join("\n") + "\n");
}

async function askSwitchIP(prompt) {
  console.log("Wait for 'Awaiting payload' on the console. Use its Wi-Fi IP, after LDN has closed.");
  while (true) {
    const ip = (await prompt.question("Console IP: ")).trim();
    if (net.isIPv4(ip)) return ip;
    console.log("Enter a valid IPv4 address.");
  }
}

async function waitForLoader(opts, prompt) {
  const deadline = Date.now() + 60000;
  console.log(`Waiting for the Remote JS Loader on port ${PORT}...`);

  while (Date.now() < deadline) {
    if (opts.switchIP) {
      if (await probeLoader(opts.switchIP)) return opts.switchIP;
    } else {
      const matches = await discoverLoader(opts.phy, deadline);
      if (matches.length === 1) return matches[0];
      if (matches.length > 1) {
        console.log(`Multiple loaders found: ${matches.join(", ")}.`);
        opts.switchIP = await askSwitchIP(prompt);
      }
    }

    const remaining = deadline - Date.now();
    if (remaining > 0) await sleep(Math.min(2000, remaining));
  }

  if (!opts.switchIP) {
    console.log("Automatic discovery timed out. Enter the console IP shown by the loader.");
    opts.switchIP = await askSwitchIP(prompt);
    return waitForLoader(opts, prompt);
  }
  throw new Error(`Remote JS Loader not found on port ${PORT}. Check the console and Wi-Fi connection.`);
}

async function main(args = process.argv.slice(2)) {
  const opts = parseArgs(args);
  if (opts.help) {
    console.log("Usage: npm start -- [--keys path] [--phy radio] [--ifname name] [--host lobby-mac] [--switch-ip console-ip]");
    return;
  }

  const prompt = readline.createInterface({ input: process.stdin, output: process.stdout });
  try {
    await injectViaLDN(opts);
    opts.switchIP = await waitForLoader(opts, prompt);
    console.log(`Remote JS Loader ready at ${opts.switchIP}:${PORT}`);

    const answer = await prompt.question("Run the persistent installer? [y/N] ");
    if (answer.trim().toLowerCase() === "y") {
      await runCommand(INSTALLER_PYTHON, [
        path.join(__dirname, "installer", "install.py"), opts.switchIP, String(PORT), PAYLOAD_PATH,
      ]);
    }
  } finally {
    prompt.close();
  }
  console.log("Done.");
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exitCode = 1;
  });
}
