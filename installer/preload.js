const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getFeatureFlags: () => ipcRenderer.invoke('get-feature-flags'),
  runInstall: (options) => ipcRenderer.invoke('run-install', options),
  cancelInstall: () => ipcRenderer.invoke('cancel-install'),
  openUrl: (url) => ipcRenderer.invoke('open-url', url),
  onInstallOutput: (callback) => {
    ipcRenderer.on('install-output', (event, data) => callback(data));
  },
});