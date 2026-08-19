# =============================================================================
# NETTRADES Platform - One-Click Launcher for Windows/WSL2
# =============================================================================
# PURPOSE:
#   Fully automates the deployment of NETTRADES Platform on Windows 10/11
#   with WSL2 and Docker Desktop. Handles installation, setup, and deployment
#   in a single PowerShell script.
#
# USAGE:
#   Right-click launch.ps1 and select "Run with PowerShell", OR
#   Open PowerShell as Administrator and run: .\launch.ps1
#
# FEATURES:
#   - Automatically installs WSL2 and Ubuntu 24.04 if missing
#   - Automatically installs Docker Desktop if missing
#   - Starts Docker Desktop if not running
#   - Clones the NETTRADES repository inside WSL
#   - Runs the full deployment with --auto flag (non-interactive)
#   - Displays access URLs upon completion
# =============================================================================

# -----------------------------------------------------------------------------
# REQUIREMENTS: Run as Administrator
# -----------------------------------------------------------------------------
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "This script requires Administrator privileges." -ForegroundColor Red
    Write-Host "Please right-click PowerShell and select 'Run as Administrator'." -ForegroundColor Yellow
    Write-Host "Then run: .\launch.ps1" -ForegroundColor Cyan
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " NETTRADES Platform - One-Click Launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------------------------
# Step 1: Ensure WSL2 is installed
# -----------------------------------------------------------------------------
Write-Host "[1/6] Checking WSL2 installation..." -ForegroundColor Yellow

$wslStatus = wsl --list --verbose 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "WSL2 not found. Installing..." -ForegroundColor Yellow
    wsl --install -d Ubuntu-24.04
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WSL2 installation failed. Please install manually:" -ForegroundColor Red
        Write-Host "  wsl --install -d Ubuntu-24.04" -ForegroundColor Cyan
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "WSL2 installed. Please restart your computer and run this script again." -ForegroundColor Green
    Read-Host "Press Enter to exit"
    exit 0
}

# Check if Ubuntu-24.04 is installed
if (-not (wsl --list --verbose | Select-String "Ubuntu-24.04")) {
    Write-Host "Ubuntu-24.04 not found. Installing..." -ForegroundColor Yellow
    wsl --install -d Ubuntu-24.04
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install Ubuntu-24.04. Please install manually." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "Ubuntu-24.04 installed. Please restart your computer and run this script again." -ForegroundColor Green
    Read-Host "Press Enter to exit"
    exit 0
}

# Ensure WSL2 is the default version
wsl --set-default-version 2 2>&1 | Out-Null
Write-Host "WSL2 is ready." -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 2: Ensure Docker Desktop is installed
# -----------------------------------------------------------------------------
Write-Host "[2/6] Checking Docker Desktop installation..." -ForegroundColor Yellow

$dockerPath = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerPath) {
    Write-Host "Docker Desktop not found. Installing..." -ForegroundColor Yellow
    try {
        winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Winget installation failed. Please install Docker Desktop manually:" -ForegroundColor Red
            Write-Host "  https://www.docker.com/products/docker-desktop/" -ForegroundColor Cyan
            Read-Host "Press Enter to exit"
            exit 1
        }
        Write-Host "Docker Desktop installed. Please restart your computer and run this script again." -ForegroundColor Green
        Read-Host "Press Enter to exit"
        exit 0
    } catch {
        Write-Host "Failed to install Docker Desktop: $_" -ForegroundColor Red
        Write-Host "Please install Docker Desktop manually from:" -ForegroundColor Yellow
        Write-Host "  https://www.docker.com/products/docker-desktop/" -ForegroundColor Cyan
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Write-Host "Docker Desktop is installed." -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 3: Ensure Docker Desktop is running
# -----------------------------------------------------------------------------
Write-Host "[3/6] Starting Docker Desktop..." -ForegroundColor Yellow

$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running. Starting..." -ForegroundColor Yellow
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
        Write-Host "Waiting for Docker to become ready (up to 60 seconds)..." -ForegroundColor Yellow
        $maxAttempts = 30
        $attempt = 0
        while ($attempt -lt $maxAttempts) {
            Start-Sleep -Seconds 2
            $dockerInfo = docker info 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Docker Desktop is ready." -ForegroundColor Green
                break
            }
            $attempt++
            Write-Host "  Waiting... ($attempt/$maxAttempts)" -ForegroundColor Gray
        }
        if ($attempt -ge $maxAttempts) {
            Write-Host "Docker Desktop failed to start within 60 seconds." -ForegroundColor Red
            Write-Host "Please start Docker Desktop manually and re-run this script." -ForegroundColor Yellow
            Read-Host "Press Enter to exit"
            exit 1
        }
    } else {
        Write-Host "Docker Desktop executable not found at: $dockerExe" -ForegroundColor Red
        Write-Host "Please start Docker Desktop manually and re-run this script." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "Docker Desktop is already running." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# Step 4: Ensure WSL2 integration is enabled for Docker
# -----------------------------------------------------------------------------
Write-Host "[4/6] Checking WSL2 integration..." -ForegroundColor Yellow
# Docker Desktop with WSL2 integration should be enabled by default.
# If not, we prompt the user to enable it.
$wslIntegration = docker info 2>&1 | Select-String "WSL2"
if (-not $wslIntegration) {
    Write-Host "WSL2 integration may not be enabled in Docker Desktop." -ForegroundColor Yellow
    Write-Host "Please enable it in Docker Desktop Settings > Resources > WSL Integration." -ForegroundColor Cyan
    Read-Host "Press Enter once WSL2 integration is enabled"
}
Write-Host "WSL2 integration check complete." -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 5: Clone or update the repository inside WSL
# -----------------------------------------------------------------------------
Write-Host "[5/6] Setting up NETTRADES repository inside WSL..." -ForegroundColor Yellow

$wslCommand = @'
#!/bin/bash
set -e

# Ensure we're in the home directory
cd ~

# Clone or update the repository
if [ ! -d "nettrades-platform" ]; then
    echo "Cloning NETTRADES repository..."
    git clone -b dev-deployment1 https://github.com/nettrades/nettrades-platform.git
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to clone repository."
        exit 1
    fi
else
    echo "Repository already exists. Pulling latest changes..."
    cd nettrades-platform
    git pull origin dev-deployment1 || echo "WARNING: Git pull failed. Continuing with existing code."
    cd ~
fi

cd nettrades-platform

# Make all scripts executable
echo "Making scripts executable..."
chmod +x scripts/*.sh
chmod +x scripts/lib/*.sh
chmod +x installer/*.js
chmod +x scripts/nettrades-setup.sh

# Remove phase markers to force a clean deployment
echo "Removing phase markers..."
rm -f .phase-*-complete

# Ensure .env has correct permissions
if [ -f deploy/docker/.env ]; then
    chmod 644 deploy/docker/.env
fi

# Run the full setup with --auto flag (non-interactive)
echo "Starting NETTRADES deployment..."
./scripts/nettrades-setup.sh all --force --auto

echo "Deployment script finished with exit code: $?"
'@

Write-Host "Running NETTRADES deployment inside WSL (this may take 5-10 minutes)..." -ForegroundColor Cyan
wsl -d Ubuntu-24.04 -e bash -c "$wslCommand"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Deployment failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host "Check the logs above for details." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# -----------------------------------------------------------------------------
# Step 6: Display completion status
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[6/6] Deployment complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access the NETTRADES Platform:"
Write-Host "  Odoo:        http://localhost:8069" -ForegroundColor Cyan
Write-Host "  AI Chat UI:  http://localhost:3002" -ForegroundColor Cyan
Write-Host "  Grafana:     http://localhost:3001" -ForegroundColor Cyan
Write-Host "  Prometheus:  http://localhost:9090" -ForegroundColor Cyan
Write-Host ""
Write-Host "Credentials:"
Write-Host "  Check the .env file at: \\wsl.localhost\Ubuntu-24.04\home\$env:USERNAME\nettrades-platform\deploy\docker\.env" -ForegroundColor Yellow
Write-Host ""
Write-Host "To open the project in VS Code:"
Write-Host "  wsl -d Ubuntu-24.04 -e bash -c 'cd ~/nettrades-platform && code .'" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view files in Windows Explorer:"
Write-Host "  \\wsl.localhost\Ubuntu-24.04\home\$env:USERNAME\nettrades-platform" -ForegroundColor Cyan
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Read-Host "Press Enter to exit"