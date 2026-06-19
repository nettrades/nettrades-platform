# Getting Started as a Developer

This guide walks you through setting up a complete NETTRADES.AI development environment.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **Operating System** | Windows 10/11 Pro + WSL2, or Ubuntu 22.04+ | Ubuntu 24.04 |
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 16 GB | 32+ GB |
| **Storage** | 50 GB free | 100+ GB SSD |
| **Python** | 3.12.9 | 3.12.9 |
| **PostgreSQL** | 18 | 18 with pgvector |
| **Docker** | 27.x | 27.x |
| **Git** | Latest | Latest |
| **Internet** | Broadband | Stable broadband |

---

## Step 1: Install WSL2 (Windows Only)

If you're on Windows, install WSL2.

### 1.1 Enable WSL and Virtual Machine Platform

Open PowerShell as Administrator:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
# Restart when prompted
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
# Restart again
wsl --set-default-version 2