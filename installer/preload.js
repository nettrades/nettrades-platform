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
    // Utilities
    // ──────────────────────────────────────────────────────────────────────────
    openUrl: (url) => ipcRenderer.invoke('open-url', url),
    openPath: (path) => ipcRenderer.invoke('open-path', path),
    showDialog: (options) => ipcRenderer.invoke('show-dialog', options),
});