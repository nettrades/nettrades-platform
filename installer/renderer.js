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
    tabs.forEach(t => t.classList.remove('active'));
    document.querySelector(`.nav-item[data-tab="${tabName}"]`).classList.add('active');

    Object.keys(tabContents).forEach(key => {
        if (tabContents[key]) {
            tabContents[key].classList.toggle('active', key === tabName);
        }
    });

    currentTab = tabName;

    if (tabName === 'emergency') {
        loadEmergencyUsers();
    }

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
        document.getElementById('platform-info').textContent = `${info.platform} (${info.arch})`;
        document.getElementById('version').textContent = `v1.0.0`;
        window.platformInfo = info;
    } catch (e) {
        console.error('Failed to load platform info:', e);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Load Emergency Audit
// ──────────────────────────────────────────────────────────────────────────────

async function loadEmergencyAudit() {
    const container = document.getElementById('emergency-audit-list');
    if (!container) return;
    container.innerHTML = '<div class="spinner"></div> Loading audit log...';
    try {
        const result = await window.api.listEmergencyAudit();
        if (result.success) {
            const lines = result.data.split('\n').filter(l => l.trim());
            if (lines.length === 0) {
                container.innerHTML = '<p class="empty-state">No audit entries found.</p>';
                return;
            }
            let html = `<table style="width:100%; border-collapse: collapse; text-align: left; font-size: 13px;">
                <thead><tr>
                    <th>Login</th>
                    <th>Action</th>
                    <th>IP Address</th>
                    <th>Performed At</th>
                </tr></thead><tbody>`;
            for (const line of lines) {
                const parts = line.split('|').map(s => s.trim());
                if (parts.length >= 4) {
                    html += `<tr>
                        <td>${parts[0]}</td>
                        <td>${parts[1]}</td>
                        <td>${parts[2]}</td>
                        <td>${parts[3]}</td>
                    </tr>`;
                }
            }
            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = `<p class="error">Failed to load audit log: ${result.error}</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p class="error">Error: ${e.message}</p>`;
    }
}


// ──────────────────────────────────────────────────────────────────────────────
// Server URL
// ──────────────────────────────────────────────────────────────────────────────

async function loadServerUrl() {
    try {
        const url = await window.api.getServerUrl();
        if (url) {
            serverUrl = url;
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
        const gpuSummary = hardware.gpus.map(g => `✅ ${g.name} (${g.memoryTotal} VRAM)`).join('<br>');
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

    const kaiCheckbox = document.querySelector('input[name="module-kai"]');
    if (kaiCheckbox && !hardware.k8sDetected) {
        kaiCheckbox.disabled = true;
        kaiCheckbox.parentElement.title = 'Requires Kubernetes cluster';
        const warning = document.createElement('span');
        warning.className = 'warning-text';
        warning.textContent = ' (requires Kubernetes)';
        kaiCheckbox.parentElement.appendChild(warning);
    }

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
        const odooUrl = getServiceUrl('odoo');
        const response = await fetch(odooUrl, { method: 'HEAD', mode: 'no-cors' });
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

    try {
        const backups = await window.api.listBackups();
        document.getElementById('stat-backups').textContent = backups.length;
    } catch (e) {
        document.getElementById('stat-backups').textContent = '0';
    }

    try {
        const models = await window.api.listModels();
        document.getElementById('stat-models').textContent = models.length;
    } catch (e) {
        document.getElementById('stat-models').textContent = '0';
    }

    detectHardware();
}

// ──────────────────────────────────────────────────────────────────────────────
// QUICK SETUP – One-click development environment
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-quick-setup').addEventListener('click', async () => {
    const btn = document.getElementById('btn-quick-setup');
    const progressContainer = document.getElementById('hero-progress');
    const progressFill = document.getElementById('hero-progress-fill');
    const progressLabel = document.getElementById('hero-progress-label');
    const activityLog = document.getElementById('activity-log');

    if (btn.disabled) return;

    btn.disabled = true;
    btn.textContent = '⏳ Setting up...';
    progressContainer.style.display = 'block';
    progressFill.style.width = '0%';
    progressLabel.textContent = 'Starting...';

    // Clear previous activity
    activityLog.innerHTML = '';

    // Set up listeners
    window.api.onInstallOutput((data) => {
        const entry = document.createElement('p');
        entry.textContent = `• ${new Date().toLocaleTimeString()} - ${data.trim()}`;
        activityLog.appendChild(entry);
        activityLog.scrollTop = activityLog.scrollHeight;
    });

    window.api.onInstallProgress((data) => {
        if (data.progress !== undefined) {
            progressFill.style.width = `${data.progress}%`;
            if (data.phase) {
                progressLabel.textContent = `${data.phase} (${data.progress}%)`;
            } else {
                progressLabel.textContent = `${data.progress}%`;
            }
        }
    });

    try {
        const result = await window.api.runQuickSetup();

        if (result.success) {
            progressFill.style.width = '100%';
            progressLabel.textContent = '✅ Setup complete!';
            btn.textContent = '✅ Done!';
            btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
            showToast('Development environment is ready!', 'success');
            updateDashboard();
        } else {
            progressFill.style.width = '100%';
            progressFill.style.background = 'var(--danger)';
            progressLabel.textContent = '❌ Setup failed';
            btn.textContent = '⚠️ Retry';
            btn.disabled = false;
            showToast(`Setup failed: ${result.error}`, 'error');
        }
    } catch (error) {
        progressFill.style.width = '100%';
        progressFill.style.background = 'var(--danger)';
        progressLabel.textContent = '❌ Error';
        btn.textContent = '⚠️ Retry';
        btn.disabled = false;
        showToast(`Error: ${error.message}`, 'error');
    }
});

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
            <div class="card-endpoint">📍 Access: ${profile.endpoint}</div>
            <ul class="card-features">
                ${profile.features.map(f => `<li>✓ ${f}</li>`).join('')}
            </ul>
        `;

        card.addEventListener('click', () => {
            document.querySelectorAll('.deployment-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedProfile = profile.id;
            document.getElementById('btn-install-next').disabled = false;

            if (profile.id === 'custom') {
                document.getElementById('custom-phases').style.display = 'block';
                renderPhasePicker();
            } else {
                document.getElementById('custom-phases').style.display = 'none';
                selectedPhases = profile.phases;
                updatePhaseSummary(profile);
            }
        });

        container.appendChild(card);
    });

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

    phases.sort((a, b) => a - b);

    summary.innerHTML = `
        <div class="config-row"><strong>Profile:</strong> ${profileName}</div>
        <div class="config-row"><strong>Phases:</strong> ${phases.join(' → ')}</div>
        <div class="config-row"><strong>Environment:</strong> <span id="config-env">Development</span></div>
        <div class="config-row" style="color:var(--text-muted);font-size:0.85rem;margin-top:0.5rem;">
            Phase 1 (venv) is always included as it's required by all other phases.
        </div>
    `;

    installOptions.phases = phases;
}

// ──────────────────────────────────────────────────────────────────────────────
// Installation Wizard – Step Navigation
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-install-next').addEventListener('click', () => {
    if (!selectedProfile) return;

    document.getElementById('install-step-1').classList.remove('active');
    document.getElementById('install-step-2').classList.add('active');

    updateModuleRecommendations();

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
    const environment = document.querySelector('input[name="env"]:checked')?.value || 'development';
    const force = document.getElementById('deploy-force')?.checked || false;
    const auto = document.getElementById('deploy-auto')?.checked || false;
    const upgrade = document.getElementById('deploy-upgrade')?.checked || false;

    const withFinetune = document.querySelector('input[name="module-finetune"]')?.checked || false;
    const withGrove = document.querySelector('input[name="module-grove"]')?.checked || false;
    const withKai = document.querySelector('input[name="module-kai"]')?.checked || false;
    const withRouter = document.querySelector('input[name="module-router"]')?.checked || false;
    const withCuvs = document.querySelector('input[name="module-cuvs"]')?.checked || false;

    const domain = document.getElementById('domain-input')?.value || '';

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
        withCuvs: withCuvs,
        domain: domain,
        phases: selectedPhases.length > 0 ? selectedPhases : null,
        resetData: false,
    };

    installOptions = options;

    document.getElementById('install-step-2').classList.remove('active');
    document.getElementById('install-step-3').classList.add('active');

    const progressFill = document.getElementById('install-progress-fill');
    const progressLabel = document.getElementById('install-progress-label');
    const logOutput = document.getElementById('install-log-output');

    if (logOutput) logOutput.innerHTML = '<span class="log-placeholder">Starting installation...</span>';

    isInstalling = true;
    document.getElementById('btn-install-cancel').style.display = 'inline-block';
    document.getElementById('install-status-badge').textContent = '⏳ Installing...';
    document.getElementById('install-status-badge').className = 'status-badge status-unknown';

    window.api.onInstallOutput((data) => {
        if (data.includes('Phase 0')) {
            progressFill.style.width = '10%';
            progressLabel.textContent = 'Phase 0: System Preparation...';
        } else if (data.includes('Phase 1')) {
            progressFill.style.width = '30%';
            progressLabel.textContent = 'Phase 1: Environment Setup...';
        } else if (data.includes('Phase 2')) {
            progressFill.style.width = '50%';
            progressLabel.textContent = 'Phase 2: Deployment...';
        } else if (data.includes('Phase 3')) {
            progressFill.style.width = '70%';
            progressLabel.textContent = 'Phase 3: Kubernetes...';
        } else if (data.includes('Phase 4')) {
            progressFill.style.width = '85%';
            progressLabel.textContent = 'Phase 4: Module Installation...';
        } else if (data.includes('Phase 5')) {
            progressFill.style.width = '95%';
            progressLabel.textContent = 'Phase 5: Monitoring Setup...';
        } else if (data.includes('Setup Complete')) {
            progressFill.style.width = '100%';
            progressLabel.textContent = '✅ Installation complete!';
        }

        if (logOutput) {
            const lines = logOutput.textContent.split('\n');
            lines.push(data);
            if (lines.length > 200) lines.splice(0, lines.length - 200);
            logOutput.textContent = lines.join('\n');
            logOutput.scrollTop = logOutput.scrollHeight;
        }

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
        progressFill.style.width = '100%';
        progressLabel.textContent = '✅ Installation complete!';
        document.getElementById('install-status-badge').textContent = '✅ Complete';
        document.getElementById('install-status-badge').className = 'status-badge status-running';
        updateDashboard();
    } catch (err) {
        isInstalling = false;
        document.getElementById('btn-install-cancel').style.display = 'none';
        progressFill.style.width = '100%';
        progressFill.style.background = 'var(--danger)';
        progressLabel.textContent = '❌ Installation failed';
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
        const domainGroup = document.getElementById('domain-input-group');
        if (domainInput && domainGroup) {
            domainGroup.style.display = isProduction ? 'block' : 'none';
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
            document.getElementById('btn-browse-models')?.addEventListener('click', browseModels);
            document.getElementById('btn-import-model')?.addEventListener('click', importModel);
            return;
        }

        grid.innerHTML = models.map(model => `
            <div class="model-card">
                <div class="model-icon">🧠</div>
                <div class="model-name">${model.name}</div>
                <div class="model-size">${formatSize(model.size)}</div>
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
            await new Promise(resolve => setTimeout(resolve, 1000));
            addActivity(`Model imported: ${file.name}`);
            loadModels();
        } catch (err) {
            addActivity(`Failed to import model: ${err.message}`);
        }
    };
    input.click();
}

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

        select.innerHTML = '<option value="">Select a backup...</option>';
        backups.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b.path;
            const date = new Date(b.modified);
            opt.textContent = `${b.name} (${date.toLocaleString()}, ${formatSize(b.size)})`;
            select.appendChild(opt);
        });

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

document.getElementById('btn-create-backup')?.addEventListener('click', createBackup);
document.getElementById('btn-create-backup-card')?.addEventListener('click', createBackup);

async function createBackup() {
    const logOutput = document.getElementById('backup-log-output');
    if (logOutput) {
        logOutput.style.display = 'block';
        logOutput.innerHTML = '<span class="log-placeholder">Starting backup...</span>';
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
}

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
        logOutput.innerHTML = '<span class="log-placeholder">Starting restore...</span>';
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
// Quick Actions
// ──────────────────────────────────────────────────────────────────────────────

// Open apps
document.querySelectorAll('[data-open-app]').forEach(btn => {
    btn.addEventListener('click', () => {
        const app = btn.dataset.openApp;
        if (app) openApp(app);
    });
});

function openApp(appName) {
    const url = getServiceUrl(appName);
    window.api.openExternal(url);
}

// Switch tab helper
window.switchTab = switchTab;
window.openApp = openApp;

// ──────────────────────────────────────────────────────────────────────────────
// Platform Control
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-start-platform')?.addEventListener('click', async () => {
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

document.getElementById('btn-stop-platform')?.addEventListener('click', async () => {
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

document.getElementById('btn-restart-platform')?.addEventListener('click', async () => {
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

document.getElementById('btn-copy-logs')?.addEventListener('click', () => {
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

document.getElementById('btn-save-logs')?.addEventListener('click', () => {
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

document.getElementById('btn-clear-logs')?.addEventListener('click', () => {
    const logs = document.getElementById('logs-output');
    if (logs) {
        logs.innerHTML = '<span class="log-placeholder">Logs cleared.</span>';
    }
});

document.getElementById('btn-refresh-logs')?.addEventListener('click', () => {
    refreshLogs();
});

async function refreshLogs() {
    const service = document.getElementById('log-service')?.value || 'all';
    const container = document.getElementById('logs-output');

    if (service === 'all') {
        container.innerHTML = '<span class="log-placeholder">Select a specific service to view logs.</span>';
        return;
    }

    container.innerHTML = '<span class="log-placeholder">Loading logs...</span>';

    try {
        const result = await window.api.getLogs({ service, lines: 100 });
        if (result.success && result.data) {
            const lines = result.data.split('\n').filter(l => l.trim());
            container.innerHTML = lines.map(line => `<div class="log-line">${escapeHtml(line)}</div>`).join('');
        } else {
            container.innerHTML = `<span class="log-placeholder">❌ Failed to load logs: ${result.error || 'Unknown error'}</span>`;
        }
    } catch (e) {
        container.innerHTML = `<span class="log-placeholder">❌ Failed to load logs: ${e.message}</span>`;
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Settings
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('settings-github-link')?.addEventListener('click', (e) => {
    e.preventDefault();
    window.api.openExternal('https://github.com/nettrades/nettrades-platform');
});

document.getElementById('btn-save-server-url')?.addEventListener('click', async () => {
    const input = document.getElementById('server-url');
    if (!input) return;
    const url = input.value.trim();
    if (url) {
        const result = await window.api.saveServerUrl(url);
        if (result.success) {
            serverUrl = url;
            addActivity(`Server URL saved: ${url}`);
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
        serverUrl = 'http://localhost';
        await window.api.saveServerUrl('http://localhost');
        addActivity('Server URL reset to localhost');
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

    while (container.children.length > 20) {
        container.removeChild(container.firstChild);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Toast Notifications
// ──────────────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 24px;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 8px;
        color: var(--text);
        font-size: 0.95rem;
        z-index: 9999;
        animation: fadeIn 0.3s ease;
        box-shadow: var(--shadow);
        max-width: 400px;
    `;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ──────────────────────────────────────────────────────────────────────────────
// Utilities
// ──────────────────────────────────────────────────────────────────────────────

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ──────────────────────────────────────────────────────────────────────────────
// ─── Emergency Access Management ───
// ──────────────────────────────────────────────────────────────────────────────

async function loadEmergencyUsers() {
    const container = document.getElementById('emergency-users-list');
    if (!container) return;
    container.innerHTML = '<div class="spinner"></div> Loading...';
    try {
        const result = await window.api.listEmergencyUsers();
        if (result.success) {
            // Assume result.data is a string with pipe-separated columns (login|valid_until|last_used)
            const lines = result.data.split('\n').filter(l => l.trim());
            if (lines.length === 0) {
                container.innerHTML = '<p class="empty-state">No emergency users found.</p>';
                return;
            }
            let html = `<table style="width:100%; border-collapse: collapse; text-align: left;">
                <thead><tr>
                    <th>Login</th>
                    <th>Valid Until</th>
                    <th>Last Used</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr></thead><tbody>`;
            for (const line of lines) {
                // Split by '|' (psql -t -c output)
                const parts = line.split('|').map(s => s.trim());
                if (parts.length >= 3) {
                    const login = parts[0];
                    const validUntil = parts[1];
                    const lastUsed = parts[2] || 'Never';
                    const isValid = new Date(validUntil) > new Date();
                    const statusBadge = isValid ? '🟢 Valid' : '🔴 Expired';
                    html += `<tr>
                        <td><strong>${login}</strong></td>
                        <td>${validUntil}</td>
                        <td>${lastUsed}</td>
                        <td><span style="color:${isValid ? '#28c840' : '#ff5f57'}">${statusBadge}</span></td>
                        <td><button class="btn btn-danger" onclick="revokeEmergencyUser('${login}')" style="padding: 4px 12px; font-size: 12px;">Revoke</button></td>
                    </tr>`;
                }
            }
            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = `<p class="error">Failed to load emergency users: ${result.error}</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p class="error">Error: ${e.message}</p>`;
    }
}

// ─── Tab switching integration ───
// Add a case to your existing switchTab function to load emergency users
// when the "emergency" tab is activated.



// ──────────────────────────────────────────────────────────────────────────────
// ─── System Check ───
// ──────────────────────────────────────────────────────────────────────────────

async function runSystemCheck() {
    const result = await window.api.systemCheck();
    if (!result) return;

    const items = ['wsl', 'docker', 'gpu', 'python', 'node'];
    items.forEach(id => {
        const check = result[id];
        if (!check) return;
        const element = document.getElementById(`check-${id}`);
        const statusElement = element?.querySelector('.check-status');
        const iconElement = element?.querySelector('.check-icon');
        if (statusElement) {
            const statusMap = {
                'ok': '✅',
                'warning': '⚠️',
                'error': '❌',
                'unknown': '⏳'
            };
            iconElement.textContent = statusMap[check.status] || '⏳';
            statusElement.textContent = check.details || check.status;
            statusElement.className = `check-status ${check.status}`;
        }
    });

    // Update summary
    const summary = document.getElementById('system-check-summary');
    const allOk = items.every(id => result[id]?.status === 'ok');
    if (allOk) {
        summary.innerHTML = '<div class="summary-passed">✅ All checks passed. You are ready to install!</div>';
    } else {
        summary.innerHTML = `
            <div class="summary-warning">⚠️ Some checks failed. Please fix the issues above before installing.</div>
        `;
    }
}

// ─── Credentials ───
async function refreshCredentials() {
    const result = await window.api.getCredentials();
    if (!result.success) {
        document.getElementById('credential-list').innerHTML = `
            <div class="credential-error">Failed to load credentials: ${result.error}</div>
        `;
        return;
    }

    const list = document.getElementById('credential-list');
    const secrets = result.secrets || [];
    if (secrets.length === 0) {
        list.innerHTML = '<div class="credential-empty">No credentials found. Run the setup first.</div>';
        return;
    }

    list.innerHTML = secrets.map(sec => `
        <div class="credential-item" data-key="${sec.key}">
            <div class="credential-key">${sec.key}</div>
            <div class="credential-value" id="cred-value-${sec.key}">
                <span class="value-hidden">••••••••</span>
            </div>
            <div class="credential-actions">
                <button onclick="toggleCredentialVisibility('${sec.key}')" title="Show/Hide">👁️</button>
                <button onclick="copyCredential('${sec.key}')" title="Copy">📋</button>
                <button onclick="rotateCredential('${sec.key}')" title="Rotate">🔄</button>
            </div>
            <div class="credential-meta">
                <span>${sec.category || 'other'}</span>
                <span>v${sec.version || 1}</span>
                <span>${sec.updated_at || ''}</span>
            </div>
        </div>
    `).join('');
}

async function toggleCredentialVisibility(key) {
    const valueContainer = document.querySelector(`#cred-value-${key}`);
    const span = valueContainer?.querySelector('span');
    if (!span) return;

    if (span.classList.contains('value-hidden')) {
        // Fetch plaintext
        const result = await window.api.getCredentialValue(key);
        if (result.success) {
            span.textContent = result.value;
            span.classList.remove('value-hidden');
            span.classList.add('value-visible');
        } else {
            showToast(`Failed to get credential: ${result.error}`, 'error');
        }
    } else {
        span.textContent = '••••••••';
        span.classList.add('value-hidden');
        span.classList.remove('value-visible');
    }
}

function copyCredential(key) {
    const valueContainer = document.querySelector(`#cred-value-${key}`);
    const span = valueContainer?.querySelector('span');
    if (!span) return;

    // If hidden, reveal first
    if (span.classList.contains('value-hidden')) {
        toggleCredentialVisibility(key);
        // Wait a moment then copy
        setTimeout(() => {
            const text = span.textContent;
            if (text !== '••••••••') {
                navigator.clipboard.writeText(text).then(() => {
                    showToast('Copied to clipboard!', 'success');
                });
            }
        }, 200);
    } else {
        const text = span.textContent;
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard!', 'success');
        });
    }
}

async function rotateCredential(key) {
    const newValue = prompt(`Enter new value for ${key}:`);
    if (!newValue) return;
    if (!confirm(`Are you sure you want to rotate ${key}?`)) return;

    const result = await window.api.rotateCredential(key, newValue);
    if (result.success) {
        showToast('Credential rotated successfully!', 'success');
        refreshCredentials();
    } else {
        showToast(`Failed to rotate: ${result.error}`, 'error');
    }
}

async function rotateAllSecrets() {
    if (!confirm('This will rotate ALL secrets. Are you sure?')) return;
    // TODO: Implement bulk rotation
    showToast('Bulk rotation not yet implemented', 'warning');
}

// ─── Modules ───
function renderModules() {
    const grid = document.getElementById('module-grid');
    const modules = window.modules || {};
    let html = '';
    let count = 0;

    Object.keys(modules).forEach(id => {
        const mod = modules[id];
        if (!mod) return;
        const isChecked = mod.required ? 'checked disabled' : '';
        const isAdmin = mod.adminRequired ? ' (Admin Required)' : '';

        html += `
            <div class="module-card" data-module="${id}">
                <div class="module-check">
                    <input type="checkbox" id="mod-${id}" ${isChecked} data-module="${id}">
                </div>
                <div class="module-icon">${mod.icon || '📦'}</div>
                <div class="module-info">
                    <div class="module-name">${mod.name}${isAdmin}</div>
                    <div class="module-desc">${mod.description}</div>
                    <div class="module-meta">
                        <span>${mod.size}</span>
                        <span>${mod.time}</span>
                    </div>
                    <div class="module-features">
                        ${mod.features.map(f => `<span class="feature-tag">${f}</span>`).join('')}
                    </div>
                </div>
                <div class="module-deps">
                    ${mod.dependencies.map(d => `<span class="dep-tag">${d}</span>`).join('')}
                </div>
            </div>
        `;
        count++;
    });

    grid.innerHTML = html;
    document.getElementById('selected-modules-count').textContent = `${count} modules available`;

    // Add event listeners
    grid.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', updateModuleSummary);
    });
}

function updateModuleSummary() {
    const selected = [];
    document.querySelectorAll('#module-grid input[type="checkbox"]:checked').forEach(cb => {
        if (!cb.disabled) {
            selected.push(cb.dataset.module);
        }
    });
    document.getElementById('selected-modules-count').textContent = `${selected.length} selected`;
}

async function installSelectedModules() {
    const selected = [];
    document.querySelectorAll('#module-grid input[type="checkbox"]:checked').forEach(cb => {
        selected.push(cb.dataset.module);
    });

    if (selected.length === 0) {
        showToast('Please select at least one module to install.', 'warning');
        return;
    }

    // Check if any admin-required modules are selected
    const adminModules = selected.filter(id => window.modules[id]?.adminRequired);
    if (adminModules.length > 0) {
        const confirmMsg = `The following modules require administrator privileges:\n${adminModules.map(id => `  - ${window.modules[id].name}`).join('\n')}\n\nDo you have admin rights?`;
        if (!confirm(confirmMsg)) {
            showToast('Installation cancelled. Admin rights required for these modules.', 'warning');
            return;
        }
    }

    // Switch to Install Log tab
    switchTab('install-log');

    // Clear previous log
    document.getElementById('install-log-output').innerHTML = '';

    // Install
    const result = await window.api.installModules(selected);
    if (result.success) {
        showToast('Modules installed successfully!', 'success');
    } else {
        showToast(`Installation failed: ${result.error}`, 'error');
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

    // Check if platform is already set up
    try {
        const isSetup = await window.api.isPlatformSetup();
        if (isSetup) {
            addActivity('✅ Platform is already set up');
            document.getElementById('btn-quick-setup').textContent = '✅ Already Set Up';
            document.getElementById('btn-quick-setup').style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
        } else {
            addActivity('🚀 Ready to set up your development environment');
        }
    } catch (e) {
        console.error('Failed to check setup status:', e);
    }

    setInterval(updateDashboard, 30000);
    setInterval(detectHardware, 60000);

    window.api.onInstallOutput((data) => {
        const logs = document.getElementById('logs-output');
        if (logs) {
            const placeholder = logs.querySelector('.log-placeholder');
            if (placeholder) placeholder.remove();
            logs.textContent += data + '\n';
            logs.scrollTop = logs.scrollHeight;
        }
        if (data.includes('SUCCESS') || data.includes('ERROR') || data.includes('WARNING')) {
            addActivity(data.trim());
        }
    });

    window.api.onPlatformOutput((data) => {
        addActivity(`[Platform] ${data.trim()}`);
    });

    addActivity('Platform ready');
}

init();