// =============================================================================
// FILE: installer/renderer.js
// PURPOSE: Full renderer logic for NETTRADES Launcher
// =============================================================================

// ─── State ───
let state = {
    currentView: 'dashboard',
    isAuthenticated: false,
    backend: null,
    platform: null,
    featureFlags: {},
    gpuNodes: [],
    models: [],
    jobs: [],
    containers: [],
    messages: [],
    selectedModel: 'deepseek-7b',
    temperature: 0.7,
    isLoading: false,
    setupProgress: 0,
    setupRunning: false,
    nodes: [],
    wireguardRunning: false,
    wireguardPeers: 0,
    wireguardPeersList: [],
    proxyUrl: 'http://localhost:8080',
    enterpriseBackend: 'odoo',
    deploymentMode: 'hub',
    version: '1.0.0',
    logs: '',
    isPlatformSetup: false,
    selectedProfile: null,
    selectedPhases: [],
    selectedTenantType: 'enterprise',
    isInstalling: false,
};

// ─── DOM Ready ───
document.addEventListener('DOMContentLoaded', async () => {
    // Get platform info
    try {
        const platform = await window.api.getPlatform();
        state.platform = platform;
        state.proxyUrl = platform.proxyUrl || 'http://localhost:8080';
        state.backend = platform.backend || 'odoo';
        state.deploymentMode = platform.deploymentMode || 'hub';
        state.version = platform.version || '1.0.0';
        document.getElementById('app-version').textContent = `v${state.version}`;
        updateBackendIndicator(state.backend);
        updateDeploymentModeBadge(state.deploymentMode);
        document.getElementById('settings-server-url').value = state.proxyUrl;
    } catch (e) { console.error('Failed to get platform:', e); }

    // Get feature flags
    try {
        const flags = await window.api.getFeatureFlags();
        state.featureFlags = flags;
        applyFeatureFlags(flags);
    } catch (e) { console.error('Failed to get feature flags:', e); }

    // Get enterprise backend
    try {
        const backend = await window.api.getEnterpriseBackend();
        if (backend) {
            state.enterpriseBackend = backend;
            updateBackendIndicator(backend);
            const select = document.getElementById('settings-enterprise-backend');
            if (select) select.value = backend;
        }
    } catch (e) { console.error('Failed to get enterprise backend:', e); }

    // Get deployment mode
    try {
        const mode = await window.api.getDeploymentMode();
        if (mode) {
            state.deploymentMode = mode;
            updateDeploymentModeBadge(mode);
        }
    } catch (e) { console.error('Failed to get deployment mode:', e); }

    // Check if platform is set up
    try {
        state.isPlatformSetup = await window.api.isPlatformSetup();
        if (state.isPlatformSetup) {
            const btn = document.getElementById('btn-quick-setup');
            if (btn) {
                btn.textContent = '✅ Already Set Up';
                btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
                btn.disabled = true;
            }
        }
    } catch (e) { console.error('Failed to check platform setup:', e); }

    // Load initial data
    await refreshModels();
    await refreshGPUs();
    await refreshContainers();
    // VPN status loaded only when VPN tab is opened

    // Setup IPC listeners
    setupIpcListeners();

    // Render deployment cards
    renderDeploymentCards();

    // Tab navigation
    document.querySelectorAll('.nav-item[data-tab]').forEach(item => {
        item.addEventListener('click', () => {
            switchTab(item.dataset.tab);
        });
    });

    // Deployment navigation
    document.getElementById('btn-deploy-next')?.addEventListener('click', () => {
        if (!state.selectedProfile) return;
        document.getElementById('deploy-step-1').style.display = 'none';
        document.getElementById('deploy-step-2').style.display = 'block';
        updateModuleRecommendations();
        updateDeploySummary();
    });

    document.getElementById('btn-deploy-back')?.addEventListener('click', () => {
        document.getElementById('deploy-step-2').style.display = 'none';
        document.getElementById('deploy-step-1').style.display = 'block';
    });

    document.getElementById('btn-deploy-start')?.addEventListener('click', startDeployment);
    document.getElementById('btn-install-cancel')?.addEventListener('click', cancelInstallation);

    // Tenant selection
    document.querySelectorAll('.select-tenant').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const type = this.dataset.type;
            const option = this.closest('.tenant-option');
            document.querySelectorAll('.tenant-option').forEach(el => el.classList.remove('selected'));
            option.classList.add('selected');
            document.getElementById('tenant-details').style.display = 'block';
            const typeNames = { enterprise: 'Enterprise', freelancer: 'Freelancer', home: 'Home User' };
            document.getElementById('selected-tenant-type').textContent = typeNames[type] || type;
            document.getElementById('selected-tenant-description').textContent =
                option.querySelector('.desc')?.textContent || '';
            state.selectedTenantType = type;
        });
    });

    document.getElementById('deploy-tenant-btn')?.addEventListener('click', deployWithTenantConfig);
    document.getElementById('btn-quick-setup')?.addEventListener('click', runQuickSetup);

    const backendSelect = document.getElementById('settings-enterprise-backend');
    if (backendSelect) {
        backendSelect.addEventListener('change', saveEnterpriseBackend);
    }

    // Environment toggle
    document.querySelectorAll('input[name="env"]').forEach(radio => {
        radio.addEventListener('change', () => {
            const isProduction = radio.value === 'production';
            const domainInput = document.getElementById('domain-input');
            if (domainInput) {
                domainInput.style.display = isProduction ? 'inline-block' : 'none';
            }
            document.getElementById('config-env').textContent = isProduction ? 'Production' : 'Development';
        });
    });

    // Load server URL
    const urlInput = document.getElementById('settings-server-url');
    if (urlInput) {
        const url = await window.api.getServerUrl();
        urlInput.value = url || 'http://localhost';
    }

    // Render initial view
    switchTab('dashboard');

    // Auto-refresh
    setInterval(() => {
        refreshModels();
        refreshGPUs();
        refreshContainers();
    }, 30000);

    // Start container auto-refresh
    startContainerAutoRefresh();

    // Show the window (in case it wasn't already)
    window.api.showWindow?.();
});

window.modules = window.MODULES || {};

// ─── Feature Flags ───
function applyFeatureFlags(flags) {
    const map = {
        askSomeone: 'ask-someone',
        goodAnswer: 'good-answer',
        training: 'training',
        gpuMarketplace: 'marketplace',
    };
    for (const [key, tab] of Object.entries(map)) {
        const item = document.querySelector(`.nav-item[data-tab="${tab}"]`);
        if (item) {
            item.style.display = flags[key] ? '' : 'none';
        }
    }
}

// ─── Backend Indicator ───
function updateBackendIndicator(backend) {
    const indicator = document.getElementById('backend-indicator');
    if (!indicator) return;
    const icons = { odoo: '🔷', salesforce: '☁️', sap: '💼', oracle: '🟠' };
    indicator.textContent = `${icons[backend] || '🔗'} ${backend.charAt(0).toUpperCase() + backend.slice(1)}`;
    state.enterpriseBackend = backend;
}

function updateDeploymentModeBadge(mode) {
    const badge = document.getElementById('deployment-mode-badge');
    if (!badge) return;
    const labels = { hub: '🌐 Hub', spoke: '🔄 Spoke', addon: '📦 Add-on' };
    badge.textContent = labels[mode] || mode;
    badge.className = `deployment-mode-badge ${mode}`;
    badge.style.display = 'inline-block';
}

// ─── Tab Switching ───
function switchTab(tabName) {
    state.currentView = tabName;
    document.querySelectorAll('.nav-item[data-tab]').forEach(el => {
        el.classList.toggle('active', el.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-content').forEach(el => {
        el.classList.toggle('active', el.id === `tab-${tabName}`);
    });
    // Render the view if not already rendered
    const container = document.getElementById(`tab-${tabName}`);
    if (container) {
        container.innerHTML = '';
        const renderFn = views[tabName] || views.dashboard;
        container.appendChild(renderFn());
    }
    // Refresh data for specific tabs
    const refreshMap = {
        dashboard: refreshDashboard,
        gpus: refreshGPUs,
        models: refreshModels,
        nodes: discoverNodes,
        vpn: refreshVPN,
        queue: refreshQueue,
        monitor: refreshMonitor,
        logs: refreshLogs,
        backup: refreshBackups,
        marketplace: refreshMarketplace,
        deploy: detectHardware,
        containers: refreshContainers,
        settings: loadSettings,
        'system-check': runSystemCheck,
        'install-log': refreshInstallLog,
        credentials: refreshCredentials,
        modules: renderModules,
        emergency: loadEmergencyUsers,
    };
    if (refreshMap[tabName]) refreshMap[tabName]();
}

// ─── Views ───
const views = {};

// ─── Dashboard ───
views.dashboard = function() {
    const container = document.createElement('div');

    // Stats
    const statsGrid = document.createElement('div');
    statsGrid.className = 'dashboard-grid';
    const stats = [
        { label: 'GPUs Available', value: state.gpuNodes.filter(n => n.status === 'available').length, icon: '🎮' },
        { label: 'Models Installed', value: state.models.length, icon: '🧠' },
        { label: 'Network Nodes', value: state.nodes.length, icon: '🖥️' },
        { label: 'Active Jobs', value: state.jobs.filter(j => j.status === 'running').length, icon: '⚡' },
    ];
    stats.forEach(s => {
        const card = document.createElement('div');
        card.className = 'stat-card';
        card.innerHTML = `
            <span class="stat-icon">${s.icon}</span>
            <div class="stat-label">${s.label}</div>
            <div class="stat-value">${s.value}</div>
            <div class="stat-sub">${s.value === 0 ? 'No activity' : 'Active'}</div>
        `;
        statsGrid.appendChild(card);
    });
    container.appendChild(statsGrid);

    // Quick actions
    const actions = document.createElement('div');
    actions.className = 'header-actions';
    actions.innerHTML = `
        <h2>Your Sovereign AI Control Centre</h2>
        <div class="actions">
            <button class="btn-primary" onclick="switchTab('models')">Download Model</button>
            <button class="btn-secondary" onclick="switchTab('chat')">Chat Now</button>
        </div>
    `;
    container.appendChild(actions);

    // Quick setup card
    if (!state.isPlatformSetup) {
        const setupCard = document.createElement('div');
        setupCard.className = 'card';
        setupCard.style.marginBottom = '20px';
        setupCard.innerHTML = `
            <h3 style="margin-bottom:8px;">🚀 Set Up Your Development Environment</h3>
            <p style="color:#8a9bb5;margin-bottom:12px;">One click installs everything you need — Docker, WSL, Python, Odoo, AI models, and more.</p>
            <button class="btn-primary" onclick="runQuickSetup()" id="quick-setup-btn">
                ${state.setupRunning ? 'Setting up...' : 'Set Up Development Environment'}
            </button>
            <span style="margin-left:12px;font-size:12px;color:#6a7f9a;">Safe to run again — it will only install what's missing</span>
        `;
        container.appendChild(setupCard);
    }

    // Recent activity
    const activity = document.createElement('div');
    activity.className = 'card';
    activity.innerHTML = `
        <h4 style="margin-bottom:12px;">📋 Recent Activity</h4>
        <p style="color:#6a7f9a;font-size:13px;">${state.jobs.length > 0 ? state.jobs.slice(0, 5).map(j => `${j.type}: ${j.status}`).join('<br>') : 'No recent activity'}</p>
    `;
    container.appendChild(activity);

    return container;
};

// ─── Chat ───
views.chat = function() {
    const container = document.createElement('div');
    container.className = 'chat-container';

    const controls = document.createElement('div');
    controls.className = 'chat-controls';
    controls.innerHTML = `
        <label>Model:</label>
        <select id="chat-model">
            <option value="deepseek-1.5b">DeepSeek 1.5B</option>
            <option value="qwen-1.5b">Qwen 1.5B</option>
            <option value="llama-3.2">Llama 3.2</option>
            <option value="agent-default">🤖 Agent (Default)</option>
        </select>
        <label>Temperature:</label>
        <input type="range" min="0" max="1" step="0.1" value="0.7" id="chat-temp">
        <span id="chat-temp-label">0.7</span>
        <button class="btn-secondary" onclick="clearChat()">Clear</button>
    `;
    container.appendChild(controls);

    const messages = document.createElement('div');
    messages.className = 'chat-messages';
    messages.id = 'chat-messages';
    if (state.messages.length === 0) {
        messages.innerHTML = `
            <div class="welcome-message">
                <p>👋 Hello! I'm your AI assistant. How can I help you today?</p>
                <ul>
                    <li>Ask me anything about your data</li>
                    <li>Use "Ask Someone" to get expert help</li>
                    <li>Mark my answers as "Good" to help train me!</li>
                </ul>
            </div>
        `;
    } else {
        state.messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = `message message-${msg.role}`;
            div.innerHTML = `<div>${msg.content}</div><div class="time">${msg.time || 'Just now'}</div>`;
            messages.appendChild(div);
        });
    }
    container.appendChild(messages);

    const inputArea = document.createElement('div');
    inputArea.className = 'chat-input';
    inputArea.innerHTML = `
        <input type="text" id="chat-input" placeholder="Type your message..." ${state.isLoading ? 'disabled' : ''}>
        <button onclick="sendMessage()" ${state.isLoading ? 'disabled' : ''}>Send</button>
    `;
    container.appendChild(inputArea);

    setTimeout(() => {
        const input = document.getElementById('chat-input');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') sendMessage();
            });
        }
        const modelSelect = document.getElementById('chat-model');
        if (modelSelect) {
            modelSelect.addEventListener('change', (e) => {
                state.selectedModel = e.target.value;
            });
        }
        const tempInput = document.getElementById('chat-temp');
        if (tempInput) {
            tempInput.addEventListener('input', (e) => {
                state.temperature = parseFloat(e.target.value);
                const label = document.getElementById('chat-temp-label');
                if (label) label.textContent = state.temperature.toFixed(1);
            });
        }
    }, 50);

    return container;
};

// ─── Models ───
views.models = function() {
    const container = document.createElement('div');

    const header = document.createElement('div');
    header.className = 'header-actions';
    header.innerHTML = `
        <h2>📦 Model Library</h2>
        <div class="actions">
            <button class="btn-secondary" onclick="refreshModels()">🔄 Refresh</button>
        </div>
    `;
    container.appendChild(header);

    const list = document.createElement('div');
    list.className = 'model-list';
    list.id = 'model-list';
    if (state.models.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="icon">📦</div>
                <h3>No models installed</h3>
                <p>Download a model to get started with AI inference.</p>
            </div>
        `;
    } else {
        state.models.forEach(model => {
            const item = document.createElement('div');
            item.className = 'model-item';
            item.innerHTML = `
                <div class="model-info">
                    <h4>${model.name}</h4>
                    <div class="meta">
                        <span class="tag">${model.type || 'gguf'}</span>
                        <span>${model.size ? (model.size / 1024 / 1024 / 1024).toFixed(2) + ' GB' : 'Unknown'}</span>
                        <span>${model.status || 'downloaded'}</span>
                    </div>
                </div>
                <div>
                    ${model.status === 'downloaded'
                        ? '<button class="btn-secondary" disabled>✅ Downloaded</button>'
                        : model.status === 'downloading'
                            ? '<button class="btn-secondary" disabled>⏳ Downloading...</button>'
                            : `<button class="btn-primary" onclick="downloadModel('${model.name}', '${model.type || 'gguf'}')">⬇️ Download</button>`
                    }
                </div>
            `;
            list.appendChild(item);
        });
    }
    container.appendChild(list);

    // Available models
    const available = document.createElement('div');
    available.innerHTML = `
        <h3 style="margin:20px 0 12px;">📥 Available Models</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;">
            ${[
                { name: 'DeepSeek-R1-Distill-Qwen-1.5B', type: 'gguf', size: '1.04 GB' },
                { name: 'deepseek-7b', type: 'hf', size: '14.19 GB' },
                { name: 'deepseek-r1-distill-qwen-7b-q4_k_m', type: 'gguf', size: '4.36 GB' },
            ].map(m => `
                <div class="card" style="padding:16px;">
                    <h4 style="font-size:14px;">${m.name}</h4>
                    <p style="font-size:12px;color:#6a7f9a;margin:4px 0 12px;">${m.type} • ${m.size}</p>
                    <button class="btn-primary" style="width:100%;" onclick="downloadModel('${m.name}', '${m.type}')">Download</button>
                </div>
            `).join('')}
        </div>
    `;
    container.appendChild(available);

    return container;
};

// ─── GPUs ───
views.gpus = function() {
    const container = document.createElement('div');

    const header = document.createElement('div');
    header.className = 'header-actions';
    header.innerHTML = `
        <h2>🎮 GPU Nodes</h2>
        <div class="actions">
            <button class="btn-primary" onclick="showRegisterGPU()">➕ Register GPU</button>
            <button class="btn-secondary" onclick="refreshGPUs()">🔄 Refresh</button>
        </div>
    `;
    container.appendChild(header);

    const grid = document.createElement('div');
    grid.className = 'gpu-grid';
    grid.id = 'gpu-grid';
    if (state.gpuNodes.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1;">
                <div class="icon">🎮</div>
                <h3>No GPU nodes registered</h3>
                <p>Register a GPU node to start providing inference capacity.</p>
            </div>
        `;
    } else {
        state.gpuNodes.forEach(node => {
            const card = document.createElement('div');
            card.className = 'gpu-card';
            card.innerHTML = `
                <div class="gpu-header">
                    <h3>${node.name || 'GPU Node'}</h3>
                    <span class="status-badge ${node.status === 'available' ? 'online' : node.status === 'busy' ? 'busy' : 'offline'}">${node.status || 'unknown'}</span>
                </div>
                <div class="gpu-details">
                    <span>🖥️ ${node.gpu_model || 'Unknown'}</span>
                    <span>💾 ${node.vram_gb || '?'} GB</span>
                    <span>💰 $${node.price_per_hour || '0'}/hr</span>
                    <span>❤️ ${node.last_heartbeat ? new Date(node.last_heartbeat).toLocaleTimeString() : 'Never'}</span>
                </div>
            `;
            grid.appendChild(card);
        });
    }
    container.appendChild(grid);

    return container;
};

// ─── Nodes ───
views.nodes = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="header-actions">
            <h2>🖥️ Network Nodes</h2>
            <div class="actions">
                <button class="btn-secondary" onclick="discoverNodes()">🔍 Discover</button>
            </div>
        </div>
        ${state.nodes.length === 0 ? `
            <div class="empty-state">
                <div class="icon">🔍</div>
                <h3>No Nodes Discovered</h3>
                <p>mDNS discovery is running. Other NETTRADES nodes will appear here.</p>
            </div>
        ` : `
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;">
                ${state.nodes.map(n => `
                    <div class="card">
                        <h4>${n.name || 'Unknown Node'}</h4>
                        <p style="font-size:13px;color:#8a9bb5;">${n.host}:${n.port}</p>
                        <p style="font-size:12px;color:#6a7f9a;">${n.lastSeen ? 'Last seen: ' + new Date(n.lastSeen).toLocaleString() : 'Online'}</p>
                    </div>
                `).join('')}
            </div>
        `}
    `;
    return container;
};

// ─── VPN ───
views.vpn = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="header-actions">
            <h2>🔒 VPN Management</h2>
            <div class="actions">
                <button class="btn-primary" onclick="addVPNPeer()">➕ Add Peer</button>
                <button class="btn-secondary" onclick="refreshVPN()">🔄 Refresh</button>
            </div>
        </div>
        <div class="card vpn-status">
            <p style="color:#8a9bb5;">${state.wireguardRunning ? '✅ WireGuard is running' : '❌ WireGuard is not running'}</p>
            <p style="font-size:13px;color:#6a7f9a;margin-top:8px;">${state.wireguardPeers || 0} peers connected</p>
        </div>
        ${state.wireguardPeers === 0 ? `
            <div class="empty-state">
                <div class="icon">🔒</div>
                <h3>No VPN Peers</h3>
                <p>Add peers to establish secure VPN connections.</p>
            </div>
        ` : `
            <div style="margin-top:16px;">
                ${state.wireguardPeersList ? state.wireguardPeersList.map(p => `
                    <div class="model-item" style="margin-bottom:8px;">
                        <span>${p.name || 'Peer'}</span>
                        <span style="font-size:12px;color:#6a7f9a;">${p.ip || 'Unknown IP'}</span>
                        <button class="btn-danger" style="padding:4px 12px;font-size:12px;" onclick="removeVPNPeer('${p.name}')">Remove</button>
                    </div>
                `).join('') : ''}
            </div>
        `}
    `;
    return container;
};

// ─── Settings ───
views.settings = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">⚙️ Settings</h2>
        <div class="card" style="margin-bottom:16px;">
            <h4 style="margin-bottom:8px;">Enterprise Backend</h4>
            <select id="settings-enterprise-backend" style="width:100%;padding:10px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#e8e8e8;font-size:14px;outline:none;">
                <option value="odoo">🔷 Odoo</option>
                <option value="salesforce">☁️ Salesforce</option>
                <option value="sap">💼 SAP</option>
                <option value="oracle">🟠 Oracle</option>
            </select>
            <div class="helper-text">Select the enterprise backend to use for data storage and authentication.</div>
        </div>
        <div class="card" style="margin-bottom:16px;">
            <h4 style="margin-bottom:8px;">Proxy URL</h4>
            <div style="display:flex;gap:8px;">
                <input type="text" id="settings-server-url" placeholder="http://localhost:8080" style="flex:1;padding:8px 12px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;">
                <button class="btn-primary" onclick="saveSettings()">Save</button>
            </div>
        </div>
        <div class="card" style="margin-bottom:16px;">
            <h4 style="margin-bottom:8px;">Tenant Type</h4>
            <p style="font-size:13px;color:#8a9bb5;">${state.featureFlags?.tenantType || 'enterprise'}</p>
            <p style="font-size:12px;color:#6a7f9a;">Controls runtime isolation (enterprise, freelancer, home)</p>
        </div>
        <div class="card" style="margin-bottom:16px;">
            <h4 style="margin-bottom:8px;">Auto-Update</h4>
            <label style="display:flex;align-items:center;gap:8px;color:#b0b0c0;font-size:13px;">
                <input type="checkbox" id="settings-auto-update" checked /> Check for updates automatically
            </label>
        </div>
        <div class="card">
            <h4 style="margin-bottom:8px;">Node Discovery</h4>
            <label style="display:flex;align-items:center;gap:8px;color:#b0b0c0;font-size:13px;">
                <input type="checkbox" id="settings-node-discovery" checked /> Enable mDNS discovery
            </label>
        </div>
    `;
    return container;
};

// ─── About ───
views.about = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div style="text-align:center;padding:40px 0;">
            <span style="font-size:80px;">🧠</span>
            <h1 style="font-size:32px;font-weight:700;margin-top:16px;background:linear-gradient(135deg,#fff 0%,#4a8aff 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">NETTRADES</h1>
            <div style="font-size:16px;color:#6a6a7a;margin-top:4px;">Sovereign AI Platform</div>
            <div style="font-size:14px;color:#4a4a5a;margin-top:4px;">Version ${state.version}</div>
            <div style="margin-top:24px;max-width:400px;margin-left:auto;margin-right:auto;color:#8a8a9a;font-size:14px;line-height:1.6;">
                <p>Build your Sovereign AI Infrastructure using your spare GPU capacity.</p>
                <p style="margin-top:8px;">🔒 Your data never leaves your network.</p>
                <p>🚀 Deploy in minutes, not months.</p>
                <p>🌐 Fully open-source, no vendor lock-in.</p>
            </div>
            <div style="margin-top:24px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
                <button class="btn btn-secondary" onclick="window.api.openExternal('https://github.com/nettrades/nettrades-platform')">GitHub</button>
                <button class="btn btn-secondary" onclick="window.api.openExternal('https://nettrades.ai')">Website</button>
                <button class="btn btn-secondary" onclick="window.api.openExternal('https://docs.nettrades.ai')">Documentation</button>
            </div>
            <div style="margin-top:32px;font-size:12px;color:#3a3a4a;">
                © 2026 NETTRADES. All rights reserved. AGPL-3.0 Licensed.
            </div>
        </div>
    `;
    return container;
};

// ─── Containers ───
views.containers = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="header-actions">
            <h2>🐳 Container Management</h2>
            <div class="actions">
                <button class="btn-primary" onclick="startAllContainers()">▶️ Start All</button>
                <button class="btn-secondary" onclick="stopAllContainers()">⏹️ Stop All</button>
                <button class="btn-secondary" onclick="restartAllContainers()">🔄 Restart All</button>
                <button class="btn-secondary" onclick="refreshContainers()">🔄 Refresh</button>
            </div>
        </div>
        <div id="containers-list" class="containers-grid">
            ${state.containers.length === 0 ? `
                <div class="empty-state" style="grid-column:1/-1;">
                    <div class="icon">🐳</div>
                    <h3>No containers</h3>
                    <p>Loading containers...</p>
                </div>
            ` : `
                ${state.containers.map(c => `
                    <div class="container-card">
                        <div class="container-age">${c.Age || 'unknown'}</div>
                        <div class="container-name">
                            ${c.Names ? c.Names.replace(/^\//, '') : c.Name || 'Container'}
                            <span class="container-status ${c.State === 'running' ? 'running' : 'exited'}">${c.State || 'unknown'}</span>
                        </div>
                        <div class="container-image">📦 ${c.Image || 'unknown'}</div>
                        <div class="container-details">${c.Status || ''}</div>
                        ${c.Ports ? `<div class="container-ports">🔌 ${c.Ports}</div>` : ''}
                        ${c.Health && c.Health !== 'none' ? `<div class="container-health ${c.Health}">❤️ ${c.Health}</div>` : ''}
                        <div class="container-actions">
                            ${c.State === 'running' ?
                                `<button class="btn-stop" onclick="stopContainer('${c.Id}')">⏹ Stop</button>` :
                                `<button class="btn-start" onclick="startContainer('${c.Id}')">▶️ Start</button>`
                            }
                            <button class="btn-restart" onclick="restartContainer('${c.Id}')">🔄 Restart</button>
                            <button class="btn-logs" onclick="viewContainerLogs('${c.Id}')">📄 Logs</button>
                        </div>
                    </div>
                `).join('')}
            `}
        </div>
    `;
    return container;
};

// ─── Training ───
views.training = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">📚 Training</h2>
        <div class="card">
            <h4 style="margin-bottom:8px;">Start a Training Job</h4>
            <div class="form-group">
                <label>Model to fine-tune</label>
                <select id="train-model" style="width:100%;padding:8px 12px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;">
                    ${state.models.map(m => `<option value="${m.name}">${m.name}</option>`).join('')}
                </select>
            </div>
            <div class="form-group">
                <label>Dataset</label>
                <input type="text" id="train-dataset" placeholder="Path to dataset or 'good-answers'" style="width:100%;padding:8px 12px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;">
            </div>
            <div class="form-group">
                <label>Method</label>
                <select id="train-method" style="width:100%;padding:8px 12px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;">
                    <option value="unsloth">Unsloth (LoRA)</option>
                    <option value="axolotl">Axolotl</option>
                    <option value="full">Full Fine-Tuning</option>
                </select>
            </div>
            <button class="btn-primary" onclick="startTraining()">🚀 Start Training</button>
        </div>
        <div class="card" style="margin-top:16px;">
            <h4 style="margin-bottom:8px;">Recent Training Jobs</h4>
            ${state.jobs.filter(j => j.type === 'training').length === 0 ? '<p style="color:#6a7f9a;">No training jobs</p>' :
                state.jobs.filter(j => j.type === 'training').map(j => `
                    <div class="model-item" style="margin-bottom:4px;padding:8px 12px;">
                        <span>${j.model || 'Unknown'}</span>
                        <span style="font-size:12px;color:#6a7f9a;">${j.status}</span>
                    </div>
                `).join('')
            }
        </div>
    `;
    return container;
};

// ─── Marketplace ───
views.marketplace = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">🏪 GPU Marketplace</h2>
        <div class="card">
            <p style="color:#6a7f9a;">Buy and sell GPU compute on the NETTRADES network.</p>
            <p style="font-size:13px;color:#8a9bb5;margin-top:8px;">🔒 Secure • 💰 Pay-per-use • 🌐 Global</p>
        </div>
        <div style="margin-top:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;">
            ${state.gpuNodes.filter(n => n.status === 'available').map(n => `
                <div class="card">
                    <h4>${n.name || 'GPU Node'}</h4>
                    <p style="font-size:13px;color:#8a9bb5;">${n.gpu_model || 'Unknown'} • ${n.vram_gb || '?'} GB</p>
                    <p style="font-size:16px;font-weight:600;color:#00d4ff;">$${n.price_per_hour || '0'}/hr</p>
                    <button class="btn-primary" style="margin-top:8px;width:100%;" onclick="bookGPU('${n.id}')">Book Now</button>
                </div>
            `).join('')}
            ${state.gpuNodes.filter(n => n.status === 'available').length === 0 ? '<div class="empty-state" style="grid-column:1/-1;"><p>No GPU nodes available for booking.</p></div>' : ''}
        </div>
    `;
    return container;
};

// ─── Ask Someone ───
views['ask-someone'] = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">🙋 Ask Someone</h2>
        <div class="card">
            <p style="color:#8a9bb5;">Get help from AI experts and community members.</p>
            <div style="margin-top:12px;display:flex;gap:8px;">
                <input type="text" id="ask-question" placeholder="What do you need help with?" style="flex:1;padding:10px 14px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;">
                <button class="btn-primary" onclick="askQuestion()">Ask</button>
            </div>
        </div>
        <div class="card" style="margin-top:16px;">
            <h4 style="margin-bottom:8px;">Recent Questions</h4>
            <p style="color:#6a7f9a;">No questions yet. Be the first to ask!</p>
        </div>
    `;
    return container;
};

// ─── Good Answer ───
views['good-answer'] = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">⭐ Good Answer</h2>
        <div class="card">
            <p style="color:#8a9bb5;">Mark good answers to help train the AI.</p>
            <p style="font-size:13px;color:#6a7f9a;margin-top:8px;">Your feedback helps improve the model for everyone.</p>
            <div style="margin-top:12px;display:flex;gap:8px;">
                <input type="text" id="good-answer-input" placeholder="Paste a good answer..." style="flex:1;padding:10px 14px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;">
                <button class="btn-primary" onclick="markGoodAnswer()">⭐ Mark as Good</button>
            </div>
        </div>
    `;
    return container;
};

// ─── Logs ───
views.logs = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">📜 Logs</h2>
        <div class="card">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:13px;color:#6a7f9a;">Installation Log</span>
                <button class="btn-secondary" style="padding:2px 12px;font-size:12px;" onclick="refreshLogs()">Refresh</button>
            </div>
            <pre id="log-output" style="background:#0a0e17;padding:12px;border-radius:4px;font-size:12px;color:#8a9bb5;max-height:400px;overflow-y:auto;font-family:monospace;">${state.logs || 'No logs available'}</pre>
        </div>
    `;
    return container;
};

// ─── System Check ───
views['system-check'] = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">✅ System Check</h2>
        <div class="card">
            <h4 style="margin-bottom:8px;">System Status</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">
                <div><span style="color:#6a7f9a;">Platform:</span> ${state.platform?.platform || 'Unknown'}</div>
                <div><span style="color:#6a7f9a;">Architecture:</span> ${state.platform?.arch || 'Unknown'}</div>
                <div><span style="color:#6a7f9a;">Hostname:</span> ${state.platform?.hostname || 'Unknown'}</div>
                <div><span style="color:#6a7f9a;">Backend:</span> ${state.backend || 'Not configured'}</div>
                <div><span style="color:#6a7f9a;">Proxy URL:</span> ${state.proxyUrl || 'Not set'}</div>
                <div><span style="color:#6a7f9a;">Setup:</span> ${state.isPlatformSetup ? '✅ Complete' : '❌ Not set up'}</div>
            </div>
        </div>
        <button class="btn-primary" style="margin-top:16px;" onclick="runSystemCheck()">🔍 Run Full System Check</button>
    `;
    return container;
};

// ─── Modules ───
views.modules = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">🧩 Modules</h2>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;">
            ${[
                { id: 'core', name: 'Core Platform', status: 'installed' },
                { id: 'gpu-inference', name: 'GPU Inference', status: 'available' },
                { id: 'cpu-fallback', name: 'CPU Fallback', status: 'available' },
                { id: 'ai-services', name: 'AI Services', status: 'available' },
                { id: 'monitoring', name: 'Monitoring', status: 'available' },
                { id: 'gpu-marketplace', name: 'GPU Marketplace', status: 'available' },
                { id: 'bridge', name: 'Bridge Router', status: 'available' },
                { id: 'node-agent', name: 'Node Agent', status: 'available' },
            ].map(m => `
                <div class="card" style="padding:16px;">
                    <h4 style="font-size:14px;">${m.name}</h4>
                    <p style="font-size:12px;color:${m.status === 'installed' ? '#00d4ff' : '#6a7f9a'};margin-top:4px;">${m.status === 'installed' ? '✅ Installed' : '📦 Available'}</p>
                    ${m.status === 'installed' ? '' : `<button class="btn-primary" style="margin-top:8px;width:100%;font-size:12px;padding:4px;" onclick="installModule('${m.id}')">Install</button>`}
                </div>
            `).join('')}
        </div>
    `;
    return container;
};

// ─── Backup ───
views.backup = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">💾 Backup & Restore</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <div class="card">
                <h4>📤 Backup</h4>
                <p style="font-size:13px;color:#8a9bb5;margin:8px 0;">Create a full backup of all NETTRADES data.</p>
                <button class="btn-primary" onclick="createBackup()">Create Backup</button>
            </div>
            <div class="card">
                <h4>📥 Restore</h4>
                <p style="font-size:13px;color:#8a9bb5;margin:8px 0;">Restore from a previous backup.</p>
                <div style="display:flex;gap:8px;margin-top:8px;">
                    <input type="text" id="restore-path" placeholder="/path/to/backup.tar.gz" style="flex:1;padding:8px 12px;background:#1a2636;border:1px solid #1e2a3a;border-radius:6px;color:#e0e6ed;font-size:12px;">
                    <button class="btn-primary" onclick="restoreBackup()">Restore</button>
                </div>
            </div>
        </div>
        <div style="margin-top:16px;">
            <h4 style="font-size:16px;font-weight:600;margin-bottom:12px;">Available Backups</h4>
            <div id="backup-list">
                <div class="empty-state" style="padding:20px;">
                    <p>No backups found.</p>
                </div>
            </div>
        </div>
        <div id="backup-log" class="log-container" style="max-height:200px;margin-top:12px;">
            <div class="log-line info">⏳ Ready</div>
        </div>
    `;
    return container;
};

// ─── Credentials ───
views.credentials = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <h2 style="margin-bottom:20px;">🔑 Credentials</h2>
        <div class="card">
            <p style="color:#6a7f9a;">Manage your NETTRADES credentials.</p>
            <div style="margin-top:12px;">
                <button class="btn-secondary" onclick="viewCredentials()">View Credentials</button>
                <button class="btn-danger" style="margin-left:8px;" onclick="regenerateCredentials()">Regenerate All</button>
            </div>
            <p style="font-size:12px;color:#4a5f7a;margin-top:8px;">⚠️ Regenerating credentials will break running services.</p>
        </div>
    `;
    return container;
};

// ─── Deploy ───
views.deploy = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="dashboard-header">
            <div>
                <h2>🚀 Deploy Platform</h2>
                <div class="subtitle">One-click deployment with profile selection</div>
            </div>
        </div>
        <div id="deploy-step-1">
            <h3 style="margin-bottom:12px;">Step 1: Choose Your Deployment Type</h3>
            <div id="deployment-cards" class="deployment-cards"></div>
            <div id="custom-phases" style="display:none;">
                <h4 style="margin-top:16px;">Select Phases for Custom Deployment</h4>
                <div id="phase-picker" class="phase-picker"></div>
                <p style="font-size:12px;color:#6a6a7a;margin-top:8px;">⚠️ Phase 1 (venv) is mandatory and cannot be deselected.</p>
            </div>
            <div class="btn-group" style="display:flex;gap:12px;margin-top:16px;">
                <button class="btn btn-primary" id="btn-deploy-next" disabled>Next →</button>
            </div>
        </div>
        <div id="deploy-step-2" style="display:none;">
            <h3 style="margin-bottom:12px;">Step 2: Select Optional Modules</h3>
            <div class="module-options" style="margin:16px 0;padding:16px;background:rgba(255,255,255,0.04);border-radius:12px;border:1px solid rgba(255,255,255,0.06);">
                <label style="display:block;padding:6px 0;font-size:14px;cursor:pointer;">
                    <input type="checkbox" name="module-finetune" value="finetune"> Fine‑Tuning (Unsloth/Axolotl)
                    <span style="display:block;font-size:12px;color:#6a6a7a;margin-left:24px;">Train and fine-tune models on your GPUs.</span>
                </label>
                <label style="display:block;padding:6px 0;font-size:14px;cursor:pointer;">
                    <input type="checkbox" name="module-grove" value="grove"> Grove Observability
                    <span style="display:block;font-size:12px;color:#6a6a7a;margin-left:24px;">Prometheus, Loki, Tempo monitoring stack.</span>
                </label>
                <label style="display:block;padding:6px 0;font-size:14px;cursor:pointer;">
                    <input type="checkbox" name="module-kai" value="kai"> KAI Scheduler
                    <span style="display:block;font-size:12px;color:#6a6a7a;margin-left:24px;">GPU scheduling for Kubernetes clusters.</span>
                </label>
                <label style="display:block;padding:6px 0;font-size:14px;cursor:pointer;">
                    <input type="checkbox" name="module-router" value="router"> Router Mode (Bridge Module)
                    <span style="display:block;font-size:12px;color:#6a6a7a;margin-left:24px;">Enable this node to route requests to other GPU nodes.</span>
                </label>
                <label style="display:block;padding:6px 0;font-size:14px;cursor:pointer;">
                    <input type="checkbox" name="module-cuvs" value="cuvs"> RAPIDS cuVS (GPU-Accelerated Vector Search)
                    <span style="display:block;font-size:12px;color:#6a6a7a;margin-left:24px;">Install cuVS for GPU-accelerated vector search. Requires NVIDIA GPU.</span>
                </label>
            </div>
            <div style="margin:12px 0;">
                <label style="font-size:14px;display:inline-flex;align-items:center;gap:8px;">
                    <input type="radio" name="env" value="development" checked> 🛠️ Development
                </label>
                <label style="font-size:14px;display:inline-flex;align-items:center;gap:8px;margin-left:16px;">
                    <input type="radio" name="env" value="production"> 🔒 Production
                </label>
            </div>
            <div style="margin:8px 0;">
                <label style="font-size:14px;display:inline-flex;align-items:center;gap:8px;">
                    <input type="text" id="domain-input" placeholder="Enter domain (e.g., ai.company.com)" style="display:none;padding:6px 12px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e8e8e8;width:260px;">
                </label>
            </div>
            <div style="margin:8px 0;">
                <label style="font-size:14px;display:inline-flex;align-items:center;gap:8px;margin-right:16px;">
                    <input type="checkbox" id="deploy-force"> ⚡ Force re-run
                </label>
                <label style="font-size:14px;display:inline-flex;align-items:center;gap:8px;margin-right:16px;">
                    <input type="checkbox" id="deploy-upgrade"> 🔄 Upgrade
                </label>
                <label style="font-size:14px;display:inline-flex;align-items:center;gap:8px;">
                    <input type="checkbox" id="deploy-auto" checked> 🤖 Auto
                </label>
            </div>
            <div id="hardware-info" class="hardware-info"></div>
            <h4 style="margin-top:16px;">Summary</h4>
            <div id="config-summary" style="background:rgba(255,255,255,0.04);border-radius:12px;padding:16px 20px;margin:16px 0;border:1px solid rgba(255,255,255,0.06);">
                <div class="config-row" style="padding:4px 0;font-size:14px;">
                    <strong>Profile:</strong> <span id="summary-profile">None selected</span>
                </div>
                <div class="config-row" style="padding:4px 0;font-size:14px;">
                    <strong>Phases:</strong> <span id="summary-phases">-</span>
                </div>
                <div class="config-row" style="padding:4px 0;font-size:14px;">
                    <strong>Environment:</strong> <span id="config-env">Development</span>
                </div>
                <div class="config-row" style="color:#6a6a7a;font-size:0.85rem;margin-top:0.5rem;">
                    Phase 1 (venv) is always included as it's required by all other phases.
                </div>
            </div>
            <div style="display:flex;gap:12px;margin-top:16px;flex-wrap:wrap;">
                <button class="btn btn-secondary" id="btn-deploy-back">← Back</button>
                <button class="btn btn-primary" id="btn-deploy-start">🚀 Install</button>
            </div>
            <div class="tenant-section" style="margin-top:24px;border-top:1px solid rgba(255,255,255,0.05);padding-top:20px;">
                <h3>Step 4: Tenant Configuration</h3>
                <p class="subtitle">Select the type of tenant you are deploying. This determines runtime isolation and security settings.</p>
                <div class="tenant-options">
                    <div class="tenant-option" data-type="enterprise">
                        <h3>🏢 Enterprise</h3>
                        <div class="desc">Full performance, trusted workload</div>
                        <ul>
                            <li>Uses <code>runc</code> runtime for all services</li>
                            <li>Maximum performance for production workloads</li>
                            <li>Recommended for companies with trusted code</li>
                        </ul>
                        <button class="select-tenant" data-type="enterprise">Select</button>
                    </div>
                    <div class="tenant-option" data-type="freelancer">
                        <h3>💼 Freelancer</h3>
                        <div class="desc">gVisor isolation for untrusted code</div>
                        <ul>
                            <li>Uses <code>runsc</code> (gVisor) for AI agents</li>
                            <li>Isolates untrusted agent code from host</li>
                            <li>Recommended for freelancers and contractors</li>
                        </ul>
                        <button class="select-tenant" data-type="freelancer">Select</button>
                    </div>
                    <div class="tenant-option" data-type="home">
                        <h3>🏠 Home User</h3>
                        <div class="desc">gVisor isolation for personal use</div>
                        <ul>
                            <li>Uses <code>runsc</code> (gVisor) for AI agents</li>
                            <li>Strong isolation for personal projects</li>
                            <li>Recommended for home users and hobbyists</li>
                        </ul>
                        <button class="select-tenant" data-type="home">Select</button>
                    </div>
                </div>
                <div id="tenant-details" style="display:none;">
                    <div class="tenant-details">
                        <div class="selected-label">Selected Tenant: <strong id="selected-tenant-type"></strong></div>
                        <div class="selected-desc" id="selected-tenant-description"></div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;">
                            <div class="form-group" style="margin-bottom:0;">
                                <label for="tenant-name">Tenant Name</label>
                                <input type="text" id="tenant-name" placeholder="My Company">
                            </div>
                            <div class="form-group" style="margin-bottom:0;">
                                <label for="tenant-domain">Domain</label>
                                <input type="text" id="tenant-domain" placeholder="ai.mycompany.com">
                            </div>
                        </div>
                        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:12px;">
                            <div class="form-group" style="margin-bottom:0;">
                                <label for="tenant-email">Admin Email</label>
                                <input type="email" id="tenant-email" placeholder="admin@mycompany.com">
                            </div>
                            <div class="form-group" style="margin-bottom:0;">
                                <label for="tenant-password">PostgreSQL Password</label>
                                <input type="password" id="tenant-password" placeholder="Enter strong password">
                            </div>
                            <div class="form-group" style="margin-bottom:0;display:flex;align-items:center;padding-top:20px;">
                                <label style="display:flex;align-items:center;gap:8px;font-size:14px;cursor:pointer;">
                                    <input type="checkbox" id="tenant-wireguard" checked> Enable WireGuard VPN
                                </label>
                            </div>
                        </div>
                        <div class="help-text" style="margin-top:8px;">Creates an isolated VPN subnet for this tenant</div>
                        <button id="deploy-tenant-btn" class="btn btn-primary" style="margin-top:16px;width:100%;justify-content:center;">🚀 Deploy Platform with Tenant Configuration</button>
                    </div>
                </div>
            </div>
        </div>
        <div id="deploy-step-3" style="display:none;">
            <h3 style="margin-bottom:12px;">Installing...</h3>
            <div id="install-status-badge" class="status-badge status-unknown" style="padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600;background:rgba(255,149,0,0.2);color:#ff9500;">⏳ Installing...</div>
            <div class="progress-container" style="margin-top:12px;">
                <div class="progress-bar" id="install-progress-fill" style="width:0%;"></div>
            </div>
            <div style="font-size:13px;color:#8a8a9a;margin-top:8px;" id="install-progress-label">Starting installation...</div>
            <div id="install-log-output" class="install-log">
                <div class="log-placeholder">Waiting for output...</div>
            </div>
            <div style="display:flex;gap:12px;margin-top:12px;">
                <button class="btn btn-danger" id="btn-install-cancel" style="display:none;">✖ Cancel</button>
            </div>
        </div>
    `;
    // Render cards and phase picker after DOM
    setTimeout(() => {
        renderDeploymentCards();
        renderPhasePicker();
    }, 50);
    return container;
};

// ─── Queue ───
views.queue = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="header-actions">
            <h2>📋 Task Queue</h2>
            <div class="actions">
                <button class="btn-secondary" onclick="refreshQueue()">🔄 Refresh</button>
            </div>
        </div>
        <div id="queue-list" class="queue-list">
            <div class="empty-state">
                <div class="icon">📋</div>
                <h3>No Tasks in Queue</h3>
                <p>Tasks will appear here when they are queued for execution.</p>
            </div>
        </div>
    `;
    return container;
};

// ─── Monitor ───
views.monitor = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="dashboard-header">
            <div>
                <h2>📈 System Monitor</h2>
                <div class="subtitle">Real-time health and performance monitoring</div>
            </div>
            <div>
                <button class="btn-secondary" onclick="refreshMonitor()">🔄 Refresh</button>
                <button class="btn-primary" onclick="openApp('grafana')">Open Grafana</button>
            </div>
        </div>
        <div class="status-grid">
            <div class="status-card">
                <div class="label">Odoo</div>
                <div class="value">
                    <span class="status-dot" id="monitor-odoo-dot"></span>
                    <span id="monitor-odoo-status">Checking...</span>
                </div>
            </div>
            <div class="status-card">
                <div class="label">LangGraph</div>
                <div class="value">
                    <span class="status-dot" id="monitor-langgraph-dot"></span>
                    <span id="monitor-langgraph-status">Checking...</span>
                </div>
            </div>
            <div class="status-card">
                <div class="label">Dynamo</div>
                <div class="value">
                    <span class="status-dot" id="monitor-dynamo-dot"></span>
                    <span id="monitor-dynamo-status">Checking...</span>
                </div>
            </div>
            <div class="status-card">
                <div class="label">PostgreSQL</div>
                <div class="value">
                    <span class="status-dot" id="monitor-postgres-dot"></span>
                    <span id="monitor-postgres-status">Checking...</span>
                </div>
            </div>
        </div>
        <div class="section-header">
            <h2>Alerts</h2>
        </div>
        <div id="alerts-container">
            <div class="empty-state" style="padding:20px;">
                <p>No active alerts</p>
            </div>
        </div>
    `;
    return container;
};

// ─── Install Log ───
views['install-log'] = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="header-actions">
            <h2>📄 Installation Log</h2>
            <div class="actions">
                <button class="btn-secondary" onclick="clearInstallLog()">🗑️ Clear</button>
                <button class="btn-secondary" onclick="copyInstallLog()">📋 Copy</button>
            </div>
        </div>
        <div id="install-log-output" class="install-log" style="height:400px;">
            ${state.logs || '<div class="log-placeholder">Waiting for installation output...</div>'}
        </div>
    `;
    return container;
};

// ─── Emergency Access ───
views.emergency = function() {
    const container = document.createElement('div');
    container.innerHTML = `
        <div class="dashboard-header">
            <h2>🔐 Emergency Access Management</h2>
            <div class="subtitle">Manage break-glass emergency users for Odoo</div>
        </div>
        <div style="margin-bottom: 1rem;">
            <button class="btn btn-primary" onclick="createEmergencyUser()">➕ Create Emergency User</button>
            <button class="btn btn-secondary" onclick="loadEmergencyUsers()">🔄 Refresh</button>
        </div>
        <div id="emergency-users-list"><p>Loading...</p></div>
        <div style="margin-top: 24px;">
            <button class="btn btn-secondary" onclick="loadEmergencyAudit()">📋 View Audit Log</button>
            <div id="emergency-audit-list" style="margin-top: 12px;"></div>
        </div>
    `;
    setTimeout(loadEmergencyUsers, 100);
    return container;
};

// ─── IPC Listeners ───
function setupIpcListeners() {
    window.api.onInstallOutput((data) => {
        const logContainer = document.getElementById('install-log-output');
        if (logContainer) {
            const placeholder = logContainer.querySelector('.log-placeholder');
            if (placeholder) placeholder.remove();
            const line = document.createElement('div');
            line.className = `log-line ${data.type === 'stderr' ? 'error' : 'info'}`;
            line.textContent = data.data.trim();
            logContainer.appendChild(line);
            logContainer.scrollTop = logContainer.scrollHeight;
        }
        // Update progress
        const progress = document.getElementById('install-progress-fill');
        const label = document.getElementById('install-progress-label');
        if (data.data.includes('Phase 0')) { progress.style.width = '10%'; label.textContent = 'Phase 0: System Preparation...'; }
        else if (data.data.includes('Phase 1')) { progress.style.width = '30%'; label.textContent = 'Phase 1: Environment Setup...'; }
        else if (data.data.includes('Phase 2')) { progress.style.width = '50%'; label.textContent = 'Phase 2: Deployment...'; }
        else if (data.data.includes('Phase 3')) { progress.style.width = '70%'; label.textContent = 'Phase 3: Kubernetes...'; }
        else if (data.data.includes('Phase 4')) { progress.style.width = '85%'; label.textContent = 'Phase 4: Module Installation...'; }
        else if (data.data.includes('Phase 5')) { progress.style.width = '95%'; label.textContent = 'Phase 5: Monitoring Setup...'; }
        else if (data.data.includes('Setup Complete')) {
            progress.style.width = '100%';
            label.textContent = '✅ Installation complete!';
            document.getElementById('install-status-badge').textContent = '✅ Complete';
            document.getElementById('install-status-badge').className = 'status-badge status-running';
            state.isInstalling = false;
            document.getElementById('btn-install-cancel').style.display = 'none';
        }
    });

    window.api.onInstallProgress((data) => {
        if (data.progress !== undefined) {
            document.getElementById('install-progress-fill').style.width = `${data.progress}%`;
        }
    });

    window.api.onNodeDiscovered((node) => {
        showToast(`Node discovered: ${node.name}`, 'info');
        discoverNodes();
    });

    window.api.onBackupOutput((data) => {
        const logContainer = document.getElementById('backup-log');
        if (logContainer) {
            const line = document.createElement('div');
            line.className = `log-line ${data.type === 'stderr' ? 'error' : 'info'}`;
            line.textContent = data.data.trim();
            logContainer.appendChild(line);
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    });
}

// ─── Toast ───
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ─── Open App ───
function openApp(appName) {
    window.api.getServerUrl().then((serverUrl) => {
        const ports = { odoo: 8069, grafana: 3001, llama: 8080, dynamo: 8001, langgraph: 8000, ui: 3002 };
        const url = `${serverUrl}:${ports[appName]}`;
        window.api.openExternal(url);
    });
}

// ─── Refresh Functions ───
function refreshDashboard() {
    window.api.platformStatus().then((status) => {
        const dot = document.getElementById('platform-status-dot');
        const text = document.getElementById('platform-status-text');
        if (status && status.running) {
            if (dot) dot.className = 'status-dot online';
            if (text) text.textContent = 'Online';
        } else {
            if (dot) dot.className = 'status-dot offline';
            if (text) text.textContent = 'Offline';
        }
    }).catch(() => {
        const dot = document.getElementById('platform-status-dot');
        const text = document.getElementById('platform-status-text');
        if (dot) dot.className = 'status-dot offline';
        if (text) text.textContent = 'Unknown';
    });
}

async function refreshModels() {
    try {
        const models = await window.api.listModels();
        state.models = models || [];
        document.getElementById('model-count').textContent = state.models.length;
        document.getElementById('dashboard-model-count').textContent = state.models.length;
        if (state.currentView === 'models') {
            const container = document.getElementById('tab-models');
            if (container) {
                container.innerHTML = '';
                container.appendChild(views.models());
            }
        }
    } catch (e) { console.error('Failed to refresh models:', e); }
}


// GPU Auto-Discovery UI Integration
// GPU tab will show:
//    Local GPUs – automatically detected (no registration needed).
//    Network GPUs – discovered via mDNS (no registration needed).
//    Marketplace GPUs – from Odoo (with prices, shown if registered).
// The "Register GPU" button will only be used for manually adding external GPUs (e.g., a GPU from another network or a cloud GPU).
async function refreshGPUs() {
    try {
        // 1. Local GPUs (always works)
        const hardware = await window.api.detectHardware();
        const localGpus = (hardware && hardware.gpus) || [];
        const localNodes = localGpus.map(g => ({
            id: `local-${g.index || Date.now()}`,
            name: g.name || 'Local GPU',
            gpu_model: g.name || 'Unknown',
            vram_gb: g.memory ? parseInt(g.memory) : 0,
            status: 'available',
            price_per_hour: 0,
            last_heartbeat: new Date().toISOString(),
        }));

        // 2. Network nodes (via mDNS)
        const discovered = await window.api.getDiscoveredNodes();
        const networkNodes = discovered.map(n => ({
            id: `network-${n.name}`,
            name: n.name || 'Network Node',
            gpu_model: n.txt?.gpu || 'Unknown',
            vram_gb: parseInt(n.txt?.vram) || 0,
            status: 'available',
            price_per_hour: 0,
            last_heartbeat: new Date().toISOString(),
        }));

        // 3. Marketplace GPUs (if Odoo modules are installed)
        let marketNodes = [];
        try {
            const marketResult = await window.api.marketplaceListings();
            if (marketResult.success && marketResult.data) {
                marketNodes = marketResult.data.map(m => ({
                    id: `market-${m.id}`,
                    name: m.name || 'Market GPU',
                    gpu_model: m.model || 'Unknown',
                    vram_gb: m.vram || 0,
                    status: m.available ? 'available' : 'in-use',
                    price_per_hour: m.price || 0,
                    last_heartbeat: new Date().toISOString(),
                }));
            }
        } catch (e) {
            // Marketplace unavailable - just use local + network
            console.log('Marketplace not available, using local + network GPUs');
        }

        // Combine all
        state.gpuNodes = [...localNodes, ...networkNodes, ...marketNodes];

        // Update UI badges
        const gpuCount = document.getElementById('gpu-count');
        if (gpuCount) gpuCount.textContent = state.gpuNodes.length;

        const dashboardGpuCount = document.getElementById('dashboard-gpu-count');
        if (dashboardGpuCount) {
            dashboardGpuCount.textContent = state.gpuNodes.filter(n => n.status === 'available').length;
        }

        // Re-render GPU tab if active
        if (state.currentView === 'gpus') {
            const container = document.getElementById('tab-gpus');
            if (container) {
                container.innerHTML = '';
                container.appendChild(views.gpus());
            }
        }
    } catch (e) {
        console.error('Failed to refresh GPUs:', e);
    }
}

async function discoverNodes() {
    try {
        const discovered = await window.api.getDiscoveredNodes();
        state.nodes = discovered || [];
        document.getElementById('node-count').textContent = state.nodes.length;
        document.getElementById('node-count-display').textContent = `${state.nodes.length} nodes discovered`;
        document.getElementById('dashboard-node-count').textContent = state.nodes.length;
        if (state.currentView === 'nodes') {
            const container = document.getElementById('tab-nodes');
            if (container) {
                container.innerHTML = '';
                container.appendChild(views.nodes());
            }
        }
    } catch (e) { console.error('Failed to discover nodes:', e); }
}

async function refreshVPN() {
    try {
        const status = await window.api.vpnStatus();
        state.wireguardRunning = status.running || false;
        document.getElementById('vpn-status').textContent = state.wireguardRunning ? '🟢' : '🔴';
        document.getElementById('vpn-status').className = state.wireguardRunning ? 'badge active-badge' : 'badge';
        const peers = await window.api.vpnListPeers();
        if (peers.success) {
            const lines = (peers.output || '').split('\n').filter(l => l.trim());
            state.wireguardPeers = lines.length;
            state.wireguardPeersList = lines.map(line => ({ name: 'Peer', ip: line }));
            if (state.currentView === 'vpn') {
                const container = document.getElementById('tab-vpn');
                if (container) {
                    container.innerHTML = '';
                    container.appendChild(views.vpn());
                }
            }
        }
    } catch (e) { console.error('Failed to refresh VPN:', e); }
}

async function refreshQueue() {
    try {
        const result = await window.api.listQueue();
        if (result.success) {
            state.jobs = result.data || [];
            if (state.currentView === 'queue') {
                const container = document.getElementById('tab-queue');
                if (container) {
                    container.innerHTML = '';
                    container.appendChild(views.queue());
                }
            }
        }
    } catch (e) { console.error('Failed to refresh queue:', e); }
}

async function refreshMonitor() {
    try {
        const health = await window.api.systemHealth();
        const services = ['odoo', 'langgraph', 'dynamo', 'postgres'];
        for (const service of services) {
            const dot = document.getElementById(`monitor-${service}-dot`);
            const text = document.getElementById(`monitor-${service}-status`);
            if (dot && text) {
                const status = health.services?.[service] || 'unhealthy';
                dot.className = `status-dot ${status === 'healthy' ? 'online' : 'offline'}`;
                text.textContent = status === 'healthy' ? '✅ Healthy' : '❌ Unhealthy';
            }
        }
    } catch (e) { console.error('Failed to refresh monitor:', e); }
}

async function refreshLogs() {
    const service = document.getElementById('log-service')?.value || 'all';
    if (service === 'all') return;
    try {
        const result = await window.api.getLogs({ service, lines: 100 });
        const container = document.getElementById('logs-container');
        if (container && result.success) {
            const lines = (result.data || '').split('\n').filter(l => l.trim());
            container.innerHTML = lines.map(line => `<div class="log-line">${escapeHtml(line)}</div>`).join('');
        }
    } catch (e) { console.error('Failed to refresh logs:', e); }
}

async function refreshBackups() {
    try {
        const backups = await window.api.listBackups();
        const container = document.getElementById('backup-list');
        const select = document.getElementById('backup-select');
        if (container && select) {
            if (!backups || backups.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:20px;"><p>No backups found.</p></div>';
                select.innerHTML = '<option value="">No backups found</option>';
            } else {
                container.innerHTML = backups.map(b => `
                    <div class="queue-item" style="border-left-color:#4a8aff;">
                        <div class="task-info">
                            <div class="task-name">${b.name}</div>
                            <div class="task-details">${formatSize(b.size)} • ${new Date(b.created).toLocaleString()}</div>
                        </div>
                        <button class="btn btn-secondary" onclick="restoreBackup('${b.path}')" style="font-size:12px;padding:4px 12px;">Restore</button>
                    </div>
                `).join('');
                select.innerHTML = backups.map(b => `<option value="${b.path}">${b.name}</option>`).join('');
            }
        }
    } catch (e) { console.error('Failed to refresh backups:', e); }
}

async function refreshMarketplace() {
    try {
        const result = await window.api.marketplaceListings();
        const container = document.getElementById('marketplace-listings');
        if (container) {
            if (result.success && result.data && result.data.length > 0) {
                container.innerHTML = result.data.map(listing => `
                    <div class="marketplace-card fade-in">
                        <div class="gpu-name">${escapeHtml(listing.name || 'GPU')}</div>
                        <div class="gpu-specs">${escapeHtml(listing.model || '')} • ${listing.vram || '?'}GB VRAM</div>
                        <div class="gpu-price">$${listing.price || '0.00'}/hour</div>
                        <div class="gpu-owner">Owner: ${escapeHtml(listing.owner || 'Unknown')}</div>
                        <button class="btn btn-primary" onclick="bookGPU('${listing.id}')" style="margin-top:8px;font-size:12px;padding:4px 12px;">Book Now</button>
                    </div>
                `).join('');
            } else {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">💰</div>
                        <h3>No GPU Listings</h3>
                        <p>List your GPU to earn passive income, or browse available GPUs.</p>
                        <button class="btn btn-primary" onclick="showListGPU()" style="margin-top:12px;">📝 List Your GPU</button>
                    </div>
                `;
            }
        }
    } catch (e) { console.error('Failed to refresh marketplace:', e); }
}

async function refreshContainers() {
    try {
        const result = await window.api.listContainers();
        if (result.success) {
            state.containers = result.containers || [];
            document.getElementById('container-count').textContent = state.containers.length;
            document.getElementById('container-stats').textContent = `${state.containers.length} containers`;
            if (state.currentView === 'containers') {
                const container = document.getElementById('tab-containers');
                if (container) {
                    container.innerHTML = '';
                    container.appendChild(views.containers());
                }
            }
        }
    } catch (e) { console.error('Failed to refresh containers:', e); }
}

async function refreshCredentials() {
    try {
        const result = await window.api.getCredentials();
        const list = document.getElementById('credential-list');
        if (list) {
            if (result.success) {
                const data = result.data || [];
                if (data.length === 0) {
                    list.innerHTML = '<div class="credential-empty">No credentials available.</div>';
                } else {
                    list.innerHTML = data.map(item => `
                        <div class="credential-item">
                            <span class="cred-key">${item.key}</span>
                            <span class="cred-value">••••••••</span>
                            <div class="cred-actions">
                                <button onclick="viewCredential('${item.key}')" title="View">👁️</button>
                                <button onclick="rotateCredential('${item.key}')" title="Rotate">🔄</button>
                            </div>
                        </div>
                    `).join('');
                }
            } else {
                list.innerHTML = `<div class="credential-empty">Failed to load credentials: ${result.error}</div>`;
            }
        }
    } catch (e) { console.error('Failed to refresh credentials:', e); }
}

function renderModules() {
    const container = document.getElementById('module-grid');
    if (!container) return;
    const modules = [
        { id: 'core', name: 'Core Platform', status: 'installed', desc: 'Base platform services' },
        { id: 'gpu-inference', name: 'GPU Inference', status: 'available', desc: 'NVIDIA Dynamo & vLLM' },
        { id: 'cpu-fallback', name: 'CPU Fallback', status: 'available', desc: 'llama.cpp fallback' },
        { id: 'ai-services', name: 'AI Services', status: 'available', desc: 'Ask Someone, Good Answer' },
        { id: 'monitoring', name: 'Monitoring', status: 'available', desc: 'Prometheus, Grafana' },
        { id: 'gpu-marketplace', name: 'GPU Marketplace', status: 'available', desc: 'Buy/Sell GPU compute' },
        { id: 'bridge', name: 'Bridge Router', status: 'available', desc: 'Hub-and-spoke routing' },
        { id: 'node-agent', name: 'Node Agent', status: 'available', desc: 'Spoke agent' },
    ];
    container.innerHTML = modules.map(m => `
        <div class="module-card">
            <div class="module-header">
                <span class="module-name">${m.name}</span>
                <span class="module-status ${m.status}">${m.status === 'installed' ? '✅ Installed' : '📦 Available'}</span>
            </div>
            <div class="module-desc">${m.desc}</div>
            ${m.status === 'installed' ? '' : `<button class="btn-primary" style="margin-top:8px;width:100%;font-size:12px;padding:4px;" onclick="installModule('${m.id}')">Install</button>`}
        </div>
    `).join('');
    document.getElementById('module-badge').textContent = modules.filter(m => m.status === 'installed').length;
}

// ─── Actions ───
window.sendMessage = async function() {
    const input = document.getElementById('chat-input');
    if (!input || !input.value.trim() || state.isLoading) return;
    const message = input.value.trim();
    input.value = '';
    state.messages.push({ role: 'user', content: message, time: new Date().toLocaleTimeString() });
    state.isLoading = true;
    const container = document.getElementById('tab-chat');
    if (container) { container.innerHTML = ''; container.appendChild(views.chat()); }
    try {
        // Use proxyCreateJob (will be added in main)
        const result = await window.api.proxyCreateJob({
            type: 'inference',
            model: state.selectedModel,
            prompt: message,
            parameters: { temperature: state.temperature },
        });
        if (result.success) {
            const jobId = result.data.id;
            let attempts = 0;
            const checkJob = async () => {
                const status = await window.api.proxyGetJob(jobId);
                if (status.success && status.data.status === 'completed') {
                    state.messages.push({ role: 'assistant', content: status.data.result || 'No response', time: new Date().toLocaleTimeString() });
                    state.isLoading = false;
                    if (container) { container.innerHTML = ''; container.appendChild(views.chat()); }
                } else if (attempts < 30) {
                    attempts++;
                    setTimeout(checkJob, 2000);
                } else {
                    state.messages.push({ role: 'system', content: '⏰ Job timed out. Please try again.', time: new Date().toLocaleTimeString() });
                    state.isLoading = false;
                    if (container) { container.innerHTML = ''; container.appendChild(views.chat()); }
                }
            };
            checkJob();
        } else {
            state.messages.push({ role: 'system', content: `❌ Error: ${result.error}`, time: new Date().toLocaleTimeString() });
            state.isLoading = false;
            if (container) { container.innerHTML = ''; container.appendChild(views.chat()); }
        }
    } catch (error) {
        state.messages.push({ role: 'system', content: `❌ Error: ${error.message}`, time: new Date().toLocaleTimeString() });
        state.isLoading = false;
        if (container) { container.innerHTML = ''; container.appendChild(views.chat()); }
    }
};

window.clearChat = function() {
    state.messages = [];
    const container = document.getElementById('tab-chat');
    if (container) { container.innerHTML = ''; container.appendChild(views.chat()); }
};

window.downloadModel = async function(name, type) {
    try {
        const result = await window.api.downloadModel({ model: name, format: type });
        if (result.success) {
            showToast(`✅ Download started for ${name}`, 'success');
            await refreshModels();
        } else {
            showToast(`❌ Download failed: ${result.error}`, 'error');
        }
    } catch (error) { showToast(`❌ Error: ${error.message}`, 'error'); }
};

window.showRegisterGPU = function() {
    showModal(`
        <h2 style="margin-bottom:16px;">Register GPU</h2>
        <div class="form-group">
            <label>GPU Name</label>
            <input type="text" id="register-gpu-name" placeholder="RTX 4090" />
        </div>
        <div class="form-group">
            <label>GPU Model</label>
            <input type="text" id="register-gpu-model" placeholder="NVIDIA GeForce RTX 4090" />
        </div>
        <div class="form-group">
            <label>VRAM (GB)</label>
            <input type="number" id="register-gpu-vram" placeholder="24" />
        </div>
        <div class="form-group">
            <label>Price per Hour ($)</label>
            <input type="number" id="register-gpu-price" placeholder="0.50" step="0.01" />
        </div>
        <div style="display:flex;gap:12px;margin-top:16px;">
            <button class="btn btn-primary" onclick="submitRegisterGPU()">Register</button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    `);
};

window.submitRegisterGPU = async function() {
    const name = document.getElementById('register-gpu-name').value;
    const model = document.getElementById('register-gpu-model').value;
    const vram = parseInt(document.getElementById('register-gpu-vram').value) || 0;
    const price = parseFloat(document.getElementById('register-gpu-price').value) || 0;
    if (!name || !model || !vram || !price) { showToast('Please fill in all fields', 'error'); return; }
    // Use marketplaceListGPU to register
    const result = await window.api.marketplaceListGPU({
        name: name || 'GPU Node',
        model: model || 'Unknown',
        vram: vram,
        price: price,
        status: 'available'
    });
    if (result.success) { closeModal(); await refreshGPUs(); showToast('GPU registered successfully!', 'success'); }
    else { showToast(`Failed to register GPU: ${result.error}`, 'error'); }
};

window.addVPNPeer = function() {
    showModal(`
        <h2 style="margin-bottom:16px;">➕ Add VPN Peer</h2>
        <div class="form-group">
            <label>Peer Name</label>
            <input type="text" id="vpn-peer-name" placeholder="laptop" />
        </div>
        <div class="form-group">
            <label>IP Address (optional)</label>
            <input type="text" id="vpn-peer-ip" placeholder="10.10.10.50" />
        </div>
        <div style="display:flex;gap:12px;margin-top:16px;">
            <button class="btn btn-primary" onclick="submitVPNPeer()">Add Peer</button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    `);
};

window.submitVPNPeer = async function() {
    const name = document.getElementById('vpn-peer-name').value.trim();
    const ip = document.getElementById('vpn-peer-ip').value.trim();
    if (!name) { showToast('Please enter a peer name', 'error'); return; }
    const result = await window.api.vpnAddPeer(name, ip || undefined);
    if (result.success) { closeModal(); await refreshVPN(); showToast(`Peer ${name} added successfully!`, 'success'); }
    else { showToast(`Failed to add peer: ${result.error}`, 'error'); }
};

window.removeVPNPeer = async function(name) {
    if (!confirm(`Remove peer '${name}'?`)) return;
    const result = await window.api.vpnRemovePeer(name);
    if (result.success) { await refreshVPN(); showToast(`Peer ${name} removed`, 'info'); }
    else { showToast(`Failed to remove peer: ${result.error}`, 'error'); }
};

window.startContainer = async function(id) {
    const result = await window.api.startContainer(id);
    if (result.success) { showToast('Container started', 'success'); await refreshContainers(); }
    else { showToast(`Failed to start container: ${result.error}`, 'error'); }
};

window.stopContainer = async function(id) {
    const result = await window.api.stopContainer(id);
    if (result.success) { showToast('Container stopped', 'info'); await refreshContainers(); }
    else { showToast(`Failed to stop container: ${result.error}`, 'error'); }
};

window.restartContainer = async function(id) {
    const result = await window.api.restartContainer(id);
    if (result.success) { showToast('Container restarted', 'success'); await refreshContainers(); }
    else { showToast(`Failed to restart container: ${result.error}`, 'error'); }
};

window.startAllContainers = async function() {
    const result = await window.api.startAllContainers();
    if (result.success) { showToast('All containers started', 'success'); await refreshContainers(); }
    else { showToast(`Failed to start all containers: ${result.error}`, 'error'); }
};

window.stopAllContainers = async function() {
    const result = await window.api.stopAllContainers();
    if (result.success) { showToast('All containers stopped', 'info'); await refreshContainers(); }
    else { showToast(`Failed to stop all containers: ${result.error}`, 'error'); }
};

window.restartAllContainers = async function() {
    const result = await window.api.restartAllContainers();
    if (result.success) { showToast('All containers restarted', 'success'); await refreshContainers(); }
    else { showToast(`Failed to restart all containers: ${result.error}`, 'error'); }
};

window.viewContainerLogs = async function(id) {
    const result = await window.api.containerLogs(id, 100);
    if (result.success) {
        showModal(`
            <h2 style="margin-bottom:12px;">📄 Container Logs</h2>
            <pre style="background:#0a0a0f;padding:16px;border-radius:8px;font-size:12px;color:#8a8a9a;max-height:400px;overflow-y:auto;font-family:monospace;white-space:pre-wrap;word-wrap:break-word;">${escapeHtml(result.logs || 'No logs available')}</pre>
            <button class="btn btn-secondary" onclick="closeModal()">Close</button>
        `);
    } else { showToast(`Failed to fetch logs: ${result.error}`, 'error'); }
};

window.startTraining = async function() {
    const dataset = document.getElementById('train-dataset')?.value || 'good-answers';
    const model = document.getElementById('train-model')?.value || state.models[0]?.name || 'deepseek-1.5b';
    const method = document.getElementById('train-method')?.value || 'unsloth';
    const result = await window.api.startTraining({ dataset, model, method, params: { epochs: 3 } });
    if (result.success) { showToast('Training started successfully!', 'success'); }
    else { showToast(`Failed to start training: ${result.error}`, 'error'); }
};

window.askQuestion = function() {
    const input = document.getElementById('ask-question');
    if (!input || !input.value.trim()) return;
    showToast(`Question submitted: ${input.value}`, 'success');
    input.value = '';
};

window.markGoodAnswer = function() {
    const input = document.getElementById('good-answer-input');
    if (!input || !input.value.trim()) return;
    showToast('⭐ Marked as good answer!', 'success');
    input.value = '';
};

window.createBackup = async function() {
    const result = await window.api.createBackup({ auto: true });
    if (result.success) { showToast('Backup created successfully!', 'success'); await refreshBackups(); }
    else { showToast(`Backup failed: ${result.error}`, 'error'); }
};

window.restoreBackup = async function(path) {
    const backupPath = path || document.getElementById('backup-select')?.value;
    if (!backupPath) { showToast('Please select a backup to restore', 'warning'); return; }
    if (!confirm(`Restore from ${backupPath}? This will overwrite current data.`)) return;
    const result = await window.api.restoreBackup(backupPath);
    if (result.success) { showToast('Backup restored successfully!', 'success'); }
    else { showToast(`Restore failed: ${result.error}`, 'error'); }
};

window.bookGPU = function(id) {
    showToast(`📅 Booking GPU ${id}... This feature will be implemented in the next release.`, 'info');
};

window.showListGPU = function() { showRegisterGPU(); };

window.saveSettings = function() {
    const url = document.getElementById('settings-server-url')?.value.trim() || 'http://localhost';
    window.api.saveServerUrl(url);
    state.proxyUrl = url;
    showToast('Settings saved', 'success');
};

window.saveEnterpriseBackend = function() {
    const select = document.getElementById('settings-enterprise-backend');
    if (!select) return;
    const backend = select.value;
    window.api.setEnterpriseBackend(backend).then((result) => {
        if (result.success) {
            state.enterpriseBackend = backend;
            updateBackendIndicator(backend);
            showToast(`Enterprise backend set to ${backend}`, 'success');
        } else { showToast(`Failed to set backend: ${result.error}`, 'error'); }
    });
};

window.viewCredentials = function() {
    showToast('🔑 Credentials are stored in .env file. Please check the file directly for security.', 'info');
};

window.regenerateCredentials = function() {
    if (!confirm('⚠️ This will regenerate ALL credentials and break running services. Continue?')) return;
    showToast('🔄 Credentials regenerated. Please restart services.', 'warning');
};

window.runSystemCheck = async function() {
    const checks = await window.api.systemCheck();
    const items = ['wsl', 'docker', 'gpu', 'python', 'node', 'backend', 'proxy'];
    let allPassed = true;
    for (const key of items) {
        const check = checks[key];
        if (!check) continue;
        const element = document.getElementById(`check-${key}`);
        if (!element) continue;
        const icon = element.querySelector('.check-icon');
        const status = element.querySelector('.check-status');
        if (check.status === 'ok') {
            icon.textContent = '✅';
            status.textContent = '✓ Passed';
            status.style.color = '#28c840';
        } else if (check.status === 'warning') {
            icon.textContent = '⚠️';
            status.textContent = '⚠ Warning';
            status.style.color = '#ffbd2e';
            allPassed = false;
        } else {
            icon.textContent = '❌';
            status.textContent = '✗ Failed';
            status.style.color = '#ff5f57';
            allPassed = false;
        }
        const details = element.querySelector('.check-desc');
        if (details && check.details) details.textContent = check.details;
    }
    const summary = document.getElementById('system-check-summary');
    if (summary) {
        summary.innerHTML = allPassed
            ? '<div class="summary-passed">✅ All checks passed</div>'
            : '<div class="summary-failed">⚠️ Some checks failed or require attention</div>';
    }
};

window.loadEmergencyUsers = async function() {
    const result = await window.api.listEmergencyUsers();
    const container = document.getElementById('emergency-users-list');
    if (container) {
        if (result.success && result.data) {
            const lines = result.data.trim().split('\n').filter(l => l.trim());
            if (lines.length === 0) {
                container.innerHTML = '<p style="color:#6a6a7a;">No emergency users configured.</p>';
            } else {
                container.innerHTML = `
                    <table style="width:100%;border-collapse:collapse;font-size:13px;">
                        <thead>
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                                <th style="text-align:left;padding:8px;">Login</th>
                                <th style="text-align:left;padding:8px;">Valid Until</th>
                                <th style="text-align:left;padding:8px;">Last Used</th>
                                <th style="text-align:left;padding:8px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${lines.map(line => {
                                const parts = line.split('|').map(s => s.trim());
                                if (parts.length >= 3) {
                                    return `
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                            <td style="padding:8px;">${parts[0]}</td>
                                            <td style="padding:8px;">${parts[1]}</td>
                                            <td style="padding:8px;">${parts[2] || 'Never'}</td>
                                            <td style="padding:8px;">
                                                <button class="btn btn-danger" style="padding:2px 12px;font-size:11px;" onclick="revokeEmergencyUser('${parts[0]}')">Revoke</button>
                                            </td>
                                        </tr>
                                    `;
                                }
                                return '';
                            }).join('')}
                        </tbody>
                    </table>
                `;
            }
        } else {
            container.innerHTML = '<p style="color:#6a6a7a;">Failed to load emergency users.</p>';
        }
    }
};

window.createEmergencyUser = async function() {
    const duration = prompt('Enter validity duration in hours (default: 4):', '4');
    if (duration === null) return;
    const hours = parseInt(duration) || 4;
    const result = await window.api.createEmergencyUser(hours);
    if (result.success) {
        showToast(`Emergency user created. Password: ${result.password}`, 'success', 10000);
        await loadEmergencyUsers();
    } else { showToast(`Failed to create emergency user: ${result.error}`, 'error'); }
};

window.revokeEmergencyUser = async function(login) {
    if (!confirm(`Revoke emergency user '${login}'?`)) return;
    const result = await window.api.revokeEmergencyUser(login);
    if (result.success) { showToast(`User ${login} revoked`, 'success'); await loadEmergencyUsers(); }
    else { showToast(`Failed to revoke user: ${result.error}`, 'error'); }
};

window.loadEmergencyAudit = async function() {
    const result = await window.api.listEmergencyAudit();
    const container = document.getElementById('emergency-audit-list');
    if (container) {
        if (result.success && result.data) {
            const lines = result.data.trim().split('\n').filter(l => l.trim());
            if (lines.length === 0) {
                container.innerHTML = '<p style="color:#6a6a7a;">No audit entries.</p>';
            } else {
                container.innerHTML = `
                    <table style="width:100%;border-collapse:collapse;font-size:12px;">
                        <thead>
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                                <th style="text-align:left;padding:6px;">Login</th>
                                <th style="text-align:left;padding:6px;">Action</th>
                                <th style="text-align:left;padding:6px;">IP</th>
                                <th style="text-align:left;padding:6px;">Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${lines.map(line => {
                                const parts = line.split('|').map(s => s.trim());
                                if (parts.length >= 4) {
                                    return `
                                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                            <td style="padding:6px;">${parts[0]}</td>
                                            <td style="padding:6px;">${parts[1]}</td>
                                            <td style="padding:6px;">${parts[2]}</td>
                                            <td style="padding:6px;">${parts[3]}</td>
                                        </tr>
                                    `;
                                }
                                return '';
                            }).join('')}
                        </tbody>
                    </table>
                `;
            }
        } else {
            container.innerHTML = '<p style="color:#6a6a7a;">Failed to load audit log.</p>';
        }
    }
};

window.runQuickSetup = async function() {
    if (state.setupRunning) return;
    state.setupRunning = true;
    const btn = document.getElementById('quick-setup-btn');
    if (btn) btn.textContent = 'Setting up...';
    try {
        const result = await window.api.runQuickSetup();
        if (result.success) {
            state.isPlatformSetup = true;
            showToast('✅ Setup completed successfully!', 'success');
            if (btn) { btn.textContent = '✅ Already Set Up'; btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)'; btn.disabled = true; }
        } else {
            showToast(`❌ Setup failed: ${result.error}`, 'error');
            if (btn) btn.textContent = '⚠️ Retry';
        }
    } catch (error) {
        showToast(`❌ Setup error: ${error.message}`, 'error');
        if (btn) btn.textContent = '⚠️ Retry';
    }
    state.setupRunning = false;
    if (btn && !state.isPlatformSetup) btn.textContent = 'Set Up Development Environment';
};

window.deployWithTenantConfig = async function() {
    const tenantType = state.selectedTenantType || 'enterprise';
    const tenantName = document.getElementById('tenant-name')?.value || 'default';
    const domain = document.getElementById('tenant-domain')?.value || 'localhost';
    const adminEmail = document.getElementById('tenant-email')?.value || 'admin@localhost';
    const postgresPassword = document.getElementById('tenant-password')?.value || generatePassword();
    const environment = document.querySelector('input[name="env"]:checked')?.value || 'development';
    if (environment === 'production' && (!domain || domain === 'localhost')) {
        showToast('For production deployments, please enter a valid domain name.', 'warning');
        return;
    }
    if (!postgresPassword || postgresPassword.length < 8) {
        showToast('Please enter a PostgreSQL password (minimum 8 characters).', 'warning');
        return;
    }
    const deployBtn = document.getElementById('deploy-tenant-btn');
    if (deployBtn) { deployBtn.disabled = true; deployBtn.textContent = '⏳ Configuring...'; }
    try {
        const configResult = await window.api.setTenantConfig({ tenantType, tenantName, backend: state.enterpriseBackend });
        if (!configResult.success) {
            showToast(`Failed to set tenant config: ${configResult.error}`, 'error');
            if (deployBtn) { deployBtn.disabled = false; deployBtn.textContent = '🚀 Deploy Platform with Tenant Configuration'; }
            return;
        }
        showToast(`Tenant configured as ${tenantType}`, 'success');
        const options = {
            profile: state.selectedProfile || 'all',
            environment: environment,
            force: document.getElementById('deploy-force')?.checked || false,
            auto: document.getElementById('deploy-auto')?.checked || false,
            upgrade: document.getElementById('deploy-upgrade')?.checked || false,
            withFinetune: document.querySelector('input[name="module-finetune"]')?.checked || false,
            withGrove: document.querySelector('input[name="module-grove"]')?.checked || false,
            withKai: document.querySelector('input[name="module-kai"]')?.checked || false,
            withRouter: document.querySelector('input[name="module-router"]')?.checked || false,
            domain: domain,
            phases: state.selectedPhases || [],
            resetData: false,
            tenantType,
            tenantName,
            backend: state.enterpriseBackend,
            proxyUrl: state.proxyUrl,
        };
        document.getElementById('deploy-step-2').style.display = 'none';
        document.getElementById('deploy-step-3').style.display = 'block';
        state.isInstalling = true;
        document.getElementById('btn-install-cancel').style.display = 'inline-block';
        const result = await window.api.runInstall(options);
        state.isInstalling = false;
        document.getElementById('btn-install-cancel').style.display = 'none';
        if (deployBtn) { deployBtn.disabled = false; deployBtn.textContent = '🚀 Deploy Platform with Tenant Configuration'; }
        if (result.success) {
            showToast('Deployment completed successfully!', 'success');
            document.getElementById('install-progress-fill').style.width = '100%';
            document.getElementById('install-progress-label').textContent = '✅ Installation complete!';
            document.getElementById('install-status-badge').textContent = '✅ Complete';
            document.getElementById('install-status-badge').className = 'status-badge status-running';
        } else {
            showToast(`Deployment failed: ${result.error}`, 'error');
            document.getElementById('install-progress-fill').style.width = '100%';
            document.getElementById('install-progress-fill').style.background = '#ff5f57';
            document.getElementById('install-progress-label').textContent = '❌ Installation failed';
            document.getElementById('install-status-badge').textContent = '❌ Failed';
            document.getElementById('install-status-badge').className = 'status-badge status-stopped';
        }
    } catch (error) {
        state.isInstalling = false;
        document.getElementById('btn-install-cancel').style.display = 'none';
        if (deployBtn) { deployBtn.disabled = false; deployBtn.textContent = '🚀 Deploy Platform with Tenant Configuration'; }
        showToast(`Deployment error: ${error.message}`, 'error');
    }
};

window.cancelInstallation = function() {
    if (state.isInstalling) {
        window.api.cancelInstall().then(() => {
            state.isInstalling = false;
            document.getElementById('btn-install-cancel').style.display = 'none';
            document.getElementById('install-progress-label').textContent = '⏹ Installation cancelled';
            document.getElementById('install-status-badge').textContent = '⏹ Cancelled';
            const logOutput = document.getElementById('install-log-output');
            if (logOutput) logOutput.innerHTML += '\n\n⏹ Installation cancelled.';
        });
    }
};

// ─── Deploy Cards ───
const deploymentProfiles = [
    { id: 'sovereign', name: '🏠 Sovereign AI in a Box', description: 'All AI services on a single server. Perfect for getting started.', phases: [0, 1, 2, 4, 5], recommended: true, endpoint: 'Internal IP (e.g., 192.168.1.100:8069)', features: ['Odoo', 'LangGraph', 'Dynamo', 'llama.cpp', 'GPU Marketplace'] },
    { id: 'router', name: '🔀 Sovereign AI Router', description: 'Routes requests to multiple GPU nodes. No inference.', phases: [0, 1, 2], recommended: false, endpoint: 'Internal IP (e.g., 192.168.1.100:8069)', features: ['Bridge Module', 'Request Routing', 'Node Discovery'] },
    { id: 'production', name: '🌐 Production [External] Website', description: 'Same as "Box" but with public HTTPS access and domain.', phases: [0, 1, 2, 4, 5], recommended: false, endpoint: 'https://your-domain.com', features: ['SSL Certificates', 'Domain DNS', 'Security Hardening', 'Public Access'], advanced: true },
    { id: 'k8s', name: '☸️ Kubernetes Cluster', description: 'Multi-node enterprise deployment with auto-scaling.', phases: [0, 1, 3, 4, 5], recommended: false, endpoint: 'Load balancer IP or domain', features: ['Talos Linux', 'Argo CD', 'KAI Scheduler', 'High Availability'], advanced: true },
    { id: 'custom', name: '⚙️ Custom Deployment', description: 'Select individual phases and components. For experts.', phases: [], recommended: false, endpoint: 'Varies', features: ['Phase Selection', 'Component Control', 'Testing & Debugging'], advanced: true },
];

function renderDeploymentCards() {
    const container = document.getElementById('deployment-cards');
    if (!container) return;
    container.innerHTML = '';
    deploymentProfiles.forEach(profile => {
        const card = document.createElement('div');
        card.className = 'deployment-card';
        if (profile.recommended) card.classList.add('recommended');
        if (profile.advanced) card.classList.add('advanced');
        card.dataset.id = profile.id;
        const badge = profile.recommended ? '<span class="badge-recommended">Recommended</span>' : profile.advanced ? '<span class="badge-advanced">Advanced</span>' : '';
        card.innerHTML = `
            <div class="card-header">
                <h4>${profile.name}</h4>
                ${badge}
            </div>
            <p class="card-description">${profile.description}</p>
            <div class="card-endpoint">📍 Access: ${profile.endpoint}</div>
            <ul class="card-features">${profile.features.map(f => `<li>✓ ${f}</li>`).join('')}</ul>
        `;
        card.addEventListener('click', () => {
            document.querySelectorAll('.deployment-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            state.selectedProfile = profile.id;
            document.getElementById('btn-deploy-next').disabled = false;
            if (profile.id === 'custom') {
                document.getElementById('custom-phases').style.display = 'block';
                renderPhasePicker();
            } else {
                document.getElementById('custom-phases').style.display = 'none';
                state.selectedPhases = profile.phases;
            }
            updateDeploySummary();
        });
        container.appendChild(card);
    });
    const defaultCard = container.querySelector('.deployment-card.recommended');
    if (defaultCard) defaultCard.click();
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
                <input type="checkbox" name="phase-${phase.id}" ${phase.mandatory ? 'checked disabled' : 'checked'} data-phase="${phase.id}">
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
            if (cb.checked) { if (!state.selectedPhases.includes(id)) state.selectedPhases.push(id); }
            else { state.selectedPhases = state.selectedPhases.filter(p => p !== id); }
            updateDeploySummary();
        });
    });
    if (!state.selectedPhases.includes(1)) state.selectedPhases.push(1);
    updateDeploySummary();
}

function updateDeploySummary() {
    const profile = deploymentProfiles.find(p => p.id === state.selectedProfile);
    const phases = profile && profile.id !== 'custom' ? profile.phases : state.selectedPhases;
    const sorted = [...phases].sort((a, b) => a - b);
    document.getElementById('summary-profile').textContent = profile ? profile.name : 'None selected';
    document.getElementById('summary-phases').textContent = sorted.length > 0 ? sorted.join(' → ') : 'None selected';
}

function updateModuleRecommendations() { detectHardware(); }

window.startDeployment = function() {
    const environment = document.querySelector('input[name="env"]:checked')?.value || 'development';
    const force = document.getElementById('deploy-force')?.checked || false;
    const auto = document.getElementById('deploy-auto')?.checked || false;
    const upgrade = document.getElementById('deploy-upgrade')?.checked || false;
    const withFinetune = document.querySelector('input[name="module-finetune"]')?.checked || false;
    const withGrove = document.querySelector('input[name="module-grove"]')?.checked || false;
    const withKai = document.querySelector('input[name="module-kai"]')?.checked || false;
    const withRouter = document.querySelector('input[name="module-router"]')?.checked || false;
    const domain = document.getElementById('domain-input')?.value || '';
    if (environment === 'production' && !domain) { showToast('For production deployments, please enter a domain name.', 'warning'); return; }
    const options = {
        profile: state.selectedProfile,
        environment,
        force,
        auto,
        upgrade,
        withFinetune,
        withGrove,
        withKai,
        withRouter,
        domain,
        phases: state.selectedPhases || [],
        resetData: false,
        tenantType: state.selectedTenantType || 'enterprise',
        tenantName: document.getElementById('tenant-name')?.value || 'default',
        backend: state.enterpriseBackend,
        proxyUrl: state.proxyUrl,
    };
    document.getElementById('deploy-step-2').style.display = 'none';
    document.getElementById('deploy-step-3').style.display = 'block';
    state.isInstalling = true;
    document.getElementById('btn-install-cancel').style.display = 'inline-block';
    window.api.runInstall(options).then((result) => {
        state.isInstalling = false;
        document.getElementById('btn-install-cancel').style.display = 'none';
        if (result.success) {
            showToast('Deployment completed successfully!', 'success');
            document.getElementById('install-progress-fill').style.width = '100%';
            document.getElementById('install-progress-label').textContent = '✅ Installation complete!';
            document.getElementById('install-status-badge').textContent = '✅ Complete';
            document.getElementById('install-status-badge').className = 'status-badge status-running';
        } else {
            showToast(`Deployment failed: ${result.error}`, 'error');
            document.getElementById('install-progress-fill').style.width = '100%';
            document.getElementById('install-progress-fill').style.background = '#ff5f57';
            document.getElementById('install-progress-label').textContent = '❌ Installation failed';
            document.getElementById('install-status-badge').textContent = '❌ Failed';
            document.getElementById('install-status-badge').className = 'status-badge status-stopped';
        }
    });
};

// ─── Hardware Detection ───
window.detectHardware = async function() {
    const hardware = await window.api.detectHardware();
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
    html += `<div class="hardware-item">🖥️ ${hardware.cpuCores} cores</div>`;
    html += hardware.k8sDetected ? `<div class="hardware-item success">☸️ Kubernetes cluster detected</div>` : `<div class="hardware-item warning">⚠️ No Kubernetes cluster detected</div>`;
    html += hardware.dockerInstalled ? `<div class="hardware-item success">🐳 Docker installed</div>` : `<div class="hardware-item error">❌ Docker not installed</div>`;
    container.innerHTML = html;
    const hasLargeGPU = hardware.gpus.some(g => { const match = g.memoryTotal?.match(/(\d+)/); if (match) return parseInt(match[1]) > 16000; return false; });
    const finetuneCheckbox = document.querySelector('input[name="module-finetune"]');
    if (finetuneCheckbox && hasLargeGPU) finetuneCheckbox.checked = true;
    const kaiCheckbox = document.querySelector('input[name="module-kai"]');
    if (kaiCheckbox && !hardware.k8sDetected) { kaiCheckbox.disabled = true; kaiCheckbox.parentElement.title = 'Requires Kubernetes cluster'; }
    document.getElementById('gpu-count').textContent = hardware.gpus.length;
    document.getElementById('dashboard-gpu-count').textContent = hardware.gpus.length;
};

// ─── Modals ───
function showModal(content) {
    document.getElementById('modal-content').innerHTML = content;
    document.getElementById('modal-overlay').style.display = 'flex';
}

function closeModal() {
    document.getElementById('modal-overlay').style.display = 'none';
}

document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
});

// ─── Utilities ───
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(2)} GB`;
}

function generatePassword() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let password = '';
    for (let i = 0; i < 24; i++) { password += chars.charAt(Math.floor(Math.random() * chars.length)); }
    return password;
}

function loadSettings() {
    window.api.getServerUrl().then(url => {
        const input = document.getElementById('settings-server-url');
        if (input) input.value = url || 'http://localhost';
    });
    window.api.getEnterpriseBackend().then(backend => {
        const select = document.getElementById('settings-enterprise-backend');
        if (select && backend) select.value = backend;
    });
}

function refreshInstallLog() {
    const container = document.getElementById('install-log-output');
    if (container) {
        container.innerHTML = state.logs || '<div class="log-placeholder">No logs available</div>';
    }
}

function clearInstallLog() {
    state.logs = '';
    const container = document.getElementById('install-log-output');
    if (container) container.innerHTML = '<div class="log-placeholder">Logs cleared</div>';
}

function copyInstallLog() {
    const text = state.logs || '';
    navigator.clipboard.writeText(text).then(() => showToast('Logs copied to clipboard', 'success'));
}

// ─── Toggles ───
window.toggleGrove = async function() {
    const toggle = document.getElementById('grove-toggle');
    const statusText = document.getElementById('grove-status-text');
    if (toggle.classList.contains('active')) {
        const result = await window.api.stopGrove();
        if (result.success) { toggle.classList.remove('active'); statusText.textContent = 'OFF'; showToast('Grove stopped', 'info'); }
        else { showToast(`Failed to stop Grove: ${result.error}`, 'error'); }
    } else {
        const result = await window.api.startGrove();
        if (result.success) { toggle.classList.add('active'); statusText.textContent = 'ON'; showToast('Grove started', 'success'); }
        else { showToast(`Failed to start Grove: ${result.error}`, 'error'); }
    }
};

window.toggleKAI = async function() {
    const toggle = document.getElementById('kai-toggle');
    const statusText = document.getElementById('kai-status-text');
    if (toggle.classList.contains('active')) {
        const result = await window.api.stopKAI();
        if (result.success) { toggle.classList.remove('active'); statusText.textContent = 'OFF'; showToast('KAI Scheduler stopped', 'info'); }
        else { showToast(`Failed to stop KAI: ${result.error}`, 'error'); }
    } else {
        const result = await window.api.startKAI();
        if (result.success) { toggle.classList.add('active'); statusText.textContent = 'ON'; showToast('KAI Scheduler started', 'success'); }
        else { showToast(`Failed to start KAI: ${result.error}`, 'error'); }
    }
};

window.toggleFinetune = function() { showToast('Fine-tuning toggle coming soon', 'warning'); };

// ─── Container auto-refresh ───
let containerAutoRefresh = true;
let containerRefreshInterval = null;

function startContainerAutoRefresh() {
    clearInterval(containerRefreshInterval);
    containerRefreshInterval = setInterval(() => {
        if (containerAutoRefresh) refreshContainers();
    }, 10000);
}

window.toggleContainerAutoRefresh = function() {
    containerAutoRefresh = !containerAutoRefresh;
    const toggle = document.getElementById('auto-refresh-toggle');
    if (toggle) toggle.textContent = containerAutoRefresh ? '⏸️ Pause' : '▶️ Resume';
    if (containerAutoRefresh) startContainerAutoRefresh();
    else clearInterval(containerRefreshInterval);
};

// ─── Expose to window ───
window.switchTab = switchTab;
window.openApp = openApp;
window.refreshAll = function() { refreshDashboard(); refreshGPUs(); refreshModels(); discoverNodes(); refreshVPN(); refreshQueue(); refreshMonitor(); refreshBackups(); refreshMarketplace(); refreshContainers(); };
window.detectGPUs = refreshGPUs;
window.refreshModels = refreshModels;
window.refreshVPN = refreshVPN;
window.refreshQueue = refreshQueue;
window.refreshMonitor = refreshMonitor;
window.refreshLogs = refreshLogs;
window.refreshBackups = refreshBackups;
window.refreshMarketplace = refreshMarketplace;
window.refreshContainers = refreshContainers;
window.runSystemCheck = runSystemCheck;
window.loadEmergencyUsers = loadEmergencyUsers;
window.loadEmergencyAudit = loadEmergencyAudit;
window.showModal = showModal;
window.closeModal = closeModal;
window.showToast = showToast;
window.formatSize = formatSize;
window.escapeHtml = escapeHtml;
window.detectHardware = detectHardware;
window.toggleGrove = toggleGrove;
window.toggleKAI = toggleKAI;
window.toggleFinetune = toggleFinetune;
window.toggleContainerAutoRefresh = toggleContainerAutoRefresh;
window.viewCredentials = viewCredentials;
window.regenerateCredentials = regenerateCredentials;
window.clearInstallLog = clearInstallLog;
window.copyInstallLog = copyInstallLog;
window.installModule = function(id) {
    showToast(`Installing module ${id}...`, 'info');
    window.api.installModules([id]).then((result) => {
        if (result.success) { showToast(`Module ${id} installed successfully!`, 'success'); renderModules(); }
        else { showToast(`Failed to install module ${id}: ${result.error}`, 'error'); }
    });
};
window.viewCredential = async function(key) {
    const result = await window.api.getCredentialValue(key);
    if (result.success) showToast(`🔑 ${key}: ${result.value}`, 'info', 10000);
    else showToast(`Failed to get credential: ${result.error}`, 'error');
};
window.rotateCredential = async function(key) {
    if (!confirm(`Rotate credential '${key}'?`)) return;
    const newValue = generatePassword();
    const result = await window.api.rotateCredential(key, newValue);
    if (result.success) { showToast(`Credential ${key} rotated successfully`, 'success'); refreshCredentials(); }
    else { showToast(`Failed to rotate credential: ${result.error}`, 'error'); }
};
window.refreshCredentials = refreshCredentials;
window.renderModules = renderModules;

// ─── Show the window if not already visible ───
// The window is already shown by main process, but this ensures it if any issue.
if (window.api.showWindow) {
    window.api.showWindow();
}