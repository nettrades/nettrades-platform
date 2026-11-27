// =============================================================================
// FILE: installer/main.js
// =============================================================================
// PURPOSE:
//   Main Electron process for the NETTRADES Launcher.
//   Handles window creation, IPC communication with the renderer,
//   and orchestrates the execution of shell scripts.
//
// KEY FEATURES:
//   - Creates the main application window
//   - Exposes safe IPC APIs to the renderer via preload.js
//   - Runs shell scripts (installation, backup, restore, etc.)
//   - Streams output to the renderer for live log viewing
//   - Handles platform detection and environment setup
//   - Model management (download, import, list)
//   - Platform control (start/stop Docker Compose)
//   - GPU detection and status monitoring
//   - Odoo authentication integration
//   - "Ask Someone" expert system integration
//   - "Good Answer" training data management
//   - Agent management and orchestration
//   - Training and fine-tuning job management
//   - Queue monitoring and task management
//   - GPU marketplace integration
//   - Node discovery and WireGuard VPN management
//   - Grove and KAI Scheduler management
//   - Tenant type selection and runtime configuration
//   - gVisor enablement for untrusted tenants
//   - Developer Mode with Wine installer (NEW)
//   - Hub/Spoke detection (NEW)
//   - Universal Enterprise Proxy integration (NEW)
//
// UPDATES (2026-10-30):
//   - Added registerSafe() to prevent duplicate ipcMain.handle crashes.
//     Electron throws "Attempted to register a second handler" when the
//     same channel is registered twice. The Demo tab was blank because
//     get-demo-status called ipcMain.handle() from inside itself.
//   - Extracted fetchHealthNodes / fetchRoutingEvents / fetchClusterState /
//     fetchActiveTrack as plain functions. The individual IPC handlers and
//     get-demo-status now both call them, instead of re-registering.
//   - Added httpWithRetry() with Retry-After + exponential backoff for
//     Odoo 429 responses. The GPU tab was showing "HTTP 429" because it
//     polled every 5s without backoff.
//   - get-platform-gpus now uses httpWithRetry.
//
// USAGE:
//   npm start
// =============================================================================

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn, exec, execSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const https = require('https');
const crypto = require('crypto');
const net = require('net');
const SERVICE_PIPE = '\\\\.\\pipe\\NETTRADESNetSvc';

// -----------------------------------------------------------------------------
// Disable GPU acceleration to avoid rendering errors on WSL
// -----------------------------------------------------------------------------
app.disableHardwareAcceleration(); // prevents SharedImage errors on WSL

// -----------------------------------------------------------------------------
// Global variables
// -----------------------------------------------------------------------------

let mainWindow = null;
let installProcess = null;
let downloadProcess = null;
let logFile = null;
let discoveredNodes = new Map();
let isDeploying = false;
let deploymentProgress = 0;

// Determine project root – CRITICAL FIX for packaged app and development
// When running from source (npm start), __dirname is /path/to/repo/installer
// So PROJECT_ROOT should be one level up: /path/to/repo
// When packaged, resources are in process.resourcesPath
const isPackaged = app.isPackaged;
const PROJECT_ROOT = isPackaged ? process.resourcesPath : path.join(__dirname, '..');

// Models directory (where llama.cpp and Dynamo look for models).
// Resolution order:
//   1. NETTRADES_MODELS_DIR env var
//   2. models_dir in ~/.config/nettrades-launcher/config.json
//   3. ~/nettrades-platform/deploy/docker/dynamo-data/models
// The packaged AppImage runs from a mount point that does not contain
// the git repo, so the env var / config / homedir defaults are used
// instead of PROJECT_ROOT.
function _resolveModelsDir() {
    if (process.env.NETTRADES_MODELS_DIR) return process.env.NETTRADES_MODELS_DIR;
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        if (fs.existsSync(configPath)) {
            const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            if (config.models_dir) return config.models_dir;
        }
    } catch {}
    return path.join(os.homedir(), 'nettrades-platform', 'deploy', 'docker', 'dynamo-data', 'models');
}
const MODELS_DIR = _resolveModelsDir();

// Docker Compose file path
const COMPOSE_FILE = path.join(PROJECT_ROOT, 'deploy', 'docker', 'docker-compose.yaml');

// Virtual environment directory
const VENV_DIR = path.join(PROJECT_ROOT, '.venv');

// .env file path
const ENV_FILE = path.join(PROJECT_ROOT, 'deploy', 'docker', '.env');

// Phase marker directory
const PHASE_MARKER_DIR = PROJECT_ROOT;

// Proxy URL (can be overridden via environment or settings)
let PROXY_URL = process.env.PROXY_URL || 'http://localhost:8080';

// Enterprise backend (odoo, salesforce, sap, oracle)
let ENTERPRISE_BACKEND = process.env.ENTERPRISE_BACKEND || 'odoo';

// =============================================================================
// SAFE IPC REGISTRATION (2026-10-30)
// =============================================================================
// Electron's ipcMain.handle() throws if the same channel is registered twice.
// This happened when get-demo-status called ipcMain.handle('get-health-nodes')
// from inside its own handler — the second call threw and the whole Demo tab
// went blank. registerSafe() removes any existing handler before registering,
// so a re-registration is a no-op instead of a crash.
//
// Every IPC handler in this file uses registerSafe(). Do not use ipcMain.handle
// directly. If you add a handler and forget, the launcher will crash the first
// time the channel is touched twice.
// =============================================================================
function registerSafe(channel, handler) {
    try { ipcMain.removeHandler(channel); } catch (_) { /* no-op if not registered */ }
    ipcMain.handle(channel, handler);
}

// =============================================================================
// HTTP WITH RETRY — handles 429 from the odoo-proxy (2026-10-30)
// =============================================================================
// The GPUs tab shows "Odoo GPU query: HTTP 429" because it polls every 5s
// without backoff. Every Launcher HTTP call to the odoo-proxy MUST go
// through this helper. Do not call fetch() directly against :8090.
//
// Behaviour:
//   - Non-429 responses pass through unchanged.
//   - 429 responses are retried up to `attempts` times, each after
//     Retry-After seconds (capped at 10s) plus jitter.
//   - Network errors also back off exponentially.
// =============================================================================

async function httpWithRetry(url, opts = {}, attempts = 3) {
    let lastErr = null;
    for (let i = 0; i < attempts; i++) {
        try {
            const resp = await fetch(url, opts);
            if (resp.status !== 429) return resp;
            const retryAfter = parseInt(resp.headers.get('Retry-After') || '5', 10);
            const waitMs = Math.min(retryAfter * 1000, 10000) + Math.floor(Math.random() * 1000);
            logInfo(`HTTP 429 from ${url} — backing off ${Math.round(waitMs/1000)}s (attempt ${i+1}/${attempts})`);
            await new Promise(r => setTimeout(r, waitMs));
            lastErr = new Error(`HTTP 429 after ${attempts} attempts`);
        } catch (e) {
            lastErr = e;
            if (i < attempts - 1) await new Promise(r => setTimeout(r, 1000 * Math.pow(2, i)));
        }
    }
    throw lastErr || new Error('httpWithRetry failed');
}

// -----------------------------------------------------------------------------
// Helper: Execute a shell command and return stdout
// -----------------------------------------------------------------------------
function execCommand(command) {
    return new Promise((resolve, reject) => {
        exec(command, (error, stdout, stderr) => {
            if (error) {
                reject(error);
            } else {
                resolve(stdout);
            }
        });
    });
}

// -----------------------------------------------------------------------------
// Helper: Promise-based exec helper
// -----------------------------------------------------------------------------

function execPromise(cmd) {
    return new Promise((resolve, reject) => {
        exec(cmd, (error, stdout, stderr) => {
            if (error) reject({ error, stderr });
            else resolve({ stdout, stderr });
        });
    });
}

// -----------------------------------------------------------------------------
// For the NETTRADES Networking Service for WSL Port Forwarding
// Part of the code for the NETTRADES Networking Service, a Go-based Windows service using the official
// Go extended standard library golang.org/x/sys/windows/svc for NETTRADES WSL Port Forwarding
// Launcher's NSIS installer registers the service during installation. The deployment scripts call
// phase-windows-service.sh

// The problem it solves:
// WSL2 is running in NAT mode. The WSL distro has a different IP address on a private virtual
// subnet that only the Windows host can route to. The Windows host's vEthernet (WSL) adapter
// is the only thing that can reach WSL. Other machines cannot reach it — that is why ping works.
// (Other machines can reach the Windows host via ICMP at the Ethernet layer, but the TCP
// connection to WSL from the other machines is impossible.
// Also after WSL restarts (e.g., after wsl --shutdown) it changes the WSL IP

// Windows 10 does not support mirrored networking
// networkingMode=mirrored — the single-line fix that makes WSL2 share the Windows
// host's IP — is only available on Windows 11 22H2 and later.
// It does not exist on Windows 10.  On Windows 10, WSL2 is locked into NAT mode.
// -----------------------------------------------------------------------------

function sendServiceCommand(command, params = {}) {
    return new Promise((resolve) => {
        const client = net.connect(SERVICE_PIPE, () => {
            client.write(JSON.stringify({ command, ...params }) + '\n');
        });
        let data = '';
        client.on('data', (chunk) => { data += chunk.toString(); });
        client.on('end', () => {
            try { resolve(JSON.parse(data.trim())); }
            catch (e) { resolve({ status: 'error', error: e.message }); }
        });
        client.on('error', () => resolve({ status: 'unavailable' }));
    });
}

// -----------------------------------------------------------------------------
// Tenant Types and Runtime Configuration
// -----------------------------------------------------------------------------

const TENANT_TYPES = {
    ENTERPRISE: 'enterprise',
    FREELANCER: 'freelancer',
    HOME: 'home'
};

const RUNTIME_CONFIG = {
    [TENANT_TYPES.ENTERPRISE]: {
        langgraph: '',
        selfImproving: '',
        ui: '',
        description: 'Full performance, trusted workload'
    },
    [TENANT_TYPES.FREELANCER]: {
        langgraph: 'runsc',
        selfImproving: 'runsc',
        ui: 'runsc',
        description: 'gVisor isolation for untrusted code'
    },
    [TENANT_TYPES.HOME]: {
        langgraph: 'runsc',
        selfImproving: 'runsc',
        ui: 'runsc',
        description: 'gVisor isolation for home users'
    }
};

// -----------------------------------------------------------------------------
// Logging
// -----------------------------------------------------------------------------

function logInfo(message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[INFO] ${timestamp} ${message}`;
    console.log(logMessage);
    if (mainWindow) {
        mainWindow.webContents.send('log-output', { type: 'info', message: logMessage });
    }
}

function logError(message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[ERROR] ${timestamp} ${message}`;
    console.error(logMessage);
    if (mainWindow) {
        mainWindow.webContents.send('log-output', { type: 'error', message: logMessage });
    }
}

function logSuccess(message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[SUCCESS] ${timestamp} ${message}`;
    console.log(logMessage);
    if (mainWindow) {
        mainWindow.webContents.send('log-output', { type: 'success', message: logMessage });
    }
}

// -----------------------------------------------------------------------------
// Helper: generate safe password (alphanumeric)
// -----------------------------------------------------------------------------
function generateSafePassword() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let password = '';
    for (let i = 0; i < 24; i++) {
        password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return password;
}

// -----------------------------------------------------------------------------
// Create the main window
// -----------------------------------------------------------------------------

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 1000,
        minHeight: 750,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        },
        icon: path.join(__dirname, 'build', 'icon.png'),
        title: 'NETTRADES Launcher',
        backgroundColor: '#0a0a0f',
        show: false,
        frame: true,
    });

    mainWindow.loadFile('index.html');

    // Show window when ready
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // Open external links in default browser
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    // Log window events
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// -----------------------------------------------------------------------------
// App lifecycle
// -----------------------------------------------------------------------------

app.whenReady().then(() => {
    createWindow();
    logInfo('NETTRADES Launcher started');
    logInfo(`Project root: ${PROJECT_ROOT}`);
    logInfo(`Models directory: ${MODELS_DIR}`);
    logInfo(`Virtual environment: ${VENV_DIR}`);
    logInfo(`Platform: ${process.platform}`);
    logInfo(`Packaged: ${isPackaged}`);
    logInfo(`Compose file: ${COMPOSE_FILE}`);
    logInfo(`Proxy URL: ${PROXY_URL}`);
    logInfo(`Enterprise Backend: ${ENTERPRISE_BACKEND}`);

    // Check for virtual environment
    checkVirtualEnvironment();

    // Start auto-updater
    setupAutoUpdater();

    // Start node discovery
    startNodeDiscovery();
    loadProxyUrlFromConfig();

    // Check for updates on startup
    setTimeout(() => {
        autoUpdater.checkForUpdates();
    }, 5000);
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// -----------------------------------------------------------------------------
// Proxy URL Config
// -----------------------------------------------------------------------------

function loadProxyUrlFromConfig() {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        if (fs.existsSync(configPath)) {
            const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            if (config.proxyUrl) {
                PROXY_URL = config.proxyUrl;
                logInfo(`Loaded proxy URL from config: ${PROXY_URL}`);
            }
            if (config.enterpriseBackend) {
                ENTERPRISE_BACKEND = config.enterpriseBackend;
                logInfo(`Loaded enterprise backend from config: ${ENTERPRISE_BACKEND}`);
            }
        }
    } catch (error) {
        logError(`Error loading config: ${error.message}`);
    }
}

function saveProxyUrlToConfig(url, backend) {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        let config = {};
        if (fs.existsSync(configPath)) {
            config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        }
        config.proxyUrl = url || PROXY_URL;
        if (backend) {
            config.enterpriseBackend = backend;
        }
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
        logInfo(`Saved proxy URL to config: ${url || PROXY_URL}`);
        return { success: true };
    } catch (error) {
        logError(`Error saving config: ${error.message}`);
        return { success: false, error: error.message };
    }
}

// -----------------------------------------------------------------------------
// Hub-level configuration: the Launcher can be pointed at a different hub
// (e.g. the Blackwell or a Contabo stand-in) without rebuilding. The values
// are stored alongside proxyUrl/enterpriseBackend in the same config file.
// -----------------------------------------------------------------------------
const DEFAULT_HUB_CONFIG = {
    dynamo_url: process.env.DYNAMO_URL || 'http://localhost:8001/v1',
    langgraph_url: process.env.LANGGRAPH_URL || 'http://localhost:8000',
    odoo_url: process.env.ODOO_URL || 'http://localhost:8069',
};

function loadHubConfig() {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        if (!fs.existsSync(configPath)) return { ...DEFAULT_HUB_CONFIG };
        const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        return { ...DEFAULT_HUB_CONFIG, ...(config.hub || {}) };
    } catch (e) {
        logError(`loadHubConfig failed: ${e.message}`);
        return { ...DEFAULT_HUB_CONFIG };
    }
}

registerSafe('get-hub-config', () => loadHubConfig());

registerSafe('save-hub-config', (_evt, hub) => {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        const existing = fs.existsSync(configPath)
            ? JSON.parse(fs.readFileSync(configPath, 'utf8'))
            : {};
        existing.hub = { ...DEFAULT_HUB_CONFIG, ...(existing.hub || {}), ...hub };
        fs.writeFileSync(configPath, JSON.stringify(existing, null, 2));
        logInfo(`saved hub config: ${JSON.stringify(existing.hub)}`);
        return { success: true, hub: existing.hub };
    } catch (e) {
        logError(`save-hub-config failed: ${e.message}`);
        return { success: false, error: e.message };
    }
});



// -----------------------------------------------------------------------------
// Auto-Updater
// -----------------------------------------------------------------------------

function setupAutoUpdater() {
    autoUpdater.setFeedURL({
        provider: 'github',
        repo: 'nettrades-platform',
        owner: 'nettrades',
    });

    autoUpdater.on('checking-for-update', () => {
        mainWindow?.webContents.send('update-status', { status: 'checking' });
    });

    autoUpdater.on('update-available', (info) => {
        mainWindow?.webContents.send('update-status', {
            status: 'available',
            version: info.version,
            releaseNotes: info.releaseNotes,
        });
    });

    autoUpdater.on('update-not-available', () => {
        mainWindow?.webContents.send('update-status', { status: 'uptodate' });
    });

    autoUpdater.on('download-progress', (progress) => {
        mainWindow?.webContents.send('update-progress', {
            percent: progress.percent,
            bytesPerSecond: progress.bytesPerSecond,
            transferred: progress.transferred,
            total: progress.total,
        });
    });

    autoUpdater.on('update-downloaded', () => {
        mainWindow?.webContents.send('update-status', { status: 'downloaded' });
        dialog.showMessageBox({
            type: 'info',
            title: 'Update Ready',
            message: 'A new version has been downloaded. Restart the application to install it.',
            buttons: ['Restart Now', 'Later'],
        }).then((result) => {
            if (result.response === 0) {
                autoUpdater.quitAndInstall();
            }
        });
    });

    autoUpdater.on('error', (err) => {
        mainWindow?.webContents.send('update-status', {
            status: 'error',
            error: err.message,
        });
    });

    // Check for updates every 6 hours
    setInterval(() => {
        autoUpdater.checkForUpdates();
    }, 21600000);
}

// -----------------------------------------------------------------------------
// Virtual Environment Check
// -----------------------------------------------------------------------------

function checkVirtualEnvironment() {
    const venvActivate = path.join(VENV_DIR, 'bin', 'activate');
    if (!fs.existsSync(venvActivate)) {
        logError(`Virtual environment not found at ${VENV_DIR}`);
        logInfo('Please run Phase 1 first: ./scripts/nettrades-setup.sh dev');
        dialog.showMessageBox({
            type: 'warning',
            title: 'Virtual Environment Not Found',
            message: 'The Python virtual environment is not set up. Please run the deployment script first.',
            detail: `Expected: ${VENV_DIR}`,
            buttons: ['OK'],
        });
    } else {
        logSuccess(`Virtual environment found at ${VENV_DIR}`);
    }
}

// -----------------------------------------------------------------------------
// Node Discovery (mDNS/Avahi)
// -----------------------------------------------------------------------------

function startNodeDiscovery() {
    // Use bonjour for mDNS discovery
    try {
        const bonjour = require('bonjour')();

        // Discover NETTRADES nodes
        bonjour.find({ type: 'nettrades' }, (service) => {
            const nodeId = `${service.name}-${service.host}`;
            if (!discoveredNodes.has(nodeId)) {
                discoveredNodes.set(nodeId, {
                    name: service.name,
                    host: service.host,
                    port: service.port,
                    addresses: service.addresses,
                    txt: service.txt || {},
                    firstSeen: Date.now(),
                    lastSeen: Date.now(),
                });
                mainWindow?.webContents.send('node-discovered', {
                    name: service.name,
                    host: service.host,
                    port: service.port,
                    addresses: service.addresses,
                });
                logInfo(`Node discovered: ${service.name} at ${service.host}:${service.port}`);
            } else {
                const node = discoveredNodes.get(nodeId);
                node.lastSeen = Date.now();
            }
        });

        // Also broadcast our own service
        const serverIP = getServerIP();
        bonjour.publish({
            name: `NETTRADES-${crypto.randomBytes(4).toString('hex')}`,
            type: 'nettrades',
            port: 3002,
            host: serverIP,
            txt: {
                version: app.getVersion(),
                platform: process.platform,
                // role=hub tells spokes that this service is a hub, not
                // another spoke. spoke-agent.py's mDNS discovery picks
                // the first hub it finds. Without this key, spokes would
                // need a different heuristic (e.g. "the service with
                // port 3002"), which is less reliable.
                role: 'hub',
                gpus: '0',
                backend: ENTERPRISE_BACKEND,
            },
        });
        logInfo(`Broadcasting NETTRADES service on ${serverIP}:3002`);

        // Clean up stale nodes (not seen for 60 seconds)
        setInterval(() => {
            const now = Date.now();
            for (const [id, node] of discoveredNodes) {
                if (now - node.lastSeen > 60000) {
                    discoveredNodes.delete(id);
                    mainWindow?.webContents.send('node-lost', { id });
                }
            }
        }, 30000);
    } catch (error) {
        logError(`mDNS discovery error: ${error.message}`);
    }
}

function getServerIP() {
    try {
        const interfaces = os.networkInterfaces();
        for (const name of Object.keys(interfaces)) {
            for (const iface of interfaces[name]) {
                if (iface.family === 'IPv4' && !iface.internal) {
                    return iface.address;
                }
            }
        }
    } catch {}
    return 'localhost';
}

// -----------------------------------------------------------------------------
// Helper: Check if a phase is complete (idempotency check)
// -----------------------------------------------------------------------------

function isPhaseComplete(phaseNumber) {
    const markerFile = path.join(PHASE_MARKER_DIR, `.phase-${phaseNumber}-complete`);
    return fs.existsSync(markerFile);
}

// -----------------------------------------------------------------------------
// Helper: Check if the platform is already fully set up
// -----------------------------------------------------------------------------

function isPlatformSetup() {
    // Check if Phase 1 and Phase 2 are complete (minimum for a working dev environment)
    return isPhaseComplete(1) && isPhaseComplete(2);
}

// -----------------------------------------------------------------------------
// Helper: Detect deployment mode (hub/spoke/addon)
// -----------------------------------------------------------------------------

function detectDeploymentMode() {
    // Check for hub marker
    const hubMarker = path.join(PROJECT_ROOT, '.nettrades_hub');
    if (fs.existsSync(hubMarker)) {
        return 'hub';
    }

    // Check for Odoo
    let hasOdoo = false;
    try {
        const result = execSync('which odoo 2>/dev/null || echo ""', { encoding: 'utf8' });
        if (result.trim()) hasOdoo = true;
    } catch (e) {}
    if (!hasOdoo) {
        try {
            const result = execSync('ps aux | grep -v grep | grep -q odoo', { encoding: 'utf8' });
            if (result.trim()) hasOdoo = true;
        } catch (e) {}
    }

    // Check for sub-hub on network (via mDNS cache)
    let subHubFound = false;
    for (const [id, node] of discoveredNodes) {
        if (node.txt && node.txt.role === 'hub') {
            subHubFound = true;
            break;
        }
    }

    if (subHubFound) return 'spoke';
    else if (hasOdoo) return 'addon';
    else return 'hub';
}

// =============================================================================
// IPC HANDLERS – All handlers are registered once via registerSafe()
// =============================================================================

// ─────────────────────────────────────────────────────────────────────────────
// Platform & System
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-platform', () => {
    return {
        platform: process.platform,
        arch: process.arch,
        version: app.getVersion(),
        projectRoot: PROJECT_ROOT,
        modelsDir: MODELS_DIR,
        venvDir: VENV_DIR,
        envFile: ENV_FILE,
        isPackaged: isPackaged,
        tenantTypes: Object.values(TENANT_TYPES),
        proxyUrl: PROXY_URL,
        backend: ENTERPRISE_BACKEND,
        deploymentMode: detectDeploymentMode(),
    };
});

registerSafe('get-project-root', () => PROJECT_ROOT);
registerSafe('get-models-dir', () => MODELS_DIR);

registerSafe('is-platform-setup', () => isPlatformSetup());

registerSafe('get-deployment-mode', () => detectDeploymentMode());

registerSafe('get-proxy-url', () => PROXY_URL);

registerSafe('get-enterprise-backend', () => ENTERPRISE_BACKEND);

registerSafe('set-enterprise-backend', (event, backend) => {
    const validBackends = ['odoo', 'salesforce', 'sap', 'oracle'];
    if (!validBackends.includes(backend)) {
        return { success: false, error: `Invalid backend: ${backend}. Valid: ${validBackends.join(', ')}` };
    }
    ENTERPRISE_BACKEND = backend;
    saveProxyUrlToConfig(PROXY_URL, backend);
    return { success: true, backend: ENTERPRISE_BACKEND };
});

// get-server-url handler
registerSafe('get-server-url', () => {
    return PROXY_URL;
});

registerSafe('save-server-url', (event, url) => {
    if (url) {
        PROXY_URL = url;
        saveProxyUrlToConfig(url, ENTERPRISE_BACKEND);
        return { success: true };
    }
    return { success: false, error: 'No URL provided' };
});

// ─────────────────────────────────────────────────────────────────────────────
// QUICK SETUP
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('run-quick-setup', async (event) => {
    if (installProcess) {
        return { success: false, error: 'Setup already in progress' };
    }

    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'nettrades-setup.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Setup script not found: ${scriptPath}` };
    }

    // Check if already set up – if so, just run the upgrade/repair
    const alreadySetup = isPlatformSetup();

    return new Promise((resolve) => {
        // Build the command: always run with --force --auto for idempotency
        // If already setup, we still run to ensure everything is up-to-date (safe to re-run)
        const cmd = `bash ${scriptPath} all --force --auto`;
        logInfo(`Starting quick setup: ${cmd}`);
        logInfo(`Platform previously setup: ${alreadySetup}`);

        installProcess = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
            env: { ...process.env },
            shell: true,
        });

        let output = '';
        let errorOutput = '';

        installProcess.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stdout', data: text });
            // Parse progress from phase names
            if (text.includes('Phase 0')) {
                deploymentProgress = 10;
                mainWindow?.webContents.send('install-progress', { progress: 10, phase: 'System Preparation' });
            } else if (text.includes('Phase 1')) {
                deploymentProgress = 30;
                mainWindow?.webContents.send('install-progress', { progress: 30, phase: 'Development Environment' });
            } else if (text.includes('Phase 2')) {
                deploymentProgress = 50;
                mainWindow?.webContents.send('install-progress', { progress: 50, phase: 'Deployment' });
            } else if (text.includes('Phase 3')) {
                deploymentProgress = 70;
                mainWindow?.webContents.send('install-progress', { progress: 70, phase: 'Kubernetes Scaling' });
            } else if (text.includes('Phase 4')) {
                deploymentProgress = 85;
                mainWindow?.webContents.send('install-progress', { progress: 85, phase: 'Module Installation' });
            } else if (text.includes('Phase 5')) {
                deploymentProgress = 95;
                mainWindow?.webContents.send('install-progress', { progress: 95, phase: 'Monitoring Setup' });
            } else if (text.includes('Setup Complete')) {
                deploymentProgress = 100;
                mainWindow?.webContents.send('install-progress', { progress: 100, phase: 'Complete!' });
            }
        });

        installProcess.stderr.on('data', (data) => {
            const text = data.toString();
            errorOutput += text;
            mainWindow?.webContents.send('install-output', { type: 'stderr', data: text });
        });

        installProcess.on('close', (code) => {
            installProcess = null;
            isDeploying = false;
            deploymentProgress = 100;
            if (code === 0) {
                logSuccess('Quick setup completed successfully');
                resolve({ success: true, output, alreadySetup });
            } else {
                logError(`Quick setup failed with code ${code}`);
                resolve({ success: false, error: errorOutput || `Process exited with code ${code}` });
            }
        });

        installProcess.on('error', (err) => {
            installProcess = null;
            isDeploying = false;
            logError(`Quick setup error: ${err.message}`);
            resolve({ success: false, error: err.message });
        });
    });
});


// ──────────────────────────────────────────────────────────────────────────
// For the NETTRADES Networking Service for WSL Port Forwarding
// ──────────────────────────────────────────────────────────────────────────

registerSafe('netsvc-get-status', async () => {
    return await sendServiceCommand('get-status');
});

registerSafe('netsvc-repair', async () => {
    return await sendServiceCommand('repair');
});

registerSafe('netsvc-wireguard-start', async (_, config) => {
    return await sendServiceCommand('wireguard-start', { config });
});

registerSafe('netsvc-wireguard-stop', async () => {
    return await sendServiceCommand('wireguard-stop');
});

// =============================================================================
// GPU Node Management (local registration)
// =============================================================================

// In-memory store for GPU nodes and jobs (for development)
let gpuNodes = [];
let inferenceJobs = [];
let jobIdCounter = 0;

registerSafe('proxy-get-gpu-nodes', () => {
    // Return local GPU nodes (from file or memory)
    return { success: true, data: gpuNodes };
});

registerSafe('proxy-register-gpu-node', (event, nodeData) => {
    // Add a new GPU node
    const newNode = {
        id: `gpu-${Date.now()}`,
        ...nodeData,
        status: nodeData.status || 'available',
        registeredAt: new Date().toISOString(),
        last_heartbeat: new Date().toISOString(),
    };
    gpuNodes.push(newNode);
    logInfo(`GPU node registered: ${newNode.name}`);
    return { success: true, data: newNode };
});

registerSafe('proxy-create-job', (event, jobData) => {
    // Create a new inference job
    const job = {
        id: `job-${++jobIdCounter}`,
        ...jobData,
        status: 'pending',
        created: new Date().toISOString(),
        result: null,
    };
    inferenceJobs.push(job);
    logInfo(`Job created: ${job.id}`);
    // Simulate job processing (in a real system, this would trigger an agent)
    setTimeout(() => {
        const j = inferenceJobs.find(j => j.id === job.id);
        if (j) {
            j.status = 'completed';
            j.result = `Processed prompt: ${jobData.prompt || ''}`;
            logInfo(`Job ${job.id} completed`);
        }
    }, 2000);
    return { success: true, data: job };
});

registerSafe('proxy-get-job', (event, jobId) => {
    const job = inferenceJobs.find(j => j.id === jobId);
    if (job) {
        return { success: true, data: job };
    }
    return { success: false, error: 'Job not found' };
});

// ─────────────────────────────────────────────────────────────────────────────
// VPN Remove Peer
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('vpn-remove-peer', async (event, username) => {
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'wireguard-manager.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `WireGuard script not found: ${scriptPath}` };
    }
    return new Promise((resolve) => {
        const cmd = `sudo ${scriptPath} remove ${username}`;
        logInfo(`Removing WireGuard peer: ${username}`);
        exec(cmd, { cwd: PROJECT_ROOT }, (error, stdout, stderr) => {
            if (error) {
                logError(`WireGuard peer removal failed: ${stderr}`);
                resolve({ success: false, error: stderr || error.message });
            } else {
                logSuccess(`WireGuard peer removed: ${username}`);
                resolve({ success: true, output: stdout });
            }
        });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Platform Status (combines Docker status and service health)
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-platform-status', async () => {
    // Get Docker compose status
    const dockerStatus = await getDockerStatus();
    // Get system health
    const health = await computeSystemHealth();             // ← plain function call
    return {
        running: dockerStatus.running,
        services: dockerStatus.services || [],
        health: health.services || {},
    };
});

// ─────────────────────────────────────────────────────────────────────────────
// List Emergency Audit
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('list-emergency-audit', async () => {
    try {
        const result = await execCommand(
            `docker compose exec -T postgres psql -U odoo -d odoo -t -c "SELECT login, action, ip_address, performed_at FROM nettrades_emergency_audit ORDER BY performed_at DESC LIMIT 50;"`
        );
        return { success: true, data: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Installation / Deployment
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('run-install', async (event, options) => {
    if (installProcess) {
        return { success: false, error: 'Installation already in progress' };
    }

    const {
        profile = 'all',
        force = false,
        auto = true,
        production = false,
        upgrade = false,
        withFinetune = false,
        withGrove = false,
        withKai = false,
        withRouter = false,
        withCuvs = false,
        domain = '',
        phases = null,
        resetData = false,
        tenantType = 'enterprise',
        tenantName = 'default',
        backend = 'odoo',
        proxyUrl = null,
    } = options || {};

    // Update enterprise backend if provided
    if (backend && ['odoo', 'salesforce', 'sap', 'oracle'].includes(backend)) {
        ENTERPRISE_BACKEND = backend;
    }

    // Update proxy URL if provided
    if (proxyUrl) {
        PROXY_URL = proxyUrl;
        saveProxyUrlToConfig(PROXY_URL, ENTERPRISE_BACKEND);
    }

    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'nettrades-setup.sh');

    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Deployment script not found: ${scriptPath}` };
    }

    // Ensure the virtual environment exists
    const venvActivate = path.join(VENV_DIR, 'bin', 'activate');
    if (!fs.existsSync(venvActivate)) {
        logError('Virtual environment not found. Please run Phase 1 first.');
        return { success: false, error: 'Virtual environment not found. Please run Phase 1 first.' };
    }

    // Set tenant configuration in .env
    // FIX (2026-10): Call the extracted function directly.
    // see the comment above _setTenantConfig.
    const tenantResult = await _setTenantConfig({ tenantType, tenantName });
    if (!tenantResult.success) {
        return { success: false, error: `Failed to set tenant config: ${tenantResult.error}` };
    }

    // Set enterprise backend in .env
    try {
        let envContent = '';
        if (fs.existsSync(ENV_FILE)) {
            envContent = fs.readFileSync(ENV_FILE, 'utf8');
        }
        if (envContent.match(/^ENTERPRISE_BACKEND=/m)) {
            envContent = envContent.replace(/^ENTERPRISE_BACKEND=\w+/m, `ENTERPRISE_BACKEND=${ENTERPRISE_BACKEND}`);
        } else {
            envContent += `\nENTERPRISE_BACKEND=${ENTERPRISE_BACKEND}\n`;
        }
        fs.writeFileSync(ENV_FILE, envContent, 'utf8');
        logInfo(`Enterprise backend set to: ${ENTERPRISE_BACKEND}`);
    } catch (error) {
        logError(`Error setting enterprise backend: ${error.message}`);
        return { success: false, error: `Failed to set enterprise backend: ${error.message}` };
    }

    return new Promise((resolve) => {
        let cmd = `bash ${scriptPath}`;

        // Profile or phases
        if (profile === 'custom' && phases && phases.length > 0) {
            cmd += ` --phases=${phases.join(',')}`;
        } else if (profile && profile !== 'custom') {
            cmd += ` ${profile}`;
        } else {
            cmd += ' all';
        }

        // Flags
        if (force) cmd += ' --force';
        if (auto) cmd += ' --auto';
        if (production) cmd += ' --production';
        if (upgrade) cmd += ' --upgrade';
        if (resetData) cmd += ' --reset-data';
        if (withFinetune) cmd += ' --with-finetune';
        if (withGrove) cmd += ' --with-grove';
        if (withKai) cmd += ' --with-kai';
        if (withRouter) cmd += ' --with-router';
        if (withCuvs) cmd += ' --with-cuvs';
        if (domain) cmd += ` --domain=${domain}`;

        // Set environment variables for tenant type and backend
        const env = {
            ...process.env,
            VIRTUAL_ENV: VENV_DIR,
            TENANT_TYPE: tenantType,
            ENTERPRISE_BACKEND: ENTERPRISE_BACKEND,
        };

        logInfo(`Starting deployment: ${cmd}`);
        logInfo(`Tenant type: ${tenantType}`);
        logInfo(`Enterprise backend: ${ENTERPRISE_BACKEND}`);

        installProcess = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
            env: env,
            shell: true,
        });

        let output = '';
        let errorOutput = '';

        installProcess.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stdout', data: text });

            // Parse progress
            const progressMatch = text.match(/\[([0-9]+)%\]/);
            if (progressMatch) {
                deploymentProgress = parseInt(progressMatch[1]);
                mainWindow?.webContents.send('install-progress', { progress: deploymentProgress });
            }
        });

        installProcess.stderr.on('data', (data) => {
            const text = data.toString();
            errorOutput += text;
            mainWindow?.webContents.send('install-output', { type: 'stderr', data: text });
        });

        installProcess.on('close', (code) => {
            installProcess = null;
            isDeploying = false;
            deploymentProgress = 100;
            if (code === 0) {
                logSuccess('Deployment completed successfully');
                resolve({ success: true, output });
            } else {
                logError(`Deployment failed with code ${code}`);
                resolve({ success: false, error: errorOutput || `Process exited with code ${code}` });
            }
        });

        installProcess.on('error', (err) => {
            installProcess = null;
            isDeploying = false;
            logError(`Deployment error: ${err.message}`);
            resolve({ success: false, error: err.message });
        });
    });
});

// =============================================================================
// SPOKE INSTALL
// =============================================================================
registerSafe('run-spoke-install', async (event, options) => {
    const { hubHost, token, nodeName, inferenceCapability = 'rpc_worker' } = options || {};

    if (!hubHost || !token) {
        return { success: false, error: 'hubHost and token are required.' };
    }

    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'install-spoke.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Spoke installer not found: ${scriptPath}` };
    }

    const args = [
        'bash', scriptPath,
        `--hub-host=${hubHost}`,
        `--token=${token}`,
        `--inference-capability=${inferenceCapability}`,
        '--no-wireguard',
    ];
    if (nodeName) args.push(`--node-name=${nodeName}`);

    logInfo(`Starting spoke install: ${args.join(' ')}`);

    return new Promise((resolve) => {
        const proc = spawn(args[0], args.slice(1), {
            cwd: PROJECT_ROOT,
            env: { ...process.env },
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stdout', data: text });
        });
        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stderr', data: text });
        });
        proc.on('close', (code) => {
            if (code === 0) {
                logSuccess('Spoke install completed');
                resolve({ success: true, output });
            } else {
                logError(`Spoke install failed with code ${code}`);
                resolve({ success: false, error: output });
            }
        });
    });
});

// =============================================================================
// BLACKWELL vLLM INSTALL
// =============================================================================
registerSafe('run-blackwell-install', async (event, options) => {
    const { modelName = 'deepseek-7b', tensorParallel = 4 } = options || {};

    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'install-blackwell-vllm.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Blackwell installer not found: ${scriptPath}` };
    }

    const args = [
        'bash', scriptPath,
        `--model=${modelName}`,
        `--tensor-parallel=${tensorParallel}`,
    ];

    logInfo(`Starting Blackwell install: ${args.join(' ')}`);

    return new Promise((resolve) => {
        const proc = spawn(args[0], args.slice(1), {
            cwd: PROJECT_ROOT,
            env: { ...process.env },
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stdout', data: text });
        });
        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stderr', data: text });
        });
        proc.on('close', (code) => {
            resolve(code === 0 ? { success: true, output } : { success: false, error: output });
        });
    });
});

registerSafe('cancel-install', () => {
    if (installProcess) {
        installProcess.kill('SIGTERM');
        installProcess = null;
        isDeploying = false;
        logInfo('Deployment cancelled');
        return { success: true };
    }
    return { success: false, error: 'No installation in progress' };
});

registerSafe('get-install-status', () => {
    return {
        isRunning: !!installProcess,
        progress: deploymentProgress,
    };
});

// ─────────────────────────────────────────────────────────────────────────────
// Tenant Configuration
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-tenant-config', () => {
    try {
        if (fs.existsSync(ENV_FILE)) {
            const content = fs.readFileSync(ENV_FILE, 'utf8');
            const tenantType = content.match(/^TENANT_TYPE=(\w+)/m)?.[1] || 'enterprise';
            const tenantName = content.match(/^TENANT_NAME=(.+)/m)?.[1] || 'default';
            const backend = content.match(/^ENTERPRISE_BACKEND=(\w+)/m)?.[1] || 'odoo';
            return {
                tenantType,
                tenantName,
                backend,
                runtimeConfig: RUNTIME_CONFIG[tenantType] || RUNTIME_CONFIG[TENANT_TYPES.ENTERPRISE]
            };
        }
    } catch (error) {
        logError(`Error reading tenant config: ${error.message}`);
    }
    return {
        tenantType: 'enterprise',
        tenantName: 'default',
        backend: 'odoo',
        runtimeConfig: RUNTIME_CONFIG[TENANT_TYPES.ENTERPRISE]
    };
});

// FIX (2026-10): Extract the set-tenant-config body into a plain async
// function. The previous version registered this as an ipcMain handler
// and then called ipcMain.handle('set-tenant-config', ...) from inside
// run-install. ipcMain.handle registers a handler; it does not invoke
// one. On the second call it threw "Attempted to register a second
// handler for 'set-tenant-config'", and on the first call it returned
// undefined, so tenantResult.success threw TypeError.
async function _setTenantConfig(config) {
    const { tenantType, tenantName, backend } = config;

    if (!Object.values(TENANT_TYPES).includes(tenantType)) {
        return { success: false, error: `Invalid tenant type: ${tenantType}` };
    }

    try {
        let content = '';
        if (fs.existsSync(ENV_FILE)) {
            content = fs.readFileSync(ENV_FILE, 'utf8');
        }

        if (content.match(/^TENANT_TYPE=/m)) {
            content = content.replace(/^TENANT_TYPE=\w+/m, `TENANT_TYPE=${tenantType}`);
        } else {
            content += `\nTENANT_TYPE=${tenantType}\n`;
        }

        if (content.match(/^TENANT_NAME=/m)) {
            content = content.replace(/^TENANT_NAME=.+/m, `TENANT_NAME=${tenantName || 'default'}`);
        } else {
            content += `TENANT_NAME=${tenantName || 'default'}\n`;
        }

        if (backend && content.match(/^ENTERPRISE_BACKEND=/m)) {
            content = content.replace(/^ENTERPRISE_BACKEND=\w+/m, `ENTERPRISE_BACKEND=${backend}`);
        } else if (backend) {
            content += `ENTERPRISE_BACKEND=${backend}\n`;
        }

        const runtime = RUNTIME_CONFIG[tenantType];
        const runtimeVars = [
            { key: 'RUNTIME_LANGGRAPH', value: runtime.langgraph },
            { key: 'RUNTIME_SELF_IMPROVING', value: runtime.selfImproving },
            { key: 'RUNTIME_UI', value: runtime.ui },
        ];

        for (const { key, value } of runtimeVars) {
            if (content.match(new RegExp(`^${key}=`))) {
                content = content.replace(new RegExp(`^${key}=.*`, 'm'), `${key}=${value}`);
            } else {
                content += `${key}=${value}\n`;
            }
        }

        fs.writeFileSync(ENV_FILE, content, 'utf8');
        logSuccess(`Tenant configuration updated: ${tenantType} (${tenantName || 'default'})`);

        if (backend) {
            ENTERPRISE_BACKEND = backend;
            saveProxyUrlToConfig(PROXY_URL, backend);
        }

        return { success: true };
    } catch (error) {
        logError(`Error setting tenant config: ${error.message}`);
        return { success: false, error: error.message };
    }
}

// Register the IPC handler using the extracted function.
registerSafe('set-tenant-config', (event, config) => _setTenantConfig(config));

// ─────────────────────────────────────────────────────────────────────────────
// Grove & KAI Scheduler Management
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-grove-status', async () => {
    try {
        const result = await getDockerServiceStatus('grove');
        return { running: result.running, error: result.error };
    } catch (error) {
        return { running: false, error: error.message };
    }
});

registerSafe('get-kai-status', async () => {
    try {
        const result = await getDockerServiceStatus('kai-scheduler');
        return { running: result.running, error: result.error };
    } catch (error) {
        return { running: false, error: error.message };
    }
});

registerSafe('start-grove', async () => {
    return runDockerComposeWithFile('docker-compose.grove.yaml', 'up -d grove loki tempo');
});

registerSafe('stop-grove', async () => {
    return runDockerComposeWithFile('docker-compose.grove.yaml', 'down');
});

registerSafe('start-kai', async () => {
    return runDockerComposeWithFile('docker-compose.kai.yaml', 'up -d kai-scheduler');
});

registerSafe('stop-kai', async () => {
    return runDockerComposeWithFile('docker-compose.kai.yaml', 'down');
});

async function getDockerServiceStatus(serviceName) {
    return new Promise((resolve) => {
        const cmd = `docker compose -f ${COMPOSE_FILE} ps --format json ${serviceName}`;
        exec(cmd, { cwd: path.dirname(COMPOSE_FILE) }, (error, stdout) => {
            if (error) {
                resolve({ running: false, error: error.message });
                return;
            }
            try {
                const services = JSON.parse(stdout);
                const isRunning = services.some(s => s.State === 'running');
                resolve({ running: isRunning });
            } catch (e) {
                resolve({ running: false, error: 'Failed to parse docker compose output' });
            }
        });
    });
}

function runDockerComposeWithFile(composeFile, command) {
    return new Promise((resolve) => {
        const composePath = path.join(path.dirname(COMPOSE_FILE), composeFile);

        if (!fs.existsSync(composePath)) {
            logError(`Compose file not found: ${composePath}`);
            resolve({ success: false, error: `Compose file not found: ${composeFile}` });
            return;
        }

        const cmd = `docker compose -f ${COMPOSE_FILE} -f ${composePath} ${command}`;
        logInfo(`Running: ${cmd}`);

        const proc = spawn('bash', ['-c', cmd], {
            cwd: path.dirname(COMPOSE_FILE),
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('platform-output', { type: 'stdout', data: text });
        });

        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('platform-output', { type: 'stderr', data: text });
        });

        proc.on('close', (code) => {
            if (code === 0) {
                logSuccess(`Docker compose ${command} completed`);
                resolve({ success: true, output });
            } else {
                logError(`Docker compose ${command} failed with code ${code}`);
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Feature Flags
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-feature-flags', () => {
    const flags = {
        gpuMarketplace: true,
        askSomeone: true,
        goodAnswer: true,
        selfImproving: true,
        training: true,
        bridge: true,
        notifications: true,
        fairness: false,
        jobMatching: false,
        research: false,
        triggers: false,
    };

    try {
        if (fs.existsSync(ENV_FILE)) {
            const envContent = fs.readFileSync(ENV_FILE, 'utf8');
            const lines = envContent.split('\n');
            for (const line of lines) {
                if (line.startsWith('FEATURE_')) {
                    const [key, value] = line.split('=');
                    const featureKey = key.replace('FEATURE_', '').toLowerCase();
                    if (flags.hasOwnProperty(featureKey)) {
                        flags[featureKey] = value.trim().toLowerCase() === 'true';
                    }
                }
            }
        }
    } catch (error) {
        logError(`Error reading feature flags: ${error.message}`);
    }

    return flags;
});

// ─────────────────────────────────────────────────────────────────────────────
// Platform Control (Docker Compose)
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('start-platform', () => {
    return runDockerCompose('up -d');
});

registerSafe('stop-platform', () => {
    return runDockerCompose('down');
});

registerSafe('restart-platform', () => {
    return runDockerCompose('restart');
});

registerSafe('platform-status', () => {
    return getDockerStatus();
});

function runDockerCompose(command) {
    return new Promise((resolve) => {
        const cmd = `docker compose -f ${COMPOSE_FILE} ${command}`;
        logInfo(`Running: ${cmd}`);

        const proc = spawn('bash', ['-c', cmd], {
            cwd: path.dirname(COMPOSE_FILE),
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('platform-output', { type: 'stdout', data: text });
        });

        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('platform-output', { type: 'stderr', data: text });
        });

        proc.on('close', (code) => {
            if (code === 0) {
                logSuccess(`Docker compose ${command} completed`);
                resolve({ success: true, output });
            } else {
                logError(`Docker compose ${command} failed with code ${code}`);
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });
    });
}

function getDockerStatus() {
    return new Promise((resolve) => {
        const cmd = `docker compose -f ${COMPOSE_FILE} ps --format json`;
        exec(cmd, { cwd: path.dirname(COMPOSE_FILE) }, (error, stdout) => {
            if (error) {
                resolve({ running: false, error: error.message });
                return;
            }
            try {
                const services = JSON.parse(stdout);
                const allRunning = services.every(s => s.State === 'running');
                resolve({
                    running: allRunning,
                    services: services.map(s => ({
                        name: s.Name,
                        status: s.State,
                        ports: s.Ports,
                    })),
                });
            } catch (e) {
                resolve({ running: false, error: 'Failed to parse docker compose output' });
            }
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Model Management
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('list-models', () => {
    return listModels();
});

registerSafe('download-model', async (event, options) => {
    const { model = 'deepseek-1.5b', format = 'gguf' } = options || {};
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'download-model.sh');

    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Download script not found: ${scriptPath}` };
    }

    // Ensure models directory exists
    if (!fs.existsSync(MODELS_DIR)) {
        fs.mkdirSync(MODELS_DIR, { recursive: true });
    }

    return new Promise((resolve) => {
        const cmd = `bash ${scriptPath} --model ${model} --format ${format} --dir ${MODELS_DIR}`;
        logInfo(`Downloading model: ${model} (${format})`);

        downloadProcess = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
        });

        let output = '';
        downloadProcess.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('download-progress', { data: text });
        });

        downloadProcess.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('download-progress', { data: text });
        });

        downloadProcess.on('close', (code) => {
            downloadProcess = null;
            if (code === 0) {
                logSuccess(`Model ${model} downloaded successfully`);
                resolve({ success: true, output });
            } else {
                logError(`Model download failed with code ${code}`);
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });
    });
});

registerSafe('import-model', async (event, modelPath) => {
    if (!fs.existsSync(modelPath)) {
        return { success: false, error: `Model path not found: ${modelPath}` };
    }

    const targetPath = path.join(MODELS_DIR, path.basename(modelPath));
    try {
        fs.cpSync(modelPath, targetPath, { recursive: true });
        logSuccess(`Model imported: ${targetPath}`);
        return { success: true, path: targetPath };
    } catch (error) {
        logError(`Model import failed: ${error.message}`);
        return { success: false, error: error.message };
    }
});

registerSafe('delete-model', async (event, modelPath) => {
    try {
        fs.rmSync(modelPath, { recursive: true, force: true });
        logSuccess(`Model deleted: ${modelPath}`);
        return { success: true };
    } catch (error) {
        logError(`Model deletion failed: ${error.message}`);
        return { success: false, error: error.message };
    }
});

registerSafe('load-model', async (event, modelPath) => {
    // Update the .env file to use this model
    try {
        let envContent = fs.readFileSync(ENV_FILE, 'utf8');
        const modelName = path.basename(modelPath);
        envContent = envContent.replace(/^MODEL_NAME=.*$/m, `MODEL_NAME=${modelName}`);
        fs.writeFileSync(ENV_FILE, envContent);
        logSuccess(`Model loaded: ${modelName}`);
        return { success: true, model: modelName };
    } catch (error) {
        logError(`Failed to load model: ${error.message}`);
        return { success: false, error: error.message };
    }
});

function listModels() {
    const models = [];
    if (!fs.existsSync(MODELS_DIR)) return models;

    try {
        const files = fs.readdirSync(MODELS_DIR);
        for (const file of files) {
            const fullPath = path.join(MODELS_DIR, file);
            const stats = fs.statSync(fullPath);

            if (stats.isDirectory()) {
                // Check for config.json (HF model)
                if (fs.existsSync(path.join(fullPath, 'config.json'))) {
                    models.push({
                        name: file,
                        type: 'hf',
                        path: fullPath,
                        size: getDirectorySize(fullPath),
                        format: 'Hugging Face',
                    });
                }
            } else if (file.endsWith('.gguf')) {
                models.push({
                    name: file.replace('.gguf', ''),
                    type: 'gguf',
                    path: fullPath,
                    size: stats.size,
                    format: 'GGUF (llama.cpp)',
                });
            }
        }
    } catch (error) {
        logError(`Error listing models: ${error.message}`);
    }
    return models;
}

function getDirectorySize(dirPath) {
    let size = 0;
    try {
        const files = fs.readdirSync(dirPath);
        for (const file of files) {
            const fullPath = path.join(dirPath, file);
            const stats = fs.statSync(fullPath);
            if (stats.isDirectory()) {
                size += getDirectorySize(fullPath);
            } else {
                size += stats.size;
            }
        }
    } catch {}
    return size;
}

// ─────────────────────────────────────────────────────────────────────────────
// GPU Detection
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('detect-gpu', () => {
    return detectGPUs();
});

registerSafe('detect-hardware', async () => {
    const gpus = detectGPUs();
    const totalMemory = os.totalmem();
    const cpus = os.cpus();

    // Check for Kubernetes.
    // FIX (2026-10): The previous version used the callback form of
    // exec(), so this handler returned before the callback fired and
    // k8sDetected was always false. Must await.
    let k8sDetected = false;
    try {
        const result = await execPromise('kubectl cluster-info 2>/dev/null');
        k8sDetected = result.stdout.length > 0;
    } catch (e) { k8sDetected = false; }

    // Check for Docker.
    let dockerInstalled = false;
    try {
        const result = await execPromise('docker --version 2>/dev/null');
        dockerInstalled = result.stdout.length > 0;
    } catch (e) { dockerInstalled = false; }

    return {
        gpus: gpus,
        gpuAvailable: gpus.length > 0,
        totalMemory: `${Math.round(totalMemory / 1024 / 1024 / 1024)} GB`,
        freeMemory: `${Math.round(os.freemem() / 1024 / 1024 / 1024)} GB`,
        cpuCores: cpus.length,
        cpuModel: cpus.length > 0 ? cpus[0].model : 'Unknown',
        k8sDetected: k8sDetected,
        dockerInstalled: dockerInstalled,
        platform: process.platform,
        isWSL: process.platform === 'linux' && fs.existsSync('/proc/sys/fs/binfmt_misc/WSLInterop'),
    };
});

// =============================================================================
// HARDWARE DETECTION (moved out of Odoo into src/core/hardware_detection.py)
// =============================================================================
// The Python hardware detection module is invoked as a subprocess from the
// Launcher. This decouples hardware discovery from Odoo entirely, which
// means:
//   1. The Launcher can show hardware info BEFORE any deployment
//   2. Users can see what their machine can do without installing Odoo
//   3. The same detection works for the Hub (Linux) and Spoke (Windows)
//   4. We can move to a non-Odoo backend in the future without touching
//      this code path
// =============================================================================

registerSafe('detect-hardware-profile', async () => {
    /**
     * Run the Python hardware detection module and return the SystemProfile.
     *
     * The script is located at src/core/hardware_detection.py. It prints
     * JSON to stdout, which we parse and return.
     */
    const scriptPath = path.join(PROJECT_ROOT, 'src', 'core', 'hardware_detection.py');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Hardware detection script not found: ${scriptPath}` };
    }

    // Use the venv Python if it exists, otherwise fall back to system Python
    const venvPython = path.join(VENV_DIR, 'bin', 'python');
    const pythonBin = fs.existsSync(venvPython) ? venvPython : 'python3';

    return new Promise((resolve) => {
        exec(`${pythonBin} "${scriptPath}"`, { cwd: PROJECT_ROOT, maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
            if (error) {
                logError(`Hardware detection failed: ${stderr || error.message}`);
                resolve({ success: false, error: stderr || error.message });
                return;
            }
            try {
                const profile = JSON.parse(stdout);
                logInfo(`Hardware profile: ${profile.hostname}, ${profile.gpus.length} GPU(s), recommended role: ${profile.recommended_role || 'unknown'}`);
                resolve({ success: true, data: profile });
            } catch (e) {
                logError(`Failed to parse hardware profile JSON: ${e.message}`);
                resolve({ success: false, error: `Invalid JSON output: ${stdout.substring(0, 500)}` });
            }
        });
    });
});

registerSafe('get-recommended-role', async () => {
    /**
     * Convenience handler that returns only the recommended role for this
     * machine (dynamo_worker / rpc_worker / local_only). This is used by
     * the Spoke installer to decide which software to install.
     */
    const result = await ipcMain.handle('detect-hardware-profile');
    if (result.success && result.data) {
        return { success: true, role: result.data.recommended_role || 'local_only' };
    }
    return { success: false, role: 'local_only', error: result.error };
});

function detectGPUs() {
    const gpus = [];
    const platform = process.platform;

    try {
        // NVIDIA GPU detection
        if (platform === 'linux' || platform === 'win32') {
            try {
                const result = execSync('nvidia-smi --query-gpu=name,index,memory.total,compute_cap --format=csv,noheader', { encoding: 'utf8', stdio: 'pipe' });
                if (result) {
                    const lines = result.trim().split('\n');
                    for (const line of lines) {
                        const parts = line.split(',').map(s => s.trim());
                        gpus.push({
                            vendor: 'nvidia',
                            name: parts[0] || 'Unknown',
                            index: parseInt(parts[1]) || 0,
                            memory: parts[2] || '0 MiB',
                            computeCapability: parts[3] || 'unknown',
                        });
                    }
                }
            } catch (e) {
                // nvidia-smi not available – skip NVIDIA detection
                logInfo('nvidia-smi not available – skipping NVIDIA GPU detection');
            }
        }

        // AMD GPU detection (ROCm)
        if (platform === 'linux') {
            try {
                const result = execSync('rocminfo | grep "Name:"', { encoding: 'utf8', stdio: 'pipe' });
                if (result) {
                    const lines = result.trim().split('\n');
                    for (const line of lines) {
                        const name = line.replace('Name:', '').trim();
                        if (name && !name.includes('AMD')) {
                            gpus.push({
                                vendor: 'amd',
                                name: name,
                                index: gpus.length,
                                memory: 'Unknown',
                                computeCapability: 'unknown',
                            });
                        }
                    }
                }
            } catch (e) { /* rocminfo not available – skip AMD detection */ }

            // Intel GPU detection
            try {
                const result = execSync('clinfo | grep -i "intel"', { encoding: 'utf8', stdio: 'pipe' });
                if (result) {
                    gpus.push({
                        vendor: 'intel',
                        name: 'Intel GPU',
                        index: gpus.length,
                        memory: 'Unknown',
                        computeCapability: 'unknown',
                    });
                }
            } catch (e) { /* clinfo not available – skip Intel detection */ }
        }
    } catch (error) {
        logError(`GPU detection error: ${error.message}`);
    }

    return gpus;
}

// ─────────────────────────────────────────────────────────────────────────────
// Backup & Restore
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('create-backup', async (event, options) => {
    const { outputDir } = options || {};
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'backup.sh');

    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Backup script not found: ${scriptPath}` };
    }

    return new Promise((resolve) => {
        let cmd = `bash ${scriptPath}`;
        if (outputDir) cmd += ` --output-dir ${outputDir}`;
        if (options?.auto) cmd += ' --auto';

        logInfo(`Starting backup: ${cmd}`);

        const proc = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('backup-output', { type: 'stdout', data: text });
        });

        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('backup-output', { type: 'stderr', data: text });
        });

        proc.on('close', (code) => {
            if (code === 0) {
                logSuccess('Backup completed successfully');
                resolve({ success: true, output });
            } else {
                logError(`Backup failed with code ${code}`);
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });
    });
});

registerSafe('list-backups', () => {
    const backupDir = path.join(os.homedir(), '.nettrades', 'backups');
    const backups = [];

    try {
        if (fs.existsSync(backupDir)) {
            const files = fs.readdirSync(backupDir);
            for (const file of files) {
                if (file.startsWith('nettrades-backup-') && file.endsWith('.tar.gz')) {
                    const fullPath = path.join(backupDir, file);
                    const stats = fs.statSync(fullPath);
                    backups.push({
                        name: file,
                        path: fullPath,
                        size: stats.size,
                        created: stats.mtime,
                    });
                }
            }
        }
    } catch (error) {
        logError(`Error listing backups: ${error.message}`);
    }

    return backups.sort((a, b) => b.created - a.created);
});

registerSafe('restore-backup', async (event, backupPath) => {
    if (!fs.existsSync(backupPath)) {
        return { success: false, error: `Backup file not found: ${backupPath}` };
    }

    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'restore.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `Restore script not found: ${scriptPath}` };
    }

    return new Promise((resolve) => {
        const cmd = `bash ${scriptPath} ${backupPath} --auto`;
        logInfo(`Starting restore: ${cmd}`);

        const proc = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('backup-output', { type: 'stdout', data: text });
        });

        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('backup-output', { type: 'stderr', data: text });
        });

        proc.on('close', (code) => {
            if (code === 0) {
                logSuccess('Restore completed successfully');
                resolve({ success: true, output });
            } else {
                logError(`Restore failed with code ${code}`);
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Container Management (Docker)
// ─────────────────────────────────────────────────────────────────────────────

// Helper: Get container status using docker compose
async function getContainerStatus() {
    try {
        const result = await execCommand(
            `docker compose -f ${COMPOSE_FILE} ps --format json`
        );
        return JSON.parse(result);
    } catch (error) {
        // Fallback to docker ps if compose fails
        const result = await execCommand(
            `docker ps -a --format json`
        );
        return result.split('\n').filter(line => line.trim()).map(line => JSON.parse(line));
    }
}

// List all containers
registerSafe('list-containers', async () => {
    try {
        // Use docker compose ps for detailed info
        const cmd = `docker compose -f ${COMPOSE_FILE} ps --format json --all`;
        const result = await execCommand(cmd);
        if (!result || result.trim() === '') {
            return { success: true, containers: [] };
        }
        // Parse JSON array
        const containers = JSON.parse(result);
        // Enhance with health status
        for (const container of containers) {
            // Get health status
            try {
                const healthCmd = `docker inspect ${container.Name || container.ID} --format '{{.State.Health.Status}}'`;
                const health = await execCommand(healthCmd);
                container.Health = health.trim() || 'none';
            } catch (e) {
                container.Health = 'none';
            }
            // Get age
            try {
                const ageCmd = `docker inspect ${container.Name || container.ID} --format '{{.Created}}'`;
                const created = await execCommand(ageCmd);
                const createdDate = new Date(created.trim());
                container.Age = timeAgo(createdDate);
            } catch (e) {
                container.Age = 'unknown';
            }
            // Get image
            try {
                const imageCmd = `docker inspect ${container.Name || container.ID} --format '{{.Config.Image}}'`;
                const image = await execCommand(imageCmd);
                container.Image = image.trim() || 'unknown';
            } catch (e) {
                container.Image = 'unknown';
            }
        }
        return { success: true, containers };
    } catch (error) {
        // Fallback: use docker ps
        try {
            const cmd = `docker ps -a --format json`;
            const result = await execCommand(cmd);
            if (!result || result.trim() === '') {
                return { success: true, containers: [] };
            }
            const lines = result.split('\n').filter(line => line.trim());
            const containers = lines.map(line => JSON.parse(line));
            return { success: true, containers };
        } catch (e) {
            return { success: false, error: e.message };
        }
    }
});

// Start a container
registerSafe('start-container', async (event, containerId) => {
    try {
        const cmd = `docker compose -f ${COMPOSE_FILE} start ${containerId}`;
        const result = await execCommand(cmd);
        return { success: true, output: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Stop a container
registerSafe('stop-container', async (event, containerId) => {
    try {
        const cmd = `docker compose -f ${COMPOSE_FILE} stop ${containerId}`;
        const result = await execCommand(cmd);
        return { success: true, output: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Restart a container
registerSafe('restart-container', async (event, containerId) => {
    try {
        const cmd = `docker compose -f ${COMPOSE_FILE} restart ${containerId}`;
        const result = await execCommand(cmd);
        return { success: true, output: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Start all containers
registerSafe('start-all-containers', async () => {
    try {
        const cmd = `docker compose -f ${COMPOSE_FILE} up -d`;
        const result = await execCommand(cmd);
        return { success: true, output: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Stop all containers
registerSafe('stop-all-containers', async () => {
    try {
        const cmd = `docker compose -f ${COMPOSE_FILE} down`;
        const result = await execCommand(cmd);
        return { success: true, output: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Restart all containers
registerSafe('restart-all-containers', async () => {
    try {
        const cmd = `docker compose -f ${COMPOSE_FILE} restart`;
        const result = await execCommand(cmd);
        return { success: true, output: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Get container logs
registerSafe('container-logs', async (event, containerId, lines = 100) => {
    try {
        const cmd = `docker logs --tail ${lines} ${containerId}`;
        const result = await execCommand(cmd);
        return { success: true, logs: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Helper: Time ago formatter
function timeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    const intervals = [
        { label: 'year', seconds: 31536000 },
        { label: 'month', seconds: 2592000 },
        { label: 'day', seconds: 86400 },
        { label: 'hour', seconds: 3600 },
        { label: 'minute', seconds: 60 },
        { label: 'second', seconds: 1 },
    ];
    for (const interval of intervals) {
        const count = Math.floor(seconds / interval.seconds);
        if (count >= 1) {
            return `${count} ${interval.label}${count > 1 ? 's' : ''} ago`;
        }
    }
    return 'just now';
}

// ─────────────────────────────────────────────────────────────────────────────
// VPN Management (WireGuard)
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('vpn-add-peer', async (event, username, ip) => {
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'wireguard-manager.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `WireGuard script not found: ${scriptPath}` };
    }

    return new Promise((resolve) => {
        const cmd = `sudo ${scriptPath} add ${username} ${ip || ''}`;
        logInfo(`Adding WireGuard peer: ${username}`);

        exec(cmd, { cwd: PROJECT_ROOT }, (error, stdout, stderr) => {
            if (error) {
                logError(`WireGuard peer add failed: ${stderr}`);
                resolve({ success: false, error: stderr || error.message });
            } else {
                logSuccess(`WireGuard peer added: ${username}`);
                resolve({ success: true, output: stdout });
            }
        });
    });
});

registerSafe('vpn-list-peers', () => {
    return new Promise((resolve) => {
        exec('sudo wg show', { cwd: PROJECT_ROOT }, (error, stdout) => {
            if (error) {
                resolve({ success: false, error: error.message });
            } else {
                resolve({ success: true, output: stdout });
            }
        });
    });
});

registerSafe('vpn-status', () => {
    return new Promise((resolve) => {
        exec('sudo wg show', { cwd: PROJECT_ROOT }, (error, stdout) => {
            if (error) {
                resolve({ running: false, error: error.message });
            } else {
                resolve({ running: true, output: stdout });
            }
        });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// "Ask Someone" Expert System Integration
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('ask-someone', async (event, data) => {
    const { question, category, urgency, expertId } = data || {};
    const serverUrl = await getServerUrlInternal();

    // Call the LangGraph Good Answer agent
    try {
        const response = await fetch(`${serverUrl}:8000/runs/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input: { question, category, urgency, expert_id: expertId, action: 'ask_someone' },
                config: { configurable: { thread_id: crypto.randomUUID() } }
            }),
        });

        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        logError(`Ask Someone error: ${error.message}`);
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// "Good Answer" Training Data Management
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('good-answer', async (event, data) => {
    const { question, answer, rating, userId } = data || {};
    const serverUrl = await getServerUrlInternal();

    // Call the LangGraph Good Answer agent
    try {
        const response = await fetch(`${serverUrl}:8000/runs/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input: { question, answer, rating, user_id: userId, action: 'good_answer' },
                config: { configurable: { thread_id: crypto.randomUUID() } }
            }),
        });

        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        logError(`Good Answer error: ${error.message}`);
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Training & Fine-Tuning
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('start-training', async (event, data) => {
    const { dataset, model, method, params } = data || {};
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/runs/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input: { dataset, model, method: method || 'unsloth', params: params || {}, action: 'start_training' },
                config: { configurable: { thread_id: crypto.randomUUID() } }
            }),
        });

        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        logError(`Training error: ${error.message}`);
        return { success: false, error: error.message };
    }
});

registerSafe('training-status', async () => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/training/status`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Agent Management
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('list-agents', async () => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/agents/list`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('agent-status', async (event, agentId) => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/agents/${agentId}/status`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Queue Management
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('list-queue', async () => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/queue/list`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('cancel-task', async (event, taskId) => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/queue/${taskId}/cancel`, { method: 'POST' });
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('retry-task', async (event, taskId) => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/queue/${taskId}/retry`, { method: 'POST' });
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// GPU Marketplace
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('marketplace-listings', async () => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8090/api/v1/gpu/listings`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('marketplace-list-gpu', async (event, data) => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8090/api/v1/gpu/list`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('marketplace-book-gpu', async (event, data) => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8090/api/v1/gpu/book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Node Discovery
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-discovered-nodes', () => {
    return Array.from(discoveredNodes.values());
});

// ─────────────────────────────────────────────────────────────────────────────
// System Health & Monitoring
// ─────────────────────────────────────────────────────────────────────────────

async function computeSystemHealth() {
    const serverUrl = await getServerUrlInternal();
    const health = { services: {}, gpus: [], models: [], uptime: process.uptime() };

    // Check Odoo
    try {
        const response = await fetch(`${serverUrl}:8069/web/health`);
        health.services.odoo = response.ok ? 'healthy' : 'unhealthy';
    } catch { health.services.odoo = 'unhealthy'; }

    // Check LangGraph
    try {
        const response = await fetch(`${serverUrl}:8000/health`);
        health.services.langgraph = response.ok ? 'healthy' : 'unhealthy';
    } catch { health.services.langgraph = 'unhealthy'; }

    // Check Dynamo
    try {
        const env = _readEnvFile();
        const dynamoKey = env.DYNAMO_API_KEY || 'dummy';
        const response = await fetch(`${serverUrl}:8001/v1/models`, {
            headers: { 'Authorization': `Bearer ${dynamoKey}` }
        });
        health.services.dynamo = response.ok ? 'healthy' : 'unhealthy';
    } catch { health.services.dynamo = 'unhealthy'; }

    // ── NEW: Check PostgreSQL ──
    try {
        const { stdout } = await execPromise(
            `docker compose -f ${COMPOSE_FILE} exec -T postgres pg_isready -U odoo -d odoo`
        );
        health.services.postgres = stdout.includes('accepting connections')
            ? 'healthy'
            : 'unhealthy';
    } catch {
        health.services.postgres = 'unhealthy';
    }

    health.gpus = detectGPUs();
    health.models = listModels();
    return health;
}

registerSafe('system-health', async () => {
    return computeSystemHealth();
});

// =============================================================================
// CLUSTER, ROUTING, HEALTH, TOKENS — 2026-10 handlers
// =============================================================================
// These handlers surface state that the backend produces:
//   - The RPC scheduler's layer assignment (Cluster tab)
//   - The health monitor's live node state (enhanced Nodes tab)
//   - The supervisor's routing decisions and failover events (Routing tab)
//   - The gpu.registration.token lifecycle (Tokens tab)
//
// The four helpers below (fetchHealthNodes, fetchRoutingEvents,
// fetchClusterState, fetchActiveTrack) are plain functions. They are
// called both by the individual IPC handlers and by the aggregate
// get-demo-status handler. Never call ipcMain.handle from inside a
// handler — that was the cause of the blank Demo tab on 2026-10-29.
// =============================================================================

// -----------------------------------------------------------------------------
// Helper: Get the LangGraph base URL from the hub config or the default
// -----------------------------------------------------------------------------
function getLangGraphUrl() {
    const hub = loadHubConfig();
    return (hub.langgraph_url || 'http://localhost:8000').replace(/\/+$/, '');
}

// -----------------------------------------------------------------------------
// Helper: Get the LANGGRAPH_API_KEY from the .env file
// -----------------------------------------------------------------------------
//function getLangGraphApiKey() {
//    try {
//        if (!fs.existsSync(ENV_FILE)) return '';
//        const content = fs.readFileSync(ENV_FILE, 'utf8');
//        const m = content.match(/^LANGGRAPH_API_KEY=['"]?([^'"\n]+)['"]?/m);
//        return m ? m[1] : '';
//    } catch {
//        return '';
//    }
//}     HARDCODED VALUES FOR DEMO

function getLangGraphApiKey() {
    try {
        if (!fs.existsSync(ENV_FILE)) return 'IC05QU52jL2evU0AxlrOgpxeIPrj7LuWXvwRTqrCsvufLBGT';
        const content = fs.readFileSync(ENV_FILE, 'utf8');
        const m = content.match(/^LANGGRAPH_API_KEY=['"]?([^'"\n]+)['"]?/m);
        return m ? m[1] : 'IC05QU52jL2evU0AxlrOgpxeIPrj7LuWXvwRTqrCsvufLBGT';
    } catch {
        return 'IC05QU52jL2evU0AxlrOgpxeIPrj7LuWXvwRTqrCsvufLBGT';
    }
}
// -----------------------------------------------------------------------------
// ─── Plain async helpers (extracted from the ipcMain.handle wrappers) ───
// -----------------------------------------------------------------------------

async function fetchHealthNodes() {
    try {
        const resp = await fetch(`${getLangGraphUrl()}/nodes`, {
            headers: { 'X-API-Key': getLangGraphApiKey() },
            signal: AbortSignal.timeout(5000)
        });
        if (!resp.ok) return { success: false, error: `HTTP ${resp.status}`, nodes: [] };
        const data = await resp.json();
        return { success: true, nodes: data.nodes || [] };
    } catch (e) {
        logError(`fetchHealthNodes failed: ${e.message}`);
        return { success: false, error: e.message, nodes: [] };
    }
}

async function fetchRoutingEvents(limit = 100) {
    try {
        const resp = await fetch(`${getLangGraphUrl()}/routing/events?limit=${limit}`, {
            headers: { 'X-API-Key': getLangGraphApiKey() },
        });
        if (!resp.ok) return { success: false, error: `HTTP ${resp.status}`, events: [] };
        const data = await resp.json();
        return { success: true, events: data.events || [] };
    } catch (e) {
        return { success: false, error: e.message, events: [] };
    }
}

async function fetchClusterState(clusterId = 1) {
    try {
        const resp = await fetch(`${getLangGraphUrl()}/cluster/${clusterId}`, {
            headers: { 'X-API-Key': getLangGraphApiKey() },
            signal: AbortSignal.timeout(5000)
        });
        if (!resp.ok) return { success: false, error: `HTTP ${resp.status}` };
        const data = await resp.json();
        return { success: true, data };
    } catch (e) {
        logError(`fetchClusterState failed: ${e.message}`);
        return { success: false, error: e.message };
    }
}

async function fetchActiveTrack() {
    try {
        const resp = await fetch(`${getLangGraphUrl()}/routing/events?limit=1`, {
            headers: { 'X-API-Key': getLangGraphApiKey() },
            signal: AbortSignal.timeout(5000)
        });
        if (!resp.ok) return { success: false, error: `HTTP ${resp.status}` };
        const data = await resp.json();
        const events = data.events || [];
        if (events.length === 0) return { success: true, track: null, event: null };
        const last = events[events.length - 1];
        return { success: true, track: last.track, event: last };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

// ─── Thin IPC wrappers around the plain functions ───

registerSafe('get-health-nodes', async () => fetchHealthNodes());
registerSafe('get-routing-events', async (_evt, limit = 100) => fetchRoutingEvents(limit));
registerSafe('get-cluster-state', async (_evt, clusterId = 1) => fetchClusterState(clusterId));
registerSafe('get-active-track', async () => fetchActiveTrack());

// =============================================================================
// DEMO STATUS AGGREGATION (2026-10-30)
// =============================================================================
// Combines health, routing, cluster, and claim status into a single payload
// for the Demo tab. Polled every 5 seconds.
//
// FIX: the previous version called ipcMain.handle() from inside this handler,
// which threw "Attempted to register a second handler" and left the Demo tab
// blank. It now calls the plain fetch functions above.
// =============================================================================
registerSafe('get-demo-status', async () => {
    const [nodesRes, routingRes, clusterRes, activeTrackRes] = await Promise.allSettled([
        fetchHealthNodes(),
        fetchRoutingEvents(50),
        fetchClusterState(1),
        fetchActiveTrack(),
    ]);

    const nodes = nodesRes.status === 'fulfilled' ? (nodesRes.value.nodes || []) : [];
    const events = routingRes.status === 'fulfilled' ? (routingRes.value.events || []) : [];
    const cluster = clusterRes.status === 'fulfilled' ? clusterRes.value.data : null;
    const activeTrack = activeTrackRes.status === 'fulfilled' ? activeTrackRes.value : null;

    // Count healthy nodes by role
    const rpcHealthy = nodes.filter(n => n.role === 'rpc_worker' && n.is_healthy).length;
    const dynamoHealthy = nodes.filter(n => n.role === 'dynamo_worker' && n.is_healthy).length;

    // Determine claim status
    const claim1 = {
        id: 1,
        name: 'llama.cpp CPU Baseline',
        status: 'checking',
        detail: 'Not tested',
    };
    const claim2 = {
        id: 2,
        name: 'Distributed RPC (AMD GPUs)',
        status: rpcHealthy > 0 ? 'ready' : 'down',
        detail: `${rpcHealthy} RPC worker${rpcHealthy === 1 ? '' : 's'} healthy`,
    };
    const claim3 = {
        id: 3,
        name: 'V100 vLLM (Dynamo Track)',
        status: dynamoHealthy > 0 ? 'ready' : 'down',
        detail: `${dynamoHealthy} dynamo worker${dynamoHealthy === 1 ? '' : 's'} healthy`,
    };
    const claim4 = {
        id: 4,
        name: 'Fail‑Loud Failover',
        status: 'ready', // always ready (testable)
        detail: events.some(e => e.event.startsWith('failover_tier')) ? 'Last failover seen' : 'No failovers yet',
    };

    // Last failover event
    const lastFailover = events.filter(e => e.event.startsWith('failover_tier')).pop() || null;

    return {
        claims: [claim1, claim2, claim3, claim4],
        nodes,
        activeTrack: activeTrack?.track || null,
        cluster,
        lastFailover,
        rpcHealthy,
        dynamoHealthy,
    };
});

registerSafe('run-pre-demo-check', async () => {
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'pre-demo-check.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: 'pre-demo-check.sh not found' };
    }
    return new Promise((resolve) => {
        const proc = spawn('bash', [scriptPath], { cwd: PROJECT_ROOT });
        let output = '';
        proc.stdout.on('data', d => { output += d.toString(); });
        proc.stderr.on('data', d => { output += d.toString(); });
        proc.on('close', code => resolve({ success: code === 0, output }));
    });
});

registerSafe('trigger-failover', async () => {
    // Send a pinned RPC request after stopping the AMD spoke
    // The rehearsal does this; for the demo we want a button.
    const env = _readEnvFile();
    const langgraphUrl = (loadHubConfig().langgraph_url || 'http://localhost:8000').replace(/\/+$/, '');
    const apiKey = env.LANGGRAPH_API_KEY || '';
    const tid = `demo-failover-${Date.now()}`;

    // First, stop the AMD spoke (via SSH if configured, else prompt)
    // For the Launcher, we assume the operator has stopped it manually.
    // We simply send a pinned RPC request.
    try {
        const resp = await fetch(`${langgraphUrl}/invoke`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({
                input: { messages: [{ role: 'user', content: 'Hello after spoke stop.' }], company_id: 1, _force_track: 'rpc' },
                config: { configurable: { thread_id: tid } },
            }),
        });
        if (resp.status === 503) {
            const retryAfter = resp.headers.get('Retry-After') || '30';
            return { success: true, status: 503, retryAfter, detail: 'Tier 6 fail-loud triggered' };
        }
        const data = await resp.json();
        return { success: true, status: resp.status, data };
    } catch (e) {
        return { success: false, error: e.message };
    }
});


// -----------------------------------------------------------------------------
// relaunch-cluster
// -----------------------------------------------------------------------------
// Triggers RPCScheduler.launch_cluster() or restart_without_node() via
// POST /rpc/relaunch. The options object may carry:
//   - cluster_id (required)
//   - exclude_node_id (optional; triggers restart_without_node)
//   - exclude_port (optional; per-GPU failure)
registerSafe('relaunch-cluster', async (_evt, opts = {}) => {
    const url = `${getLangGraphUrl()}/rpc/relaunch`;
    const body = {
        cluster_id: opts.cluster_id || 1,
    };
    if (opts.exclude_node_id != null) body.exclude_node_id = opts.exclude_node_id;
    if (opts.exclude_port != null) body.exclude_port = opts.exclude_port;

    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': getLangGraphApiKey(),
            },
            body: JSON.stringify(body),
        });
        const data = await resp.json().catch(() => ({}));
        return { success: resp.ok, data, status: resp.status };
    } catch (e) {
        logError(`relaunch-cluster failed: ${e.message}`);
        return { success: false, error: e.message };
    }
});

// -----------------------------------------------------------------------------
// get-node-health
// -----------------------------------------------------------------------------
registerSafe('get-node-health', async (_evt, nodeId) => {
    const url = `${getLangGraphUrl()}/nodes/${encodeURIComponent(nodeId)}/health`;
    try {
        const resp = await fetch(url, {
            headers: { 'X-API-Key': getLangGraphApiKey() },
        });
        if (!resp.ok) return { success: false, error: `HTTP ${resp.status}` };
        return { success: true, data: await resp.json() };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// -----------------------------------------------------------------------------
// get-inference-config
// -----------------------------------------------------------------------------
// Returns the LLM_BASE_URL, MODEL_NAME, and model sizing env vars so the
// Routing tab can show which endpoint the "dynamo" track is currently
// pointing at (Contabo, V100, or a local mock).
registerSafe('get-inference-config', () => {
    try {
        const envContent = fs.existsSync(ENV_FILE)
            ? fs.readFileSync(ENV_FILE, 'utf8')
            : '';
        const pick = (key, fallback = '') => {
            const m = envContent.match(new RegExp(`^${key}=['"]?([^'"\\n]+)['"]?`, 'm'));
            return m ? m[1] : fallback;
        };
        return {
            success: true,
            data: {
                llm_base_url: pick('LLM_BASE_URL', '(not set)'),
                model_name: pick('MODEL_NAME', '(not set)'),
                model_size_bytes: parseInt(pick('MODEL_SIZE_BYTES', '0')) || 0,
                model_layers: parseInt(pick('MODEL_LAYERS', '0')) || 0,
                rpc_master_model: pick('RPC_MASTER_MODEL', '(not set)'),
                rpc_backends: pick('RPC_BACKENDS', ''),
                rpc_split: pick('RPC_SPLIT', ''),
            },
        };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// list-tokens
// ─────────────────────────────────────────────────────────────────────────────
registerSafe('list-tokens', async () => {
    const url = `${getLangGraphUrl()}/tokens`;
    try {
        const resp = await fetch(url, {
            headers: { 'X-API-Key': getLangGraphApiKey() },
        });
        if (!resp.ok) return { success: false, error: `HTTP ${resp.status}`, tokens: [] };
        const data = await resp.json();
        return { success: true, tokens: data.tokens || [] };
    } catch (e) {
        return { success: false, error: e.message, tokens: [] };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// create-token
// ─────────────────────────────────────────────────────────────────────────────
registerSafe('create-token', async (_evt, opts = {}) => {
    const serverUrl = await getServerUrlInternal();
    const tokenName = opts.name || 'Launcher Token';
    const clusterId = opts.cluster_id || 1;

    // Generate a URL-safe random token
    const plaintext = crypto.randomBytes(24).toString('hex');

    try {
        const envContent = fs.readFileSync(ENV_FILE, 'utf8');
        const pick = (k, d = '') => {
            const m = envContent.match(new RegExp(`^${k}=['"]?([^'"\\n]+)['"]?`, 'm'));
            return m ? m[1] : d;
        };
        const resp = await httpWithRetry(`${serverUrl}:8090/jsonrpc`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': pick('PROXY_API_KEY'),
            },
            body: JSON.stringify({
                jsonrpc: '2.0', method: 'call',
                params: {
                    service: 'object', method: 'execute_kw',
                    args: [
                        pick('ODOO_DB', 'odoo'),
                        parseInt(pick('ODOO_USER', '2')),
                        pick('ODOO_ADMIN_PASSWORD', 'admin'),
                        'gpu.registration.token', 'create',
                        [{ name: tokenName, cluster_id: clusterId, token: plaintext }],
                    ],
                },
                id: 1,
            }),
        });
        const body = await resp.json();
        if (body.error) {
            return { success: false, error: JSON.stringify(body.error) };
        }
        return { success: true, token_id: body.result, plaintext };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// revoke-token
// ─────────────────────────────────────────────────────────────────────────────
registerSafe('revoke-token', async (_evt, tokenId) => {
    const serverUrl = await getServerUrlInternal();
    try {
        const envContent = fs.readFileSync(ENV_FILE, 'utf8');
        const pick = (k, d = '') => {
            const m = envContent.match(new RegExp(`^${k}=['"]?([^'"\\n]+)['"]?`, 'm'));
            return m ? m[1] : d;
        };
        const resp = await httpWithRetry(`${serverUrl}:8090/jsonrpc`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': pick('PROXY_API_KEY'),
            },
            body: JSON.stringify({
                jsonrpc: '2.0', method: 'call',
                params: {
                    service: 'object', method: 'execute_kw',
                    args: [
                        pick('ODOO_DB', 'odoo'),
                        parseInt(pick('ODOO_USER', '2')),
                        pick('ODOO_ADMIN_PASSWORD', 'admin'),
                        'gpu.registration.token', 'write',
                        [[tokenId], { is_revoked: true }],
                    ],
                },
                id: 1,
            }),
        });
        const body = await resp.json();
        if (body.error) return { success: false, error: JSON.stringify(body.error) };
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Logs
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-logs', async (event, options) => {
    const { service, lines = 100 } = options || {};
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/logs/${service}?lines=${lines}`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Alerts & Notifications
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-alerts', async () => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/alerts`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('get-notifications', async () => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/notifications`);
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('mark-notification-read', async (event, notificationId) => {
    const serverUrl = await getServerUrlInternal();

    try {
        const response = await fetch(`${serverUrl}:8000/notifications/${notificationId}/read`, { method: 'POST' });
        if (response.ok) {
            const result = await response.json();
            return { success: true, data: result };
        } else {
            return { success: false, error: `HTTP error: ${response.status}` };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Developer Tools – Wine Installer
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('install-wine', async (event) => {
    // Check if wine is already installed
    try {
        execSync('wine --version', { stdio: 'ignore' });
        return { success: true, alreadyInstalled: true, message: 'Wine is already installed.' };
    } catch (e) { /* Not installed, proceed */ }

    return new Promise((resolve) => {
        const commands = [
            'sudo dpkg --add-architecture i386',
            'sudo apt update',
            `sudo apt install -y wine wine64 wine32 libasound2t64 libasound2t64:i386 libnspr4 libnss3 libxss1 libatk-bridge2.0-0t64 libgtk-3-0t64 libgbm1 libnspr4:i386 libnss3:i386 libgtk-3-0t64:i386`
        ];
        const fullCmd = commands.join(' && ');
        logInfo(`Installing Wine with: ${fullCmd}`);

        const proc = spawn('bash', ['-c', fullCmd], { stdio: 'pipe', shell: true });
        let output = '';

        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('wine-output', { type: 'stdout', data: text });
        });

        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('wine-output', { type: 'stderr', data: text });
        });

        proc.on('close', (code) => {
            if (code === 0) {
                logSuccess('Wine installation completed successfully');
                resolve({ success: true, output });
            } else {
                logError(`Wine installation failed with code ${code}`);
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });

        proc.on('error', (err) => {
            logError(`Wine installation error: ${err.message}`);
            resolve({ success: false, error: err.message });
        });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('open-external', (event, url) => {
    shell.openExternal(url);
});

registerSafe('show-dialog', async (event, options) => {
    return dialog.showMessageBox(options);
});

// ─────────────────────────────────────────────────────────────────────────────
// System Check
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('system-check', async () => {
    const checks = {
        wsl: { name: 'WSL2', status: 'unknown', details: '' },
        docker: { name: 'Docker', status: 'unknown', details: '' },
        gpu: { name: 'GPU Drivers', status: 'unknown', details: '' },
        python: { name: 'Python 3.10+', status: 'unknown', details: '' },
        node: { name: 'Node.js 20+', status: 'unknown', details: '' },
        backend: { name: 'Enterprise Backend', status: 'unknown', details: '' },
        proxy: { name: 'Proxy URL', status: 'unknown', details: '' },
    };

    // Check WSL2 (on Windows) or Linux
    if (process.platform === 'win32') {
        try {
            const result = execSync('wsl --list --verbose', { encoding: 'utf8', stdio: 'pipe' });
            checks.wsl.status = result.includes('Ubuntu') ? 'ok' : 'warning';
            checks.wsl.details = result.includes('Ubuntu') ? 'Ubuntu distribution found' : 'No Ubuntu distribution found';
        } catch (e) {
            checks.wsl.status = 'error';
            checks.wsl.details = 'WSL2 not installed or not configured';
        }
    } else {
        // On Linux, WSL check is not applicable
        checks.wsl.status = 'ok';
        checks.wsl.details = 'Native Linux (no WSL needed)';
    }

    // Check Docker
    try {
        const result = execSync('docker info', { encoding: 'utf8', stdio: 'pipe' });
        checks.docker.status = result.includes('Server Version') ? 'ok' : 'error';
        checks.docker.details = result.includes('Server Version') ? 'Docker daemon is running' : 'Docker daemon not responding';
    } catch (e) {
        checks.docker.status = 'error';
        checks.docker.details = 'Docker not installed or not running';
    }

    // Check GPU (nvidia-smi)
    try {
        const result = execSync('nvidia-smi', { encoding: 'utf8', stdio: 'pipe' });
        checks.gpu.status = 'ok';
        checks.gpu.details = 'NVIDIA GPU detected';
    } catch (e) {
        checks.gpu.status = 'warning';
        checks.gpu.details = 'No NVIDIA GPU or nvidia-smi not found';
    }

    // Check Python
    try {
        const result = execSync('python3 --version', { encoding: 'utf8', stdio: 'pipe' });
        const version = result.match(/\d+\.\d+/)?.[0];
        if (version && parseFloat(version) >= 3.10) {
            checks.python.status = 'ok';
            checks.python.details = `Python ${version} found`;
        } else {
            checks.python.status = 'error';
            checks.python.details = `Python ${version || 'unknown'} (need 3.10+)`;
        }
    } catch (e) {
        checks.python.status = 'error';
        checks.python.details = 'Python 3 not found';
    }

    // Check Node.js
    try {
        const result = execSync('node --version', { encoding: 'utf8', stdio: 'pipe' });
        const version = result.match(/\d+\.\d+\.\d+/)?.[0];
        if (version && parseFloat(version) >= 20.0) {
            checks.node.status = 'ok';
            checks.node.details = `Node.js ${version} found`;
        } else {
            checks.node.status = 'error';
            checks.node.details = `Node.js ${version || 'unknown'} (need 20+)`;
        }
    } catch (e) {
        checks.node.status = 'error';
        checks.node.details = 'Node.js not found';
    }

    // Check Enterprise Backend
    try {
        const backend = ENTERPRISE_BACKEND || 'odoo';
        checks.backend.status = 'ok';
        checks.backend.details = `Using ${backend} backend`;
    } catch (e) {
        checks.backend.status = 'warning';
        checks.backend.details = 'Could not determine backend';
    }

    // Check Proxy URL
    try {
        const proxy = PROXY_URL || 'http://localhost:8080';
        checks.proxy.status = 'ok';
        checks.proxy.details = proxy;
    } catch (e) {
        checks.proxy.status = 'warning';
        checks.proxy.details = 'Could not determine proxy URL';
    }

    return checks;
});

// ─────────────────────────────────────────────────────────────────────────────
// Credentials (Secrets)
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('get-credentials', async () => {
    // Get the server URL
    const serverUrl = await getServerUrlInternal();
    // Call Odoo API to get secret list (metadata only)
    try {
        const response = await fetch(`${serverUrl}:8069/api/secrets/list`, {
            headers: { 'Authorization': `Bearer ${await getOdooAuthToken()}` }
        });
        if (response.ok) {
            const data = await response.json();
            return { success: true, data };
        } else {
            return { success: false, error: 'Failed to fetch credentials' };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('get-credential-value', async (event, key) => {
    const serverUrl = await getServerUrlInternal();
    try {
        const response = await fetch(`${serverUrl}:8069/api/secrets/${key}`, {
            headers: { 'Authorization': `Bearer ${await getOdooAuthToken()}` }
        });
        if (response.ok) {
            const data = await response.json();
            return { success: true, value: data.value };
        } else {
            return { success: false, error: 'Failed to fetch credential' };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('rotate-credential', async (event, key, newValue) => {
    const serverUrl = await getServerUrlInternal();
    try {
        const response = await fetch(`${serverUrl}:8069/api/secrets/${key}/rotate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${await getOdooAuthToken()}`
            },
            body: JSON.stringify({ value: newValue })
        });
        if (response.ok) {
            return { success: true };
        } else {
            const error = await response.json();
            return { success: false, error: error.error };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Modular Installation
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('install-modules', async (event, modules) => {
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'install-modules.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: 'install-modules.sh not found' };
    }

    const moduleList = modules.join(',');
    const cmd = `bash ${scriptPath} --force --auto --modules=${moduleList}`;

    return new Promise((resolve) => {
        const proc = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
            env: { ...process.env, VIRTUAL_ENV: VENV_DIR }
        });

        let output = '';
        proc.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stdout', data: text });
        });

        proc.stderr.on('data', (data) => {
            const text = data.toString();
            output += text;
            mainWindow?.webContents.send('install-output', { type: 'stderr', data: text });
        });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true, output });
            } else {
                resolve({ success: false, error: output || `Process exited with code ${code}` });
            }
        });
    });
});

// Helper to get Odoo auth token (simplified; in production use proper OAuth)
async function getOdooAuthToken() {
    // In a real implementation, this would use OAuth or stored session
    // For now, we use the admin password from .env
    const envContent = fs.readFileSync(ENV_FILE, 'utf8');
    const match = envContent.match(/^ODOO_ADMIN_PASSWORD='([^']+)'/m);
    const password = match ? match[1] : 'admin';
    // Simulate a simple token (just for development)
    return Buffer.from(`admin:${password}`).toString('base64');
}

// Helper to get internal server URL
async function getServerUrlInternal() {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        if (fs.existsSync(configPath)) {
            const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            if (config.proxyUrl) {
                return config.proxyUrl;
            }
        }
    } catch (error) {
        logError(`Error reading config: ${error.message}`);
    }
    return 'http://localhost';
}

// ─────────────────────────────────────────────────────────────────────────────
// Emergency Access Management
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('list-emergency-users', async () => {
    try {
        const result = await execCommand(
            `docker compose exec -T postgres psql -U odoo -d odoo -t -c "SELECT login, valid_until, last_used FROM nettrades_emergency_users ORDER BY created_at DESC;"`
        );
        return { success: true, data: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('revoke-emergency-user', async (event, login) => {
    try {
        await execCommand(
            `docker compose exec -T postgres psql -U odoo -d odoo -c "DELETE FROM nettrades_emergency_users WHERE login='${login}';"`
        );
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

registerSafe('create-emergency-user', async (event, duration) => {
    const password = generateSafePassword();
    const validUntil = new Date(Date.now() + (duration || 4) * 3600000)
        .toISOString()
        .replace('T', ' ')
        .slice(0, 19);

    try {
        await execCommand(
            `docker compose exec -T postgres psql -U odoo -d odoo -c "
                INSERT INTO nettrades_emergency_users (login, password_hash, valid_until)
                VALUES ('emergency', crypt('${password}', gen_salt('bf')), '${validUntil}')
                ON CONFLICT (login) DO UPDATE SET
                    password_hash = crypt('${password}', gen_salt('bf')),
                    valid_until = '${validUntil}';
            "`
        );
        return { success: true, password, validUntil };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Window Controls
// ─────────────────────────────────────────────────────────────────────────────

registerSafe('minimize-window', () => {
    if (mainWindow) mainWindow.minimize();
});

registerSafe('maximize-window', () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) {
            mainWindow.unmaximize();
        } else {
            mainWindow.maximize();
        }
    }
});

registerSafe('close-window', () => {
    if (mainWindow) mainWindow.close();
});

// =============================================================================
// WINDOW CONTROLS — must use ipcMain.on because preload uses ipcRenderer.send
// =============================================================================

ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) mainWindow.unmaximize();
        else mainWindow.maximize();
    }
});

ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
});

registerSafe('show-window', () => {
    if (mainWindow) mainWindow.show();
    return { success: true };
});

// =============================================================================
// PLATFORM GPUs (fixed 2026-10-30 to use httpWithRetry)
// =============================================================================
// Combines:
//   - Local GPUs (V100) via nvidia-smi / sysfs
//   - Spoke GPUs from Odoo `gpu.node.gpus` JSON, one entry per registered node
//
// The Odoo query now goes through httpWithRetry() so a 429 from the proxy
// does not blank the GPUs tab.
// =============================================================================

function _readEnvFile() {
    try {
        if (!fs.existsSync(ENV_FILE)) return {};
        const content = fs.readFileSync(ENV_FILE, 'utf8');
        const out = {};
        for (const line of content.split('\n')) {
            const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
            if (!m) continue;
            let v = m[2].trim();
            if ((v.startsWith('"') && v.endsWith('"')) ||
                (v.startsWith("'") && v.endsWith("'"))) {
                v = v.slice(1, -1);
            }
            out[m[1]] = v;
        }
        return out;
    } catch {
        return {};
    }
}

registerSafe('get-platform-gpus', async () => {
    const result = { local: [], spokes: [], errors: [] };

    // ---- Local GPUs (V100 / host) ----
    try {
        const hardware = await (async () => {
            return detectGPUs();
        })();
        result.local = (hardware || []).map((g, i) => {
            const memMatch = String(g.memory || '').match(/(\d+)/);
            return {
                index: i,
                vendor: g.vendor || 'nvidia',
                model: g.name || 'Unknown',
                memory_mb: memMatch ? parseInt(memMatch[1]) : 0,
                compute_capability: g.computeCapability || null,
            };
        });
    } catch (e) {
        result.errors.push(`Local GPU detection: ${e.message}`);
    }

    // ---- Spoke GPUs (from Odoo) ----
    try {
        const env = _readEnvFile();
        const proxyUrl = 'http://localhost:8090';
        const proxyKey = env.PROXY_API_KEY || env.ODOO_API_KEY || '';
        const odooDb = env.ODOO_DB || 'odoo';
        const odooUser = parseInt(env.ODOO_USER || '2');
        const odooPass = env.ODOO_ADMIN_PASSWORD || 'admin';

        const payload = {
            jsonrpc: '2.0', method: 'call', id: 1,
            params: {
                service: 'object', method: 'execute_kw',
                args: [
                    odooDb, odooUser, odooPass,
                    'gpu.node', 'search_read',
                    [[['state', '=', 'active']]],
                    {
                        fields: [
                            'id', 'hostname', 'endpoint', 'wireguard_ip',
                            'gpus', 'compute_profile',
                            'inference_capability', 'status',
                            'gpu_utilisation_pct', 'last_seen',
                        ]
                    },
                ],
            },
        };

        const resp = await httpWithRetry(`${proxyUrl}/jsonrpc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': proxyKey },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            result.errors.push(`Odoo GPU query: HTTP ${resp.status}`);
        } else {
            const body = await resp.json();
            if (body.error) {
                result.errors.push(`Odoo GPU query: ${JSON.stringify(body.error).slice(0, 200)}`);
            } else {
                for (const node of body.result || []) {
                    let gpus = node.gpus || [];
                    if (typeof gpus === 'string') {
                        try { gpus = JSON.parse(gpus); } catch { gpus = []; }
                    }
                    let profile = node.compute_profile || {};
                    if (typeof profile === 'string') {
                        try { profile = JSON.parse(profile); } catch { profile = {}; }
                    }
                    result.spokes.push({
                        node_id: node.id,
                        hostname: node.hostname || `node-${node.id}`,
                        endpoint: node.endpoint || '',
                        ip: node.wireguard_ip || '',
                        status: node.status || 'unknown',
                        inference_capability: node.inference_capability || 'rpc_worker',
                        gpu_utilisation_pct: node.gpu_utilisation_pct || 0,
                        last_seen: node.last_seen,
                        model_cached: !!profile.model_cached,
                        ram_gb: profile.ram_gb || 0,
                        cpu_model: profile.cpu_model || '',
                        cpu_cores: profile.cpu_cores || 0,
                        rpc_backends: profile.rpc_backends || [],
                        gpus: gpus.map((g, i) => ({
                            index: g.index ?? i,
                            vendor: g.vendor || 'unknown',
                            model: g.model || 'Unknown',
                            memory_mb: g.memory_mb || 0,
                            rpc_port: g.rpc_port || (50052 + i),
                            gfx_target: g.gfx_target || null,
                            hsa_override: g.hsa_override_gfx_version || null,
                            compute_capability: g.compute_capability || null,
                        })),
                    });
                }
            }
        }
    } catch (e) {
        result.errors.push(`Spoke GPU query: ${e.message}`);
    }

    return { success: true, data: result };
});

// =============================================================================
// CHAT INVOCATION (NEW 2026-10-22)
// =============================================================================
// Real POST to LangGraph /invoke. Replaces the mock proxyCreateJob /
// proxyGetJob for chat purposes. Preserves the thread_id across messages so
// the supervisor's session affinity works (RPC cluster stays pinned across
// turns, which is what makes Claim 2 a distributed session rather than one
// isolated request).
//
// Returns:
//   { success: true, data: {...}, status: 200, thread_id, active_track }
//   { success: false, status: 503, retryAfter: 30, error: "..." }   (ClusterRecovering)
//   { success: false, status: 401, error: "Invalid API key" }
//   { success: false, status: 500, error: "..." }
// =============================================================================

registerSafe('chat-invoke', async (_evt, opts) => {
    const { messages, threadId, modelOverride } = opts || {};
    if (!Array.isArray(messages) || messages.length === 0) {
        return { success: false, status: 400, error: 'messages is required' };
    }

    const env = _readEnvFile();
    const langgraphUrl = (loadHubConfig().langgraph_url || 'http://localhost:8000')
        .replace(/\/+$/, '');
    const apiKey = env.LANGGRAPH_API_KEY || '';

    const tid = threadId || crypto.randomUUID();

    // The supervisor expects state in `input`. It reads state["messages"]
    // to extract the last user message. It also reads state["thread_id"]
    // which /invoke sets from config.configurable.thread_id.
    const payload = {
        input: {
            messages: messages.map(m => ({ role: m.role, content: m.content })),
        },
        config: {
            configurable: { thread_id: tid },
        },
    };
    if (modelOverride) {
        payload.input.model_override = modelOverride;
    }

    try {
        const resp = await fetch(`${langgraphUrl}/invoke`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': apiKey,
            },
            body: JSON.stringify(payload),
        });

        // 503 = ClusterRecovering — the supervisor raised it because the
        // pinned RPC cluster is unreachable and no fallback is permitted.
        // Return Retry-After so the UI can show a countdown.
        if (resp.status === 503) {
            let detail = 'The inference cluster is recovering. Please retry.';
            try {
                const body = await resp.json();
                if (body.detail) detail = body.detail;
            } catch {}
            const retryAfter = parseInt(resp.headers.get('Retry-After') || '30', 10);
            return {
                success: false,
                status: 503,
                retryAfter,
                thread_id: tid,
                error: detail,
            };
        }

        if (!resp.ok) {
            let detail = `HTTP ${resp.status}`;
            try {
                const body = await resp.json();
                if (body.detail) detail = body.detail;
                else if (body.error) detail = body.error;
            } catch {
                try { detail = (await resp.text()).slice(0, 300); } catch {}
            }
            return { success: false, status: resp.status, error: detail, thread_id: tid };
        }

        const data = await resp.json();

        // Extract the response text and the routing decision.
        // LangGraph returns: { intent, messages, analysis, inference_track, ... }
        const reply = data.analysis || '(empty response)';
        const activeTrack = data.inference_track || null;

        return {
            success: true,
            status: 200,
            data,
            reply,
            thread_id: tid,
            intent: data.intent || null,
            active_track: activeTrack,
            route_source: data.route_source || null,
        };
    } catch (e) {
        // Network error — LangGraph container down or network blocked.
        return {
            success: false,
            status: 0,
            error: `Cannot reach LangGraph at ${langgraphUrl}: ${e.message}`,
            thread_id: tid,
        };
    }
});

// =============================================================================
// MODEL UPLOAD (NEW 2026-10-22)
// =============================================================================
// Opens a native file dialog, then copies the selected file into MODELS_DIR.
// Supports .gguf (llama.cpp), .safetensors (HF single file), and directories
// containing config.json (HF model). For directories, the user must select
// any file inside and we copy the whole directory.
// =============================================================================

registerSafe('upload-model', async () => {
    if (!mainWindow) {
        return { success: false, error: 'No main window' };
    }

    const result = await dialog.showOpenDialog(mainWindow, {
        title: 'Select a model file or a HuggingFace model directory',
        properties: ['openFile', 'openDirectory'],
        filters: [
            { name: 'GGUF / Safetensors', extensions: ['gguf', 'safetensors', 'bin'] },
            { name: 'HuggingFace config', extensions: ['json'] },
            { name: 'All files', extensions: ['*'] },
        ],
    });

    if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
        return { success: false, canceled: true };
    }

    const srcPath = result.filePaths[0];
    const stat = fs.statSync(srcPath);
    let destPath;

    try {
        if (!fs.existsSync(MODELS_DIR)) {
            fs.mkdirSync(MODELS_DIR, { recursive: true });
        }

        if (stat.isDirectory()) {
            // HuggingFace model directory — copy the whole directory.
            const dirname = path.basename(srcPath);
            destPath = path.join(MODELS_DIR, dirname);
            if (fs.existsSync(destPath)) {
                return {
                    success: false,
                    error: `A model named "${dirname}" already exists in ${MODELS_DIR}. Delete it first.`,
                };
            }
            // Recursive copy
            fs.cpSync(srcPath, destPath, { recursive: true });
        } else {
            // Single file — copy it in.
            const basename = path.basename(srcPath);
            destPath = path.join(MODELS_DIR, basename);
            fs.copyFileSync(srcPath, destPath);
        }

        logSuccess(`Model uploaded: ${srcPath} → ${destPath}`);
        return { success: true, path: destPath, src: srcPath };
    } catch (e) {
        logError(`Model upload failed: ${e.message}`);
        return { success: false, error: e.message };
    }
});

// =============================================================================
// WSL HELPERS (NEW 2026-10-22)
// =============================================================================
// The Launcher's Dashboard shows a WSL status banner on Windows. These
// handlers detect WSL2, its Ubuntu distro, and offer install buttons.
// On Linux (the V100 demo host) they return "not applicable" without error.
// =============================================================================

registerSafe('check-wsl', async () => {
    if (process.platform !== 'win32') return true; // N/A on Linux/macOS
    try {
        await execPromise('wsl --status');
        return true;
    } catch {
        return false;
    }
});

registerSafe('check-wsl-distro', async () => {
    if (process.platform !== 'win32') return true;
    try {
        const { stdout } = await execPromise('wsl --list --quiet');
        return /ubuntu/i.test(stdout);
    } catch {
        return false;
    }
});

registerSafe('install-wsl', async () => {
    if (process.platform !== 'win32') {
        return { success: false, error: 'Not on Windows' };
    }
    // Elevate: prompt for admin and run wsl --install
    return new Promise((resolve) => {
        const cmd = 'powershell -NoProfile -Command "Start-Process wsl -ArgumentList \'--install --no-distribution\' -Verb RunAs -Wait"';
        exec(cmd, (error, _stdout, stderr) => {
            if (error) resolve({ success: false, error: stderr || error.message });
            else resolve({ success: true, message: 'WSL2 installation started. Restart may be required.' });
        });
    });
});

registerSafe('install-ubuntu', async () => {
    if (process.platform !== 'win32') {
        return { success: false, error: 'Not on Windows' };
    }
    return new Promise((resolve) => {
        const cmd = 'powershell -NoProfile -Command "Start-Process wsl -ArgumentList \'--install -d Ubuntu-24.04\' -Verb RunAs -Wait"';
        exec(cmd, (error, _stdout, stderr) => {
            if (error) resolve({ success: false, error: stderr || error.message });
            else resolve({ success: true, message: 'Ubuntu 24.04 install started.' });
        });
    });
});

registerSafe('open-wsl-terminal', async () => {
    if (process.platform !== 'win32') {
        // On Linux just open the user's default terminal in the project root
        shell.openPath(PROJECT_ROOT);
        return { success: true };
    }
    return new Promise((resolve) => {
        exec('cmd.exe /c start wsl.exe', (error) => {
            if (error) resolve({ success: false, error: error.message });
            else resolve({ success: true });
        });
    });
});

// =============================================================================
// End of main.js
// =============================================================================
