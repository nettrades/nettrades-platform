/**
 * =============================================================================
 * NETTRADES Installer - Renderer Process
 * =============================================================================
 *
 * FILE: installer/renderer.js
 *
 * PURPOSE:
 *   This script controls the UI logic for the installer wizard:
 *     1. Navigation between steps
 *     2. System checks (Docker, OS, WireGuard)
 *     3. Installation progress tracking
 *     4. Service status updates after installation
 *     5. WireGuard key generation
 *
 * The UI follows a step‑by‑step wizard pattern:
 *   System Check → Configuration → Installation → Complete
 * =============================================================================
 */

// ──────────────────────────────────────────────────────────────────────────────
// DOM References
// ──────────────────────────────────────────────────────────────────────────────

const steps = {
  check: document.getElementById('step-check'),
  config: document.getElementById('step-config'),
  progress: document.getElementById('step-progress'),
  complete: document.getElementById('step-complete'),
};

const checkItems = {
  docker: document.getElementById('check-docker'),
  compose: document.getElementById('check-compose'),
  os: document.getElementById('check-os'),
  wireguard: document.getElementById('check-wireguard'),
};

const btnCheck = document.getElementById('btn-check');
const btnInstall = document.getElementById('btn-install');
const btnCancel = document.getElementById('btn-cancel');
const btnOpenOdoo = document.getElementById('btn-open-odoo');
const btnOpenGrafana = document.getElementById('btn-open-grafana');
const btnOpenGPUStack = document.getElementById('btn-open-gpustack');
const btnGenerateWireGuard = document.getElementById('btn-generate-wireguard');
const progressFill = document.getElementById('progress-fill');
const progressLabel = document.getElementById('progress-label');
const logOutput = document.getElementById('log-output');
const checkError = document.getElementById('check-error');

let isInstalling = false;

// ──────────────────────────────────────────────────────────────────────────────
// Step 1: System Check
// ──────────────────────────────────────────────────────────────────────────────

btnCheck.addEventListener('click', async () => {
  btnCheck.disabled = true;
  btnCheck.textContent = 'Checking...';

  // Reset check states
  Object.values(checkItems).forEach(el => {
    el.querySelector('.check-icon').textContent = '⏳';
    el.style.color = '';
  });
  checkError.style.display = 'none';

  try {
    // OS check
    const osCheck = checkItems.os;
    const platform = navigator.platform;
    if (platform.includes('Win') || platform.includes('Mac') || platform.includes('Linux')) {
      osCheck.querySelector('.check-icon').textContent = '✅';
      osCheck.style.color = 'var(--success)';
    } else {
      osCheck.querySelector('.check-icon').textContent = '❌';
      osCheck.style.color = 'var(--error)';
      checkError.textContent = 'Unsupported OS. Please use Windows, macOS, or Linux.';
      checkError.style.display = 'block';
      btnCheck.disabled = false;
      btnCheck.textContent = 'Check System';
      return;
    }

    // Docker check
    const result = await window.api.checkDocker();

    const dockerItem = checkItems.docker;
    if (result.docker) {
      dockerItem.querySelector('.check-icon').textContent = '✅';
      dockerItem.style.color = 'var(--success)';
    } else {
      dockerItem.querySelector('.check-icon').textContent = '❌';
      dockerItem.style.color = 'var(--error)';
      checkError.textContent = 'Docker is not installed. Please install Docker Desktop.';
      checkError.style.display = 'block';
    }

    const composeItem = checkItems.compose;
    if (result.compose) {
      composeItem.querySelector('.check-icon').textContent = '✅';
      composeItem.style.color = 'var(--success)';
    } else {
      composeItem.querySelector('.check-icon').textContent = '❌';
      composeItem.style.color = 'var(--error)';
      if (!checkError.textContent) {
        checkError.textContent = 'Docker Compose is not installed.';
        checkError.style.display = 'block';
      }
    }

    // WireGuard is optional – we just report whether it's available
    try {
      const wgResult = await window.api.generateWireGuardKey();
      const wgCheck = checkItems.wireguard;
      if (wgResult) {
        wgCheck.querySelector('.check-icon').textContent = '✅';
        wgCheck.style.color = 'var(--success)';
      }
    } catch (err) {
      // WireGuard is not critical for installation (the script will install it)
      const wgCheck = checkItems.wireguard;
      wgCheck.querySelector('.check-icon').textContent = 'ℹ️';
      wgCheck.style.color = 'var(--warning)';
    }

    // If Docker and Compose are present, enable installation
    if (result.docker && result.compose) {
      showStep('config');
    }
  } catch (err) {
    checkError.textContent = `Error: ${err.message}`;
    checkError.style.display = 'block';
  }

  btnCheck.disabled = false;
  btnCheck.textContent = 'Check System';
});

// ──────────────────────────────────────────────────────────────────────────────
// Step 2: Installation
// ──────────────────────────────────────────────────────────────────────────────

btnInstall.addEventListener('click', async () => {
  if (isInstalling) return;
  isInstalling = true;

  const profile = document.getElementById('profile').value;
  const environment = document.getElementById('environment').value;
  const force = document.getElementById('force').checked;
  const auto = document.getElementById('auto').checked;

  showStep('progress');
  progressFill.style.width = '0%';
  progressLabel.textContent = 'Starting installation...';
  logOutput.innerHTML = '';
  btnCancel.style.display = 'inline-block';

  // Set up output listener
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

    // Append to log (keep last 100 lines)
    const lines = logOutput.textContent.split('\n');
    lines.push(data);
    if (lines.length > 100) {
      lines.splice(0, lines.length - 100);
    }
    logOutput.textContent = lines.join('\n');
    logOutput.scrollTop = logOutput.scrollHeight;
  });

  try {
    const result = await window.api.runInstall({
      profile,
      environment,
      force,
      auto
    });
    isInstalling = false;
    btnCancel.style.display = 'none';
    progressFill.style.width = '100%';
    progressLabel.textContent = '✅ Installation complete!';

    setTimeout(() => {
      showStep('complete');
      updateServiceStatus();
    }, 1000);

  } catch (err) {
    isInstalling = false;
    btnCancel.style.display = 'none';
    progressFill.style.width = '100%';
    progressFill.style.background = 'var(--error)';
    progressLabel.textContent = '❌ Installation failed';
    logOutput.textContent += `\n\n❌ Error: ${err.output || err.message}`;
  }
});

// Cancel button
btnCancel.addEventListener('click', async () => {
  if (isInstalling) {
    const result = await window.api.cancelInstall();
    if (result.success) {
      isInstalling = false;
      btnCancel.style.display = 'none';
      progressLabel.textContent = '⏹️ Installation cancelled';
      logOutput.textContent += '\n\n⏹️ Installation cancelled by user.';
    }
  }
});

// ──────────────────────────────────────────────────────────────────────────────
// Step 4: Complete
// ──────────────────────────────────────────────────────────────────────────────

async function updateServiceStatus() {
  try {
    const status = await window.api.getStatus();

    const statusMap = {
      odoo: document.getElementById('status-odoo'),
      langgraph: document.getElementById('status-langgraph'),
      gpustack: document.getElementById('status-gpustack'),
      postgres: document.getElementById('status-postgres'),
    };

    for (const [key, el] of Object.entries(statusMap)) {
      if (status[key]) {
        el.textContent = '✅ Running';
        el.className = 'status-running';
      } else {
        el.textContent = '⏳ Not running';
        el.className = 'status-stopped';
      }
    }
  } catch (err) {
    console.error('Failed to get status:', err);
  }
}

// Open services
btnOpenOdoo.addEventListener('click', () => {
  window.api.openOdoo();
});

btnOpenGrafana.addEventListener('click', () => {
  window.api.openGrafana();
});

btnOpenGPUStack.addEventListener('click', () => {
  window.api.openGPUStack();
});

btnGenerateWireGuard.addEventListener('click', async () => {
  try {
    const keys = await window.api.generateWireGuardKey();
    if (keys) {
      dialog.showMessageBox({
        type: 'info',
        title: 'WireGuard Key Pair',
        message: `Public Key: ${keys.publicKey}\n\nPrivate Key: ${keys.privateKey}`,
        buttons: ['OK']
      });
    }
  } catch (err) {
    dialog.showMessageBox({
      type: 'error',
      title: 'Error',
      message: `Failed to generate WireGuard key: ${err.message}`,
      buttons: ['OK']
    });
  }
});

// ──────────────────────────────────────────────────────────────────────────────
// Utility Functions
// ──────────────────────────────────────────────────────────────────────────────

function showStep(stepName) {
  Object.keys(steps).forEach(key => {
    steps[key].classList.remove('active');
  });
  steps[stepName].classList.add('active');
}

// ──────────────────────────────────────────────────────────────────────────────
// Initialize
// ──────────────────────────────────────────────────────────────────────────────

showStep('check');

// Auto-check on load
setTimeout(() => {
  btnCheck.click();
}, 500);