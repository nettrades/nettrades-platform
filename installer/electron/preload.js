const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  // System
  getSystemInfo: () => ipcRenderer.invoke('system-info'),
  
  // Docker
  dockerStatus: () => ipcRenderer.invoke('docker-status'),
  dockerStart: (service) => ipcRenderer.invoke('docker-start', service),
  dockerStop: (service) => ipcRenderer.invoke('docker-stop', service),
  
  // Backup
  backup: () => ipcRenderer.invoke('backup'),
  restore: (path) => ipcRenderer.invoke('restore', path),
  
  // WireGuard
  wireguardStatus: () => ipcRenderer.invoke('wireguard-status'),
  
  // Models
  listModels: () => ipcRenderer.invoke('list-models'),
});