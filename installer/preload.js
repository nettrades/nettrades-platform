/**
 * =============================================================================
 * NETTRADES Installer - Preload Script
 * =============================================================================
 *
 * FILE: installer/preload.js
 *
 * PURPOSE:
 *   This script runs in the renderer process before the web page loads.
 *   It exposes a safe, whitelisted API to the renderer via contextBridge,
 *   allowing the UI to communicate with the main process without exposing
 *   Node.js APIs directly – a security best practice.
 *
 * SECURITY:
 *   - Only specific functions are exposed.
 *   - All communication is via IPC (inter‑process communication).
 *   - No direct access to Node.js or the file system.
 * =============================================================================
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe API to the renderer process
contextBridge.exposeInMainWorld('api', {
  // System checks
  checkDocker: () => ipcRenderer.invoke('check-docker'),

  // Installation
  runInstall: (options) => ipcRenderer.invoke('run-install', options),
  cancelInstall: () => ipcRenderer.invoke('cancel-install'),

  // Status
  getStatus: () => ipcRenderer.invoke('get-status'),

  // WireGuard
  generateWireGuardKey: () => ipcRenderer.invoke('generate-wireguard-key'),

  // Service access
  openOdoo: () => ipcRenderer.invoke('open-odoo'),
  openGrafana: () => ipcRenderer.invoke('open-grafana'),
  openGPUStack: () => ipcRenderer.invoke('open-gpustack'),

  // Installation output streaming
  onInstallOutput: (callback) => {
    ipcRenderer.on('install-output', (event, data) => callback(data));
  },
  removeInstallOutputListener: () => {
    ipcRenderer.removeAllListeners('install-output');
  },
});