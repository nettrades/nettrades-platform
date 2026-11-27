// =============================================================================
// FILE: installer/preload.js
// =============================================================================
// PURPOSE:
//   Exposes a safe API to the renderer process via contextBridge.
//   Only whitelisted functions are exposed to prevent arbitrary code execution.
//
// KEY FEATURES:
//   - Secure IPC communication between renderer and main process
//   - Model management APIs
//   - Platform control APIs
//   - Odoo authentication integration
//   - GPU management APIs
//   - Training and fine-tuning APIs
//   - "Ask Someone" and "Good Answer" APIs
//   - Queue and task management APIs
//   - Marketplace APIs
//   - Backup and restore APIs
//   - Universal Enterprise Proxy integration
//   - Hub/Spoke detection
//   - Cluster topology + relaunch (NEW 2026-10)
//   - Live node health via LangGraph /nodes (NEW 2026-10)
//   - Routing events + active track (NEW 2026-10)
//   - Registration token CRUD (NEW 2026-10)
//   - Inference config read (NEW 2026-10)
//   - Platform GPUs (Sub Hub + Spokes) (NEW 2026-10-22)
//   - Chat invocation via LangGraph /invoke (NEW 2026-10-22)
//   - Model upload from local disk (NEW 2026-10-22)
//   - WSL install helpers (NEW 2026-10-22)
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
    listEmergencyAudit: () => ipcRenderer.invoke('list-emergency-audit'),
    showWindow: () => ipcRenderer.invoke('show-window'),

    // ──────────────────────────────────────────────────────────────────────────
    // Platform Setup Status (For Quick Setup)
    // ──────────────────────────────────────────────────────────────────────────

    isPlatformSetup: () => ipcRenderer.invoke('is-platform-setup'),

    // ──────────────────────────────────────────────────────────────────────────
    // Quick Setup – One-click development environment
    // ──────────────────────────────────────────────────────────────────────────

    runQuickSetup: () => ipcRenderer.invoke('run-quick-setup'),

    // ──────────────────────────────────────────────────────────────────────────
    // Feature Flags
    // ──────────────────────────────────────────────────────────────────────────

    getFeatureFlags: () => ipcRenderer.invoke('get-feature-flags'),

    // ──────────────────────────────────────────────────────────────────────────
    // Deployment Mode Detection
    // ──────────────────────────────────────────────────────────────────────────

    getDeploymentMode: () => ipcRenderer.invoke('get-deployment-mode'),

    // ──────────────────────────────────────────────────────────────────────────
    // Enterprise Backend
    // ──────────────────────────────────────────────────────────────────────────

    getEnterpriseBackend: () => ipcRenderer.invoke('get-enterprise-backend'),
    setEnterpriseBackend: (backend) => ipcRenderer.invoke('set-enterprise-backend', backend),

    // ──────────────────────────────────────────────────────────────────────────
    // Hub configuration
    // ──────────────────────────────────────────────────────────────────────────
    getHubConfig: () => ipcRenderer.invoke('get-hub-config'),
    saveHubConfig: (hub) => ipcRenderer.invoke('save-hub-config', hub),

    // ──────────────────────────────────────────────────────────────────────────
    // Emergency Access Management
    // ──────────────────────────────────────────────────────────────────────────

    listEmergencyUsers: () => ipcRenderer.invoke('list-emergency-users'),
    revokeEmergencyUser: (login) => ipcRenderer.invoke('revoke-emergency-user', login),
    createEmergencyUser: (duration) => ipcRenderer.invoke('create-emergency-user', duration),

    // ──────────────────────────────────────────────────────────────────────────
    // Container Management (Docker)
    // ──────────────────────────────────────────────────────────────────────────

    listContainers: () => ipcRenderer.invoke('list-containers'),
    startContainer: (containerId) => ipcRenderer.invoke('start-container', containerId),
    stopContainer: (containerId) => ipcRenderer.invoke('stop-container', containerId),
    restartContainer: (containerId) => ipcRenderer.invoke('restart-container', containerId),
    startAllContainers: () => ipcRenderer.invoke('start-all-containers'),
    stopAllContainers: () => ipcRenderer.invoke('stop-all-containers'),
    restartAllContainers: () => ipcRenderer.invoke('restart-all-containers'),
    containerLogs: (containerId, lines) => ipcRenderer.invoke('container-logs', containerId, lines),

    // ──────────────────────────────────────────────────────────────────────────
    // Installation / Deployment
    // ──────────────────────────────────────────────────────────────────────────

    runInstall: (options) => ipcRenderer.invoke('run-install', {
        profile: options?.profile,
        force: options?.force,
        auto: options?.auto,
        production: options?.production,
        upgrade: options?.upgrade,
        withFinetune: options?.withFinetune,
        withGrove: options?.withGrove,
        withKai: options?.withKai,
        withRouter: options?.withRouter,
        withCuvs: options?.withCuvs,
        domain: options?.domain,
        phases: options?.phases,
        resetData: options?.resetData,
        tenantType: options?.tenantType,
        tenantName: options?.tenantName,
        backend: options?.backend,
        proxyUrl: options?.proxyUrl,
    }),
    cancelInstall: () => ipcRenderer.invoke('cancel-install'),
    getInstallStatus: () => ipcRenderer.invoke('get-install-status'),
    onInstallOutput: (callback) => {
        ipcRenderer.on('install-output', (event, data) => callback(data));
    },
    onInstallProgress: (callback) => {
        ipcRenderer.on('install-progress', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Run Spoke Install / Run Blackwell Install
    // ──────────────────────────────────────────────────────────────────────────

    runSpokeInstall: (options) => ipcRenderer.invoke('run-spoke-install', options),
    runBlackwellInstall: (options) => ipcRenderer.invoke('run-blackwell-install', options),

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
    // Platform status
    // ──────────────────────────────────────────────────────────────────────────

    getPlatformStatus: () => ipcRenderer.invoke('get-platform-status'),

    // ──────────────────────────────────────────────────────────────────────────
    // Model Management
    // ──────────────────────────────────────────────────────────────────────────

    listModels: () => ipcRenderer.invoke('list-models'),
    downloadModel: (options) => ipcRenderer.invoke('download-model', options),
    importModel: (path) => ipcRenderer.invoke('import-model', path),
    deleteModel: (path) => ipcRenderer.invoke('delete-model', path),
    loadModel: (path) => ipcRenderer.invoke('load-model', path),
    uploadModel: () => ipcRenderer.invoke('upload-model'),
    onDownloadProgress: (callback) => {
        ipcRenderer.on('download-progress', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // GPU Detection
    // ──────────────────────────────────────────────────────────────────────────

    detectGpu: () => ipcRenderer.invoke('detect-gpu'),
    detectHardware: () => ipcRenderer.invoke('detect-hardware'),
    detectHardwareProfile: () => ipcRenderer.invoke('detect-hardware-profile'),
    getPlatformGPUs: () => ipcRenderer.invoke('get-platform-gpus'),

    // ──────────────────────────────────────────────────────────────────────────
    // Chat invocation (NEW 2026-10-22)
    // ──────────────────────────────────────────────────────────────────────────

    chatInvoke: (options) => ipcRenderer.invoke('chat-invoke', options),

    // ──────────────────────────────────────────────────────────────────────────
    // GPU management (local registration and job handling)
    // ──────────────────────────────────────────────────────────────────────────

    proxyGetGpuNodes: () => ipcRenderer.invoke('proxy-get-gpu-nodes'),
    proxyRegisterGpuNode: (data) => ipcRenderer.invoke('proxy-register-gpu-node', data),
    proxyCreateJob: (jobData) => ipcRenderer.invoke('proxy-create-job', jobData),
    proxyGetJob: (jobId) => ipcRenderer.invoke('proxy-get-job', jobId),

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
    // Node Discovery (mDNS)
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
    // VPN removal
    // ──────────────────────────────────────────────────────────────────────────

    vpnRemovePeer: (username) => ipcRenderer.invoke('vpn-remove-peer', username),

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

    backupConfigGet:   ()    => ipcRenderer.invoke('backup-config-get'),
    backupConfigSave:  (cfg) => ipcRenderer.invoke('backup-config-save', cfg),
    backupTestRemote:  ()    => ipcRenderer.invoke('backup-test-remote'),
    backupRunRemote:   ()    => ipcRenderer.invoke('backup-run-remote'),

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
    // Window Controls (channel names match ipcMain.on in main.js)
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
    // NETTRADES Networking Service (WSL port forwarding)
    // ──────────────────────────────────────────────────────────────────────────

    netsvcGetStatus: () => ipcRenderer.invoke('netsvc-get-status'),
    netsvcRepair: () => ipcRenderer.invoke('netsvc-repair'),
    netsvcWireGuardStart: (config) => ipcRenderer.invoke('netsvc-wireguard-start', config),
    netsvcWireGuardStop: () => ipcRenderer.invoke('netsvc-wireguard-stop'),

    // ──────────────────────────────────────────────────────────────────────────
    // WSL Installation Helpers (NEW 2026-10-22)
    // ──────────────────────────────────────────────────────────────────────────

    checkWSL: () => ipcRenderer.invoke('check-wsl'),
    checkWSLDistro: () => ipcRenderer.invoke('check-wsl-distro'),
    installWSL: () => ipcRenderer.invoke('install-wsl'),
    installUbuntu: () => ipcRenderer.invoke('install-ubuntu'),
    openWSLTerminal: () => ipcRenderer.invoke('open-wsl-terminal'),

    // ──────────────────────────────────────────────────────────────────────────
    // Update Status
    // ──────────────────────────────────────────────────────────────────────────

    onUpdateStatus: (callback) => {
        ipcRenderer.on('update-status', (event, data) => callback(data));
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Cluster topology & relaunch (NEW 2026-10)
    // ──────────────────────────────────────────────────────────────────────────
    // Surfaces the RPC scheduler's state to the Cluster tab. The Launcher
    // does not run the scheduler directly; it calls the LangGraph service,
    // which owns the scheduler and the docker socket.
    // ──────────────────────────────────────────────────────────────────────────

    getClusterState: (clusterId) => ipcRenderer.invoke('get-cluster-state', clusterId),
    relaunchCluster: (opts) => ipcRenderer.invoke('relaunch-cluster', opts),

    // ──────────────────────────────────────────────────────────────────────────
    // Live node health (NEW 2026-10)
    // ──────────────────────────────────────────────────────────────────────────
    // Reads /nodes and /nodes/{id}/health from the LangGraph service. This
    // is the authoritative live state — mDNS discovery is complementary,
    // not a substitute.
    // ──────────────────────────────────────────────────────────────────────────

    getHealthNodes: () => ipcRenderer.invoke('get-health-nodes'),
    getNodeHealth: (nodeId) => ipcRenderer.invoke('get-node-health', nodeId),

    // ──────────────────────────────────────────────────────────────────────────
    // Routing & failover (NEW 2026-10)
    // ──────────────────────────────────────────────────────────────────────────
    // The supervisor publishes recent routing decisions to /routing/events.
    // The Launcher polls this to show a live failover timeline and the
    // currently active inference track.
    // ──────────────────────────────────────────────────────────────────────────

    getRoutingEvents: (limit) => ipcRenderer.invoke('get-routing-events', limit),
    getActiveTrack: () => ipcRenderer.invoke('get-active-track'),
    getInferenceConfig: () => ipcRenderer.invoke('get-inference-config'),
    // Demo (2026-10-30): the Demo tab's renderer calls these three IPC
    // methods. Without them, refreshDemoTab() throws TypeError and the
    // tab stays blank even though the main-process handler works.
    getDemoStatus: () => ipcRenderer.invoke('get-demo-status'),
    runPreDemoCheck: () => ipcRenderer.invoke('run-pre-demo-check'),
    triggerFailover: () => ipcRenderer.invoke('trigger-failover'),

    // ──────────────────────────────────────────────────────────────────────────
    // Registration tokens (NEW 2026-10)
    // ──────────────────────────────────────────────────────────────────────────
    // Proxies gpu.registration.token CRUD to Odoo via the LangGraph service.
    // ──────────────────────────────────────────────────────────────────────────

    listTokens: () => ipcRenderer.invoke('list-tokens'),
    createToken: (opts) => ipcRenderer.invoke('create-token', opts),
    revokeToken: (tokenId) => ipcRenderer.invoke('revoke-token', tokenId),
});