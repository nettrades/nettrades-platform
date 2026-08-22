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
//   - GPU management APIs
//   - Training and fine-tuning APIs
//   - "Ask Someone" and "Good Answer" APIs
//   - Queue and task management APIs
//   - Marketplace APIs
//   - Backup and restore APIs
// =============================================================================

const { contextBridge, ipcRenderer, shell } = require('electron');

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
    // Platform Setup Status (NEW – for Quick Setup)
    // ──────────────────────────────────────────────────────────────────────────

    isPlatformSetup: () => ipcRenderer.invoke('is-platform-setup'),

    // ──────────────────────────────────────────────────────────────────────────
    // Quick Setup – One-click development environment (NEW)
    // ──────────────────────────────────────────────────────────────────────────

    runQuickSetup: () => ipcRenderer.invoke('run-quick-setup'),

    // ──────────────────────────────────────────────────────────────────────────
    // Feature Flags
    // ──────────────────────────────────────────────────────────────────────────

    getFeatureFlags: () => ipcRenderer.invoke('get-feature-flags'),

    // ──────────────────────────────────────────────────────────────────────────
    // Installation / Deployment
    // ──────────────────────────────────────────────────────────────────────────

    runInstall: (options) => ipcRenderer.invoke('run-install', options),
    cancelInstall: () => ipcRenderer.invoke('cancel-install'),
    getInstallStatus: () => ipcRenderer.invoke('get-install-status'),
    onInstallOutput: (callback) => {
        ipcRenderer.on('install-output', (event, data) => callback(data));
    },
    onInstallProgress: (callback) => {
        ipcRenderer.on('install-progress', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Platform Control (Docker Compose)
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
    // "Ask Someone" Expert System
    // ──────────────────────────────────────────────────────────────────────────

    askSomeone: (data) => ipcRenderer.invoke('ask-someone', data),

    // ──────────────────────────────────────────────────────────────────────────
    // "Good Answer" Training Data
    // ──────────────────────────────────────────────────────────────────────────

    goodAnswer: (data) => ipcRenderer.invoke('good-answer', data),

    // ──────────────────────────────────────────────────────────────────────────
    // Training & Fine-Tuning
    // ──────────────────────────────────────────────────────────────────────────

    startTraining: (data) => ipcRenderer.invoke('start-training', data),
    trainingStatus: () => ipcRenderer.invoke('training-status'),

    // ──────────────────────────────────────────────────────────────────────────
    // Agent Management
    // ──────────────────────────────────────────────────────────────────────────

    listAgents: () => ipcRenderer.invoke('list-agents'),
    agentStatus: (agentId) => ipcRenderer.invoke('agent-status', agentId),

    // ──────────────────────────────────────────────────────────────────────────
    // Queue Management
    // ──────────────────────────────────────────────────────────────────────────

    listQueue: () => ipcRenderer.invoke('list-queue'),
    cancelTask: (taskId) => ipcRenderer.invoke('cancel-task', taskId),
    retryTask: (taskId) => ipcRenderer.invoke('retry-task', taskId),

    // ──────────────────────────────────────────────────────────────────────────
    // GPU Marketplace
    // ──────────────────────────────────────────────────────────────────────────

    marketplaceListings: () => ipcRenderer.invoke('marketplace-listings'),
    marketplaceListGPU: (data) => ipcRenderer.invoke('marketplace-list-gpu', data),
    marketplaceBookGPU: (data) => ipcRenderer.invoke('marketplace-book-gpu', data),

    // ──────────────────────────────────────────────────────────────────────────
    // Node Discovery
    // ──────────────────────────────────────────────────────────────────────────

    getDiscoveredNodes: () => ipcRenderer.invoke('get-discovered-nodes'),
    onNodeDiscovered: (callback) => {
        ipcRenderer.on('node-discovered', (event, data) => callback(data));
    },
    onNodeLost: (callback) => {
        ipcRenderer.on('node-lost', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // VPN Management (WireGuard)
    // ──────────────────────────────────────────────────────────────────────────

    vpnAddPeer: (username, ip) => ipcRenderer.invoke('vpn-add-peer', username, ip),
    vpnListPeers: () => ipcRenderer.invoke('vpn-list-peers'),
    vpnStatus: () => ipcRenderer.invoke('vpn-status'),

    // ──────────────────────────────────────────────────────────────────────────
    // System Health & Monitoring
    // ──────────────────────────────────────────────────────────────────────────

    systemHealth: () => ipcRenderer.invoke('system-health'),

    // ──────────────────────────────────────────────────────────────────────────
    // Logs
    // ──────────────────────────────────────────────────────────────────────────

    getLogs: (options) => ipcRenderer.invoke('get-logs', options),

    // ──────────────────────────────────────────────────────────────────────────
    // Alerts & Notifications
    // ──────────────────────────────────────────────────────────────────────────

    getAlerts: () => ipcRenderer.invoke('get-alerts'),
    getNotifications: () => ipcRenderer.invoke('get-notifications'),
    markNotificationRead: (id) => ipcRenderer.invoke('mark-notification-read', id),

    // ──────────────────────────────────────────────────────────────────────────
    // Backup & Restore
    // ──────────────────────────────────────────────────────────────────────────

    createBackup: (options) => ipcRenderer.invoke('create-backup', options),
    listBackups: () => ipcRenderer.invoke('list-backups'),
    restoreBackup: (backupPath) => ipcRenderer.invoke('restore-backup', backupPath),
    onBackupOutput: (callback) => {
        ipcRenderer.on('backup-output', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Tenant Configuration
    // ──────────────────────────────────────────────────────────────────────────

    getTenantConfig: () => ipcRenderer.invoke('get-tenant-config'),
    setTenantConfig: (config) => ipcRenderer.invoke('set-tenant-config', config),

    // ──────────────────────────────────────────────────────────────────────────
    // Grove & KAI Scheduler Management
    // ──────────────────────────────────────────────────────────────────────────

    getGroveStatus: () => ipcRenderer.invoke('get-grove-status'),
    getKAIStatus: () => ipcRenderer.invoke('get-kai-status'),
    startGrove: () => ipcRenderer.invoke('start-grove'),
    stopGrove: () => ipcRenderer.invoke('stop-grove'),
    startKAI: () => ipcRenderer.invoke('start-kai'),
    stopKAI: () => ipcRenderer.invoke('stop-kai'),

    // ──────────────────────────────────────────────────────────────────────────
	// Developer Tools – Wine Installer
	// ──────────────────────────────────────────────────────────────────────────

	installWine: () => ipcRenderer.invoke('install-wine'),
	onWineOutput: (callback) => {
	    ipcRenderer.on('wine-output', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Utilities
    // ──────────────────────────────────────────────────────────────────────────

    openExternal: (url) => shell.openExternal(url),

    // ──────────────────────────────────────────────────────────────────────────
    // Window Controls
    // ──────────────────────────────────────────────────────────────────────────

    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),

    // ──────────────────────────────────────────────────────────────────────────
	// System Check
	// ──────────────────────────────────────────────────────────────────────────

	systemCheck: () => ipcRenderer.invoke('system-check'),

	// ──────────────────────────────────────────────────────────────────────────
	// Credentials (Secrets)
	// ──────────────────────────────────────────────────────────────────────────

	getCredentials: () => ipcRenderer.invoke('get-credentials'),
	getCredentialValue: (key) => ipcRenderer.invoke('get-credential-value', key),
	rotateCredential: (key, newValue) => ipcRenderer.invoke('rotate-credential', key, newValue),

	// ──────────────────────────────────────────────────────────────────────────
	// Modular Installation
	// ──────────────────────────────────────────────────────────────────────────

    installModules: (modules) => ipcRenderer.invoke('install-modules', modules),


    // ──────────────────────────────────────────────────────────────────────────
    // Update Status
    // ──────────────────────────────────────────────────────────────────────────

    onUpdateStatus: (callback) => {
        ipcRenderer.on('update-status', (event, data) => callback(data));
    },
});