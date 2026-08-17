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
//
// USAGE:
//   npm start
// =============================================================================

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const os = require('os');
const https = require('https');
const crypto = require('crypto');

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
        isPackaged: isPackaged,
    };
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

// Helper function to check if a Docker service is running
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

// Helper function to run docker compose with an additional file
// UPDATED: Added file existence check before running
function runDockerComposeWithFile(composeFile, command) {
    return new Promise((resolve) => {
        const composePath = path.join(path.dirname(COMPOSE_FILE), composeFile);
        
        // Check if the compose file exists before running
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

ipcMain.handle('get-project-root', () => PROJECT_ROOT);
ipcMain.handle('get-models-dir', () => MODELS_DIR);

let serverUrl = 'http://localhost';

ipcMain.handle('get-server-url', () => {
    // Try to read from a config file
    try {
        const configPath = path.join(app.getPath('userData'), 'config.json');
        if (fs.existsSync(configPath)) {
            const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            if (config.serverUrl) {
                serverUrl = config.serverUrl;
            }
        }
    } catch (error) {
        logError(`Error reading config: ${error.message}`);
    }
    return serverUrl;
});

ipcMain.handle('save-server-url', (event, url) => {
    serverUrl = url;
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
// Feature Flags
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-feature-flags', () => {
    // Read from .env file if available
    const envPath = path.join(PROJECT_ROOT, 'deploy', 'docker', '.env');
    const flags = {
        gpuMarketplace: true,
        askSomeone: true,
        goodAnswer: true,
        selfImproving: true,
        training: true,
        bridge: true,
        notifications: true,
        fairness: false,      // Coming soon
        jobMatching: false,   // Coming soon
        research: false,      // Coming soon
        triggers: false,      // Coming soon
    };

    try {
        if (fs.existsSync(envPath)) {
            const envContent = fs.readFileSync(envPath, 'utf8');
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
        domain = '',
        phases = null,
        resetData = false
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
        if (domain) cmd += ` --domain=${domain}`;

        logInfo(`Starting deployment: ${cmd}`);

        installProcess = spawn('bash', ['-c', cmd], {
            cwd: PROJECT_ROOT,
            env: { ...process.env, VIRTUAL_ENV: VENV_DIR },
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
    const envPath = path.join(PROJECT_ROOT, 'deploy', 'docker', '.env');
    try {
        let envContent = fs.readFileSync(envPath, 'utf8');
        const modelName = path.basename(modelPath);
        envContent = envContent.replace(/^MODEL_NAME=.*$/m, `MODEL_NAME=${modelName}`);
        fs.writeFileSync(envPath, envContent);
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
            } catch {}
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
            } catch {}
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
// Alerts
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

// ─────────────────────────────────────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────────────────────────────────────

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
        const response = await fetch(`${serverUrl}:8000/notifications/${notificationId}/read`, {
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

// -----------------------------------------------------------------------------
// Export
// -----------------------------------------------------------------------------

module.exports = { app };