// main.js
const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { exec, spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let installProcess = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  mainWindow.loadFile('index.html');
}

// IPC handlers
ipcMain.handle('get-feature-flags', async () => {
  // Read .env and parse FEATURE_* variables
  const envPath = path.join(app.getAppPath(), '..', 'deploy', 'docker', '.env');
  // Fallback: use defaults
  const defaults = {
    FEATURE_ASK_SOMEONE: true,
    FEATURE_GOOD_ANSWER: true,
    FEATURE_GPU_MARKETPLACE: false,
    FEATURE_ROUTER: false,
    FEATURE_TRAINING: false,
    FEATURE_ENTERPRISE: false,
    FEATURE_FORGEJO: false,
    FEATURE_RECRUITMENT: false,
    FEATURE_LEAD_GEN: false,
    FEATURE_FREELANCE: false,
  };
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    const lines = content.split('\n');
    const flags = {};
    for (const line of lines) {
      const match = line.match(/^FEATURE_(\w+)=(.+)/);
      if (match) {
        const key = `FEATURE_${match[1]}`;
        flags[key] = match[2].trim().toLowerCase() === 'true';
      }
    }
    return { ...defaults, ...flags };
  } catch (e) {
    return defaults;
  }
});

ipcMain.handle('run-install', async (event, options) => {
  const { profile, environment, force, auto } = options;
  return new Promise((resolve, reject) => {
    const script = path.join(app.getAppPath(), '..', 'scripts', 'nettrades-setup.sh');
    const args = [profile, '--environment', environment];
    if (force) args.push('--force');
    if (auto) args.push('--auto');
    installProcess = spawn('bash', [script, ...args], { cwd: path.dirname(script) });
    installProcess.stdout.on('data', (data) => {
      const output = data.toString();
      event.sender.send('install-output', output);
    });
    installProcess.stderr.on('data', (data) => {
      const output = data.toString();
      event.sender.send('install-output', output);
    });
    installProcess.on('close', (code) => {
      installProcess = null;
      if (code === 0) resolve({ success: true });
      else reject({ success: false, code });
    });
  });
});

ipcMain.handle('cancel-install', () => {
  if (installProcess) {
    installProcess.kill('SIGINT');
    installProcess = null;
    return { success: true };
  }
  return { success: false };
});

ipcMain.handle('open-url', (event, url) => {
  shell.openExternal(url);
});

ipcMain.handle('get-platform', async () => {
  // Detect platform from the environment
  const platform = process.platform; // 'darwin', 'win32', 'linux'
  if (platform === 'linux' && process.env.WSL_DISTRO_NAME) {
    return 'wsl';
  }
  return platform;
});

// (Optional) Add more handlers as needed, e.g., get-status

app.whenReady().then(createWindow);