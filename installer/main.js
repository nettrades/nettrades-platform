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

// Determine project root – CRITICAL FIX for packaged app
// When running from source (npm start), use __dirname/../..
// When packaged, resources are in process.resourcesPath
const isPackaged = app.isPackaged;
const PROJECT_ROOT = isPackaged
    ? process.resourcesPath
    : path.join(__dirname, '..', '..');

// Models directory (where llama.cpp and Dynamo look for models)
const MODELS_DIR = path.join(PROJECT_ROOT, 'deploy', 'docker', 'dynamo-data', 'models');

// -----------------------------------------------------------------------------
// Create the main window
// -----------------------------------------------------------------------------
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1100,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        },
        icon: path.join(__dirname, 'icon.png'),
        title: 'NetTrades Launcher',
        backgroundColor: '#0f172a',
        show: false,
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
        const composeFile = path.join(PROJECT_ROOT, 'deploy', 'docker', 'docker-compose.yaml');
        const command = `docker compose -f "${composeFile}" up -d`;

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
        const composeFile = path.join(PROJECT_ROOT, 'deploy', 'docker', 'docker-compose.yaml');
        const command = `docker compose -f "${composeFile}" down`;

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

// ──────────────────────────────────────────────────────────────────────────────
// Model Management (Inspired by LM Studio's approach)
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

// Download a model from Hugging Face or ModelScope
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
    });
});

// Import a model from a local file (copy to models directory)
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
// Utility: Format file size
// ──────────────────────────────────────────────────────────────────────────────
function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

// ──────────────────────────────────────────────────────────────────────────────
// Open URLs
// ──────────────────────────────────────────────────────────────────────────────

ipcMain.handle('open-url', (event, url) => {
    shell.openExternal(url);
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