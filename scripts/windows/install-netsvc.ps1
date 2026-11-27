# =============================================================================
# FILE: scripts/windows/install-netsvc.ps1
# PURPOSE: Register (or update) the NETTRADES Networking Service.
# Part of the code for the NETTRADES Networking Service, a Go-based Windows service using the official 
# Go extended standard library golang.org/x/sys/windows/svc for NETTRADES WSL Port Forwarding
# Launcher's NSIS installer registers the service during installation. The deployment scripts call 
# phase-windows-service.sh

# The problem it solves:
# WSL2 is running in NAT mode. The WSL distro has a different IP address on a private virtual 
# subnet that only the Windows host can route to. The Windows host's vEthernet (WSL) adapter 
# is the only thing that can reach WSL. Other machines cannot reach it — that is why ping works. 
# (Other machines can reach the Windows host via ICMP at the Ethernet layer, but the TCP 
# connection to WSL from the other machines is impossible.
# Also after WSL restarts (e.g., after wsl --shutdown) it changes the WSL IP

# Windows 10 does not support mirrored networking
# networkingMode=mirrored — the single-line fix that makes WSL2 share the Windows 
# host's IP — is only available on Windows 11 22H2 and later. 
# It does not exist on Windows 10.  On Windows 10, WSL2 is locked into NAT mode.
# =============================================================================

param(
    [string]$ServiceExe = "$PSScriptRoot\nettrades-netsvc.exe",
    [string]$ServiceName = "NETTRADESNetSvc"
)

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Error "Must run as Administrator."
    exit 1
}

# Stop and remove any existing service.
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

# Register the service using the binary's built-in install command.
& $ServiceExe install
if ($LASTEXITCODE -ne 0) {
    Write-Error "Service installation failed."
    exit 1
}

# Ensure the preshutdown timeout is set even on reinstall. The Go
# service's installService() sets this on a fresh install via
# ChangeServiceConfig2, but returns early when the service already
# exists — which means a re-install over an older service loses
# PRESHUTDOWN delivery. Re-applying sc.exe config here is idempotent
# and ensures the graceful drain works across upgrades.
sc.exe config $ServiceName preshutdown= 60000 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Failed to configure preshutdown timeout. Graceful drain on Windows shutdown will not work, but service will start normally."
}

# Start the service.
Start-Service -Name $ServiceName
Write-Host "NETTRADESNetSvc installed and started."