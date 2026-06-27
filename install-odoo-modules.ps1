<#
.SYNOPSIS
    Installs all NETTRADES Odoo modules in the correct dependency order.
.DESCRIPTION
    This script installs all NETTRADES Odoo modules and their third-party
    dependencies in the correct sequence to satisfy module dependencies.
    It can be safely rerun multiple times.

    The script installs modules in the following batches:
    Batch 1: Foundation (queue_job, llm modules)
    Batch 2: NETTRADES Core
    Batch 3: Core NETTRADES modules
    Batch 4: Self-improving system modules
    Batch 5: LLM Configuration (nettrades_llm_config)
    Batch 6: Additional modules

    Each batch is installed in order so that module dependencies are satisfied.

    Before installing Odoo modules, the script ensures all required Python
    packages are installed, including:
        - torch, transformers, datasets, accelerate
        - langchain-openai, langchain-anthropic, langchain-ollama, langchain-deepseek
        - All packages from third-party/odoo_llm/requirements.txt
        - All packages from third-party/odoo/requirements.txt
.PARAMETER OdooBin
    Path to the Odoo binary. Defaults to '.\third-party\odoo\odoo-bin'
.PARAMETER ConfigFile
    Path to the Odoo configuration file. Defaults to '.\deploy\docker\config\odoo.conf'
.PARAMETER AddonsPath
    Comma-separated list of addons paths. Defaults to the standard NETTRADES paths.
.PARAMETER StopOnError
    Stop execution if a module installation fails. Defaults to $true.
.PARAMETER SkipInstalled
    Skip modules that are already installed. Defaults to $true.
.PARAMETER LogFile
    Path to log file. Defaults to '.\module-install.log'
.PARAMETER ForceReinstall
    Force reinstall even if modules are already installed (uses -u update flag).
.EXAMPLE
    .\install-odoo-modules.ps1
    Installs all missing modules using default paths.
.EXAMPLE
    .\install-odoo-modules.ps1 -ForceReinstall
    Forces reinstallation of all modules (same as updating).
.EXAMPLE
    .\install-odoo-modules.ps1 -StopOnError:$false -LogFile ".\install.log"
    Continues on errors and logs to a custom file.
.EXAMPLE
    .\install-odoo-modules.ps1 -SkipInstalled:$false -ForceReinstall
    Reinstall all modules even if already installed (useful after code changes).
#>

[CmdletBinding()]
param(
    # Path to the Odoo binary (odoo-bin)
    [string]$OdooBin = ".\third-party\odoo\odoo-bin",
    # Path to the Odoo configuration file
    [string]$ConfigFile = ".\deploy\docker\config\odoo.conf",
    # Comma-separated list of addons paths
    [string]$AddonsPath = ".\third-party\odoo\addons,.\odoo-modules,.\third-party\odoo_llm,.\third-party\odoo_llm_compat,.\third-party\website_sale_marketplace,.\third-party\queue-19",
    # Whether to stop the script if a module fails to install
    [bool]$StopOnError = $true,
    # Whether to skip modules that are already installed (saves time)
    [bool]$SkipInstalled = $true,
    # Path to the log file where all output will be recorded
    [string]$LogFile = ".\module-install.log",
    # Switch to force reinstall of all modules (uses -u update instead of -i install)
    [switch]$ForceReinstall
)

# =============================================================================
# 1. SETUP: Logging and output functions
# =============================================================================

# Function: Write a message to the log file with a timestamp
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append -Encoding UTF8
}

# Coloured output functions (each writes to console and log)
function Write-Success { Write-Host "[SUCCESS] $($args[0])" -ForegroundColor Green; Write-Log "[SUCCESS] $($args[0])" }
function Write-Info { Write-Host "[INFO] $($args[0])" -ForegroundColor Cyan; Write-Log "[INFO] $($args[0])" }
function Write-Warning { Write-Host "[WARNING] $($args[0])" -ForegroundColor Yellow; Write-Log "[WARNING] $($args[0])" }
function Write-Error { Write-Host "[ERROR] $($args[0])" -ForegroundColor Red; Write-Log "[ERROR] $($args[0])" }

# Clear the log file at the start of each run
if (Test-Path $LogFile) { Remove-Item $LogFile -Force }
Write-Info "=== NETTRADES Module Installation ==="
Write-Info "Starting installation at $(Get-Date)"
Write-Info "Log file: $LogFile"

# =============================================================================
# 2. PRE-FLIGHT CHECKS: Verify that required files and tools exist
# =============================================================================

# Check if the Odoo binary exists at the specified path
if (-not (Test-Path $OdooBin)) {
    Write-Error "Odoo binary not found at: $OdooBin"
    Write-Error "Please ensure the path is correct and the file exists."
    exit 1
}
Write-Success "Odoo binary found: $OdooBin"

# Check if the Odoo configuration file exists
if (-not (Test-Path $ConfigFile)) {
    Write-Error "Config file not found at: $ConfigFile"
    exit 1
}
Write-Success "Config file found: $ConfigFile"

# Parse the configuration file to get database connection details
Write-Info "Checking PostgreSQL connection..."
try {
    $configContent = Get-Content $ConfigFile -Raw -ErrorAction Stop
    # Extract database host (default to localhost if not specified)
    $dbHost = if ($configContent -match 'db_host\s*=\s*(\S+)') { $matches[1] } else { "localhost" }
    # Extract database port (default to 5432 if not specified)
    $dbPort = if ($configContent -match 'db_port\s*=\s*(\S+)') { $matches[1] } else { "5432" }
    # Extract database name (default to "odoo" if not specified)
    $dbName = if ($configContent -match 'db_name\s*=\s*(\S+)') { $matches[1] } else { "odoo" }
    Write-Info ("Database: {0} @ {1}:{2}" -f $dbName, $dbHost, $dbPort)
} catch {
    Write-Warning "Could not parse database config: $_"
    Write-Warning "Continuing anyway..."
}

# Check if Python is available in the PATH (required to run Odoo)
try {
    $pythonVersion = & "python" --version 2>&1
    Write-Info "Python version: $pythonVersion"
} catch {
    Write-Warning "Python not found in PATH. Ensure Python is installed and in your PATH."
}

# =============================================================================
# 3. INSTALL PYTHON DEPENDENCIES
# =============================================================================

Write-Info "=== Installing Python Dependencies ==="

# =============================================================================
# 3.1 Install torch, transformers, datasets, accelerate
# These are required for the llm_training module and fine-tuning pipeline
# =============================================================================
Write-Info "Installing torch, transformers, datasets, accelerate..."

$ml_packages = @("torch", "transformers", "datasets", "accelerate")
$to_install = @()
$pip_list = & "python" -m pip list 2>$null

foreach ($pkg in $ml_packages) {
    if ($pip_list -match $pkg) {
        Write-Info "Package $pkg already installed"
    } else {
        $to_install += $pkg
    }
}

if ($to_install.Count -gt 0) {
    Write-Info "Installing: $($to_install -join ', ')"
    & "python" -m pip install $to_install
    Write-Success "ML packages installed"
} else {
    Write-Success "All ML packages already installed"
}

# =============================================================================
# 3.2 Install LangGraph and LangChain providers
# These are required for the LangGraph agents and the LLM factory
# =============================================================================
Write-Info "Installing LangGraph and LangChain providers..."

$lang_packages = @(
    "langgraph",
    "langgraph-checkpoint-postgres",
    "langchain-openai",
    "langchain-anthropic",
    "langchain-ollama",
    "langchain-deepseek",
    "langchain-core"
)

$to_install = @()
foreach ($pkg in $lang_packages) {
    if ($pip_list -match $pkg) {
        Write-Info "Package $pkg already installed"
    } else {
        $to_install += $pkg
    }
}

if ($to_install.Count -gt 0) {
    Write-Info "Installing: $($to_install -join ', ')"
    & "python" -m pip install $to_install
    Write-Success "LangGraph packages installed"
} else {
    Write-Success "All LangGraph packages already installed"
}

# =============================================================================
# 3.3 Install odoo_llm requirements
# =============================================================================
$llm_reqs = "third-party/odoo_llm/requirements.txt"
if (Test-Path $llm_reqs) {
    Write-Info "Installing odoo_llm requirements..."
    & "python" -m pip install -r $llm_reqs
    Write-Success "odoo_llm requirements installed"
} else {
    Write-Warning "odoo_llm requirements file not found at: $llm_reqs"
}

# =============================================================================
# 3.4 Install Odoo core requirements
# =============================================================================
$odoo_reqs = "third-party/odoo/requirements.txt"
if (Test-Path $odoo_reqs) {
    Write-Info "Installing Odoo core requirements..."
    & "python" -m pip install -r $odoo_reqs
    Write-Success "Odoo core requirements installed"
} else {
    Write-Warning "Odoo requirements file not found at: $odoo_reqs"
}

# =============================================================================
# 3.5 Install prometheus-client for metrics
# =============================================================================
Write-Info "Installing prometheus-client for metrics..."
& "python" -m pip install prometheus-client
Write-Success "prometheus-client installed"

# =============================================================================
# 3.6 Upgrade Starlette (security fix for CVE-2026-48710)
# =============================================================================
Write-Info "Upgrading Starlette (CVE-2026-48710 fix)..."
& "python" -m pip install --upgrade "starlette>=1.0.1"
Write-Success "Starlette upgraded"

Write-Info "All dependencies installed successfully"

# =============================================================================
# 4. DEFINE MODULE BATCHES (in dependency order)
# =============================================================================

# =============================================================================
# Batch 1: Foundation modules – required by everything else
# queue_job is required by nettrades_core; llm modules are required by
# the self-improving system and nettrades modules.
# =============================================================================
$batch1 = @(
    "queue_job",
    "queue_job_batch",
    "queue_job_cron",
    "llm",
    "llm_tool",
    "llm_store",
    "llm_pgvector",
    "llm_knowledge",
    "llm_assistant",
    "llm_thread",
    "llm_generate",
    "llm_training"
)

# =============================================================================
# Batch 2: NETTRADES Core – the central business logic module
# All other NETTRADES modules depend on this.
# =============================================================================
$batch2 = @(
    "nettrades_core"
)

# =============================================================================
# Batch 3: Core NETTRADES modules – depend on nettrades_core
# =============================================================================
$batch3 = @(
    "nettrades_gpu_admin",
    "nettrades_gpustack_adapter",
    "nettrades_good_answer",
    "nettrades_ask_someone",
    "nettrades_queue",
    "nettrades_notifications",
    "nettrades_job_matching",
    "nettrades_lead_scoring",
    "nettrades_chatbot"
)

# =============================================================================
# Batch 4: Self-improving system modules – depend on nettrades_core and llm_training
# These must be installed in order:
#   1. nettrades_bridge       - Hub-and-spoke routing
#   2. nettrades_data_collection - Data collection (Monitor phase)
#   3. nettrades_trigger      - Trigger detection (Analyze phase)
#   4. nettrades_loop         - Plan + Execute phases
#   5. nettrades_self_improving_config - Administration interface
# =============================================================================
$batch4 = @(
    "nettrades_bridge",
    "nettrades_data_collection",
    "nettrades_trigger",
    "nettrades_loop",
    "nettrades_self_improving_config"
)

# =============================================================================
# Batch 5: LLM Configuration – depends on llm, nettrades_core, nettrades_gpu_admin
# This module provides company-specific LLM provider configuration.
# It must be installed after nettrades_core and nettrades_gpu_admin.
# =============================================================================
$batch5 = @(
    "nettrades_llm_config"
)

# =============================================================================
# Batch 6: Additional modules – depend on nettrades_core but not on
# the self-improving system.
# =============================================================================
$batch6 = @(
    "nettrades_fairness",
    "nettrades_onboarding",
    "nettrades_proposals",
    "nettrades_research",
    "nettrades_pwa"
)

# Combine all modules into a single list for installation order (used for reference)
$allModules = $batch1 + $batch2 + $batch3 + $batch4 + $batch5 + $batch6

# =============================================================================
# 5. HELPER FUNCTION: Get list of already installed modules
# =============================================================================

function Get-InstalledModules {
    param(
        [string]$OdooBin,
        [string]$ConfigFile,
        [string]$AddonsPath,
        [string]$DbName
    )

    Write-Info "Checking which modules are already installed..."

    # Build the command to list installed modules
    # Odoo's --list-installed-modules flag outputs a list of module names
    $cmd = "python $OdooBin -c $ConfigFile --addons-path=$AddonsPath -d $DbName --list-installed-modules --stop-after-init"

    try {
        # Execute the command and capture both stdout and stderr
        $output = & cmd /c $cmd 2>&1
        if ($LASTEXITCODE -eq 0) {
            # Parse the output: lines with only alphanumeric characters (and underscores) are module names
            $installed = @()
            foreach ($line in $output) {
                # Trim whitespace and check if it's a valid module name
                $trimmed = $line.Trim()
                if ($trimmed -match '^[a-zA-Z_][a-zA-Z0-9_]*$') {
                    $installed += $trimmed
                }
            }
            Write-Success "Found $($installed.Count) installed modules"
            return $installed
        } else {
            Write-Warning "Could not list installed modules. Continuing with full installation."
            return @()
        }
    } catch {
        Write-Warning "Error listing installed modules: $_"
        return @()
    }
}

# =============================================================================
# 6. HELPER FUNCTION: Install a single module
# =============================================================================

function Install-Module {
    param(
        [string]$ModuleName,
        [string]$OdooBin,
        [string]$ConfigFile,
        [string]$AddonsPath,
        [bool]$ForceReinstall
    )

    Write-Info "Installing module: $ModuleName"

    # Determine whether to install (-i) or update (-u)
    # -i: install (if not installed) or do nothing (if already installed)
    # -u: update (reinstall) even if already installed
    $action = if ($ForceReinstall) { "-u" } else { "-i" }

    # Build the full command
    $cmd = "python $OdooBin -c $ConfigFile --addons-path=$AddonsPath $action $ModuleName --stop-after-init"
    Write-Info "Command: $cmd"

    # Execute the command and capture both stdout and stderr
    try {
        $output = & cmd /c $cmd 2>&1
        $exitCode = $LASTEXITCODE

        # Print the full output to the console so the user can see what happened
        if ($output) {
            Write-Info "Odoo output:"
            Write-Host $output -ForegroundColor Gray
        }

        if ($exitCode -eq 0) {
            Write-Success "Module '$ModuleName' installed successfully"
            return $true
        } else {
            Write-Error "Module '$ModuleName' installation failed with exit code: $exitCode"
            # If output contains error details, show them
            if ($output) {
                Write-Error "Error details: $output"
            }
            return $false
        }
    } catch {
        Write-Error "Exception installing '$ModuleName': $_"
        return $false
    }
}

# =============================================================================
# 7. HELPER FUNCTION: Install a batch of modules
# =============================================================================

function Invoke-BatchInstall {
    param(
        [string]$BatchName,
        [string[]]$ModuleList,
        [string]$OdooBin,
        [string]$ConfigFile,
        [string]$AddonsPath,
        [bool]$StopOnError,
        [bool]$ForceReinstall,
        [string[]]$InstalledModules
    )

    Write-Info "=== Installing $BatchName ==="
    Write-Info "Modules: $($ModuleList -join ', ')"

    $failedModules = @()

    foreach ($module in $ModuleList) {
        # Check if the module is already installed (if SkipInstalled is true and ForceReinstall is false)
        if ($SkipInstalled -and $InstalledModules -contains $module -and -not $ForceReinstall) {
            Write-Info "Module '$module' is already installed. Skipping."
            continue
        }

        # Install the module
        $result = Install-Module -ModuleName $module -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -ForceReinstall $ForceReinstall

        if (-not $result) {
            $failedModules += $module
            if ($StopOnError) {
                Write-Error "Stopping due to StopOnError=true. Failed module: $module"
                Write-Error "Check the log file for details: $LogFile"
                exit 1
            } else {
                Write-Warning "Continuing despite error (StopOnError=false)"
            }
        }
    }

    if ($failedModules.Count -gt 0) {
        Write-Warning "Batch '$BatchName' completed with failures: $($failedModules -join ', ')"
    } else {
        Write-Success "Batch '$BatchName' complete"
    }

    return $failedModules
}

# =============================================================================
# 8. MAIN EXECUTION
# =============================================================================

Write-Info "=== Starting Installation ==="
Write-Info "Addons path: $AddonsPath"
Write-Info "Skip installed modules: $SkipInstalled"
Write-Info "Force reinstall: $ForceReinstall"
Write-Info "Stop on error: $StopOnError"

# First, get a list of already installed modules (if we are skipping installed modules)
$installedModules = @()
if ($SkipInstalled) {
    $installedModules = Get-InstalledModules -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -DbName $dbName
}

# Track all failed modules across batches
$allFailed = @()

# =============================================================================
# Install each batch in order
# The dependencies cascade: batch1 → batch2 → batch3 → batch4 → batch5 → batch6
# =============================================================================

# Batch 1: Foundation modules
$allFailed += Invoke-BatchInstall -BatchName "Batch 1: Foundation (queue_job, llm modules)" -ModuleList $batch1 -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -StopOnError $StopOnError -ForceReinstall $ForceReinstall -InstalledModules $installedModules

# Refresh installed modules list after batch 1 (if new modules were installed)
if ($SkipInstalled) {
    $installedModules = Get-InstalledModules -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -DbName $dbName
}

# Batch 2: NETTRADES Core
$allFailed += Invoke-BatchInstall -BatchName "Batch 2: NETTRADES Core" -ModuleList $batch2 -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -StopOnError $StopOnError -ForceReinstall $ForceReinstall -InstalledModules $installedModules

# Refresh installed modules list
if ($SkipInstalled) {
    $installedModules = Get-InstalledModules -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -DbName $dbName
}

# Batch 3: Core NETTRADES modules
$allFailed += Invoke-BatchInstall -BatchName "Batch 3: Core NETTRADES modules" -ModuleList $batch3 -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -StopOnError $StopOnError -ForceReinstall $ForceReinstall -InstalledModules $installedModules

# Refresh installed modules list
if ($SkipInstalled) {
    $installedModules = Get-InstalledModules -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -DbName $dbName
}

# Batch 4: Self-improving system modules
$allFailed += Invoke-BatchInstall -BatchName "Batch 4: Self-improving system modules" -ModuleList $batch4 -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -StopOnError $StopOnError -ForceReinstall $ForceReinstall -InstalledModules $installedModules

# Refresh installed modules list
if ($SkipInstalled) {
    $installedModules = Get-InstalledModules -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -DbName $dbName
}

# Batch 5: LLM Configuration (NEW)
$allFailed += Invoke-BatchInstall -BatchName "Batch 5: LLM Configuration" -ModuleList $batch5 -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -StopOnError $StopOnError -ForceReinstall $ForceReinstall -InstalledModules $installedModules

# Refresh installed modules list
if ($SkipInstalled) {
    $installedModules = Get-InstalledModules -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -DbName $dbName
}

# Batch 6: Additional modules
$allFailed += Invoke-BatchInstall -BatchName "Batch 6: Additional modules" -ModuleList $batch6 -OdooBin $OdooBin -ConfigFile $ConfigFile -AddonsPath $AddonsPath -StopOnError $StopOnError -ForceReinstall $ForceReinstall -InstalledModules $installedModules

# =============================================================================
# 9. POST-INSTALLATION SUMMARY
# =============================================================================

Write-Info ""
Write-Info "=== Installation Summary ==="

if ($allFailed.Count -eq 0) {
    Write-Success "All module installations completed successfully!"
} else {
    Write-Warning "Some modules failed to install: $($allFailed -join ', ')"
    Write-Info "Check the log file for details: $LogFile"
}

# Print a summary of what was installed
Write-Info ""
Write-Info "Installed modules summary:"
Write-Info "  Foundation (queue_job + llm): $($batch1.Count) modules"
Write-Info "  NETTRADES Core: $($batch2.Count) module"
Write-Info "  Core NETTRADES: $($batch3.Count) modules"
Write-Info "  Self-improving system: $($batch4.Count) modules"
Write-Info "  LLM Configuration: $($batch5.Count) module"
Write-Info "  Additional: $($batch6.Count) modules"

Write-Info ""
Write-Info "=== Next Steps ==="
Write-Info "1. Restart Odoo server if it was running during installation"
Write-Info "2. Log in to Odoo at http://localhost:8069"
Write-Info "3. Check Apps menu to verify all modules are installed"
Write-Info "4. Configure LLM providers: LLM → Configuration → Providers"
Write-Info "5. Configure company LLM settings: Settings → Technical → LLM Configuration → Company LLM Settings"
Write-Info "6. Configure bridge module: Settings → Technical → Bridge → Global Configuration"

Write-Info ""
Write-Info "=== Important Notes ==="
Write-Info "The self-improving system modules have the following dependencies:"
Write-Info "  - nettrades_bridge depends on: nettrades_core, nettrades_gpu_admin"
Write-Info "  - nettrades_data_collection depends on: nettrades_core, nettrades_good_answer, nettrades_ask_someone"
Write-Info "  - nettrades_trigger depends on: nettrades_data_collection"
Write-Info "  - nettrades_loop depends on: nettrades_data_collection, nettrades_trigger, llm_training, gpu_gpustack_adapter"
Write-Info "  - nettrades_self_improving_config depends on: nettrades_loop, nettrades_trigger, nettrades_data_collection"
Write-Info ""
Write-Info "The LLM Configuration module (nettrades_llm_config) depends on:"
Write-Info "  - nettrades_core, llm, nettrades_gpu_admin"

# Exit with appropriate code (0 = success, 1 = some failures)
if ($allFailed.Count -eq 0) {
    Write-Info "Exiting with code 0 (success)"
    exit 0
} else {
    Write-Error "Exiting with code 1 (some modules failed)"
    exit 1
}