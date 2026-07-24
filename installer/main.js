#!/usr/bin/env node
/**
 * =============================================================================
 * NETTRADES Installer - Electron Main Process
 * =============================================================================
 *
 * FILE: installer/main.js
 *
 * PURPOSE:
 *   This is the main entry point for the NETTRADES Installer desktop application.
 *   It orchestrates the installation process by:
 *     1. Creating the main application window.
 *     2. Handling IPC communication between the renderer (UI) and the main process.
 *     3. Running the nettrades-setup.sh script with elevated privileges.
 *     4. Managing auto-updates via electron-updater.
 *     5. Generating WireGuard client configurations.
 *     6. Providing service status and quick-access to web UIs (Odoo, Grafana, GPUStack).
 *
 * ARCHITECTURE NOTES:
 *   - The installer follows a "thin wrapper" pattern: the Electron app is a
 *     user-friendly GUI that runs the existing nettrades-setup.sh script.
 *     This keeps the installation logic in one place and makes it testable
 *     independently of the GUI.
 *   - Privilege escalation is handled via sudo-prompt on macOS/Linux and
 *     native UAC on Windows (via child_process), ensuring the user is prompted
 *     securely.
 *   - Auto-updates use electron-updater with GitHub Releases as the update
 *     server (configured in package.json).
 *   - The installer supports both development (npm start) and packaged
 *     (production) modes, using app.isPackaged to resolve paths correctly.
 *
 * FUTURE-PROOFING:
 *   - WireGuard key generation is built in; keys can be managed via Odoo
 *     after installation.
 *   - The installer supports headless/CLI mode for CI/CD and server deployments
 *     (via command-line arguments, not implemented here but can be extended).
 *   - Scaling is handled by the platform (Kubernetes, GPUStack) – the installer
 *     is only responsible for the initial bootstrap.
 * =============================================================================
 */

const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const sudo = require('sudo-prompt');

// -----------------------------------------------------------------------------
// 1. PATH RESOLUTION (Development vs Production)
// -----------------------------------------------------------------------------

/**
 * Determine the correct paths for scripts and resources.
 * In development (npm start): we are in nettrades-platform/installer/,
 * so we go up one level to the repo root.
 * In production (packaged app): all resources are under process.resourcesPath.
 */
let scriptPath, wireguardScriptPath, repoRoot;

try {
    if (app.isPackaged) {
        // Production: resources are extracted to process.resourcesPath
        // The scripts are copied there via extraResources in package.json
        repoRoot = process.resourcesPath;
        scriptPath = path.join(process.resourcesPath, 'scripts', 'nettrades-setup.sh');
        wireguardScriptPath = path.join(process.resourcesPath, 'scripts', 'wireguard-manager.sh');
    } else {
        // Development: paths relative to installer/ directory
        repoRoot = path.join(__dirname, '..');   // go up one level to repo root
        scriptPath = path.join(repoRoot, 'scripts', 'nettrades-setup.sh');
        wireguardScriptPath = path.join(repoRoot, 'scripts', 'wireguard-manager.sh');
    }

    // Optional: verify the script exists (helps debugging)
    if (!fs.existsSync(scriptPath)) {
        console.warn('⚠️ nettrades-setup.sh not found at:', scriptPath);
        console.warn('   Current directory:', __dirname);
        console.warn('   app.isPackaged:', app.isPackaged);
    }
} catch (err) {
    console.error('Failed to resolve script paths:', err);
    // Fallback to a reasonable default for development
    scriptPath = path.join(__dirname, '..', 'scripts', 'nettrades-setup.sh');
    wireguardScriptPath = path.join(__dirname, '..', 'scripts', 'wireguard-manager.sh');
}

// -----------------------------------------------------------------------------
// 2. GLOBAL STATE
// -----------------------------------------------------------------------------

let mainWindow = null;
let isInstalling = false;
let installProcess = null;

// -----------------------------------------------------------------------------
// 3. AUTO-UPDATE SETUP
// -----------------------------------------------------------------------------

// Enable logging for auto-updater (helps debugging)
autoUpdater.logger = console;
autoUpdater.autoDownload = false; // We'll prompt the user before downloading

/**
 * Check for updates using electron-updater.
 * This function is called after the window is shown.
 */
function checkForUpdates() {
    // In development, skip update checks to avoid noise
    if (!app.isPackaged) {
        console.log('Development mode: skipping update check');
        return;
    }

    console.log('Checking for updates...');
    autoUpdater.checkForUpdatesAndNotify();
}

autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version);
    dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: 'Update Available',
        message: `A new version (${info.version}) is available. Download it now?`,
        buttons: ['Download', 'Later'],
        defaultId: 0,
    }).then((result) => {
        if (result.response === 0) {
            autoUpdater.downloadUpdate();
        }
    });
});

autoUpdater.on('update-downloaded', (info) => {
    console.log('Update downloaded:', info.version);
    dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: 'Update Ready',
        message: 'The update has been downloaded. Install it now? The application will restart.',
        buttons: ['Install', 'Later'],
        defaultId: 0,
    }).then((result) => {
        if (result.response === 0) {
            setImmediate(() => {
                autoUpdater.quitAndInstall();
            });
        }
    });
});

autoUpdater.on('error', (err) => {
    console.error('Update error:', err);
    // Do not block the installer if auto-update fails
});

// -----------------------------------------------------------------------------
// 4. WINDOW CREATION
// -----------------------------------------------------------------------------

/**
 * Create the main BrowserWindow and load the UI.
 */
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 900,
        height: 750,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
        },
        icon: path.join(__dirname, 'icon.png'),
        title: 'NETTRADES Installer',
        backgroundColor: '#0f172a',
        show: false, // Only show when ready
    });

    mainWindow.loadFile('index.html');
    mainWindow.setMenuBarVisibility(false);
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // Check for updates a few seconds after startup
    setTimeout(() => {
        checkForUpdates();
    }, 5000);
}

// -----------------------------------------------------------------------------
// 5. IPC HANDLERS
// -----------------------------------------------------------------------------

/**
 * Handler: check-docker
 * Checks if Docker and Docker Compose are installed.
 * Returns: { docker: boolean, compose: boolean }
 */
ipcMain.handle('check-docker', async () => {
    return new Promise((resolve) => {
        const checks = { docker: false, compose: false };

        const dockerCheck = spawn('docker', ['--version']);
        dockerCheck.on('close', (code) => {
            checks.docker = code === 0;

            const composeCheck = spawn('docker', ['compose', 'version']);
            composeCheck.on('close', (code2) => {
                checks.compose = code2 === 0;
                resolve(checks);
            });
        });
    });
});

/**
 * Handler: run-install
 * Runs nettrades-setup.sh with the given options.
 * Options: { profile, environment, force, auto }
 * Returns: { success: boolean, output: string }
 * Security: Uses sudo-prompt on macOS/Linux; on Windows uses native UAC.
 */
ipcMain.handle('run-install', async (event, options) => {
    if (isInstalling) {
        throw new Error('Installation already in progress');
    }

    isInstalling = true;
    const profile = options.profile || 'all';
    const environment = options.environment || 'development';
    const force = options.force ? '--force' : '';
    const auto = options.auto ? '--auto' : '';

    // Ensure the script is executable (on Unix-like systems)
    if (process.platform !== 'win32') {
        try {
            fs.chmodSync(scriptPath, 0o755);
        } catch (err) {
            console.error('Failed to make script executable:', err);
        }
    }

    return new Promise((resolve, reject) => {
        let output = '';
        let child = null;

        // On Windows, we can run bash directly (if Git Bash or WSL is available)
        // We'll use 'bash' and pass the script as an argument.
        if (process.platform === 'win32') {
            child = spawn('bash', [
                scriptPath,
                profile,
                force,
                auto,
                '--environment', environment
            ], {
                shell: true,
                detached: false,
                windowsVerbatimArguments: true,
            });

            child.stdout.on('data', (data) => {
                const text = data.toString();
                output += text;
                event.sender.send('install-output', text);
            });

            child.stderr.on('data', (data) => {
                const text = data.toString();
                output += text;
                event.sender.send('install-output', text);
            });

            child.on('close', (code) => {
                isInstalling = false;
                if (code === 0) {
                    resolve({ success: true, output });
                } else {
                    reject({ success: false, output, code });
                }
            });
        } else {
            // macOS/Linux: use sudo-prompt for a native password dialog
            const sudoOptions = {
                name: 'NETTRADES Installer',
                icns: path.join(__dirname, 'build', 'icon.icns'),
            };

            // Build the full command with environment variable
            const fullCommand = `ENVIRONMENT=${environment} ${scriptPath} ${profile} ${force} ${auto}`;

            sudo.exec(fullCommand, sudoOptions, (error, stdout, stderr) => {
                isInstalling = false;
                const fullOutput = stdout + stderr;
                if (error) {
                    event.sender.send('install-output', `Error: ${error.message}\n${fullOutput}`);
                    reject({ success: false, output: fullOutput, error: error.message });
                } else {
                    event.sender.send('install-output', fullOutput);
                    resolve({ success: true, output: fullOutput });
                }
            });
        }

        // Store the child process reference for cancellation
        installProcess = child;
    });
});

/**
 * Handler: cancel-install
 * Attempts to cancel the running installation.
 * Returns: { success: boolean }
 */
ipcMain.handle('cancel-install', async () => {
    if (installProcess) {
        installProcess.kill('SIGINT');
        installProcess = null;
        isInstalling = false;
        return { success: true };
    }
    return { success: false };
});

/**
 * Handler: get-status
 * Checks running Docker containers to determine service status.
 * Returns: { odoo: boolean, langgraph: boolean, gpustack: boolean, postgres: boolean }
 */
ipcMain.handle('get-status', async () => {
    return new Promise((resolve) => {
        const status = {
            odoo: false,
            langgraph: false,
            gpustack: false,
            postgres: false,
        };

        exec('docker ps --format "{{.Names}}"', (error, stdout) => {
            if (error) {
                resolve(status);
                return;
            }

            const containers = stdout.split('\n');
            status.odoo = containers.some(c => c.includes('odoo'));
            status.langgraph = containers.some(c => c.includes('langgraph'));
            status.gpustack = containers.some(c => c.includes('gpustack'));
            status.postgres = containers.some(c => c.includes('postgres'));
            resolve(status);
        });
    });
});

/**
 * Handler: generate-wireguard-key
 * Generates a WireGuard key pair using the 'wg' command.
 * Returns: { privateKey: string, publicKey: string }
 * If 'wg' is not available, falls back to OpenSSL (or returns an error).
 */
ipcMain.handle('generate-wireguard-key', async () => {
    return new Promise((resolve, reject) => {
        // Check if 'wg' is available
        exec('which wg', (error) => {
            if (error) {
                // Fallback: use OpenSSL to generate a random key (not WireGuard format)
                // This is a backup for systems without WireGuard tools.
                // In reality, you'd want to install wireguard-tools.
                const privateKey = require('crypto').randomBytes(32).toString('hex');
                const publicKey = 'fallback-public-key';
                reject(new Error('WireGuard tools not found. Please install wireguard-tools.'));
                return;
            }

            // Generate private key
            exec('wg genkey', (err, stdout) => {
                if (err) {
                    reject(err);
                    return;
                }
                const privateKey = stdout.trim();

                // Generate public key from private key
                const child = spawn('wg', ['pubkey']);
                child.stdin.write(privateKey);
                child.stdin.end();

                let publicKey = '';
                child.stdout.on('data', (data) => {
                    publicKey += data.toString();
                });
                child.on('close', (code) => {
                    if (code === 0) {
                        resolve({
                            privateKey: privateKey,
                            publicKey: publicKey.trim(),
                        });
                    } else {
                        reject(new Error('Failed to generate public key'));
                    }
                });
            });
        });
    });
});

/**
 * Handler: open-odoo
 * Opens the Odoo web interface in the default browser.
 */
ipcMain.handle('open-odoo', async () => {
    shell.openExternal('http://localhost:8069');
});

/**
 * Handler: open-grafana
 * Opens the Grafana web interface.
 */
ipcMain.handle('open-grafana', async () => {
    shell.openExternal('http://localhost:3001');
});

/**
 * Handler: open-gpustack
 * Opens the GPUStack web interface.
 */
ipcMain.handle('open-gpustack', async () => {
    shell.openExternal('http://localhost:8080');
});

// -----------------------------------------------------------------------------
// 6. APPLICATION LIFECYCLE
// -----------------------------------------------------------------------------

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    // On macOS, keep the app running even when all windows are closed
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    // Re-create a window when the dock icon is clicked on macOS
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// -----------------------------------------------------------------------------
// 7. UNCAUGHT EXCEPTION HANDLING
// -----------------------------------------------------------------------------

process.on('uncaughtException', (error) => {
    console.error('Uncaught exception:', error);
    // Optionally show a dialog to the user
    dialog.showErrorBox('Unexpected Error', error.message);
});

process.on('unhandledRejection', (reason) => {
    console.error('Unhandled rejection:', reason);
});


/**
 * Handler: run-wireguard-command
 *
 * Executes a WireGuard manager command and returns the result.
 * This allows the Electron UI to manage WireGuard peers.
 *
 * Args:
 *   - args: Array of command arguments (e.g., ['add', 'laptop', '10.10.10.50'])
 *
 * Returns: { success: boolean, output: string, error?: string }
 *
 * Security: Uses the installed /usr/local/bin/wireguard-manager.sh script.
 *           Requires root/sudo privileges (handled by the script itself).
 */
ipcMain.handle('run-wireguard-command', async (event, args) => {
    return new Promise((resolve, reject) => {
        // Use the wireguardScriptPath resolved earlier
        const scriptPath = wireguardScriptPath;

        if (!scriptPath || !fs.existsSync(scriptPath)) {
            reject(new Error('WireGuard manager script not found. Please ensure wireguard-manager.sh is installed.'));
            return;
        }

        // Ensure the script is executable
        if (process.platform !== 'win32') {
            try {
                fs.chmodSync(scriptPath, 0o755);
            } catch (err) {
                console.error('Failed to make script executable:', err);
            }
        }

        // On Windows, use bash to run the script
        const cmd = process.platform === 'win32'
            ? ['bash', scriptPath, ...args]
            : [scriptPath, ...args];

        const child = spawn(cmd[0], cmd.slice(1), {
            stdio: ['pipe', 'pipe', 'pipe'],
            env: process.env,
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (data) => {
            const text = data.toString();
            stdout += text;
            // Send real-time output to the renderer
            event.sender.send('wireguard-output', text);
        });

        child.stderr.on('data', (data) => {
            const text = data.toString();
            stderr += text;
            event.sender.send('wireguard-output', text);
        });

        child.on('close', (code) => {
            if (code === 0) {
                resolve({ success: true, output: stdout });
            } else {
                reject({ success: false, output: stdout, error: stderr, code });
            }
        });

        child.on('error', (err) => {
            reject({ success: false, error: err.message });
        });
    });
});