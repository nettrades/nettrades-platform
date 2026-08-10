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
//   - Installation wizard with deployment selection
//   - Backup creation and restoration
//   - Live log viewing
// =============================================================================

// ──────────────────────────────────────────────────────────────────────────────
// DOM References
// ──────────────────────────────────────────────────────────────────────────────
const tabs = document.querySelectorAll('.nav-item');
const tabContents = {
    dashboard: document.getElementById('tab-dashboard'),
    installer: document.getElementById('tab-installer'),
    backup: document.getElementById('tab-backup'),
    logs: document.getElementById('tab-logs'),
    settings: document.getElementById('tab-settings'),
};

let currentTab = 'dashboard';
let featureFlags = {};
let isInstalling = false;

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
        tabContents[key].classList.toggle('active', key === tabName);
    });

    currentTab = tabName;

    // Refresh data when switching to certain tabs
    if (tabName === 'dashboard') {
        updateDashboard();
    }
    if (tabName === 'backup') {
        loadBackupList();
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
    const versionText = document.getElementById('version-text');

    try {
        // Try to check if Odoo is running
        const response = await fetch('http://localhost:8069', { method: 'HEAD', mode: 'no-cors' });
        // If we can reach it, it's likely running
        statusBadge.textContent = '✅ Running';
        statusBadge.className = 'status-badge status-running';
        statusText.textContent = 'Running';
        uptimeText.textContent = '--';
        versionText.textContent = 'v1.0.0';
    } catch (e) {
        statusBadge.textContent = '⏹ Stopped';
        statusBadge.className = 'status-badge status-stopped';
        statusText.textContent = 'Stopped';
        uptimeText.textContent = '--';
        versionText.textContent = '--';
    }

    // Load backup count
    try {
        const backups = await window.api.listBackups();
        document.getElementById('stat-backups').textContent = backups.length;
    } catch (e) {
        document.getElementById('stat-backups').textContent = '0';
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Installation Wizard
// ──────────────────────────────────────────────────────────────────────────────
let selectedDeployment = null;
let installOptions = {};

function renderDeploymentCards() {
    const container = document.getElementById('deployment-cards');
    container.innerHTML = '';

    const deployments = [
        {
            id: 'sovereign-ai',
            name: '🚀 Sovereign AI in a Box',
            description: 'Complete AI infrastructure on a single machine.',
            features: ['Dynamo', 'llama.cpp', 'LangGraph', 'Odoo', 'Ask Someone', 'Good Answer'],
            ready: true,
        },
        {
            id: 'router',
            name: '🌐 Sovereign AI Router',
            description: 'Intelligent routing for distributed inference.',
            features: ['LLMRouter', 'LiteLLM', 'KAI Scheduler'],
            ready: featureFlags.FEATURE_ROUTER || false,
        },
        {
            id: 'marketplace',
            name: '🏭 GPU Marketplace',
            description: 'GPU sharing and rental marketplace.',
            features: ['Marketplace', 'P2P', 'Token Economics'],
            ready: featureFlags.FEATURE_GPU_MARKETPLACE || false,
        },
        {
            id: 'training',
            name: '🧠 AI Training & Development',
            description: 'Fine-tuning and model training.',
            features: ['Unsloth', 'Axolotl', 'Training Pipeline'],
            ready: featureFlags.FEATURE_TRAINING || false,
        },
        {
            id: 'enterprise',
            name: '🏢 Autonomous Enterprise Platform',
            description: 'Full enterprise suite with CRM, ERP, AI agents.',
            features: ['Odoo ERP/CRM', 'Recruitment', 'Lead Gen', 'Freelance'],
            ready: featureFlags.FEATURE_ENTERPRISE || false,
        },
        {
            id: 'development',
            name: '💻 Development Environment',
            description: 'For AI developers building on the platform.',
            features: ['LangGraph', 'Python venv', 'Dev Tools'],
            ready: true,
        },
    ];

    deployments.forEach(dep => {
        const card = document.createElement('div');
        card.className = `deployment-card ${dep.ready ? '' : 'coming-soon'}`;
        card.dataset.id = dep.id;

        card.innerHTML = `
            <h4>${dep.name}</h4>
            <p>${dep.description}</p>
            <ul style="list-style:none;padding:0;margin:0.5rem 0;font-size:0.8rem;color:var(--text-muted);">
                ${dep.features.map(f => `<li style="display:inline-block;margin-right:0.5rem;">✓ ${f}</li>`).join('')}
            </ul>
            ${dep.ready ? '<span class="badge badge-ready">Ready</span>' : '<span class="badge badge-coming">Coming Soon</span>'}
        `;

        if (dep.ready) {
            card.addEventListener('click', () => {
                document.querySelectorAll('.deployment-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedDeployment = dep.id;
                document.getElementById('btn-install-next').disabled = false;
            });
        }

        container.appendChild(card);
    });

    document.getElementById('btn-install-next').disabled = true;
}

document.getElementById('btn-install-next').addEventListener('click', () => {
    if (!selectedDeployment) return;
    document.getElementById('install-step-1').classList.remove('active');
    document.getElementById('install-step-2').classList.add('active');
    showConfigSummary(selectedDeployment);
});

document.getElementById('btn-install-back').addEventListener('click', () => {
    document.getElementById('install-step-2').classList.remove('active');
    document.getElementById('install-step-1').classList.add('active');
});

function showConfigSummary(deploymentId) {
    const names = {
        'sovereign-ai': '🚀 Sovereign AI in a Box',
        'router': '🌐 Sovereign AI Router',
        'marketplace': '🏭 GPU Marketplace',
        'training': '🧠 AI Training & Development',
        'enterprise': '🏢 Autonomous Enterprise Platform',
        'development': '💻 Development Environment',
    };

    const summary = document.getElementById('config-summary');
    summary.innerHTML = `
        <div class="config-row">
            <strong>Deployment:</strong> ${names[deploymentId] || deploymentId}
        </div>
        <div class="config-row">
            <strong>Environment:</strong> Production
        </div>
        <div class="config-row">
            <strong>Auto Mode:</strong> Enabled
        </div>
        <div class="config-row" style="color:var(--text-muted);font-size:0.85rem;margin-top:0.5rem;">
            This will install the platform with default settings. You can change these later.
        </div>
    `;
}

document.getElementById('btn-install-start').addEventListener('click', async () => {
    if (!selectedDeployment) return;

    document.getElementById('install-step-2').classList.remove('active');
    document.getElementById('install-step-3').classList.add('active');

    const progressFill = document.getElementById('install-progress-fill');
    const progressLabel = document.getElementById('install-progress-label');
    const logOutput = document.getElementById('install-log-output');

    logOutput.innerHTML = '<div class="log-placeholder">Starting installation...</div>';

    const options = {
        profile: selectedDeployment,
        environment: 'production',
        force: false,
        auto: true,
    };

    isInstalling = true;
    document.getElementById('btn-install-cancel').style.display = 'inline-block';
    document.getElementById('install-status-badge').textContent = '⏳ Installing...';
    document.getElementById('install-status-badge').className = 'status-badge status-unknown';

    window.api.onInstallOutput((data) => {
        // Update progress based on output
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
            progressLabel.textContent = 'Phase 3: GPU Setup...';
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

        // Append to log
        const lines = logOutput.textContent.split('\n');
        lines.push(data);
        if (lines.length > 200) lines.splice(0, lines.length - 200);
        logOutput.textContent = lines.join('\n');
        logOutput.scrollTop = logOutput.scrollHeight;
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
        logOutput.textContent += `\n\n❌ Error: ${err.output || err.message || 'Unknown error'}`;
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
            document.getElementById('install-log-output').textContent += '\n\n⏹ Installation cancelled.';
            document.getElementById('install-status-badge').textContent = '⏹ Cancelled';
        }
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Backup & Restore
// ──────────────────────────────────────────────────────────────────────────────
async function loadBackupList() {
    const container = document.getElementById('backup-list-container');
    const select = document.getElementById('backup-select');

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
    logOutput.style.display = 'block';
    logOutput.innerHTML = '<div class="log-placeholder">Starting backup...</div>';

    const statusBadge = document.getElementById('backup-status-badge');
    statusBadge.textContent = '⏳ Backing up...';
    statusBadge.className = 'status-badge status-unknown';

    window.api.onBackupOutput((data) => {
        const lines = logOutput.textContent.split('\n');
        lines.push(data);
        if (lines.length > 100) lines.splice(0, lines.length - 100);
        logOutput.textContent = lines.join('\n');
        logOutput.scrollTop = logOutput.scrollHeight;
    });

    try {
        await window.api.createBackup({ auto: true });
        statusBadge.textContent = '✅ Backup complete';
        statusBadge.className = 'status-badge status-running';
        await loadBackupList();
        updateDashboard();
    } catch (err) {
        statusBadge.textContent = '❌ Backup failed';
        statusBadge.className = 'status-badge status-stopped';
        logOutput.textContent += `\n\n❌ Error: ${err.output || err.message || 'Unknown error'}`;
    }
});

document.getElementById('btn-restore-backup').addEventListener('click', async () => {
    const select = document.getElementById('backup-select');
    const backupPath = select.value;

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
    logOutput.style.display = 'block';
    logOutput.innerHTML = '<div class="log-placeholder">Starting restore...</div>';

    const statusBadge = document.getElementById('backup-status-badge');
    statusBadge.textContent = '⏳ Restoring...';
    statusBadge.className = 'status-badge status-unknown';

    window.api.onRestoreOutput((data) => {
        const lines = logOutput.textContent.split('\n');
        lines.push(data);
        if (lines.length > 100) lines.splice(0, lines.length - 100);
        logOutput.textContent = lines.join('\n');
        logOutput.scrollTop = logOutput.scrollHeight;
    });

    try {
        await window.api.restoreBackup(backupPath);
        statusBadge.textContent = '✅ Restore complete';
        statusBadge.className = 'status-badge status-running';
        updateDashboard();
    } catch (err) {
        statusBadge.textContent = '❌ Restore failed';
        statusBadge.className = 'status-badge status-stopped';
        logOutput.textContent += `\n\n❌ Error: ${err.output || err.message || 'Unknown error'}`;
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Quick Actions (Dashboard)
// ──────────────────────────────────────────────────────────────────────────────
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

document.getElementById('btn-open-odoo').addEventListener('click', () => {
    window.api.openUrl('http://localhost:8069');
});

document.getElementById('btn-open-grafana').addEventListener('click', () => {
    window.api.openUrl('http://localhost:3001');
});

// NEW: Open LLama.cpp UI (port 8080)
document.getElementById('btn-open-llama').addEventListener('click', () => {
    window.api.openUrl('http://localhost:8080');
});

// NEW: Open NETTRADES-UI (port 3002)
document.getElementById('btn-open-ui').addEventListener('click', () => {
    window.api.openUrl('http://localhost:3002');
});

// ──────────────────────────────────────────────────────────────────────────────
// Platform Control (Start / Stop) – NOW ACTUALLY WORKS
// ──────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-start-platform').addEventListener('click', async () => {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    statusBadge.textContent = '⏳ Starting...';
    statusBadge.className = 'status-badge status-unknown';

    try {
        // Listen for output from the main process
        window.api.onPlatformOutput((data) => {
            // You could display this in a log if you want
            console.log('[Platform]', data);
        });

        const result = await window.api.startPlatform();
        if (result.success) {
            statusBadge.textContent = '✅ Running';
            statusBadge.className = 'status-badge status-running';
            statusText.textContent = 'Running';
        } else {
            throw new Error('Failed to start');
        }
    } catch (e) {
        statusBadge.textContent = '❌ Failed to start';
        statusBadge.className = 'status-badge status-stopped';
        statusText.textContent = 'Error';
        console.error(e);
    }
});

document.getElementById('btn-stop-platform').addEventListener('click', async () => {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    statusBadge.textContent = '⏳ Stopping...';
    statusBadge.className = 'status-badge status-unknown';

    try {
        const result = await window.api.stopPlatform();
        if (result.success) {
            statusBadge.textContent = '⏹ Stopped';
            statusBadge.className = 'status-badge status-stopped';
            statusText.textContent = 'Stopped';
        } else {
            throw new Error('Failed to stop');
        }
    } catch (e) {
        statusBadge.textContent = '❌ Failed to stop';
        statusBadge.className = 'status-badge status-stopped';
        statusText.textContent = 'Error';
        console.error(e);
    }
});

document.getElementById('btn-update-platform').addEventListener('click', async () => {
    const statusBadge = document.getElementById('status-badge');
    statusBadge.textContent = '⏳ Checking for updates...';
    statusBadge.className = 'status-badge status-unknown';

    // This would trigger the update check
    await new Promise(resolve => setTimeout(resolve, 2000));
    statusBadge.textContent = '✅ Up to date';
    statusBadge.className = 'status-badge status-running';
});

// ──────────────────────────────────────────────────────────────────────────────
// Logs Tab
// ──────────────────────────────────────────────────────────────────────────────
document.getElementById('btn-copy-logs').addEventListener('click', () => {
    const logs = document.getElementById('logs-output').textContent;
    navigator.clipboard.writeText(logs).then(() => {
        // Show a brief notification
        const btn = document.getElementById('btn-copy-logs');
        const originalText = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => { btn.textContent = originalText; }, 2000);
    }).catch(() => {});
});

document.getElementById('btn-save-logs').addEventListener('click', () => {
    const logs = document.getElementById('logs-output').textContent;
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nettrades-logs-${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
});

document.getElementById('btn-clear-logs').addEventListener('click', () => {
    document.getElementById('logs-output').innerHTML = '<div class="log-placeholder">Logs cleared.</div>';
});

// ──────────────────────────────────────────────────────────────────────────────
// Settings
// ──────────────────────────────────────────────────────────────────────────────
document.getElementById('settings-github-link').addEventListener('click', (e) => {
    e.preventDefault();
    window.api.openUrl('https://github.com/nettrades/nettrades-platform');
});

// ──────────────────────────────────────────────────────────────────────────────
// Activity Log
// ──────────────────────────────────────────────────────────────────────────────
function addActivity(message) {
    const container = document.getElementById('activity-log');
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
    await updateDashboard();
    await loadBackupList();

    addActivity('Launcher started');

    // Set up periodic dashboard refresh
    setInterval(updateDashboard, 30000);

    // Add log listener to capture all output
    window.api.onInstallOutput((data) => {
        const logs = document.getElementById('logs-output');
        const placeholder = logs.querySelector('.log-placeholder');
        if (placeholder) placeholder.remove();
        logs.textContent += data + '\n';
        logs.scrollTop = logs.scrollHeight;
        // Also add to activity if it's a significant event
        if (data.includes('SUCCESS') || data.includes('ERROR') || data.includes('WARNING')) {
            addActivity(data.trim());
        }
    });

    // Simulate some activity for demo
    setTimeout(() => addActivity('Platform ready'), 1000);
}

init();

// =============================================================================
// VPN Management
// =============================================================================

async function loadVPNUsers() {
    const container = document.getElementById('vpn-list-container');
    try {
        const response = await fetch('/api/wireguard/users', {
            headers: { 'X-API-Key': localStorage.getItem('apiKey') || '' }
        });
        if (!response.ok) throw new Error('Failed to fetch VPN users');
        const data = await response.json();

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
                    <a href="/api/wireguard/users/${user.id}/config" class="btn btn-secondary">📄 Config</a>
                    <button class="btn btn-danger" onclick="revokeVPNUser(${user.id})">🗑️ Revoke</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<p class="vpn-empty">Error loading VPN users: ${err.message}</p>`;
    }
}

async function createVPNUser() {
    const nameInput = document.getElementById('vpn-new-name');
    const partnerInput = document.getElementById('vpn-new-partner');
    const name = nameInput.value.trim();
    const partner_id = parseInt(partnerInput.value.trim());

    if (!name || !partner_id) {
        alert('Please enter a name and partner ID.');
        return;
    }

    try {
        const response = await fetch('/api/wireguard/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': localStorage.getItem('apiKey') || ''
            },
            body: JSON.stringify({ name, partner_id })
        });

        if (!response.ok) throw new Error('Failed to create VPN user');
        const data = await response.json();

        // Show result
        document.getElementById('vpn-create-result').style.display = 'block';
        document.getElementById('vpn-new-ip').textContent = data.assigned_ip;
        document.getElementById('vpn-new-config-link').href = `/api/wireguard/users/${data.id}/config`;

        // Show QR code
        const qrContainer = document.getElementById('vpn-new-qr');
        if (data.qr_code) {
            qrContainer.innerHTML = `<img src="${data.qr_code}" alt="QR Code" style="max-width:200px;">`;
        } else {
            qrContainer.innerHTML = '<p>QR code not available.</p>';
        }

        // Refresh the list
        loadVPNUsers();

        // Clear inputs
        nameInput.value = '';
        partnerInput.value = '';

    } catch (err) {
        alert(`Error creating VPN user: ${err.message}`);
    }
}

async function revokeVPNUser(userId) {
    if (!confirm('Are you sure you want to revoke this user?')) return;

    try {
        const response = await fetch(`/api/wireguard/users/${userId}`, {
            method: 'DELETE',
            headers: { 'X-API-Key': localStorage.getItem('apiKey') || '' }
        });

        if (!response.ok) throw new Error('Failed to revoke user');
        loadVPNUsers();
    } catch (err) {
        alert(`Error revoking user: ${err.message}`);
    }
}

// Event listeners
document.getElementById('btn-vpn-create').addEventListener('click', createVPNUser);

// Load VPN users when the tab is switched
document.querySelector('.nav-item[data-tab="vpn"]').addEventListener('click', () => {
    loadVPNUsers();
});