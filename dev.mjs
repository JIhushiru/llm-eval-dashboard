#!/usr/bin/env node
// Run the EvalForge backend (FastAPI) and frontend (Next.js) together for local
// development. Zero dependencies (Node only), cross-platform. Streams both logs
// with a colored [backend]/[frontend] prefix; Ctrl+C stops both.
//
//   npm start          (or: node dev.mjs)
//
// (`npm run dev` is left to the frontend — inside frontend/ — so the two don't
// get confused.) Backend -> http://localhost:8000   Frontend -> http://localhost:3000
//
// If port 8000 is taken (or Windows has it in a reserved range — the symptom is
// uvicorn's "WinError 10013 ... forbidden by its access permissions"), pick
// another: `BACKEND_PORT=8010 npm start`. The frontend is pointed at the same
// port automatically, so the two stay linked. FRONTEND_PORT overrides 3000.

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const isWin = process.platform === "win32";

// Ports. Backend honors BACKEND_PORT (or PORT) so you can dodge a busy/reserved
// 8000; frontend honors FRONTEND_PORT. The frontend's port is set explicitly on
// its child env below so Next.js (which also reads PORT) can never collide with
// the backend. The frontend is told the matching API URL so the browser talks
// to the right backend in dev.
const backendPort = process.env.BACKEND_PORT ?? process.env.PORT ?? "8000";
const frontendPort = process.env.FRONTEND_PORT ?? "3000";
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? `http://localhost:${backendPort}`;

// The backend runs from its own virtualenv; the interpreter lives under
// Scripts/ on Windows and bin/ elsewhere.
const venvPython = join(
  root,
  "backend",
  ".venv",
  isWin ? "Scripts" : "bin",
  isWin ? "python.exe" : "python",
);

if (!existsSync(venvPython)) {
  console.error(`\n[dev] Backend virtualenv not found at:\n      ${venvPython}\n`);
  console.error("[dev] Create it once, then re-run `npm run dev`:");
  console.error("      cd backend");
  console.error("      python -m venv .venv");
  console.error(
    `      ${isWin ? ".venv\\Scripts\\python" : ".venv/bin/python"} -m pip install -r requirements.txt\n`,
  );
  process.exit(1);
}

const children = [];
let shuttingDown = false;

function killTree(child) {
  if (child.pid == null || child.exitCode !== null) return;
  if (isWin) {
    // npm -> node -> next dev (and uvicorn's --reload worker) spawn grandchildren
    // that a plain child.kill() would orphan on Windows; kill the whole tree.
    spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore" });
  } else {
    try {
      child.kill("SIGTERM");
    } catch {
      /* already gone */
    }
  }
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) killTree(child);
  process.exit(code);
}

function start(name, colorCode, command, args, opts) {
  const child = spawn(command, args, {
    cwd: opts.cwd,
    shell: opts.shell ?? false,
    env: opts.env ?? process.env,
  });
  children.push(child);

  const tag = `\x1b[${colorCode}m[${name}]\x1b[0m `;
  const forward = (stream, out) => {
    let buffered = "";
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => {
      buffered += chunk;
      const lines = buffered.split("\n");
      buffered = lines.pop() ?? "";
      for (const line of lines) out.write(tag + line + "\n");
    });
    stream.on("end", () => {
      if (buffered) out.write(tag + buffered + "\n");
    });
  };
  forward(child.stdout, process.stdout);
  forward(child.stderr, process.stderr);

  child.on("error", (err) => {
    process.stderr.write(tag + `failed to start: ${err.message}\n`);
    shutdown(1);
  });
  child.on("exit", (code) => {
    if (shuttingDown) return;
    process.stdout.write(tag + `exited with code ${code}\n`);
    shutdown(code ?? 0);
  });
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

console.log(
  `\x1b[1m[dev]\x1b[0m backend -> http://localhost:${backendPort}   frontend -> http://localhost:${frontendPort}\n`,
);

// Spawn the venv interpreter directly (absolute path, no shell) so Windows path
// separators are never an issue.
start(
  "backend",
  "36", // cyan
  venvPython,
  ["-m", "uvicorn", "app.main:app", "--reload", "--port", backendPort],
  { cwd: join(root, "backend") },
);

// npm is a shell wrapper (npm.cmd on Windows); run it through the shell. Set
// PORT explicitly (Next.js reads it) so the frontend never lands on the backend
// port, and pass the API URL so the browser reaches the backend.
start("frontend", "32" /* green */, "npm run dev", [], {
  cwd: join(root, "frontend"),
  shell: true,
  env: { ...process.env, PORT: frontendPort, NEXT_PUBLIC_API_URL: apiUrl },
});
