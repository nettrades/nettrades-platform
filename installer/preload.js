// =============================================================================
// FILE: installer/preload.js
// =============================================================================
// PURPOSE:
//   Exposes a safe API to the renderer process via contextBridge.
//   Only whitelisted functions are exposed to prevent arbitrary code execution.
//
// KEY FEATURES:
//   - Secure IPC communication between renderer and main process
//   - Exposes only necessary APIs for the launcher UI
//   - Model management APIs
//   - Platform control APIs
//   - Odoo authentication integration
// =============================================================================

const { contextBridge, ipcRenderer } = require('electron');

// -----------------------------------------------------------------------------
// Expose safe API to renderer
// -----------------------------------------------------------------------------
contextBridge.exposeInMainWorld('api', {
    // ──────────────────────────────────────────────────────────────────────────
    // Platform & System
    // ──────────────────────────────────────────────────────────────────────────
    getPlatform: () => ipcRenderer.invoke('get-platform'),
    getProjectRoot: () => ipcRenderer.invoke('get-project-root'),
    getModelsDir: () => ipcRenderer.invoke('get-models-dir'),
    getServerUrl: () => ipcRenderer.invoke('get-server-url'),
    saveServerUrl: (url) => ipcRenderer.invoke('save-server-url', url),

    // ──────────────────────────────────────────────────────────────────────────
    // Feature Flags
    // ──────────────────────────────────────────────────────────────────────────
    getFeatureFlags: () => ipcRenderer.invoke('get-feature-flags'),

    // ──────────────────────────────────────────────────────────────────────────
    // Installation
    // ──────────────────────────────────────────────────────────────────────────
    runInstall: (options) => ipcRenderer.invoke('run-install', options),
    cancelInstall: () => ipcRenderer.invoke('cancel-install'),
    getInstallStatus: () => ipcRenderer.invoke('get-install-status'),
    onInstallOutput: (callback) => {
        ipcRenderer.on('install-output', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Platform Control
    // ──────────────────────────────────────────────────────────────────────────
    startPlatform: () => ipcRenderer.invoke('start-platform'),
    stopPlatform: () => ipcRenderer.invoke('stop-platform'),
    restartPlatform: () => ipcRenderer.invoke('restart-platform'),
    platformStatus: () => ipcRenderer.invoke('platform-status'),
    onPlatformOutput: (callback) => {
        ipcRenderer.on('platform-output', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Model Management
    // ──────────────────────────────────────────────────────────────────────────
    listModels: () => ipcRenderer.invoke('list-models'),
    downloadModel: (options) => ipcRenderer.invoke('download-model', options),
    importModel: (path) => ipcRenderer.invoke('import-model', path),
    deleteModel: (path) => ipcRenderer.invoke('delete-model', path),
    loadModel: (path) => ipcRenderer.invoke('load-model', path),
    onDownloadProgress: (callback) => {
        ipcRenderer.on('download-progress', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // GPU Detection
    // ──────────────────────────────────────────────────────────────────────────
    detectGpu: () => ipcRenderer.invoke('detect-gpu'),

    // ──────────────────────────────────────────────────────────────────────────
    // Backup & Restore
    // ──────────────────────────────────────────────────────────────────────────
    createBackup: (options) => ipcRenderer.invoke('create-backup', options),
    listBackups: () => ipcRenderer.invoke('list-backups'),
    restoreBackup: (backupPath) => ipcRenderer.invoke('restore-backup', backupPath),
    onBackupOutput: (callback) => {
        ipcRenderer.on('backup-output', (event, data) => callback(data));
    },
    onRestoreOutput: (callback) => {
        ipcRenderer.on('restore-output', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Service Launcher (Dynamic Server URLs)
    // ──────────────────────────────────────────────────────────────────────────
    openUrl: (url) => ipcRenderer.invoke('open-url', url),
    openService: (service) => ipcRenderer.invoke('open-service', service),
    openPath: (path) => ipcRenderer.invoke('open-path', path),

    // ──────────────────────────────────────────────────────────────────────────
    // Logs
    // ──────────────────────────────────────────────────────────────────────────
    getLogs: () => ipcRenderer.invoke('get-logs'),
    getLogContent: (path) => ipcRenderer.invoke('get-log-content', path),

    // ──────────────────────────────────────────────────────────────────────────
    // Dialog
    // ──────────────────────────────────────────────────────────────────────────
    showDialog: (options) => ipcRenderer.invoke('show-dialog', options),
});