const { app, BrowserWindow, Menu, dialog, session, shell } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const APP_PORT = 8765;
const APP_URL = `http://127.0.0.1:${APP_PORT}`;
const GITHUB_URL = "https://github.com/topherPedersen/DXT-1";
const MINIMUM_PYTHON = [3, 9];

let mainWindow = null;
let setupWindow = null;
let backendChildren = [];
let isQuitting = false;
let logStream = null;

function backendRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "backend")
    : path.resolve(__dirname, "..");
}

function runtimeRoot() {
  return app.isPackaged
    ? path.join(app.getPath("userData"), "runtime", ".venv")
    : path.join(backendRoot(), ".venv");
}

function runtimePython() {
  return path.join(runtimeRoot(), "bin", "python");
}

function runtimeDemucs() {
  return path.join(runtimeRoot(), "bin", "demucs");
}

function executableExists(candidate) {
  try {
    fs.accessSync(candidate, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function findFfmpeg() {
  const candidates = [
    process.env.DXT_FFMPEG,
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg"
  ].filter(Boolean);
  return candidates.find(executableExists) || null;
}

function parsePythonVersion(executable) {
  const result = spawnSync(executable, ["--version"], { encoding: "utf8" });
  if (result.status !== 0) return null;
  const match = `${result.stdout}${result.stderr}`.match(/Python\s+(\d+)\.(\d+)/);
  return match ? [Number(match[1]), Number(match[2])] : null;
}

function versionAtLeast(version, minimum) {
  return version && (
    version[0] > minimum[0]
    || (version[0] === minimum[0] && version[1] >= minimum[1])
  );
}

function findSystemPython() {
  const candidates = [
    process.env.DXT_SYSTEM_PYTHON,
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3"
  ].filter(Boolean);
  return candidates.find(candidate => (
    executableExists(candidate)
    && versionAtLeast(parsePythonVersion(candidate), MINIMUM_PYTHON)
  )) || null;
}

function setupStatus(message) {
  if (setupWindow && !setupWindow.isDestroyed()) {
    setupWindow.webContents.send("setup-status", message);
  }
}

function createSetupWindow() {
  setupWindow = new BrowserWindow({
    width: 620,
    height: 360,
    resizable: false,
    title: "Setting up DXT-1",
    backgroundColor: "#111111",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  setupWindow.loadFile(path.join(__dirname, "setup.html"));
  setupWindow.on("closed", () => { setupWindow = null; });
}

function runSetupCommand(executable, args, label) {
  return new Promise((resolve, reject) => {
    setupStatus(label);
    const child = spawn(executable, args, {
      cwd: backendRoot(),
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    });
    let recentError = "";
    const handleOutput = chunk => {
      const text = chunk.toString();
      recentError = `${recentError}${text}`.slice(-4000);
      const lines = text.trim().split(/\r?\n/);
      if (lines.length && lines[lines.length - 1]) setupStatus(lines[lines.length - 1]);
    };
    child.stdout.on("data", handleOutput);
    child.stderr.on("data", handleOutput);
    child.on("error", reject);
    child.on("exit", code => {
      if (code === 0) resolve();
      else reject(new Error(`${label} failed.\n\n${recentError}`));
    });
  });
}

async function ensurePythonRuntime() {
  if (executableExists(runtimePython()) && executableExists(runtimeDemucs())) return;

  if (!app.isPackaged) {
    throw new Error(
      "The Python environment is missing. Run npm run desktop:setup in the DXT-1 folder, then start the app again."
    );
  }

  const systemPython = findSystemPython();
  if (!systemPython) {
    throw new Error(
      "DXT-1 needs Python 3.9 or newer for its first-time setup. Install Python with Homebrew or python.org, then reopen DXT-1."
    );
  }

  createSetupWindow();
  await runSetupCommand(systemPython, ["-m", "venv", runtimeRoot()], "Creating the local Python environment…");
  await runSetupCommand(
    runtimePython(),
    ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
    "Preparing the Python installer…"
  );
  await runSetupCommand(
    runtimePython(),
    ["-m", "pip", "install", "-r", path.join(backendRoot(), "requirements.txt")],
    "Installing Demucs, PyTorch, and ADTOF… This can take several minutes."
  );
  await runSetupCommand(
    runtimePython(),
    [path.join(backendRoot(), "patch_adtof_compat.py")],
    "Applying compatibility checks…"
  );

  if (!executableExists(runtimeDemucs())) {
    throw new Error("First-time setup completed without installing the Demucs executable.");
  }
}

function backendEnvironment(ffmpegPath) {
  const userData = app.getPath("userData");
  const dataDirectory = path.join(userData, "data");
  const cacheDirectory = path.join(userData, "cache");
  fs.mkdirSync(dataDirectory, { recursive: true });
  fs.mkdirSync(cacheDirectory, { recursive: true });
  const pathParts = [
    path.dirname(runtimePython()),
    path.dirname(ffmpegPath),
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin"
  ];
  return {
    ...process.env,
    DXT_DATA_DIR: dataDirectory,
    DXT_JOB_RETENTION_HOURS: "24",
    DXT_MAX_ACTIVE_JOBS: "10",
    DXT_WORKER_POLL_SECONDS: "1",
    DXT_STALE_JOB_HOURS: "6",
    HOME: app.getPath("home"),
    XDG_CACHE_HOME: cacheDirectory,
    TORCH_HOME: path.join(cacheDirectory, "torch"),
    PATH: [...new Set(pathParts)].join(":"),
    PYTHONUNBUFFERED: "1"
  };
}

function openLogStream() {
  const logsDirectory = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logsDirectory, { recursive: true });
  logStream = fs.createWriteStream(path.join(logsDirectory, "backend.log"), { flags: "a" });
  logStream.write(`\n--- DXT-1 started ${new Date().toISOString()} ---\n`);
}

function spawnBackend(args, name, env) {
  const child = spawn(runtimePython(), args, {
    cwd: backendRoot(),
    env,
    detached: true,
    stdio: ["ignore", "pipe", "pipe"]
  });
  child.stdout.pipe(logStream, { end: false });
  child.stderr.pipe(logStream, { end: false });
  child.on("error", error => logStream.write(`${name} error: ${error.stack || error}\n`));
  child.on("exit", (code, signal) => {
    logStream.write(`${name} exited (code=${code}, signal=${signal})\n`);
    if (!isQuitting && name === "API") {
      dialog.showErrorBox("DXT-1 backend stopped", "The local conversion service stopped unexpectedly. Reopen DXT-1 and inspect the backend log if the problem continues.");
    }
  });
  backendChildren.push(child);
}

function waitForBackend(timeoutMs = 120000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const request = http.get(`${APP_URL}/api/health`, response => {
        let body = "";
        response.on("data", chunk => { body += chunk; });
        response.on("end", () => {
          try {
            const health = JSON.parse(body);
            if (health.ok && health.demucs_available) return resolve();
          } catch {}
          retry();
        });
      });
      request.on("error", retry);
      request.setTimeout(2000, () => request.destroy());
    };
    const retry = () => {
      if (Date.now() - started >= timeoutMs) {
        reject(new Error("The local conversion service did not become ready."));
      } else {
        setTimeout(check, 500);
      }
    };
    check();
  });
}

async function startBackend() {
  const ffmpegPath = findFfmpeg();
  if (!ffmpegPath) {
    throw new Error("FFmpeg is missing. Install Homebrew and run: brew install ffmpeg");
  }
  await ensurePythonRuntime();
  setupStatus("Starting DXT-1…");
  const env = backendEnvironment(ffmpegPath);
  openLogStream();
  spawnBackend(["worker.py"], "Worker", env);
  spawnBackend(["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", String(APP_PORT)], "API", env);
  await waitForBackend();
}

function stopBackend() {
  isQuitting = true;
  for (const child of backendChildren) {
    if (!child.pid) continue;
    try { process.kill(-child.pid, "SIGTERM"); } catch {}
  }
  backendChildren = [];
  if (logStream) {
    logStream.end();
    logStream = null;
  }
}

function installDownloadHandler() {
  session.defaultSession.on("will-download", (event, item) => {
    if (!item.getURL().startsWith(`${APP_URL}/api/jobs/`)) return;
    const destination = dialog.showSaveDialogSync({
      title: "Save MIDI File",
      defaultPath: path.join(app.getPath("downloads"), item.getFilename()),
      filters: [{ name: "MIDI files", extensions: ["mid", "midi"] }]
    });
    if (destination) item.setSavePath(destination);
    else item.cancel();
  });
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 820,
    minWidth: 760,
    minHeight: 640,
    title: "DXT-1",
    backgroundColor: "#111111",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url === GITHUB_URL) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(APP_URL)) event.preventDefault();
  });
  mainWindow.loadURL(APP_URL);
  mainWindow.on("closed", () => { mainWindow = null; });
}

function createMenu() {
  const template = [
    {
      label: "DXT-1",
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit" }
      ]
    },
    { label: "Edit", submenu: [{ role: "undo" }, { role: "redo" }, { type: "separator" }, { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" }] },
    { label: "View", submenu: [{ role: "reload" }, { role: "toggleDevTools" }, { type: "separator" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { type: "separator" }, { role: "togglefullscreen" }] },
    { role: "windowMenu" },
    { label: "Help", submenu: [{ label: "DXT-1 on GitHub", click: () => shell.openExternal(GITHUB_URL) }] }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function launch() {
  try {
    await startBackend();
    if (setupWindow && !setupWindow.isDestroyed()) setupWindow.close();
    installDownloadHandler();
    createMenu();
    createMainWindow();
  } catch (error) {
    stopBackend();
    if (setupWindow && !setupWindow.isDestroyed()) setupWindow.close();
    dialog.showErrorBox("DXT-1 could not start", error.message || String(error));
    app.quit();
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(launch);
  app.on("activate", () => {
    if (!mainWindow && backendChildren.length) createMainWindow();
  });
  app.on("before-quit", stopBackend);
  app.on("window-all-closed", () => {
    // Standard macOS behavior keeps the application running without a window.
  });
}
