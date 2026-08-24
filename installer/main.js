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
//
// USAGE:
//   npm start
// =============================================================================

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn, exec, execSync } = require('child_process'); // FIXED: added execSync
const fs = require('fs');
const os = require('os');
const https = require('https');
const crypto = require('crypto');

// -----------------------------------------------------------------------------
// Disable GPU acceleration to avoid rendering errors on WSL
// -----------------------------------------------------------------------------
app.disableHardwareAcceleration(); // FIXED: prevents SharedImage errors on WSL

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

// Models directory (where llama.cpp and Dynamo look for models)
const MODELS_DIR = path.join(PROJECT_ROOT, 'deploy', 'docker', 'dynamo-data', 'models');

// Docker Compose file path
const COMPOSE_FILE = path.join(PROJECT_ROOT, 'deploy', 'docker', 'docker-compose.yaml');

// Virtual environment directory
const VENV_DIR = path.join(PROJECT_ROOT, '.venv');

// .env file path
const ENV_FILE = path.join(PROJECT_ROOT, 'deploy', 'docker', '.env');

// Phase marker directory
const PHASE_MARKER_DIR = PROJECT_ROOT;


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

    // Check for virtual environment
    checkVirtualEnvironment();

    // Start auto-updater
    setupAutoUpdater();

    // Start node discovery
    startNodeDiscovery();

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
                gpus: '0',
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
// IPC Handlers
// -----------------------------------------------------------------------------

// ─────────────────────────────────────────────────────────────────────────────
// Platform & System
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-platform', () => {
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
    };
});

ipcMain.handle('get-project-root', () => PROJECT_ROOT);
ipcMain.handle('get-models-dir', () => MODELS_DIR);

ipcMain.handle('is-platform-setup', () => {
    return isPlatformSetup();
});

// ─────────────────────────────────────────────────────────────────────────────
// QUICK SETUP – One-click development environment setup
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('run-quick-setup', async (event) => {
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


// ─────────────────────────────────────────────────────────────────────────────
// List Emergency Audit
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('list-emergency-audit', async () => {
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

ipcMain.handle('run-install', async (event, options) => {
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
    } = options || {};

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
    const tenantResult = await ipcMain.handle('set-tenant-config', null, { tenantType, tenantName });
    if (!tenantResult.success) {
        return { success: false, error: `Failed to set tenant config: ${tenantResult.error}` };
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

        // Set environment variables for tenant type
        const env = { ...process.env, VIRTUAL_ENV: VENV_DIR, TENANT_TYPE: tenantType };

        logInfo(`Starting deployment: ${cmd}`);
        logInfo(`Tenant type: ${tenantType}`);

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

ipcMain.handle('cancel-install', () => {
    if (installProcess) {
        installProcess.kill('SIGTERM');
        installProcess = null;
        isDeploying = false;
        logInfo('Deployment cancelled');
        return { success: true };
    }
    return { success: false, error: 'No installation in progress' };
});

ipcMain.handle('get-install-status', () => {
    return {
        isRunning: !!installProcess,
        progress: deploymentProgress,
    };
});

// ─────────────────────────────────────────────────────────────────────────────
// Tenant Configuration
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-tenant-config', () => {
    try {
        if (fs.existsSync(ENV_FILE)) {
            const content = fs.readFileSync(ENV_FILE, 'utf8');
            const tenantType = content.match(/^TENANT_TYPE=(\w+)/m)?.[1] || 'enterprise';
            const tenantName = content.match(/^TENANT_NAME=(.+)/m)?.[1] || 'default';
            return {
                tenantType,
                tenantName,
                runtimeConfig: RUNTIME_CONFIG[tenantType] || RUNTIME_CONFIG[TENANT_TYPES.ENTERPRISE]
            };
        }
    } catch (error) {
        logError(`Error reading tenant config: ${error.message}`);
    }
    return {
        tenantType: 'enterprise',
        tenantName: 'default',
        runtimeConfig: RUNTIME_CONFIG[TENANT_TYPES.ENTERPRISE]
    };
});

ipcMain.handle('set-tenant-config', async (event, config) => {
    const { tenantType, tenantName } = config;

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

        return { success: true };
    } catch (error) {
        logError(`Error setting tenant config: ${error.message}`);
        return { success: false, error: error.message };
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Grove & KAI Scheduler Management
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-grove-status', async () => {
    try {
        const result = await getDockerServiceStatus('grove');
        return { running: result.running, error: result.error };
    } catch (error) {
        return { running: false, error: error.message };
    }
});

ipcMain.handle('get-kai-status', async () => {
    try {
        const result = await getDockerServiceStatus('kai-scheduler');
        return { running: result.running, error: result.error };
    } catch (error) {
        return { running: false, error: error.message };
    }
});

ipcMain.handle('start-grove', async () => {
    return runDockerComposeWithFile('docker-compose.grove.yaml', 'up -d grove loki tempo');
});

ipcMain.handle('stop-grove', async () => {
    return runDockerComposeWithFile('docker-compose.grove.yaml', 'down');
});

ipcMain.handle('start-kai', async () => {
    return runDockerComposeWithFile('docker-compose.kai.yaml', 'up -d kai-scheduler');
});

ipcMain.handle('stop-kai', async () => {
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

ipcMain.handle('get-feature-flags', () => {
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

ipcMain.handle('start-platform', () => {
    return runDockerCompose('up -d');
});

ipcMain.handle('stop-platform', () => {
    return runDockerCompose('down');
});

ipcMain.handle('restart-platform', () => {
    return runDockerCompose('restart');
});

ipcMain.handle('platform-status', () => {
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

ipcMain.handle('list-models', () => {
    return listModels();
});

ipcMain.handle('download-model', async (event, options) => {
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

ipcMain.handle('import-model', async (event, modelPath) => {
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

ipcMain.handle('delete-model', async (event, modelPath) => {
    try {
        fs.rmSync(modelPath, { recursive: true, force: true });
        logSuccess(`Model deleted: ${modelPath}`);
        return { success: true };
    } catch (error) {
        logError(`Model deletion failed: ${error.message}`);
        return { success: false, error: error.message };
    }
});

ipcMain.handle('load-model', async (event, modelPath) => {
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

ipcMain.handle('detect-gpu', () => {
    return detectGPUs();
});

ipcMain.handle('detect-hardware', () => {
    const gpus = detectGPUs();
    const totalMemory = os.totalmem();
    const cpus = os.cpus();

    // Check for Kubernetes
    let k8sDetected = false;
    try {
        exec('kubectl cluster-info 2>/dev/null', (error, stdout) => {
            k8sDetected = !error && stdout.length > 0;
        });
    } catch (e) {
        k8sDetected = false;
    }

    // Check for Docker
    let dockerInstalled = false;
    try {
        exec('docker --version 2>/dev/null', (error, stdout) => {
            dockerInstalled = !error && stdout.length > 0;
        });
    } catch (e) {
        dockerInstalled = false;
    }

    const result = {
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

    return result;
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
            } catch (e) {
                // rocminfo not available – skip AMD detection
            }
        }

        // Intel GPU detection
        if (platform === 'linux') {
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
            } catch (e) {
                // clinfo not available – skip Intel detection
            }
        }
    } catch (error) {
        logError(`GPU detection error: ${error.message}`);
    }

    return gpus;
}

// ─────────────────────────────────────────────────────────────────────────────
// Backup & Restore
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('create-backup', async (event, options) => {
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

ipcMain.handle('list-backups', () => {
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

ipcMain.handle('restore-backup', async (event, backupPath) => {
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
// VPN Management (WireGuard)
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('vpn-add-peer', async (event, username) => {
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'add-wireguard-user.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `WireGuard script not found: ${scriptPath}` };
    }

    return new Promise((resolve) => {
        const cmd = `bash ${scriptPath} ${username}`;
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

ipcMain.handle('vpn-list-peers', () => {
    return new Promise((resolve) => {
        exec('wg show', { cwd: PROJECT_ROOT }, (error, stdout) => {
            if (error) {
                resolve({ success: false, error: error.message });
            } else {
                resolve({ success: true, output: stdout });
            }
        });
    });
});

ipcMain.handle('vpn-status', () => {
    return new Promise((resolve) => {
        exec('wg show', { cwd: PROJECT_ROOT }, (error, stdout) => {
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

ipcMain.handle('ask-someone', async (event, data) => {
    const { question, category, urgency, expertId } = data || {};
    const serverUrl = await ipcMain.handle('get-server-url');

    // Call the LangGraph Ask Someone agent
    try {
        const response = await fetch(`${serverUrl}:8000/runs/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                input: {
                    question,
                    category,
                    urgency,
                    expert_id: expertId,
                    action: 'ask_someone',
                },
                config: {
                    configurable: {
                        thread_id: crypto.randomUUID(),
                    },
                },
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

ipcMain.handle('good-answer', async (event, data) => {
    const { question, answer, rating, userId } = data || {};
    const serverUrl = await ipcMain.handle('get-server-url');

    // Call the LangGraph Good Answer agent
    try {
        const response = await fetch(`${serverUrl}:8000/runs/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                input: {
                    question,
                    answer,
                    rating,
                    user_id: userId,
                    action: 'good_answer',
                },
                config: {
                    configurable: {
                        thread_id: crypto.randomUUID(),
                    },
                },
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

ipcMain.handle('start-training', async (event, data) => {
    const { dataset, model, method, params } = data || {};
    const serverUrl = await ipcMain.handle('get-server-url');

    try {
        const response = await fetch(`${serverUrl}:8000/runs/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                input: {
                    dataset,
                    model,
                    method: method || 'unsloth',
                    params: params || {},
                    action: 'start_training',
                },
                config: {
                    configurable: {
                        thread_id: crypto.randomUUID(),
                    },
                },
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

ipcMain.handle('training-status', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('list-agents', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('agent-status', async (event, agentId) => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('list-queue', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('cancel-task', async (event, taskId) => {
    const serverUrl = await ipcMain.handle('get-server-url');

    try {
        const response = await fetch(`${serverUrl}:8000/queue/${taskId}/cancel`, {
            method: 'POST',
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

ipcMain.handle('retry-task', async (event, taskId) => {
    const serverUrl = await ipcMain.handle('get-server-url');

    try {
        const response = await fetch(`${serverUrl}:8000/queue/${taskId}/retry`, {
            method: 'POST',
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
// GPU Marketplace
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('marketplace-listings', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('marketplace-list-gpu', async (event, data) => {
    const serverUrl = await ipcMain.handle('get-server-url');

    try {
        const response = await fetch(`${serverUrl}:8090/api/v1/gpu/list`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
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

ipcMain.handle('marketplace-book-gpu', async (event, data) => {
    const serverUrl = await ipcMain.handle('get-server-url');

    try {
        const response = await fetch(`${serverUrl}:8090/api/v1/gpu/book`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
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

ipcMain.handle('get-discovered-nodes', () => {
    return Array.from(discoveredNodes.values());
});

// ─────────────────────────────────────────────────────────────────────────────
// System Health & Monitoring
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('system-health', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');
    const health = {
        services: {},
        gpus: [],
        models: [],
        uptime: process.uptime(),
    };

    // Check Odoo
    try {
        const response = await fetch(`${serverUrl}:8069/web/health`);
        health.services.odoo = response.ok ? 'healthy' : 'unhealthy';
    } catch {
        health.services.odoo = 'unhealthy';
    }

    // Check LangGraph
    try {
        const response = await fetch(`${serverUrl}:8000/health`);
        health.services.langgraph = response.ok ? 'healthy' : 'unhealthy';
    } catch {
        health.services.langgraph = 'unhealthy';
    }

    // Check Dynamo
    try {
        const response = await fetch(`${serverUrl}:8001/v1/models`);
        health.services.dynamo = response.ok ? 'healthy' : 'unhealthy';
    } catch {
        health.services.dynamo = 'unhealthy';
    }

    // Get GPU info
    health.gpus = detectGPUs();

    // Get models
    health.models = listModels();

    return health;
});

// ─────────────────────────────────────────────────────────────────────────────
// Logs
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-logs', async (event, options) => {
    const { service, lines = 100 } = options || {};
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('get-alerts', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('get-notifications', async () => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('mark-notification-read', async (event, notificationId) => {
    const serverUrl = await ipcMain.handle('get-server-url');

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

ipcMain.handle('install-wine', async (event) => {
    // Check if wine is already installed
    try {
        execSync('wine --version', { stdio: 'ignore' });
        return { success: true, alreadyInstalled: true, message: 'Wine is already installed.' };
    } catch (e) {
        // Not installed, proceed
    }

    return new Promise((resolve) => {
        const commands = [
            'sudo dpkg --add-architecture i386',
            'sudo apt update',
            `sudo apt install -y wine wine64 wine32 libasound2t64 libasound2t64:i386 libnspr4 libnss3 libxss1 libatk-bridge2.0-0t64 libgtk-3-0t64 libgbm1 libnspr4:i386 libnss3:i386 libgtk-3-0t64:i386`
        ];

        const fullCmd = commands.join(' && ');
        logInfo(`Installing Wine with: ${fullCmd}`);

        const proc = spawn('bash', ['-c', fullCmd], {
            stdio: 'pipe',
            shell: true,
        });

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

ipcMain.handle('open-external', (event, url) => {
    shell.openExternal(url);
});

ipcMain.handle('show-dialog', async (event, options) => {
    return dialog.showMessageBox(options);
});

ipcMain.handle('get-server-url', () => {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        if (fs.existsSync(configPath)) {
            const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            if (config.serverUrl) {
                return config.serverUrl;
            }
        }
    } catch (error) {
        logError(`Error reading config: ${error.message}`);
    }
    return 'http://localhost';
});

ipcMain.handle('save-server-url', (event, url) => {
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        const config = { serverUrl: url };
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
        logInfo(`Server URL saved: ${url}`);
        return { success: true };
    } catch (error) {
        logError(`Error saving config: ${error.message}`);
        return { success: false, error: error.message };
    }
});


// ─────────────────────────────────────────────────────────────────────────────
// System Check
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('system-check', async () => {
    const checks = {
        wsl: { name: 'WSL2', status: 'unknown', details: '' },
        docker: { name: 'Docker', status: 'unknown', details: '' },
        gpu: { name: 'GPU Drivers', status: 'unknown', details: '' },
        python: { name: 'Python 3.10+', status: 'unknown', details: '' },
        node: { name: 'Node.js 20+', status: 'unknown', details: '' },
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

    return checks;
});

// ─────────────────────────────────────────────────────────────────────────────
// Credentials (Secrets)
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-credentials', async () => {
    // Get the server URL
    const serverUrl = await ipcMain.handle('get-server-url');
    // Call Odoo API to get secret list (metadata only)
    try {
        const response = await fetch(`${serverUrl}:8069/api/secrets/list`, {
            headers: {
                'Authorization': `Bearer ${await getOdooAuthToken()}`
            }
        });
        if (response.ok) {
            const data = await response.json();
            return data;
        } else {
            return { success: false, error: 'Failed to fetch credentials' };
        }
    } catch (error) {
        return { success: false, error: error.message };
    }
});

ipcMain.handle('get-credential-value', async (event, key) => {
    const serverUrl = await ipcMain.handle('get-server-url');
    try {
        const response = await fetch(`${serverUrl}:8069/api/secrets/${key}`, {
            headers: {
                'Authorization': `Bearer ${await getOdooAuthToken()}`
            }
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

ipcMain.handle('rotate-credential', async (event, key, newValue) => {
    const serverUrl = await ipcMain.handle('get-server-url');
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

ipcMain.handle('install-modules', async (event, modules) => {
    // Build the command to install only selected modules
    const scriptPath = path.join(PROJECT_ROOT, 'scripts', 'install-modules.sh');
    if (!fs.existsSync(scriptPath)) {
        return { success: false, error: 'install-modules.sh not found' };
    }

    // Prepare module list as comma-separated
    const moduleList = modules.join(',');
    const cmd = `bash ${scriptPath} --force --auto --modules ${moduleList}`;

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
    const match = envContent.match(/^ADMIN_PASSWORD='([^']+)'/m);
    const password = match ? match[1] : 'admin';
    // Simulate a simple token (just for development)
    return Buffer.from(`admin:${password}`).toString('base64');
}


// ─────────────────────────────────────────────────────────────────────────────
// Emergency Access Management (Hub-and-Spoke Security)
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('list-emergency-users', async () => {
    try {
        const result = await execCommand(
            `docker compose exec -T postgres psql -U odoo -d odoo -t -c "SELECT login, valid_until, last_used FROM nettrades_emergency_users ORDER BY created_at DESC;"`
        );
        return { success: true, data: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

ipcMain.handle('revoke-emergency-user', async (event, login) => {
    try {
        await execCommand(
            `docker compose exec -T postgres psql -U odoo -d odoo -c "DELETE FROM nettrades_emergency_users WHERE login='${login}';"`
        );
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

ipcMain.handle('create-emergency-user', async (event, duration) => {
    const password = generate_safe_password();
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

ipcMain.handle('minimize-window', () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.handle('maximize-window', () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) {
            mainWindow.unmaximize();
        } else {
            mainWindow.maximize();
        }
    }
});

ipcMain.handle('close-window', () => {
    if (mainWindow) mainWindow.close();
});

// ─────────────────────────────────────────────────────────────────────────────
// Export
// ─────────────────────────────────────────────────────────────────────────────

module.exports = { app };