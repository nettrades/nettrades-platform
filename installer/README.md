# NETTRADES Platform Installer

This is the Electron-based desktop installer for the NETTRADES Platform – a sovereign AI control centre for autonomous enterprises.

## Prerequisites

- **Docker** and **Docker Compose** must be installed on the target machine.
- The installer will check for these and guide you if they are missing.

## Building the Installer

Once phase-system.sh has run (It runs npm install), a developer (or CI) can build the installer without any extra setup:
bash

# Clone the repository (already done)
cd nettrades-platform
cd installer

# Install Node.js dependencies (npm is now installed)
npm install

# Build the installer
npm run build:all   