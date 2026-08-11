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
//
// USAGE:
//   npm start
// =============================================================================

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const os = require('os');
const https = require('https');

// -----------------------------------------------------------------------------
// Global variables
// -----------------------------------------------------------------------------
let mainWindow = null;
let installProcess = null;
let downloadProcess = null;
let logFile = null;

// Determine project root – CRITICAL FIX for packaged app and development
// When running from source (npm start), __dirname is /path/to/repo/installer
// So PROJECT_ROOT should be one level up: /path/to/repo
// When packaged, resources are in process.resourcesPath
const isPackaged = app.isPackaged;
const PROJECT_ROOT = isPackaged
    ? process.resourcesPath
    : path.join(__dirname, '..');   // FIXED: was '../..' which pointed to wrong location

// Models directory (where llama.cpp and Dynamo look for models)
const MODELS_DIR = path.join(PROJECT_ROOT, 'deploy', 'docker', 'dynamo-data', 'models');

// Docker Compose file path
const COMPOSE_FILE = path.join(PROJECT_ROOT, 'deploy', 'docker', 'docker-compose.yaml');

// -----------------------------------------------------------------------------
// Create the main window
// -----------------------------------------------------------------------------
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 850,
        minWidth: 900,
        minHeight: 700,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        },
        icon: path.join(__dirname, 'icon.png'),
        title: 'NetTrades Launcher',
        backgroundColor: '#0f172a',
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
    logInfo('NetTrades Launcher started');
    logInfo(`Project root: ${PROJECT_ROOT}`);
    logInfo(`Models directory: ${MODELS_DIR}`);
    logInfo(`Platform: ${process.platform}`);
    logInfo(`Packaged: ${isPackaged}`);
    logInfo(`Compose file: ${COMPOSE_FILE}`);
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
// Logging helper (main process)
// -----------------------------------------------------------------------------
function logInfo(message) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [INFO] ${message}`);
}

function logError(message) {
    const timestamp = new Date().toISOString();
    console.error(`[${timestamp}] [ERROR] ${message}`);
}

// -----------------------------------------------------------------------------
// Utility: Ensure models directory exists
// -----------------------------------------------------------------------------
function ensureModelsDir() {
    if (!fs.existsSync(MODELS_DIR)) {
        fs.mkdirSync(MODELS_DIR, { recursive: true });
        logInfo(`Created models directory: ${MODELS_DIR}`);
    }
    return MODELS_DIR;
}

// -----------------------------------------------------------------------------
// Utility: Format file size
// -----------------------------------------------------------------------------
function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

// -----------------------------------------------------------------------------
// Utility: Get server URL from config or environment
// -----------------------------------------------------------------------------
function getServerUrl() {
    // Priority: 1. User setting, 2. .env file, 3. localhost
    const userConfigPath = path.join(os.homedir(), '.nettrades', 'config.json');
    try {
        if (fs.existsSync(userConfigPath)) {
            const config = JSON.parse(fs.readFileSync(userConfigPath, 'utf8'));
            if (config.serverUrl) {
                return config.serverUrl;
            }
        }
    } catch (e) {
        logError(`Failed to read user config: ${e.message}`);
    }

    // Try to read from .env
    const envPath = path.join(PROJECT_ROOT, 'deploy', 'docker', '.env');
    try {
        if (fs.existsSync(envPath)) {
            const content = fs.readFileSync(envPath, 'utf8');
            const match = content.match(/^DOMAIN=(.+)$/m);
            if (match) {
                const domain = match[1].trim();
                if (domain && domain !== 'changeit' && domain !== 'localhost') {
                    return `https://${domain}`;
                }
            }
        }
    } catch (e) {
        logError(`Failed to read .env: ${e.message}`);
    }

    return 'http://localhost';
}

// -----------------------------------------------------------------------------
// IPC Handlers
// -----------------------------------------------------------------------------

// ──────────────────────────────────────────────────────────────────────────────
// Platform & System Information
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-platform', () => {
    return {
        platform: process.platform,
        arch: process.arch,
        hostname: os.hostname(),
        cpus: os.cpus().length,
        totalMemory: os.totalmem(),
        freeMemory: os.freemem(),
        homeDir: os.homedir(),
        isPackaged: app.isPackaged,
        resourcesPath: process.resourcesPath,
    };
});

ipcMain.handle('get-project-root', () => {
    return PROJECT_ROOT;
});

ipcMain.handle('get-models-dir', () => {
    return ensureModelsDir();
});

ipcMain.handle('get-server-url', () => {
    return getServerUrl();
});

ipcMain.handle('save-server-url', async (event, url) => {
    const configDir = path.join(os.homedir(), '.nettrades');
    const configPath = path.join(configDir, 'config.json');
    try {
        if (!fs.existsSync(configDir)) {
            fs.mkdirSync(configDir, { recursive: true });
        }
        let config = {};
        if (fs.existsSync(configPath)) {
            config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        }
        config.serverUrl = url;
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
        return { success: true };
    } catch (e) {
        logError(`Failed to save server URL: ${e.message}`);
        return { success: false, error: e.message };
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Feature Flags
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-feature-flags', async () => {
    const envPath = path.join(PROJECT_ROOT, 'deploy', 'docker', '.env');
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
        logInfo('No .env file found, using default feature flags');
        return defaults;
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Installation
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('run-install', async (event, options) => {
    const { profile, environment, force, auto } = options;
    return new Promise((resolve, reject) => {
        const script = path.join(PROJECT_ROOT, 'scripts', 'nettrades-setup.sh');
        const args = [profile, '--environment', environment];
        if (force) args.push('--force');
        if (auto) args.push('--auto');

        logInfo(`Running installation: ${script} ${args.join(' ')}`);

        // Ensure script is executable
        try {
            fs.chmodSync(script, 0o755);
        } catch (e) {
            logError(`Failed to make script executable: ${e.message}`);
        }

        installProcess = spawn('bash', [script, ...args], {
            cwd: PROJECT_ROOT,
            env: { ...process.env, FORCE_COLOR: 'true' },
        });

        installProcess.stdout.on('data', (data) => {
            const output = data.toString();
            event.sender.send('install-output', output);
            logInfo(`[INSTALL] ${output.trim()}`);
        });

        installProcess.stderr.on('data', (data) => {
            const output = data.toString();
            event.sender.send('install-output', output);
            logInfo(`[INSTALL ERR] ${output.trim()}`);
        });

        installProcess.on('close', (code) => {
            installProcess = null;
            if (code === 0) {
                resolve({ success: true });
            } else {
                reject({ success: false, code });
            }
        });

        installProcess.on('error', (err) => {
            installProcess = null;
            reject({ success: false, error: err.message });
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

ipcMain.handle('get-install-status', () => {
    return {
        running: !!installProcess,
        pid: installProcess ? installProcess.pid : null,
    };
});

// ──────────────────────────────────────────────────────────────────────────────
// Platform Control (Start / Stop Docker Compose)
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('start-platform', async (event) => {
    return new Promise((resolve, reject) => {
        const command = `docker compose -f "${COMPOSE_FILE}" up -d`;

        logInfo(`Starting platform: ${command}`);

        const proc = spawn('bash', ['-c', command], {
            cwd: path.join(PROJECT_ROOT, 'deploy', 'docker'),
        });

        proc.stdout.on('data', (data) => {
            const output = data.toString();
            event.sender.send('platform-output', output);
            logInfo(`[START] ${output.trim()}`);
        });

        proc.stderr.on('data', (data) => {
            const output = data.toString();
            event.sender.send('platform-output', output);
            logInfo(`[START ERR] ${output.trim()}`);
        });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true });
            } else {
                reject({ success: false, code });
            }
        });

        proc.on('error', (err) => {
            reject({ success: false, error: err.message });
        });
    });
});

ipcMain.handle('stop-platform', async (event) => {
    return new Promise((resolve, reject) => {
        const command = `docker compose -f "${COMPOSE_FILE}" down`;

        logInfo(`Stopping platform: ${command}`);

        const proc = spawn('bash', ['-c', command], {
            cwd: path.join(PROJECT_ROOT, 'deploy', 'docker'),
        });

        proc.stdout.on('data', (data) => {
            const output = data.toString();
            event.sender.send('platform-output', output);
            logInfo(`[STOP] ${output.trim()}`);
        });

        proc.stderr.on('data', (data) => {
            const output = data.toString();
            event.sender.send('platform-output', output);
            logInfo(`[STOP ERR] ${output.trim()}`);
        });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true });
            } else {
                reject({ success: false, code });
            }
        });

        proc.on('error', (err) => {
            reject({ success: false, error: err.message });
        });
    });
});

ipcMain.handle('restart-platform', async (event) => {
    return new Promise((resolve, reject) => {
        const command = `docker compose -f "${COMPOSE_FILE}" restart`;

        logInfo(`Restarting platform: ${command}`);

        const proc = spawn('bash', ['-c', command], {
            cwd: path.join(PROJECT_ROOT, 'deploy', 'docker'),
        });

        proc.stdout.on('data', (data) => {
            const output = data.toString();
            event.sender.send('platform-output', output);
            logInfo(`[RESTART] ${output.trim()}`);
        });

        proc.stderr.on('data', (data) => {
            const output = data.toString();
            event.sender.send('platform-output', output);
            logInfo(`[RESTART ERR] ${output.trim()}`);
        });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true });
            } else {
                reject({ success: false, code });
            }
        });

        proc.on('error', (err) => {
            reject({ success: false, error: err.message });
        });
    });
});

ipcMain.handle('platform-status', async () => {
    return new Promise((resolve) => {
        const command = `docker compose -f "${COMPOSE_FILE}" ps --format json`;

        exec(command, { cwd: path.join(PROJECT_ROOT, 'deploy', 'docker') }, (error, stdout, stderr) => {
            if (error) {
                resolve({ running: false, error: error.message });
                return;
            }
            try {
                const containers = JSON.parse(stdout);
                const services = {};
                for (const c of containers) {
                    services[c.Service] = {
                        name: c.Name,
                        status: c.Status,
                        state: c.State,
                    };
                }
                resolve({ running: true, services });
            } catch (e) {
                resolve({ running: false, error: e.message });
            }
        });
    });
});

// ──────────────────────────────────────────────────────────────────────────────
// Model Management (LM Studio-style)
// ──────────────────────────────────────────────────────────────────────────────

// List models in the models directory
ipcMain.handle('list-models', async () => {
    try {
        const modelsDir = ensureModelsDir();
        const files = fs.readdirSync(modelsDir);
        const models = files
            .filter(f => f.endsWith('.gguf'))
            .map(f => {
                const filePath = path.join(modelsDir, f);
                const stats = fs.statSync(filePath);
                return {
                    name: f,
                    path: filePath,
                    size: stats.size,
                    sizeFormatted: formatSize(stats.size),
                    modified: stats.mtime,
                };
            });
        return models;
    } catch (e) {
        logError(`Failed to list models: ${e.message}`);
        return [];
    }
});

// Download a model from Hugging Face
ipcMain.handle('download-model', async (event, options) => {
    const { url, filename, onProgress } = options || {};
    return new Promise((resolve, reject) => {
        const modelsDir = ensureModelsDir();
        const filePath = path.join(modelsDir, filename || 'model.gguf');
        const tempPath = filePath + '.download';

        logInfo(`Downloading model from ${url} to ${filePath}`);

        const file = fs.createWriteStream(tempPath);
        let downloadedSize = 0;

        const request = https.get(url, (response) => {
            if (response.statusCode !== 200) {
                reject(new Error(`Download failed with status ${response.statusCode}`));
                return;
            }

            const totalSize = parseInt(response.headers['content-length'], 10);

            response.on('data', (chunk) => {
                downloadedSize += chunk.length;
                if (event && totalSize) {
                    const progress = (downloadedSize / totalSize) * 100;
                    event.sender.send('download-progress', {
                        filename,
                        progress: Math.round(progress),
                        downloaded: downloadedSize,
                        total: totalSize,
                    });
                }
            });

            response.pipe(file);

            file.on('finish', () => {
                file.close();
                fs.renameSync(tempPath, filePath);
                logInfo(`Download complete: ${filePath}`);
                resolve({ success: true, path: filePath, size: downloadedSize });
            });

            file.on('error', (err) => {
                fs.unlink(tempPath, () => {});
                reject(err);
            });
        });

        request.on('error', (err) => {
            fs.unlink(tempPath, () => {});
            reject(err);
        });

        request.setTimeout(300000); // 5 minute timeout
    });
});

// Import a model from a local file
ipcMain.handle('import-model', async (event, sourcePath) => {
    return new Promise((resolve, reject) => {
        try {
            const modelsDir = ensureModelsDir();
            const filename = path.basename(sourcePath);
            const destPath = path.join(modelsDir, filename);

            if (!fs.existsSync(sourcePath)) {
                reject(new Error(`Source file not found: ${sourcePath}`));
                return;
            }

            fs.copyFileSync(sourcePath, destPath);
            logInfo(`Imported model: ${sourcePath} -> ${destPath}`);
            resolve({ success: true, path: destPath });
        } catch (e) {
            reject(e);
        }
    });
});

// Delete a model
ipcMain.handle('delete-model', async (event, modelPath) => {
    return new Promise((resolve, reject) => {
        try {
            if (fs.existsSync(modelPath)) {
                fs.unlinkSync(modelPath);
                logInfo(`Deleted model: ${modelPath}`);
                resolve({ success: true });
            } else {
                reject(new Error(`Model not found: ${modelPath}`));
            }
        } catch (e) {
            reject(e);
        }
    });
});

// Load a model into llama.cpp (via API call)
ipcMain.handle('load-model', async (event, modelPath) => {
    // This will trigger a model load in llama.cpp via the API
    // The llama.cpp server is already running with a default model
    // We can use the /v1/models endpoint to check and /v1/chat/completions to test
    return new Promise((resolve) => {
        // Check if the model exists
        if (!fs.existsSync(modelPath)) {
            resolve({ success: false, error: 'Model file not found' });
            return;
        }

        // For now, we'll just check if the model is accessible
        // In the future, we can dynamically update the llama.cpp container's model
        resolve({
            success: true,
            message: `Model ${path.basename(modelPath)} is available. Restart llama.cpp to load it.`,
        });
    });
});

// ──────────────────────────────────────────────────────────────────────────────
// GPU Detection and Status
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('detect-gpu', async () => {
    return new Promise((resolve) => {
        const command = 'nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader';
        exec(command, (error, stdout, stderr) => {
            if (error) {
                resolve({ gpuAvailable: false, error: error.message });
                return;
            }
            try {
                const lines = stdout.trim().split('\n');
                const gpus = lines.map(line => {
                    const parts = line.split(',');
                    return {
                        name: parts[0].trim(),
                        memoryTotal: parts[1].trim(),
                        memoryUsed: parts[2].trim(),
                    };
                });
                resolve({ gpuAvailable: true, gpus });
            } catch (e) {
                resolve({ gpuAvailable: false, error: e.message });
            }
        });
    });
});

// ──────────────────────────────────────────────────────────────────────────────
// Backup & Restore
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('create-backup', async (event, options) => {
    return new Promise((resolve, reject) => {
        const script = path.join(PROJECT_ROOT, 'scripts', 'backup.sh');
        const args = [];
        if (options && options.outputDir) {
            args.push('--output-dir', options.outputDir);
        }
        if (options && options.auto) {
            args.push('--auto');
        }

        logInfo(`Running backup: ${script} ${args.join(' ')}`);

        try {
            fs.chmodSync(script, 0o755);
        } catch (e) {
            logError(`Failed to make script executable: ${e.message}`);
        }

        const proc = spawn('bash', [script, ...args], {
            cwd: PROJECT_ROOT,
            env: { ...process.env, FORCE_COLOR: 'true' },
        });

        proc.stdout.on('data', (data) => {
            const output = data.toString();
            event.sender.send('backup-output', output);
            logInfo(`[BACKUP] ${output.trim()}`);
        });

        proc.stderr.on('data', (data) => {
            const output = data.toString();
            event.sender.send('backup-output', output);
            logInfo(`[BACKUP ERR] ${output.trim()}`);
        });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true });
            } else {
                reject({ success: false, code });
            }
        });

        proc.on('error', (err) => {
            reject({ success: false, error: err.message });
        });
    });
});

ipcMain.handle('list-backups', async () => {
    const backupDir = path.join(os.homedir(), '.nettrades', 'backups');
    try {
        if (!fs.existsSync(backupDir)) {
            return [];
        }
        const files = fs.readdirSync(backupDir);
        const backups = files
            .filter(f => f.startsWith('nettrades-backup-') && f.endsWith('.tar.gz'))
            .map(f => {
                const filePath = path.join(backupDir, f);
                const stats = fs.statSync(filePath);
                return {
                    name: f,
                    path: filePath,
                    size: stats.size,
                    modified: stats.mtime,
                };
            })
            .sort((a, b) => b.modified - a.modified);
        return backups;
    } catch (e) {
        logError(`Failed to list backups: ${e.message}`);
        return [];
    }
});

ipcMain.handle('restore-backup', async (event, backupPath) => {
    return new Promise((resolve, reject) => {
        const script = path.join(PROJECT_ROOT, 'scripts', 'restore.sh');
        const args = [backupPath, '--auto'];

        logInfo(`Running restore: ${script} ${args.join(' ')}`);

        try {
            fs.chmodSync(script, 0o755);
        } catch (e) {
            logError(`Failed to make script executable: ${e.message}`);
        }

        const proc = spawn('bash', [script, ...args], {
            cwd: PROJECT_ROOT,
            env: { ...process.env, FORCE_COLOR: 'true' },
        });

        proc.stdout.on('data', (data) => {
            const output = data.toString();
            event.sender.send('restore-output', output);
            logInfo(`[RESTORE] ${output.trim()}`);
        });

        proc.stderr.on('data', (data) => {
            const output = data.toString();
            event.sender.send('restore-output', output);
            logInfo(`[RESTORE ERR] ${output.trim()}`);
        });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true });
            } else {
                reject({ success: false, code });
            }
        });

        proc.on('error', (err) => {
            reject({ success: false, error: err.message });
        });
    });
});

// ──────────────────────────────────────────────────────────────────────────────
// Open URLs (with dynamic server detection and error handling)
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('open-url', (event, url) => {
    shell.openExternal(url).catch((err) => {
        logError(`Failed to open URL ${url}: ${err.message}`);
        // Send error back to renderer
        event.sender.send('open-error', { url, error: err.message });
    });
});

ipcMain.handle('open-service', (event, service) => {
    const serverUrl = getServerUrl();
    const ports = {
        odoo: ':8069',
        grafana: ':3001',
        llama: ':8080',
        ui: ':3002',
        api: ':8000',
        prometheus: ':9090',
    };
    const port = ports[service] || '';
    const url = `${serverUrl}${port}`;
    
    shell.openExternal(url).catch((err) => {
        logError(`Failed to open service ${service} at ${url}: ${err.message}`);
        // Send error back to renderer for user feedback
        event.sender.send('open-error', { service, url, error: err.message });
    });
    return { url };
});

// ──────────────────────────────────────────────────────────────────────────────
// Open File Explorer
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('open-path', (event, pathToOpen) => {
    shell.openPath(pathToOpen);
});

// ──────────────────────────────────────────────────────────────────────────────
// Show dialog
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('show-dialog', async (event, options) => {
    return await dialog.showMessageBox(mainWindow, options);
});

// ──────────────────────────────────────────────────────────────────────────────
// Logging
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('get-logs', async () => {
    const logDir = path.join(os.homedir(), '.nettrades', 'logs');
    try {
        if (!fs.existsSync(logDir)) {
            return [];
        }
        const files = fs.readdirSync(logDir);
        return files.map(f => {
            const filePath = path.join(logDir, f);
            const stats = fs.statSync(filePath);
            return {
                name: f,
                path: filePath,
                size: stats.size,
                modified: stats.mtime,
            };
        }).sort((a, b) => b.modified - a.modified);
    } catch (e) {
        logError(`Failed to list logs: ${e.message}`);
        return [];
    }
});

ipcMain.handle('get-log-content', async (event, logPath) => {
    try {
        if (!fs.existsSync(logPath)) {
            return { success: false, error: 'Log file not found' };
        }
        const content = fs.readFileSync(logPath, 'utf8');
        return { success: true, content };
    } catch (e) {
        return { success: false, error: e.message };
    }
});