#!/bin/bash
# =============================================================================
# NETTRADES Installer - Post-Installation Script (Linux DEB)
# =============================================================================
#
# FILE: installer/scripts/postinstall.sh
#
# PURPOSE:
#   This script runs after the DEB package is installed on Linux systems.
#   It sets up desktop shortcuts and ensures the binary is in the PATH.
#
# USAGE:
#   Automatically called by dpkg/apt after installation.
# =============================================================================

echo "NETTRADES Installer installed successfully."
echo "You can now run the installer from your applications menu."

# Create desktop entry
cat > /usr/share/applications/nettrades-installer.desktop << EOF
[Desktop Entry]
Name=NETTRADES Installer
Comment=Install and manage the NETTRADES Platform
Exec=/usr/bin/nettrades-installer
Icon=nettrades-installer
Terminal=false
Type=Application
Categories=Development;System;
EOF

# Ensure the binary is linked to /usr/bin
if [ ! -f /usr/bin/nettrades-installer ] && [ -f /opt/nettrades-installer/nettrades-installer ]; then
    ln -sf /opt/nettrades-installer/nettrades-installer /usr/bin/nettrades-installer
fi

# Make the platform scripts executable (they are inside the app resources)
if [ -d /usr/share/nettrades-installer/resources/scripts ]; then
    chmod +x /usr/share/nettrades-installer/resources/scripts/*.sh
fi

echo "✅ Desktop entry created."