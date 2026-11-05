#!/usr/bin/env node
/** Compress and inject over LDN, restore networking, then offer the installer. */
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const path = require("path");
const readline = require("readline/promises");
const compress = require("./compress");

const PAYLOAD_PATH = path.join(__dirname, "payloads", "core.js");
const PYTHON = path.join(__dirname, "ldn", ".venv", "bin", "python-ldn");
const INSTALLER_PYTHON = path.join(__dirname, "ldn", ".venv", "bin", "python");
const PORT = 9026;

function parseArgs(args) {
  const opts = { keys: path.join(__dirname, "prod.keys"), ifname: "civ7-ldn" };
  const values = {
    "--keys": "keys", "--phy": "phy", "--ifname": "ifname",
    "--payload": "payload", "--host": "host", "--switch-ip": "switchIP",
  };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (values[arg]) {
      if (!args[i + 1] || args[i + 1].startsWith("--")) {
        throw new Error(`Missing value for ${arg}`);
      }
      opts[values[arg]] = args[++i];
    } else if (arg === "--skip-inject") {
      opts.skipInject = true;
    } else if (arg === "--help" || arg === "-h") {
      opts.help = true;
    } else if (!arg.startsWith("-") && !opts.payload) {
      opts.payload = arg;
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

function runCommand(command, args, input) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: __dirname,
      stdio: [input === undefined ? "inherit" : "pipe", "inherit", "inherit"],
    });
    // Keep Node alive until network.sh has restored networking on interruption.
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
  const lines = await compress(fs.readFileSync(PAYLOAD_PATH, "utf8"));
  console.log(`${lines.length} chat lines ready.`);
  const args = [
    path.join(__dirname, "network.sh"), "--phy", phy,
    PYTHON, path.join(__dirname, "ldn", "main.py"), "join",
    "--keys", path.resolve(opts.keys), "--phy", phy, "--ifname", opts.ifname, "--chat-stdin",
  ];
  if (opts.host) args.push("--host", opts.host);
  await runCommand("bash", args, lines.join("\n") + "\n");
}

function sendPayload(ip, filePath) {
  return new Promise((resolve, reject) => {
    const data = fs.readFileSync(filePath);
    console.log(`Sending ${filePath} (${data.length} bytes) to ${ip}:${PORT}`);
    const sock = net.createConnection({ host: ip, port: PORT }, () => sock.end(data));
    sock.setTimeout(30000, () => sock.destroy(new Error("Payload connection timed out.")));
    sock.on("data", (chunk) => process.stdout.write(chunk));
    sock.once("end", resolve);
    sock.once("error", reject);
  });
}

async function askSwitchIP(prompt, value) {
  if (value) return value;
  if (!prompt) throw new Error("Use --switch-ip with the IP displayed by the console's Remote JS Loader.");
  console.log("Wait for 'Awaiting payload' on the console. Use its Wi-Fi IP, after LDN has closed.");
  while (true) {
    const ip = (await prompt.question("Console IP: ")).trim();
    if (net.isIPv4(ip)) return ip;
    console.log("Enter a valid IPv4 address.");
  }
}

async function main(args = process.argv.slice(2)) {
  const opts = parseArgs(args);
  if (opts.help) {
    console.log("Usage: npm start -- [--keys path] [--phy radio] [--host lobby-mac]");
    console.log("Optional: --payload file.js --switch-ip console-ip --skip-inject");
    return;
  }
  if (opts.payload && !fs.existsSync(opts.payload)) throw new Error(`Payload not found: ${opts.payload}`);
  if (!opts.skipInject) await injectViaLDN(opts);

  const prompt = process.stdin.isTTY ? readline.createInterface({ input: process.stdin, output: process.stdout }) : null;
  try {
    if (opts.payload) {
      opts.switchIP = await askSwitchIP(prompt, opts.switchIP);
      await sendPayload(opts.switchIP, opts.payload);
    }
    if (prompt) {
      const answer = await prompt.question("Run the persistent installer? This replaces the game's single-player saves. [y/N] ");
      if (answer.trim().toLowerCase() === "y") {
        const ip = await askSwitchIP(prompt, opts.switchIP);
        await runCommand(INSTALLER_PYTHON, [
          path.join(__dirname, "installer", "install.py"), ip, String(PORT), PAYLOAD_PATH,
        ]);
      }
    } else {
      console.log("To install later: ldn/.venv/bin/python installer/install.py <console-ip>");
    }
  } finally {
    prompt?.close();
  }
  console.log("Done.");
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exitCode = 1;
  });
}
