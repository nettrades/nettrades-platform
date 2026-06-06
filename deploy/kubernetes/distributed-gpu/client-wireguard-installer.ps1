# =============================================================================
# NETTRADES AI – Windows WireGuard & GPU Agent Installer
# =============================================================================
# Installs WireGuard, copies all agent Python modules, registers a scheduled
# task for DNS re-resolution, and starts the agent as a Windows service.
#
# The DNS watchdog re-resolves the WireGuard endpoint hostname every 60 seconds
# and updates the config if the ISP changes the public IP.
# =============================================================================
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey
)

Write-Host "Installing NETTRADES AI GPU Agent on Windows..."

# ---- 1. Install WireGuard ----
Write-Host "Installing WireGuard..."
$wireGuardUrl = "https://download.wireguard.com/windows-client/wireguard-installer.exe"
$installerPath = "$env:TEMP\wireguard-installer.exe"
Invoke-WebRequest -Uri $wireGuardUrl -OutFile $installerPath
Start-Process -FilePath $installerPath -Args "/S" -Wait

# ---- 2. Create agent configuration directory ----
$configDir = "C:\ProgramData\NettradesAgent"
New-Item -ItemType Directory -Force -Path $configDir

# ---- 3. Store API key ----
Set-Content -Path "$configDir\agent.env" -Value "API_KEY=$ApiKey"

# ---- 4. Copy agent Python files ----
Copy-Item -Path ".\agent.py", ".\wg_setup.py", ".\isolate.py", ".\wg_dns_watchdog.py", ".\tee_detect.py" -Destination $configDir -ErrorAction SilentlyContinue
Copy-Item -Path ".\modes" -Destination $configDir -Recurse -ErrorAction SilentlyContinue

# ---- 5. Install Python dependencies ----
pip install requests psutil pyyaml netifaces

# ---- 6. Register as a Windows service using nssm ----
Write-Host "Registering service..."
nssm install NettradesAgent "C:\Users\Owner\AppData\Local\Programs\Python\Python312\python.exe" "$configDir\agent.py"
nssm set NettradesAgent AppDirectory $configDir
nssm start NettradesAgent

# ---- 7. Install WireGuard DNS watchdog ----
Write-Host "Installing WireGuard DNS watchdog..."

$watchdogScript = @'
$ConfigPath = "$env:ProgramData\NettradesAgent\wg0.conf"
$IntervalSec = 60
$MaxFailures = 3
$failCount = 0

while ($true) {
    try {
        $config = Get-Content $ConfigPath -Raw
        if ($config -match "Endpoint\s*=\s*([^:]+):(\d+)") {
            $domain = $Matches[1]
            $port = $Matches[2]
            if ($domain -notmatch "^\d+\.\d+\.\d+\.\d+$") {
                try {
                    $newIP = (Resolve-DnsName $domain -Type A -ErrorAction Stop)[0].IPAddress
                    $oldEndpoint = "$domain`:$port"
                    $newEndpoint = "$newIP`:$port"
                    if ($config -notmatch [regex]::Escape($newEndpoint)) {
                        Write-Host "$(Get-Date): IP changed, updating endpoint to $newIP"
                        $newConfig = $config -replace [regex]::Escape($oldEndpoint), $newEndpoint
                        Set-Content $ConfigPath $newConfig
                        Restart-Service -Name "WireGuardTunnel`$wg0" -Force
                        Write-Host "WireGuard service restarted with new endpoint."
                    }
                    $failCount = 0
                } catch {
                    $failCount++
                    Write-Warning "DNS resolution failed ($failCount/$MaxFailures): $_"
                    if ($failCount -ge $MaxFailures) {
                        Restart-Service -Name "WireGuardTunnel`$wg0" -Force
                        $failCount = 0
                    }
                }
            }
        }
    } catch {
        Write-Warning "Watchdog error: $_"
    }
    Start-Sleep -Seconds $IntervalSec
}
'@

$watchdogPath = "$configDir\wg-watchdog.ps1"
Set-Content -Path $watchdogPath -Value $watchdogScript

$taskName = "NETTRADES WireGuard DNS Watchdog"
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdogPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -Description "Keeps WireGuard tunnel alive when ISP changes IP"
Start-ScheduledTask -TaskName $taskName

Write-Host "WireGuard DNS watchdog installed and started."
Write-Host "Installation complete. The agent is running as a Windows service."