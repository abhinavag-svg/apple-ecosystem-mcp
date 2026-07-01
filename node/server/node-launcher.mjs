#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { delimiter } from "node:path";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const srcPath = resolve(root, "src");
const libPath = resolve(root, "server", "lib");

function pythonVersion(command) {
  const probe = spawnSync(command, ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], {
    encoding: "utf8",
  });
  if (probe.status !== 0) {
    return null;
  }
  const [major, minor] = probe.stdout.trim().split(".").map((part) => Number.parseInt(part, 10));
  if (!Number.isInteger(major) || !Number.isInteger(minor)) {
    return null;
  }
  return { major, minor };
}

function findPython() {
  const candidates = [
    process.env.APPLE_ECOSYSTEM_MCP_PYTHON_COMMAND,
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "python3.14",
    "python3.13",
    "python3.12",
    "python3.11",
    "python3",
  ].filter(Boolean);

  for (const candidate of candidates) {
    const version = pythonVersion(candidate);
    if (version && (version.major > 3 || (version.major === 3 && version.minor >= 11))) {
      return candidate;
    }
  }
  return null;
}

const pythonCommand = findPython();
if (!pythonCommand) {
  console.error(
    [
      "Apple Ecosystem MCP requires Python 3.11 or newer.",
      "Claude Desktop's built-in Node.js started correctly, but no compatible Python interpreter was found.",
      "Install Python 3.11+ or set APPLE_ECOSYSTEM_MCP_PYTHON_COMMAND to a compatible interpreter.",
    ].join("\n"),
  );
  process.exit(127);
}
const pythonPath = [srcPath, libPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter);
const selectedVersion = pythonVersion(pythonCommand);
console.error(
  [
    "Apple Ecosystem MCP compatibility launcher starting",
    `root=${root}`,
    `python=${pythonCommand}`,
    `python_version=${selectedVersion ? `${selectedVersion.major}.${selectedVersion.minor}` : "unknown"}`,
    `src=${srcPath}`,
    `lib=${libPath}`,
  ].join("\n"),
);
const env = {
  ...process.env,
  PYTHONPATH: pythonPath,
};
const child = spawn(
  pythonCommand,
  ["-m", "apple_ecosystem_mcp", ...process.argv.slice(2)],
  {
    cwd: root,
    env,
    stdio: ["pipe", "pipe", "pipe"],
  },
);

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
child.stderr.pipe(process.stderr);

child.on("error", (error) => {
  console.error(
    [
      "Apple Ecosystem MCP Node compatibility launcher could not start the Python tool engine.",
      `Tried to run: ${pythonCommand} -m apple_ecosystem_mcp`,
      `PYTHONPATH included: ${pythonPath}`,
      "Install Python 3 or set APPLE_ECOSYSTEM_MCP_PYTHON_COMMAND to a Python 3 interpreter.",
      `Original error: ${error.message}`,
    ].join("\n"),
  );
  process.exit(127);
});

child.on("exit", (code, signal) => {
  console.error(`Apple Ecosystem MCP Python child exited code=${code ?? "null"} signal=${signal ?? "null"}`);
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
