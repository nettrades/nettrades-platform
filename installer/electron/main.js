const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { exec } = require('child_process');
const fs = require('fs');
const os = require('os');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    icon: path.join(__dirname, '../build/icon.png'),
  });

  const isDev = process.env.NODE_ENV === 'development';
  
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../build/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

// ===== IPC Handlers for system operations =====

// Get system info
ipcMain.handle('system-info', async () => {
  return {
    platform: os.platform(),
    arch: os.arch(),
    cpus: os.cpus().length,
    totalMemory: os.totalmem(),
    freeMemory: os.freemem(),
    hostname: os.hostname(),
  };
});

// Check Docker status
ipcMain.handle('docker-status', async () => {
  return new Promise((resolve) => {
    exec('docker ps', (error, stdout) => {
      if (error) {
        resolve({ running: false, error: error.message });
      } else {
        const containers = stdout.split('\n').slice(1).filter(line => line.trim());
        resolve({ running: true, containers: containers.length });
      }
    });
  });
});

// Start/Stop Docker containers
ipcMain.handle('docker-start', async (event, service) => {
  return new Promise((resolve) => {
    exec(`docker-compose -f /home/owner/nettrades-platform/deploy/docker/docker-compose.yaml up -d ${service || ''}`, 
      (error, stdout) => {
        resolve({ success: !error, output: stdout, error: error?.message });
      }
    );
  });
});

ipcMain.handle('docker-stop', async (event, service) => {
  return new Promise((resolve) => {
    exec(`docker-compose -f /home/owner/nettrades-platform/deploy/docker/docker-compose.yaml stop ${service || ''}`,
      (error, stdout) => {
        resolve({ success: !error, output: stdout, error: error?.message });
      }
    );
  });
});

// Backup
ipcMain.handle('backup', async () => {
  return new Promise((resolve) => {
    exec('/home/owner/nettrades-platform/scripts/backup.sh --auto', (error, stdout, stderr) => {
      resolve({ success: !error, output: stdout, error: stderr || error?.message });
    });
  });
});

// Restore
ipcMain.handle('restore', async (event, backupPath) => {
  return new Promise((resolve) => {
    exec(`/home/owner/nettrades-platform/scripts/restore.sh ${backupPath} --auto`, (error, stdout, stderr) => {
      resolve({ success: !error, output: stdout, error: stderr || error?.message });
    });
  });
});

// Get WireGuard status
ipcMain.handle('wireguard-status', async () => {
  return new Promise((resolve) => {
    exec('wg show', (error, stdout) => {
      if (error) {
        resolve({ running: false, error: error.message });
      } else {
        const peers = stdout.match(/peer: /g)?.length || 0;
        resolve({ running: true, peers });
      }
    });
  });
});

// Get installed models
ipcMain.handle('list-models', async () => {
  const modelsDir = '/home/owner/nettrades-platform/deploy/docker/dynamo-data/models';
  try {
    const files = fs.readdirSync(modelsDir);
    const models = files
      .filter(f => f.endsWith('.gguf') || f.endsWith('.bin'))
      .map(f => {
        const stats = fs.statSync(`${modelsDir}/${f}`);
        return { name: f, size: stats.size, path: `${modelsDir}/${f}` };
      });
    return models;
  } catch (error) {
    return { error: error.message };
  }
});