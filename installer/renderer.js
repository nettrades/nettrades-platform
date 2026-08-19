// =============================================================================
// FILE: installer/renderer.js
// =============================================================================
// PURPOSE:
//   Controls the UI logic for the NETTRADES Launcher.
//   Handles tab switching, dashboard updates, installation flow,
//   backup/restore operations, and log viewing.
//
// KEY FEATURES:
//   - Tab navigation
//   - Dashboard status updates
//   - Installation wizard with profile selection
//   - Custom deployment with phase picker
//   - Upgrade path with module selection
//   - Hardware detection and auto-recommendations
//   - Backup creation and restoration
//   - Live log viewing
//   - Model management
//   - VPN management
//   - Platform control
// =============================================================================

// ──────────────────────────────────────────────────────────────────────────────
// DOM References
// ──────────────────────────────────────────────────────────────────────────────
const tabs = document.querySelectorAll('.nav-item');
const tabContents = {
    dashboard: document.getElementById('tab-dashboard'),
    installer: document.getElementById('tab-installer'),
    models: document.getElementById('tab-models'),
    backup: document.getElementById('tab-backup'),
    logs: document.getElementById('tab-logs'),
    settings: document.getElementById('tab-settings'),
    vpn: document.getElementById('tab-vpn'),
};

let currentTab = 'dashboard';
let featureFlags = {};
let isInstalling = false;
let serverUrl = 'http://localhost';
let selectedProfile = null;
let selectedPhases = [];
let installOptions = {};
let detectedHardware = null;

// ──────────────────────────────────────────────────────────────────────────────
// Tab Navigation
// ──────────────────────────────────────────────────────────────────────────────
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        switchTab(tabName);
    });
});

function switchTab(tabName) {
	// Update nav items
    tabs.forEach(t => t.classList.remove('active'));
    document.querySelector(`.nav-item[data-tab="${tabName}"]`).classList.add('active');

    // Update content
    Object.keys(tabContents).forEach(key => {
        if (tabContents[key]) {
            tabContents[key].classList.toggle('active', key === tabName);
        }
    });

    currentTab = tabName;

    // Refresh data when switching to certain tabs
    if (tabName === 'dashboard') {
        updateDashboard();
        detectHardware();
    }
    if (tabName === 'backup') {
        loadBackupList();
    }
    if (tabName === 'models') {
        loadModels();
    }
    if (tabName === 'vpn') {
        loadVPNUsers();
    }
    if (tabName === 'installer') {
        detectHardware();
        renderDeploymentCards();
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Platform Information
// ──────────────────────────────────────────────────────────────────────────────
async function loadPlatformInfo() {
    try {
        const info = await window.api.getPlatform();
        document.getElementById('platform-info').textContent =
            `${info.platform} (${info.arch})`;
        document.getElementById('version').textContent = `v1.0.0`;
        // Store for later use
        window.platformInfo = info;
    } catch (e) {
        console.error('Failed to load platform info:', e);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Server URL (dynamic, replaces hardcoded localhost)
// ──────────────────────────────────────────────────────────────────────────────
async function loadServerUrl() {
    try {
        const url = await window.api.getServerUrl();
        if (url) {
            serverUrl = url;
            // Update the settings input if it exists
            const input = document.getElementById('server-url');
            if (input) {
                input.value = serverUrl;
            }
        }
    } catch (e) {
        console.error('Failed to load server URL:', e);
    }
}

function getServiceUrl(service) {
    const ports = {
        odoo: ':8069',
        grafana: ':3001',
        llama: ':8080',
        ui: ':3002',
        api: ':8000',
        prometheus: ':9090',
    };
    const port = ports[service] || '';
    // If serverUrl already includes a port, don't add another one
    // Simple check: if serverUrl ends with a number, assume it has a port
    const hasPort = /:\d+$/.test(serverUrl);
    if (hasPort) {
        return `${serverUrl}${port}`;
    }
    return `${serverUrl}${port}`;
}

// ──────────────────────────────────────────────────────────────────────────────
// Hardware Detection
// ──────────────────────────────────────────────────────────────────────────────
async function detectHardware() {
    try {
        const hardware = await window.api.detectHardware();
        detectedHardware = hardware;
        updateHardwareDisplay(hardware);
        updateRecommendations(hardware);
        return hardware;
    } catch (e) {
        console.error('Hardware detection failed:', e);
        return null;
    }
}

function updateHardwareDisplay(hardware) {
    const container = document.getElementById('hardware-info');
    if (!container) return;

    let html = '';
    if (hardware.gpuAvailable && hardware.gpus.length > 0) {
        const gpuSummary = hardware.gpus.map(g =>
            `✅ ${g.name} (${g.memoryTotal} VRAM)`
        ).join('<br>');
        html += `<div class="hardware-item success">${gpuSummary}</div>`;
    } else {
        html += `<div class="hardware-item warning">⚠️ No GPU detected (CPU mode only)</div>`;
    }

    html += `<div class="hardware-item">💾 ${hardware.totalMemory} RAM</div>`;
    html += `<div class="hardware-item">🖥️ ${hardware.cpuCores} cores (${hardware.cpuModel})</div>`;

    if (hardware.k8sDetected) {
        html += `<div class="hardware-item success">☸️ Kubernetes cluster detected</div>`;
    } else {
        html += `<div class="hardware-item warning">⚠️ No Kubernetes cluster detected</div>`;
    }

    if (hardware.dockerInstalled) {
        html += `<div class="hardware-item success">🐳 Docker installed</div>`;
    } else {
        html += `<div class="hardware-item error">❌ Docker not installed</div>`;
    }

    container.innerHTML = html;
}

function updateRecommendations(hardware) {
    if (!hardware) return;

    // Auto-recommend Fine-Tuning if GPU with >16GB VRAM
    const hasLargeGPU = hardware.gpus.some(g => {
        const match = g.memoryTotal.match(/(\d+)/);
        if (match) {
            const vram = parseInt(match[1]);
            return vram > 16000;
        }
        return false;
    });

    const finetuneCheckbox = document.querySelector('input[name="module-finetune"]');
    if (finetuneCheckbox && hasLargeGPU) {
        finetuneCheckbox.checked = true;
        finetuneCheckbox.parentElement.classList.add('recommended');
    }

    // Auto-disable KAI if no Kubernetes
    const kaiCheckbox = document.querySelector('input[name="module-kai"]');
    if (kaiCheckbox && !hardware.k8sDetected) {
        kaiCheckbox.disabled = true;
        kaiCheckbox.parentElement.title = 'Requires Kubernetes cluster';
        const warning = document.createElement('span');
        warning.className = 'warning-text';
        warning.textContent = ' (requires Kubernetes)';
        kaiCheckbox.parentElement.appendChild(warning);
    }

    // Update GPU status in dashboard
    const gpuStatus = document.getElementById('gpu-status');
    if (gpuStatus) {
        if (hardware.gpuAvailable) {
            gpuStatus.textContent = `✅ ${hardware.gpus.length} GPU(s) detected`;
            gpuStatus.className = 'status-badge status-running';
        } else {
            gpuStatus.textContent = '⚠️ No GPU detected (CPU mode)';
            gpuStatus.className = 'status-badge status-unknown';
        }
    }

    const statGpus = document.getElementById('stat-gpus');
    if (statGpus) {
        statGpus.textContent = hardware.gpus.length;
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Feature Flags
// ──────────────────────────────────────────────────────────────────────────────
async function loadFeatureFlags() {
    try {
        featureFlags = await window.api.getFeatureFlags();
        renderDeploymentCards();
    } catch (e) {
        console.error('Failed to load feature flags:', e);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Dashboard
// ──────────────────────────────────────────────────────────────────────────────
async function updateDashboard() {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const uptimeText = document.getElementById('uptime-text');

    try {
		// Try to check if Odoo is running using the dynamic server URL
        const odooUrl = getServiceUrl('odoo');
        const response = await fetch(odooUrl, { method: 'HEAD', mode: 'no-cors' });
        // If we can reach it, it's likely running
        statusBadge.textContent = '✅ Running';
        statusBadge.className = 'status-badge status-running';
        statusText.textContent = 'Running';
        uptimeText.textContent = '--';
    } catch (e) {
        statusBadge.textContent = '⏹ Stopped';
        statusBadge.className = 'status-badge status-stopped';
        statusText.textContent = 'Stopped';
        uptimeText.textContent = '--';
    }

    // Load backup count
    try {
        const backups = await window.api.listBackups();
        document.getElementById('stat-backups').textContent = backups.length;
    } catch (e) {
        document.getElementById('stat-backups').textContent = '0';
    }

    // Load model count
    try {
        const models = await window.api.listModels();
        document.getElementById('stat-models').textContent = models.length;
    } catch (e) {
        document.getElementById('stat-models').textContent = '0';
    }

    // Detect GPUs
    detectHardware();
}

// ──────────────────────────────────────────────────────────────────────────────
// Installation Wizard – Profile Selection
// ──────────────────────────────────────────────────────────────────────────────
const profiles = [
    {
        id: 'sovereign',
        name: '🏠 Sovereign AI in a Box',
        description: 'All AI services on a single server. Perfect for getting started.',
        phases: [0, 1, 2, 4, 5],
        recommended: true,
        endpoint: 'Internal IP (e.g., 192.168.1.100:8069)',
        features: ['Odoo', 'LangGraph', 'Dynamo', 'llama.cpp', 'GPU Marketplace'],
    },
    {
        id: 'router',
        name: '🔀 Sovereign AI Router',
        description: 'Routes requests to multiple GPU nodes. No inference.',
        phases: [0, 1, 2],
        recommended: false,
        endpoint: 'Internal IP (e.g., 192.168.1.100:8069)',
        features: ['Bridge Module', 'Request Routing', 'Node Discovery'],
    },
    {
        id: 'production',
        name: '🌐 Production [External] Website',
        description: 'Same as "Box" but with public HTTPS access and domain.',
        phases: [0, 1, 2, 4, 5],
        recommended: false,
        endpoint: 'https://your-domain.com',
        features: ['SSL Certificates', 'Domain DNS', 'Security Hardening', 'Public Access'],
        advanced: true,
    },
    {
        id: 'k8s',
        name: '☸️ Kubernetes Cluster',
        description: 'Multi-node enterprise deployment with auto-scaling.',
        phases: [0, 1, 3, 4, 5],
        recommended: false,
        endpoint: 'Load balancer IP or domain',
        features: ['Talos Linux', 'Argo CD', 'KAI Scheduler', 'High Availability'],
        advanced: true,
    },
    {
        id: 'custom',
        name: '⚙️ Custom Deployment',
        description: 'Select individual phases and components. For experts.',
        phases: [],
        recommended: false,
        endpoint: 'Varies',
        features: ['Phase Selection', 'Component Control', 'Testing & Debugging'],
        advanced: true,
    },
];

function renderDeploymentCards() {
    const container = document.getElementById('deployment-cards');
    if (!container) return;
    container.innerHTML = '';

    profiles.forEach(profile => {
        const card = document.createElement('div');
        card.className = 'deployment-card';
        if (profile.recommended) card.classList.add('recommended');
        if (profile.advanced) card.classList.add('advanced');
        card.dataset.id = profile.id;

        const badge = profile.recommended
            ? '<span class="badge badge-recommended">Recommended</span>'
            : profile.advanced
            ? '<span class="badge badge-advanced">Advanced</span>'
            : '';

        card.innerHTML = `
            <div class="card-header">
                <h4>${profile.name}</h4>
                ${badge}
            </div>
            <p class="card-description">${profile.description}</p>
            <div class="card-endpoint">
                📍 Access: ${profile.endpoint}
            </div>
            <ul class="card-features">
                ${profile.features.map(f => `<li>✓ ${f}</li>`).join('')}
            </ul>
        `;

        card.addEventListener('click', () => {
            document.querySelectorAll('.deployment-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedProfile = profile.id;
            document.getElementById('btn-install-next').disabled = false;

            // Show custom phase picker if custom is selected
            if (profile.id === 'custom') {
                document.getElementById('custom-phases').style.display = 'block';
                renderPhasePicker();
            } else {
                document.getElementById('custom-phases').style.display = 'none';
                // Pre-select phases for the profile
                selectedPhases = profile.phases;
                updatePhaseSummary(profile);
            }
        });

        container.appendChild(card);
    });

    // Set default selection
    const defaultCard = container.querySelector('.deployment-card.recommended');
    if (defaultCard) {
        defaultCard.click();
    }
}

function renderPhasePicker() {
    const container = document.getElementById('phase-picker');
    if (!container) return;

    const phases = [
        { id: 0, name: 'System Preparation & Hardening', desc: 'Docker, UFW, WireGuard, SSH hardening', time: '5-10 min' },
        { id: 1, name: 'Development Environment (MANDATORY)', desc: 'Python venv, pip, uv, dependencies', time: '2-5 min', mandatory: true },
        { id: 2, name: 'Single-VM Deployment', desc: 'NVIDIA Dynamo, llama.cpp, Docker Compose', time: '10-20 min' },
        { id: 3, name: 'Kubernetes Scaling', desc: 'Talos Linux, Argo CD, KAI Scheduler', time: '15-30 min' },
        { id: 4, name: 'Module Installation', desc: 'Odoo modules (nettrades_core, etc.)', time: '3-5 min' },
        { id: 5, name: 'Monitoring Setup', desc: 'Prometheus, Grafana', time: '3-5 min' },
    ];

    container.innerHTML = phases.map(phase => `
        <div class="phase-item">
            <label class="phase-label ${phase.mandatory ? 'mandatory' : ''}">
                <input type="checkbox"
                       name="phase-${phase.id}"
                       ${phase.mandatory ? 'checked disabled' : 'checked'}
                       data-phase="${phase.id}">
                <span class="phase-name">${phase.name}</span>
                ${phase.mandatory ? '<span class="phase-mandatory">(Required)</span>' : ''}
                <span class="phase-time">⏱ ${phase.time}</span>
            </label>
            <div class="phase-desc">${phase.desc}</div>
        </div>
    `).join('');

    // Add event listeners for checkboxes
    container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            const id = parseInt(cb.dataset.phase);
            if (cb.checked) {
                if (!selectedPhases.includes(id)) selectedPhases.push(id);
            } else {
                selectedPhases = selectedPhases.filter(p => p !== id);
            }
            updatePhaseSummary(null);
        });
    });

    // Ensure Phase 1 is always selected
    if (!selectedPhases.includes(1)) {
        selectedPhases.push(1);
    }

    updatePhaseSummary(null);
}

function updatePhaseSummary(profile) {
    const summary = document.getElementById('config-summary');
    if (!summary) return;

    let profileName = 'Custom';
    let phases = selectedPhases;

    if (profile) {
        const p = profiles.find(pr => pr.id === profile.id);
        profileName = p ? p.name : 'Custom';
        phases = profile.phases || selectedPhases;
    }

    // Sort phases
    phases.sort((a, b) => a - b);

    summary.innerHTML = `
        <div class="config-row">
            <strong>Profile:</strong> ${profileName}
        </div>
        <div class="config-row">
            <strong>Phases:</strong> ${phases.join(' → ')}
        </div>
        <div class="config-row">
            <strong>Environment:</strong> <span id="config-env">Development</span>
        </div>
        <div class="config-row" style="color:var(--text-muted);font-size:0.85rem;margin-top:0.5rem;">
            Phase 1 (venv) is always included as it's required by all other phases.
        </div>
    `;

    // Store selected phases for installation
    installOptions.phases = phases;
}

// ──────────────────────────────────────────────────────────────────────────────
// Installation Wizard – Step Navigation
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-install-next').addEventListener('click', () => {
    if (!selectedProfile) return;

    // Show step 2 (modules and summary)
    document.getElementById('install-step-1').classList.remove('active');
    document.getElementById('install-step-2').classList.add('active');

    // Update module recommendations based on hardware
    updateModuleRecommendations();

    // Update summary
    const profile = profiles.find(p => p.id === selectedProfile);
    updatePhaseSummary(profile);
});

document.getElementById('btn-install-back').addEventListener('click', () => {
    document.getElementById('install-step-2').classList.remove('active');
    document.getElementById('install-step-1').classList.add('active');
});

// ──────────────────────────────────────────────────────────────────────────────
// Installation Wizard – Module Selection
// ──────────────────────────────────────────────────────────────────────────────

function updateModuleRecommendations() {
    const hardware = detectedHardware;
    if (!hardware) return;

    // Fine-Tuning recommendation
    const finetuneLabel = document.querySelector('.module-finetune');
    if (finetuneLabel) {
        if (hardware.gpuAvailable) {
            finetuneLabel.innerHTML = `
                ☑ Fine‑Tuning (Unsloth/Axolotl) <span class="recommended-badge">Recommended</span>
                <span class="module-desc">Train and fine-tune models on your GPUs.</span>
            `;
        } else {
            finetuneLabel.innerHTML = `
                ☐ Fine‑Tuning (Unsloth/Axolotl) <span class="warning-text">(requires GPU)</span>
                <span class="module-desc">Train and fine-tune models on your GPUs.</span>
            `;
        }
    }

    // KAI Scheduler recommendation
    const kaiLabel = document.querySelector('.module-kai');
    if (kaiLabel) {
        if (hardware.k8sDetected) {
            kaiLabel.innerHTML = `
                ☑ KAI Scheduler <span class="recommended-badge">Recommended</span>
                <span class="module-desc">GPU scheduling for Kubernetes clusters.</span>
            `;
        } else {
            kaiLabel.innerHTML = `
                ☐ KAI Scheduler <span class="warning-text">(requires Kubernetes)</span>
                <span class="module-desc">GPU scheduling for Kubernetes clusters.</span>
            `;
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Installation Wizard – Start Installation
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-install-start').addEventListener('click', async () => {
    // Gather options
    const environment = document.querySelector('input[name="env"]:checked')?.value || 'development';
    const force = document.getElementById('force-checkbox')?.checked || false;
    const auto = document.getElementById('auto-checkbox')?.checked || false;
    const upgrade = document.getElementById('upgrade-checkbox')?.checked || false;

    const withFinetune = document.querySelector('input[name="module-finetune"]')?.checked || false;
    const withGrove = document.querySelector('input[name="module-grove"]')?.checked || false;
    const withKai = document.querySelector('input[name="module-kai"]')?.checked || false;
    const withRouter = document.querySelector('input[name="module-router"]')?.checked || false;

    const domain = document.getElementById('domain-input')?.value || '';

    // Validate domain for production
    if (environment === 'production' && !domain) {
        const result = await window.api.showDialog({
            type: 'warning',
            title: 'Domain Required',
            message: 'For production deployments, please enter a domain name.',
            buttons: ['OK'],
        });
        return;
    }

    const options = {
        profile: selectedProfile,
        environment: environment,
        force: force,
        auto: auto,
        upgrade: upgrade,
        withFinetune: withFinetune,
        withGrove: withGrove,
        withKai: withKai,
        withRouter: withRouter,
        domain: domain,
        phases: selectedPhases.length > 0 ? selectedPhases : null,
        resetData: false,
    };

    installOptions = options;

    // Switch to installation progress view
    document.getElementById('install-step-2').classList.remove('active');
    document.getElementById('install-step-3').classList.add('active');

    const progressFill = document.getElementById('install-progress-fill');
    const progressLabel = document.getElementById('install-progress-label');
    const logOutput = document.getElementById('install-log-output');

    if (logOutput) logOutput.innerHTML = '<div class="log-placeholder">Starting installation...</div>';

    isInstalling = true;
    document.getElementById('btn-install-cancel').style.display = 'inline-block';
    document.getElementById('install-status-badge').textContent = '⏳ Installing...';
    document.getElementById('install-status-badge').className = 'status-badge status-unknown';

    window.api.onInstallOutput((data) => {
        // Update progress based on output
        if (data.includes('Phase 0')) {
            if (progressFill) progressFill.style.width = '10%';
            if (progressLabel) progressLabel.textContent = 'Phase 0: System Preparation...';
        } else if (data.includes('Phase 1')) {
            if (progressFill) progressFill.style.width = '30%';
            if (progressLabel) progressLabel.textContent = 'Phase 1: Environment Setup...';
        } else if (data.includes('Phase 2')) {
            if (progressFill) progressFill.style.width = '50%';
            if (progressLabel) progressLabel.textContent = 'Phase 2: Deployment...';
        } else if (data.includes('Phase 3')) {
            if (progressFill) progressFill.style.width = '70%';
            if (progressLabel) progressLabel.textContent = 'Phase 3: Kubernetes...';
        } else if (data.includes('Phase 4')) {
            if (progressFill) progressFill.style.width = '85%';
            if (progressLabel) progressLabel.textContent = 'Phase 4: Module Installation...';
        } else if (data.includes('Phase 5')) {
            if (progressFill) progressFill.style.width = '95%';
            if (progressLabel) progressLabel.textContent = 'Phase 5: Monitoring Setup...';
        } else if (data.includes('Setup Complete')) {
            if (progressFill) progressFill.style.width = '100%';
            if (progressLabel) progressLabel.textContent = '✅ Installation complete!';
        }

        // Append to log
        if (logOutput) {
            const lines = logOutput.textContent.split('\n');
            lines.push(data);
            if (lines.length > 200) lines.splice(0, lines.length - 200);
            logOutput.textContent = lines.join('\n');
            logOutput.scrollTop = logOutput.scrollHeight;
        }

        // Also add to global logs
        const globalLogs = document.getElementById('logs-output');
        if (globalLogs) {
            const placeholder = globalLogs.querySelector('.log-placeholder');
            if (placeholder) placeholder.remove();
            globalLogs.textContent += data + '\n';
            globalLogs.scrollTop = globalLogs.scrollHeight;
        }
    });

    try {
        await window.api.runInstall(options);
        isInstalling = false;
        document.getElementById('btn-install-cancel').style.display = 'none';
        if (progressFill) progressFill.style.width = '100%';
        if (progressLabel) progressLabel.textContent = '✅ Installation complete!';
        document.getElementById('install-status-badge').textContent = '✅ Complete';
        document.getElementById('install-status-badge').className = 'status-badge status-running';
        updateDashboard();
    } catch (err) {
        isInstalling = false;
        document.getElementById('btn-install-cancel').style.display = 'none';
        if (progressFill) {
            progressFill.style.width = '100%';
            progressFill.style.background = 'var(--danger)';
        }
        if (progressLabel) progressLabel.textContent = '❌ Installation failed';
        if (logOutput) {
            logOutput.textContent += `\n\n❌ Error: ${err.output || err.message || 'Unknown error'}`;
        }
        document.getElementById('install-status-badge').textContent = '❌ Failed';
        document.getElementById('install-status-badge').className = 'status-badge status-stopped';
    }
});

document.getElementById('btn-install-cancel').addEventListener('click', async () => {
    if (isInstalling) {
        const result = await window.api.cancelInstall();
        if (result.success) {
            isInstalling = false;
            document.getElementById('btn-install-cancel').style.display = 'none';
            document.getElementById('install-progress-label').textContent = '⏹ Installation cancelled';
            const logOutput = document.getElementById('install-log-output');
            if (logOutput) logOutput.textContent += '\n\n⏹ Installation cancelled.';
            document.getElementById('install-status-badge').textContent = '⏹ Cancelled';
        }
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Environment toggle
// ──────────────────────────────────────────────────────────────────────────────

document.querySelectorAll('input[name="env"]').forEach(radio => {
    radio.addEventListener('change', () => {
        const isProduction = radio.value === 'production';
        const domainInput = document.getElementById('domain-input');
        if (domainInput) {
            domainInput.style.display = isProduction ? 'inline-block' : 'none';
            domainInput.required = isProduction;
        }
        document.getElementById('config-env').textContent = isProduction ? 'Production' : 'Development';
    });
});

// ──────────────────────────────────────────────────────────────────────────────
// Model Manager
// ──────────────────────────────────────────────────────────────────────────────

async function loadModels() {
    const grid = document.getElementById('model-grid');
    if (!grid) return;

    try {
        const models = await window.api.listModels();
        if (models.length === 0) {
            grid.innerHTML = `
                <div class="model-empty">
                    <p>No models found. Download or import a model to get started.</p>
                    <button class="btn btn-primary" id="btn-browse-models">📥 Browse Models</button>
                    <button class="btn btn-secondary" id="btn-import-model">📂 Import Model</button>
                </div>
            `;
            // Re-bind events
            document.getElementById('btn-browse-models')?.addEventListener('click', browseModels);
            document.getElementById('btn-import-model')?.addEventListener('click', importModel);
            return;
        }

        grid.innerHTML = models.map(model => `
            <div class="model-card">
                <div class="model-icon">🧠</div>
                <div class="model-name">${model.name}</div>
                <div class="model-size">${model.sizeFormatted}</div>
                <div class="model-actions">
                    <button class="btn btn-success" data-path="${model.path}" onclick="window.loadModel('${model.path}')">▶ Load</button>
                    <button class="btn btn-danger" data-path="${model.path}" onclick="window.deleteModel('${model.path}')">🗑️ Delete</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        grid.innerHTML = `<p class="model-error">Error loading models: ${e.message}</p>`;
    }
}

async function browseModels() {
    const searchTerm = prompt('Search for a model on Hugging Face (e.g., "llama", "qwen"):');
    if (!searchTerm) return;

    addActivity(`Searching for models matching "${searchTerm}"...`);

    // In production, this would use the Hugging Face API
    // For now, we'll show a demo list
    const demoModels = [
        { name: `llama-3.2-1B-Q4_K_M.gguf`, url: 'https://huggingface.co/...' },
        { name: `qwen-2.5-1.5B-Q4_K_M.gguf`, url: 'https://huggingface.co/...' },
        { name: `deepseek-r1-1.5B-Q4_K_M.gguf`, url: 'https://huggingface.co/...' },
    ];

    const modelList = demoModels.map(m => `${m.name}`).join('\n');
    const selection = prompt(`Available models:\n${modelList}\n\nEnter the full model name to download:`);
    if (selection) {
        downloadModel(selection);
    }
}

async function downloadModel(filename) {
    addActivity(`Downloading model: ${filename}...`);
    const progressBar = document.getElementById('download-progress-bar');
    const progressLabel = document.getElementById('download-progress-label');
    const progressContainer = document.getElementById('download-progress');
    if (progressContainer) progressContainer.style.display = 'block';
    if (progressBar) progressBar.style.width = '0%';
    if (progressLabel) progressLabel.textContent = 'Starting download...';

    // In production, this would call window.api.downloadModel()
    // with the actual Hugging Face URL
    // Simulate download progress
    let progress = 0;
    const interval = setInterval(() => {
        progress += 5;
        if (progressBar) progressBar.style.width = `${Math.min(progress, 100)}%`;
        if (progressLabel) progressLabel.textContent = `Downloading... ${Math.min(progress, 100)}%`;
        if (progress >= 100) {
            clearInterval(interval);
            if (progressLabel) progressLabel.textContent = '✅ Download complete!';
            addActivity(`Model downloaded: ${filename}`);
            loadModels();
            setTimeout(() => {
                if (progressContainer) progressContainer.style.display = 'none';
            }, 3000);
        }
    }, 200);
}

async function importModel() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.gguf';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        addActivity(`Importing model: ${file.name}...`);
        try {
            // In production, this would use window.api.importModel()
            // For now, we'll simulate
            await new Promise(resolve => setTimeout(resolve, 1000));
            addActivity(`Model imported: ${file.name}`);
            loadModels();
        } catch (err) {
            addActivity(`Failed to import model: ${err.message}`);
        }
    };
    input.click();
}

// Global functions for onclick handlers
window.loadModel = async function(modelPath) {
    addActivity(`Loading model: ${modelPath.split('/').pop()}...`);
    try {
        const result = await window.api.loadModel(modelPath);
        if (result.success) {
            addActivity(`Model loaded: ${modelPath.split('/').pop()}`);
        } else {
            addActivity(`Failed to load model: ${result.error}`);
        }
    } catch (e) {
        addActivity(`Error loading model: ${e.message}`);
    }
};

window.deleteModel = async function(modelPath) {
    const confirmResult = await window.api.showDialog({
        type: 'warning',
        title: 'Delete Model',
        message: `Are you sure you want to delete ${modelPath.split('/').pop()}?`,
        buttons: ['Cancel', 'Delete'],
        defaultId: 0,
        cancelId: 0,
    });
    if (confirmResult.response !== 1) return;

    addActivity(`Deleting model: ${modelPath.split('/').pop()}...`);
    try {
        const result = await window.api.deleteModel(modelPath);
        if (result.success) {
            addActivity(`Model deleted: ${modelPath.split('/').pop()}`);
            loadModels();
        } else {
            addActivity(`Failed to delete model: ${result.error}`);
        }
    } catch (e) {
        addActivity(`Error deleting model: ${e.message}`);
    }
};

// ──────────────────────────────────────────────────────────────────────────────
// Backup & Restore
// ──────────────────────────────────────────────────────────────────────────────

async function loadBackupList() {
    const container = document.getElementById('backup-list-container');
    const select = document.getElementById('backup-select');

    if (!container || !select) return;

    try {
        const backups = await window.api.listBackups();

        // Update select
        select.innerHTML = '<option value="">Select a backup...</option>';
        backups.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b.path;
            const date = new Date(b.modified);
            opt.textContent = `${b.name} (${date.toLocaleString()}, ${formatSize(b.size)})`;
            select.appendChild(opt);
        });

        // Update list
        if (backups.length === 0) {
            container.innerHTML = '<p class="backup-empty">No backups found. Create your first backup using the button above.</p>';
            return;
        }

        container.innerHTML = backups.map(b => {
            const date = new Date(b.modified);
            return `
                <div class="backup-item">
                    <span class="backup-name">${b.name}</span>
                    <span class="backup-date">${date.toLocaleString()}</span>
                    <span class="backup-size">${formatSize(b.size)}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        container.innerHTML = `<p class="backup-empty">Error loading backups: ${e.message}</p>`;
    }
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

document.getElementById('btn-create-backup').addEventListener('click', async () => {
    const logOutput = document.getElementById('backup-log-output');
    if (logOutput) {
        logOutput.style.display = 'block';
        logOutput.innerHTML = '<div class="log-placeholder">Starting backup...</div>';
    }

    const statusBadge = document.getElementById('backup-status-badge');
    if (statusBadge) {
        statusBadge.textContent = '⏳ Backing up...';
        statusBadge.className = 'status-badge status-unknown';
    }

    window.api.onBackupOutput((data) => {
        if (logOutput) {
            const lines = logOutput.textContent.split('\n');
            lines.push(data);
            if (lines.length > 100) lines.splice(0, lines.length - 100);
            logOutput.textContent = lines.join('\n');
            logOutput.scrollTop = logOutput.scrollHeight;
        }
    });

    try {
        await window.api.createBackup({ auto: true });
        if (statusBadge) {
            statusBadge.textContent = '✅ Backup complete';
            statusBadge.className = 'status-badge status-running';
        }
        await loadBackupList();
        updateDashboard();
    } catch (err) {
        if (statusBadge) {
            statusBadge.textContent = '❌ Backup failed';
            statusBadge.className = 'status-badge status-stopped';
        }
        if (logOutput) {
            logOutput.textContent += `\n\n❌ Error: ${err.output || err.message || 'Unknown error'}`;
        }
    }
});

document.getElementById('btn-restore-backup').addEventListener('click', async () => {
    const select = document.getElementById('backup-select');
    const backupPath = select ? select.value : null;

    if (!backupPath) {
        await window.api.showDialog({
            type: 'warning',
            title: 'No Backup Selected',
            message: 'Please select a backup to restore.',
            buttons: ['OK'],
        });
        return;
    }

    const confirmResult = await window.api.showDialog({
        type: 'warning',
        title: 'Confirm Restore',
        message: 'This will overwrite ALL current data! Are you sure you want to continue?',
        buttons: ['Cancel', 'Restore'],
        defaultId: 0,
        cancelId: 0,
    });

    if (confirmResult.response !== 1) return;

    const logOutput = document.getElementById('backup-log-output');
    if (logOutput) {
        logOutput.style.display = 'block';
        logOutput.innerHTML = '<div class="log-placeholder">Starting restore...</div>';
    }

    const statusBadge = document.getElementById('backup-status-badge');
    if (statusBadge) {
        statusBadge.textContent = '⏳ Restoring...';
        statusBadge.className = 'status-badge status-unknown';
    }

    window.api.onRestoreOutput((data) => {
        if (logOutput) {
            const lines = logOutput.textContent.split('\n');
            lines.push(data);
            if (lines.length > 100) lines.splice(0, lines.length - 100);
            logOutput.textContent = lines.join('\n');
            logOutput.scrollTop = logOutput.scrollHeight;
        }
    });

    try {
        await window.api.restoreBackup(backupPath);
        if (statusBadge) {
            statusBadge.textContent = '✅ Restore complete';
            statusBadge.className = 'status-badge status-running';
        }
        updateDashboard();
    } catch (err) {
        if (statusBadge) {
            statusBadge.textContent = '❌ Restore failed';
            statusBadge.className = 'status-badge status-stopped';
        }
        if (logOutput) {
            logOutput.textContent += `\n\n❌ Error: ${err.output || err.message || 'Unknown error'}`;
        }
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Quick Actions (Dashboard)
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-quick-backup').addEventListener('click', () => {
    switchTab('backup');
    document.getElementById('btn-create-backup').click();
});

document.getElementById('btn-quick-restore').addEventListener('click', () => {
    switchTab('backup');
});

// Service launchers with dynamic URLs
document.getElementById('btn-open-odoo').addEventListener('click', () => {
    window.api.openService('odoo');
});

document.getElementById('btn-open-grafana').addEventListener('click', () => {
    window.api.openService('grafana');
});

document.getElementById('btn-open-llama').addEventListener('click', () => {
    window.api.openService('llama');
});

document.getElementById('btn-open-ui').addEventListener('click', () => {
    window.api.openService('ui');
});

// ──────────────────────────────────────────────────────────────────────────────
// Platform Control
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-start-platform').addEventListener('click', async () => {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    if (statusBadge) {
        statusBadge.textContent = '⏳ Starting...';
        statusBadge.className = 'status-badge status-unknown';
    }

    try {
        window.api.onPlatformOutput((data) => {
            addActivity(`[Platform] ${data.trim()}`);
        });

        const result = await window.api.startPlatform();
        if (result.success) {
            if (statusBadge) {
                statusBadge.textContent = '✅ Running';
                statusBadge.className = 'status-badge status-running';
            }
            if (statusText) statusText.textContent = 'Running';
            addActivity('Platform started successfully');
        } else {
            throw new Error('Failed to start');
        }
    } catch (e) {
        if (statusBadge) {
            statusBadge.textContent = '❌ Failed to start';
            statusBadge.className = 'status-badge status-stopped';
        }
        if (statusText) statusText.textContent = 'Error';
        addActivity(`Failed to start platform: ${e.message}`);
        console.error(e);
    }
});

document.getElementById('btn-stop-platform').addEventListener('click', async () => {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    if (statusBadge) {
        statusBadge.textContent = '⏳ Stopping...';
        statusBadge.className = 'status-badge status-unknown';
    }

    try {
        const result = await window.api.stopPlatform();
        if (result.success) {
            if (statusBadge) {
                statusBadge.textContent = '⏹ Stopped';
                statusBadge.className = 'status-badge status-stopped';
            }
            if (statusText) statusText.textContent = 'Stopped';
            addActivity('Platform stopped successfully');
        } else {
            throw new Error('Failed to stop');
        }
    } catch (e) {
        if (statusBadge) {
            statusBadge.textContent = '❌ Failed to stop';
            statusBadge.className = 'status-badge status-stopped';
        }
        if (statusText) statusText.textContent = 'Error';
        addActivity(`Failed to stop platform: ${e.message}`);
        console.error(e);
    }
});

document.getElementById('btn-restart-platform').addEventListener('click', async () => {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    if (statusBadge) {
        statusBadge.textContent = '⏳ Restarting...';
        statusBadge.className = 'status-badge status-unknown';
    }

    try {
        const result = await window.api.restartPlatform();
        if (result.success) {
            if (statusBadge) {
                statusBadge.textContent = '✅ Running';
                statusBadge.className = 'status-badge status-running';
            }
            if (statusText) statusText.textContent = 'Running';
            addActivity('Platform restarted successfully');
        } else {
            throw new Error('Failed to restart');
        }
    } catch (e) {
        if (statusBadge) {
            statusBadge.textContent = '❌ Failed to restart';
            statusBadge.className = 'status-badge status-stopped';
        }
        if (statusText) statusText.textContent = 'Error';
        addActivity(`Failed to restart platform: ${e.message}`);
        console.error(e);
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Logs Tab
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-copy-logs').addEventListener('click', () => {
    const logs = document.getElementById('logs-output');
    if (!logs) return;
    const text = logs.textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('btn-copy-logs');
        if (btn) {
            const originalText = btn.textContent;
            btn.textContent = '✅ Copied!';
            setTimeout(() => { btn.textContent = originalText; }, 2000);
        }
    }).catch(() => {});
});

document.getElementById('btn-save-logs').addEventListener('click', () => {
    const logs = document.getElementById('logs-output');
    if (!logs) return;
    const text = logs.textContent;
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nettrades-logs-${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
});

document.getElementById('btn-clear-logs').addEventListener('click', () => {
    const logs = document.getElementById('logs-output');
    if (logs) {
        logs.innerHTML = '<div class="log-placeholder">Logs cleared.</div>';
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Settings
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('settings-github-link').addEventListener('click', (e) => {
    e.preventDefault();
    window.api.openUrl('https://github.com/nettrades/nettrades-platform');
});

// Server URL settings
document.getElementById('btn-save-server-url').addEventListener('click', async () => {
    const input = document.getElementById('server-url');
    if (!input) return;
    const url = input.value.trim();
    if (url) {
        const result = await window.api.saveServerUrl(url);
        if (result.success) {
            serverUrl = url;
            addActivity(`Server URL saved: ${url}`);
            // Show success feedback
            const btn = document.getElementById('btn-save-server-url');
            if (btn) {
                const originalText = btn.textContent;
                btn.textContent = '✅ Saved!';
                setTimeout(() => { btn.textContent = originalText; }, 2000);
            }
        } else {
            addActivity(`Failed to save server URL: ${result.error}`);
        }
    } else {
		// Reset to default
        serverUrl = 'http://localhost';
        await window.api.saveServerUrl('http://localhost');
        addActivity('Server URL reset to localhost');
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// VPN Management
// ──────────────────────────────────────────────────────────────────────────────

async function loadVPNUsers() {
    const container = document.getElementById('vpn-list-container');
    if (!container) return;

    try {
        const data = await window.api.vpnListUsers();
        if (data.users.length === 0) {
            container.innerHTML = '<p class="vpn-empty">No VPN users found. Add your first admin above.</p>';
            return;
        }

        container.innerHTML = data.users.map(user => `
            <div class="vpn-item">
                <div class="vpn-item-info">
                    <span class="vpn-item-name">${user.name}</span>
                    <span class="vpn-item-ip">${user.assigned_ip}</span>
                    <span class="vpn-item-status ${user.is_online ? 'online' : 'offline'}">
                        ${user.is_online ? '🟢 Online' : '🔴 Offline'}
                    </span>
                </div>
                <div class="vpn-item-actions">
                    <button class="btn btn-secondary" onclick="window.vpnConfig('${user.name}')">📄 Config</button>
                    <button class="btn btn-danger" onclick="window.vpnRevoke('${user.name}')">🗑️ Revoke</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<p class="vpn-empty">Error loading VPN users: ${err.message}</p>`;
    }
}

window.vpnConfig = function(name) {
    window.api.showDialog({
        type: 'info',
        title: `VPN Config: ${name}`,
        message: `Configuration for ${name} will be displayed here.`,
        buttons: ['Close'],
    });
};

window.vpnRevoke = async function(name) {
    const confirmResult = await window.api.showDialog({
        type: 'warning',
        title: 'Revoke VPN User',
        message: `Are you sure you want to revoke ${name}?`,
        buttons: ['Cancel', 'Revoke'],
        defaultId: 0,
        cancelId: 0,
    });
    if (confirmResult.response !== 1) return;

    try {
        const result = await window.api.vpnRevokeUser(name);
        if (result.success) {
            addActivity(`VPN user revoked: ${name}`);
            loadVPNUsers();
        } else {
            addActivity(`Failed to revoke user: ${result.error}`);
        }
    } catch (err) {
        addActivity(`Error revoking user: ${err.message}`);
    }
};

document.getElementById('btn-vpn-create').addEventListener('click', async () => {
    const nameInput = document.getElementById('vpn-new-name');
    const partnerInput = document.getElementById('vpn-new-partner');
    const name = nameInput ? nameInput.value.trim() : '';
    const partnerId = partnerInput ? parseInt(partnerInput.value.trim()) : NaN;

    if (!name || isNaN(partnerId)) {
        await window.api.showDialog({
            type: 'warning',
            title: 'Invalid Input',
            message: 'Please enter a name and partner ID.',
            buttons: ['OK'],
        });
        return;
    }

    try {
        const result = await window.api.vpnAddUser(name, partnerId);
        if (result.success) {
            addActivity(`VPN user created: ${name} (IP: ${result.assigned_ip})`);
            const resultDiv = document.getElementById('vpn-create-result');
            if (resultDiv) {
                resultDiv.style.display = 'block';
                document.getElementById('vpn-new-ip').textContent = result.assigned_ip;
            }
            loadVPNUsers();
            nameInput.value = '';
            partnerInput.value = '';
        } else {
            addActivity(`Failed to create user: ${result.error}`);
        }
    } catch (err) {
        addActivity(`Error creating user: ${err.message}`);
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Activity Log
// ──────────────────────────────────────────────────────────────────────────────

function addActivity(message) {
    const container = document.getElementById('activity-log');
    if (!container) return;

    const empty = container.querySelector('.activity-empty');
    if (empty) empty.remove();

    const entry = document.createElement('p');
    entry.textContent = `• ${new Date().toLocaleTimeString()} - ${message}`;
    container.appendChild(entry);

    // Keep last 20 entries
    while (container.children.length > 20) {
        container.removeChild(container.firstChild);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Initialize
// ──────────────────────────────────────────────────────────────────────────────

async function init() {
    await loadPlatformInfo();
    await loadFeatureFlags();
    await loadServerUrl();
    await updateDashboard();
    await loadBackupList();
    await detectHardware();

    addActivity('Launcher started');

    // Set up periodic dashboard refresh
    setInterval(updateDashboard, 30000);
    setInterval(detectHardware, 60000);

    // Add log listener to capture all output
    window.api.onInstallOutput((data) => {
        const logs = document.getElementById('logs-output');
        if (logs) {
            const placeholder = logs.querySelector('.log-placeholder');
            if (placeholder) placeholder.remove();
            logs.textContent += data + '\n';
            logs.scrollTop = logs.scrollHeight;
        }
        // Also add to activity if it's a significant event
        if (data.includes('SUCCESS') || data.includes('ERROR') || data.includes('WARNING')) {
            addActivity(data.trim());
        }
    });
    // Platform output listener
    window.api.onPlatformOutput((data) => {
        addActivity(`[Platform] ${data.trim()}`);
    });

    // Enable upgrade tab if deployment exists
    const hasDeployment = document.querySelector('.phase-marker-check')?.value === 'true';
    if (hasDeployment) {
        document.querySelector('.nav-item[data-tab="upgrade"]')?.classList.remove('disabled');
    }

    addActivity('Platform ready');
}

// Start the app
init();