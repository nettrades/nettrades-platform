// renderer.js
const tabs = document.querySelectorAll('.tab');
const tabContents = {
  welcome: document.getElementById('tab-welcome'),
  deployment: document.getElementById('tab-deployment'),
  progress: document.getElementById('tab-progress'),
};

let currentTab = 'welcome';
let featureFlags = {};

// Tab switching
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const tabName = tab.dataset.tab;
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    Object.keys(tabContents).forEach(key => {
      tabContents[key].classList.toggle('active', key === tabName);
    });
    currentTab = tabName;
  });
});

// Load feature flags
async function loadFeatureFlags() {
  const flags = await window.api.getFeatureFlags();
  featureFlags = flags;
  renderDeploymentCards();
}

function renderDeploymentCards() {
  const container = document.getElementById('deployment-cards');
  container.innerHTML = '';

  const deployments = [
    { id: 'sovereign-ai', name: 'Sovereign AI in a Box', desc: 'Complete AI infrastructure on a single machine.', features: ['Dynamo', 'llama.cpp', 'LangGraph', 'Odoo', 'Ask Someone', 'Good Answer'], ready: true },
    { id: 'router', name: 'Sovereign AI Router', desc: 'Intelligent routing for distributed inference.', features: ['LLMRouter', 'LiteLLM', 'KAI Scheduler'], ready: featureFlags.FEATURE_ROUTER },
    { id: 'marketplace', name: 'GPU Marketplace', desc: 'GPU sharing and rental marketplace.', features: ['Marketplace', 'P2P', 'Token Economics'], ready: featureFlags.FEATURE_GPU_MARKETPLACE },
    { id: 'training', name: 'AI Training & Development', desc: 'Fine-tuning and model training.', features: ['Unsloth', 'Axolotl', 'Training Pipeline'], ready: featureFlags.FEATURE_TRAINING },
    { id: 'enterprise', name: 'Autonomous Enterprise Platform', desc: 'Full enterprise suite with CRM, ERP, AI agents.', features: ['Odoo ERP/CRM', 'Recruitment', 'Lead Gen', 'Freelance'], ready: featureFlags.FEATURE_ENTERPRISE },
  ];

  deployments.forEach(dep => {
    const card = document.createElement('div');
    card.className = `deployment-card ${dep.ready ? '' : 'coming-soon'}`;
    card.innerHTML = `
      <h3>${dep.name}</h3>
      <p>${dep.desc}</p>
      <ul>${dep.features.map(f => `<li>${f}</li>`).join('')}</ul>
      ${dep.ready ? '<button class="btn select-btn" data-id="' + dep.id + '">Select</button>' : '<span class="badge">Coming Soon</span>'}
    `;
    container.appendChild(card);
  });

  // Handle selection
  document.querySelectorAll('.select-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.target.dataset.id;
      document.getElementById('selected-deployment').value = id;
      // You could show additional options
    });
  });
}

// Install button
document.getElementById('btn-install').addEventListener('click', async () => {
  const selected = document.getElementById('selected-deployment')?.value || 'sovereign-ai';
  // Switch to progress tab
  tabs.forEach(t => t.classList.remove('active'));
  document.querySelector('.tab[data-tab="progress"]').classList.add('active');
  Object.keys(tabContents).forEach(key => {
    tabContents[key].classList.toggle('active', key === 'progress');
  });
  currentTab = 'progress';

  const options = {
    profile: selected,
    environment: 'production', // could be chosen
    force: false,
    auto: true,
  };

  // Setup log output
  const logOutput = document.getElementById('log-output');
  const progressFill = document.getElementById('progress-fill');
  const progressLabel = document.getElementById('progress-label');

  // Listen to output
  window.api.onInstallOutput((data) => {
    const lines = logOutput.textContent.split('\n');
    lines.push(data);
    if (lines.length > 200) lines.splice(0, lines.length - 200);
    logOutput.textContent = lines.join('\n');
    logOutput.scrollTop = logOutput.scrollHeight;

    // Update progress based on phase
    if (data.includes('Phase 0')) { progressFill.style.width = '10%'; progressLabel.textContent = 'Phase 0: System Preparation...'; }
    else if (data.includes('Phase 1')) { progressFill.style.width = '30%'; progressLabel.textContent = 'Phase 1: Environment Setup...'; }
    else if (data.includes('Phase 2')) { progressFill.style.width = '50%'; progressLabel.textContent = 'Phase 2: Deployment...'; }
    else if (data.includes('Phase 3')) { progressFill.style.width = '70%'; progressLabel.textContent = 'Phase 3: GPU Setup...'; }
    else if (data.includes('Phase 4')) { progressFill.style.width = '85%'; progressLabel.textContent = 'Phase 4: Module Installation...'; }
    else if (data.includes('Phase 5')) { progressFill.style.width = '95%'; progressLabel.textContent = 'Phase 5: Monitoring Setup...'; }
    else if (data.includes('Setup Complete')) { progressFill.style.width = '100%'; progressLabel.textContent = '✅ Installation complete!'; }
  });

  try {
    await window.api.runInstall(options);
    progressFill.style.width = '100%';
    progressLabel.textContent = '✅ Installation complete!';
  } catch (err) {
    progressLabel.textContent = '❌ Installation failed';
    logOutput.textContent += '\n\n❌ Error: ' + (err.output || err.message);
  }
});

// Load flags on start
loadFeatureFlags();