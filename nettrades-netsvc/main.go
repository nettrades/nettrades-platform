// =============================================================================
// FILE: nettrades-netsvc/main.go
// PURPOSE:
//   Main entry point for the NETTRADES Windows service.
//
//   This service provides three capabilities for the NETTRADES platform
//   on Windows hosts:
//
//     1. WSL2 PORT FORWARDING (primary)
//        Windows 10 does not support WSL2 mirrored networking mode. WSL2
//        runs behind a NAT on a private virtual subnet, and the Windows
//        host's vEthernet (WSL) adapter is the only thing that can reach
//        it. Other machines on the LAN cannot reach the WSL IP directly.
//        This service polls the WSL IP every 5 seconds and maintains
//        netsh portproxy rules so that Odoo (:8069), LangGraph (:8000),
//        and the NETTRADES UI (:3002) are reachable from the LAN via the
//        Windows host's IP.
//
//     2. WIREGUARD TUNNEL MANAGEMENT (future)
//        The service can create, start, stop, and remove a
//        WireGuardTunnel$NETTRADES Windows service that embeds WireGuard
//        using the official tunnel.dll from the WireGuard embeddable DLL
//        service. This is disabled by default and will be enabled when
//        the platform moves to production VPN connectivity.
//
//     3. GRACEFUL SHUTDOWN COORDINATION (2026-10-20)
//        When Windows initiates a shutdown, the SCM delivers
//        SERVICE_CONTROL_PRESHUTDOWN to services that declare it. This
//        service uses that window to tell the Python spoke agent to
//        drain before its RPC workers are killed. The coordination is
//        file-based: the service writes C:\ProgramData\NETTRADES\drain.requested,
//        the agent (which runs as a separate process) polls for that
//        file and starts its drain sequence, and when the drain is
//        complete the agent writes drain.complete. This service polls
//        for drain.complete and returns from the PRESHUTDOWN handler
//        when it appears, or after the preshutdown timeout expires.
//
//        The preshutdown timeout is configured at install time via
//        `sc.exe config <service> preshutdown= 60000`, which calls
//        ChangeServiceConfig2 with SERVICE_CONFIG_PRESHUTDOWN_INFO.
//        Without that call, Windows does not deliver PRESHUTDOWN to the
//        service at all.
//
//        Design rationale: see FAILOVER-HIERARCHY.md § Graceful shutdown.
//
//   The service exposes a named pipe (\\.\pipe\NETTRADESNetSvc) that the
//   NETTRADES Launcher connects to for status queries and repair commands.
//   The Launcher does not need administrator privileges; the service runs
//   as LocalSystem and handles all privileged operations.
//
// ARCHITECTURE:
//   ┌─────────────────────────────────────────────────────────────┐
//   │ Windows Service Control Manager (SCM)                       │
//   │   - Starts the service at boot (Automatic)                  │
//   │   - Restarts on failure (3 retries, 1-minute interval)      │
//   │   - Runs as LocalSystem                                     │
//   └──────────────────────┬──────────────────────────────────────┘
//                          │
//                          ▼
//   ┌─────────────────────────────────────────────────────────────┐
//   │ NETTRADESNetSvc (this binary)                               │
//   │                                                             │
//   │  ┌───────────────────────────────────────────────────────┐  │
//   │  │ Port forwarding reconciler (5-second poll loop)       │  │
//   │  │   - Gets WSL IP from wsl-ip.txt or `wsl hostname -I`  │  │
//   │  │   - Reconciles netsh portproxy rules                  │  │
//   │  │   - Ensures Windows Firewall rules exist              │  │
//   │  └───────────────────────────────────────────────────────┘  │
//   │                                                             │
//   │  ┌───────────────────────────────────────────────────────┐  │
//   │  │ Named pipe server (\\.\pipe\NETTRADESNetSvc)           │  │
//   │  │   - get-status: returns WSL IP and forwarding state   │  │
//   │  │   - repair: triggers immediate reconciliation         │  │
//   │  │   - wireguard-*: manages the WireGuard tunnel service │  │
//   │  └───────────────────────────────────────────────────────┘  │
//   │                                                             │
//   │  ┌───────────────────────────────────────────────────────┐  │
//   │  │ PRESHUTDOWN handler (new 2026-10-20)                  │  │
//   │  │   - Writes drain.requested                            │  │
//   │  │   - Polls for drain.complete (up to 60s)              │  │
//   │  │   - Returns when drain is done or on timeout          │  │
//   │  └───────────────────────────────────────────────────────┘  │
//   └─────────────────────────────────────────────────────────────┘
//
// SERVICE INSTALLATION:
//   The service is registered by the NETTRADES Launcher's NSIS installer
//   via the customInstall macro in installer/build/installer.nsh.
//   The deployment scripts call scripts/phase-windows-service.sh which
//   copies the binary and runs install-netsvc.ps1.
//
//   installService() also runs `sc.exe config NETTRADESNetSvc preshutdown= 60000`
//   after CreateService, so the SCM delivers PRESHUTDOWN with a 60-second
//   window. This is required for the drain coordination to work.
//
// WIREGUARD /SERVICE MODE:
//   When Windows starts the WireGuardTunnel$NETTRADES service, it invokes
//   this binary with:
//
//       nettrades-netsvc.exe /service "C:\ProgramData\NETTRADES\wireguard\nettrades.conf"
//
//   We detect this before doing anything else and delegate to
//   tunnel.dll's WireGuardTunnelService function. This call blocks
//   until the tunnel service is stopped by the SCM.
//
// BUILD:
//   GOOS=windows GOARCH=amd64 go build -ldflags "-s -w" -o nettrades-netsvc.exe .
//
//   The binary requires tunnel.dll and wireguard.dll in the same
//   directory for WireGuard functionality. These are downloaded from
//   https://download.wireguard.com/wireguard-nt/ and built from the
//   embeddable-dll-service directory of wireguard-windows.
//
// USAGE:
//   nettrades-netsvc.exe install    Install the service
//   nettrades-netsvc.exe uninstall  Remove the service
//   nettrades-netsvc.exe start      Start the service
//   nettrades-netsvc.exe stop       Stop the service
//   (no arguments)                  Run as a Windows service
// =============================================================================

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/debug"
	"golang.org/x/sys/windows/svc/eventlog"
	"golang.org/x/sys/windows/svc/mgr"
)

// -----------------------------------------------------------------------------
// Constants
// -----------------------------------------------------------------------------

const (
	// ServiceName is the Windows service name registered with the SCM.
	// It must match the name used in installer.nsh and install-netsvc.ps1.
	ServiceName = "NETTRADESNetSvc"

	// ServiceDisplayName is the human-readable name shown in services.msc.
	ServiceDisplayName = "NETTRADES Networking Service"

	// ServiceDescription is the description shown in services.msc.
	ServiceDescription = "Maintains WSL2 port forwarding, WireGuard tunnels, and graceful drain coordination for the NETTRADES platform."

	// PipeName is the named pipe the Launcher connects to.
	// The full path is \\.\pipe\NETTRADESNetSvc.
	PipeName = "NETTRADESNetSvc"

	// PortsToForward is the list of ports the reconciler maintains.
	// 8069 = Odoo (spoke registration, GPU management)
	// 8000 = LangGraph (heartbeat, RPC relaunch, health monitor)
	// 3002 = NETTRADES UI (Launcher dashboard)
	PortsToForward = "8069,8000,3002"

	// WSLDistroName is the WSL distribution to query for its IP.
	// Change this if the user's WSL distro is not Ubuntu.
	WSLDistroName = "Ubuntu"

	// PollInterval is how often the reconciler checks the WSL IP.
	// 5 seconds is a good balance: responsive enough for a demo,
	// light enough for a production service.
	PollInterval = 5 * time.Second

	// LogDir is where the service writes its log file.
	LogDir = `C:\ProgramData\NETTRADES`

	// LogFile is the name of the log file.
	LogFile = "netsvc.log"

	// WSLIPFile is where the WSL-side notify service writes the current
	// WSL IP. When this file exists and is recent, the reconciler reads
	// it instead of spawning `wsl hostname -I` on every tick.
	WSLIPFile = `C:\ProgramData\NETTRADES\wsl-ip.txt`

	// DrainRequestedFile is written by this service on PRESHUTDOWN. The
	// Python spoke agent polls for it (see spoke-agent.py
	// _watch_drain_file) and starts its drain sequence when it appears.
	DrainRequestedFile = `C:\ProgramData\NETTRADES\drain.requested`

	// DrainCompleteFile is written by the Python spoke agent when its
	// drain sequence completes. This service polls for it during the
	// PRESHUTDOWN handler so the SCM knows the drain is done and can
	// proceed with the shutdown.
	DrainCompleteFile = `C:\ProgramData\NETTRADES\drain.complete`

	// PreshutdownTimeoutMs is the preshutdown window requested from the
	// SCM. Must be long enough for the Python spoke agent's
	// shutdown_grace_seconds (default 30) plus a margin.
	PreshutdownTimeoutMs = 60000

	// DrainPollInterval is how often the PRESHUTDOWN handler polls for
	// drain.complete.
	DrainPollInterval = time.Second
)

// -----------------------------------------------------------------------------
// Global state
// -----------------------------------------------------------------------------

var (
	// logger writes to the log file. Initialized in main().
	logger *log.Logger

	// currentWSLIP is the last known WSL IP. Protected by mu.
	currentWSLIP string

	// mu protects currentWSLIP.
	mu sync.RWMutex
)

// -----------------------------------------------------------------------------
// Windows service implementation
// -----------------------------------------------------------------------------

// nettradesService implements the svc.Handler interface.
type nettradesService struct {
	elog debug.Log
}

// Execute is called by the SCM when the service starts, stops, is
// interrogated, or receives a preshutdown notification. It runs until
// the service is stopped.
//
// The command set includes svc.AcceptPreshutdown. For PRESHUTDOWN to
// actually be delivered by the SCM, the service must also be configured
// with SERVICE_CONFIG_PRESHUTDOWN_INFO via ChangeServiceConfig2. That
// is done at install time by installService(), which runs
//   sc.exe config <service> preshutdown= 60000
func (s *nettradesService) Execute(
	args []string,
	r <-chan svc.ChangeRequest,
	changes chan<- svc.Status,
) (ssec bool, errno uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown | svc.AcceptPreShutdown

	// Tell the SCM we are starting.
	changes <- svc.Status{State: svc.StartPending}

	// Initialize logging.
	if err := initLogging(); err != nil {
		// If we cannot open the log file, write to the event log and
		// continue. The service must still start so the SCM does not
		// mark it as failed.
		s.elog.Error(1, fmt.Sprintf("Could not open log file: %v", err))
	}

	// Start the port forwarding reconciler in a goroutine.
	reconcilerDone := make(chan struct{})
	go func() {
		defer close(reconcilerDone)
		runReconciler()
	}()

	// Start the named pipe server in a goroutine.
	pipeDone := make(chan struct{})
	go func() {
		defer close(pipeDone)
		runPipeServer()
	}()

	// Tell the SCM we are running.
	changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
	logger.Println("NETTRADES Networking Service started.")

	// Wait for the SCM to tell us to stop.
loop:
	for {
		select {
		case c := <-r:
			switch c.Cmd {
			case svc.Interrogate:
				changes <- c.CurrentStatus
			case svc.PreShutdown:
				// Preshutdown is delivered early in the shutdown sequence,
				// before Stop/Shutdown. It gives us a chance to tell the
				// Python spoke agent to drain while the RPC workers are
				// still alive.
				logger.Println("Preshutdown requested by SCM.")
				handlePreshutdown()
				// Do not break the loop — wait for Stop or Shutdown to
				// arrive so the SCM sees the service respond normally.
			case svc.Stop, svc.Shutdown:
				logger.Println("Stop/shutdown requested by SCM.")
				break loop
			}
		}
	}

	// Tell the SCM we are stopping.
	changes <- svc.Status{State: svc.StopPending}
	logger.Println("NETTRADES Networking Service stopping.")

	// Wait for the goroutines to finish (with a timeout).
	select {
	case <-reconcilerDone:
	case <-time.After(5 * time.Second):
		logger.Println("Reconciler did not stop in time.")
	}
	select {
	case <-pipeDone:
	case <-time.After(5 * time.Second):
		logger.Println("Pipe server did not stop in time.")
	}

	logger.Println("NETTRADES Networking Service stopped.")
	return
}

// handlePreshutdown coordinates the drain of the Python spoke agent.
//
// Sequence:
//   1. Remove any stale drain.complete from a previous shutdown.
//   2. Write drain.requested. The Python agent's _watch_drain_file
//      thread polls for this and starts the drain sequence when it
//      appears.
//   3. Poll for drain.complete up to PreshutdownTimeoutMs. When it
//      appears, the drain is finished — the agent has sent the drain
//      heartbeat to the hub, waited its grace period, and stopped its
//      RPC workers.
//   4. If the timeout expires without drain.complete appearing, log
//      the timeout and return. The SCM will proceed with the shutdown
//      regardless; the drain is best-effort.
func handlePreshutdown() {
	// Clear any stale completion marker from a previous shutdown.
	_ = os.Remove(DrainCompleteFile)

	// Write the trigger file. The Python agent watches for it.
	if err := os.WriteFile(DrainRequestedFile, []byte("1"), 0644); err != nil {
		logger.Printf("Preshutdown: failed to write drain trigger file: %v", err)
		return
	}
	logger.Printf("Preshutdown: wrote drain trigger file %s", DrainRequestedFile)

	// Poll for drain.complete.
	deadline := time.Now().Add(PreshutdownTimeoutMs * time.Millisecond)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(DrainCompleteFile); err == nil {
			logger.Println("Preshutdown: drain completed (drain.complete found)")
			return
		}
		time.Sleep(DrainPollInterval)
	}
	logger.Printf(
		"Preshutdown: timeout after %dms waiting for drain to complete; "+
			"the spoke agent may not be running, or its shutdown_grace_seconds "+
			"is larger than %dms",
		PreshutdownTimeoutMs, PreshutdownTimeoutMs,
	)
}

// -----------------------------------------------------------------------------
// runHidden
// -----------------------------------------------------------------------------
// Runs an external Windows command with the CREATE_NO_WINDOW creation flag
// so that no console window is displayed. Used by restrictToSystemAndAdmins
// in wireguard.go to invoke icacls.
//
// We deliberately do not use os/exec.CommandContext here — there is no
// caller-provided context and the commands this helper runs are short-lived
// and non-hanging (icacls on a single file). A future enhancement could add
// a timeout via exec.CommandContext if a hung icacls is ever observed.
//
// The CREATE_NO_WINDOW flag (0x08000000) is a Windows process-creation
// constant. It is not exposed in the Go standard library's os/exec package
// as a named constant, so we define it here. See:
//   https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
// -----------------------------------------------------------------------------
func runHidden(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: 0x08000000, // CREATE_NO_WINDOW
	}
	// Discard stdout and stderr; the caller only cares about the exit
	// status. If a diagnostic is ever needed, wrap the returned error
	// with the command name and arguments.
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%s %v: %w", name, args, err)
	}
	return nil
}

// -----------------------------------------------------------------------------
// Logging
// -----------------------------------------------------------------------------

// initLogging opens the log file and initializes the logger.
// The log file is written to C:\ProgramData\NETTRADES\netsvc.log.
// If the directory does not exist, it is created.
func initLogging() error {
	if err := os.MkdirAll(LogDir, 0755); err != nil {
		return fmt.Errorf("could not create log directory: %w", err)
	}
	f, err := os.OpenFile(
		filepath.Join(LogDir, LogFile),
		os.O_APPEND|os.O_CREATE|os.O_WRONLY,
		0644,
	)
	if err != nil {
		return fmt.Errorf("could not open log file: %w", err)
	}
	logger = log.New(f, "", log.LstdFlags)
	return nil
}

// -----------------------------------------------------------------------------
// Port forwarding reconciler
// -----------------------------------------------------------------------------

// runReconciler runs the port forwarding reconciliation loop.
// It polls the WSL IP every PollInterval seconds and updates the
// netsh portproxy rules when the IP changes.
func runReconciler() {
	for {
		if err := reconcile(); err != nil {
			logger.Printf("Reconcile error: %v", err)
		}
		time.Sleep(PollInterval)
	}
}

// reconcile performs one reconciliation pass:
//  1. Gets the current WSL IP.
//  2. If the IP has changed since the last pass, removes stale
//     netsh portproxy rules and adds fresh ones.
//  3. Ensures Windows Firewall rules exist for each forwarded port.
func reconcile() error {
	ip, err := getWSLIP()
	if err != nil {
		return err
	}

	mu.RLock()
	same := ip == currentWSLIP
	mu.RUnlock()
	if same {
		return nil
	}

	logger.Printf("WSL IP changed to %s — reconciling port forwarding.", ip)

	ports := strings.Split(PortsToForward, ",")

	// Remove stale portproxy rules.
	for _, port := range ports {
		exec.Command("netsh", "interface", "portproxy", "delete",
			"v4tov4",
			"listenaddress=0.0.0.0",
			fmt.Sprintf("listenport=%s", strings.TrimSpace(port)),
		).Run()
	}

	// Add fresh portproxy rules.
	for _, port := range ports {
		port = strings.TrimSpace(port)
		out, err := exec.Command("netsh", "interface", "portproxy", "add",
			"v4tov4",
			"listenaddress=0.0.0.0",
			fmt.Sprintf("listenport=%s", port),
			fmt.Sprintf("connectaddress=%s", ip),
			fmt.Sprintf("connectport=%s", port),
		).CombinedOutput()
		if err != nil {
			logger.Printf("Failed to forward port %s: %v — %s", port, err, out)
		} else {
			logger.Printf("Forwarding 0.0.0.0:%s -> %s:%s", port, ip, port)
		}
	}

	// Ensure firewall rules exist.
	for _, port := range ports {
		port = strings.TrimSpace(port)
		ruleName := fmt.Sprintf("NETTRADES WSL Bridge %s", port)
		psCmd := fmt.Sprintf(
			`if (-not (Get-NetFirewallRule -DisplayName '%s' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName '%s' -Direction Inbound -Protocol TCP -LocalPort %s -Action Allow -Profile Any }`,
			ruleName, ruleName, port,
		)
		exec.Command("powershell", "-NoProfile", "-Command", psCmd).Run()
	}

	mu.Lock()
	currentWSLIP = ip
	mu.Unlock()
	return nil
}

// getWSLIP returns the current WSL IP address.
//
// It first tries to read the WSL-side notify file
// (C:\ProgramData\NETTRADES\wsl-ip.txt). This file is written by a
// systemd unit inside WSL on every boot, so reading it is much cheaper
// than spawning `wsl hostname -I` on every poll.
//
// If the file does not exist or contains an invalid IP, it falls back
// to querying WSL directly.
func getWSLIP() (string, error) {
	// Try the WSL-side notify file first.
	if data, err := os.ReadFile(WSLIPFile); err == nil {
		ip := strings.TrimSpace(string(data))
		if isValidIP(ip) {
			return ip, nil
		}
	}

	// Fall back to querying WSL directly.
	out, err := exec.Command("wsl", "-d", WSLDistroName, "hostname", "-I").Output()
	if err != nil {
		return "", fmt.Errorf("wsl hostname -I failed: %w", err)
	}
	fields := strings.Fields(string(out))
	if len(fields) == 0 {
		return "", fmt.Errorf("wsl hostname -I returned no IP")
	}
	ip := fields[0]
	if !isValidIP(ip) {
		return "", fmt.Errorf("invalid IP from WSL: %s", ip)
	}
	return ip, nil
}

// isValidIP returns true if the string is a valid IPv4 address.
func isValidIP(ip string) bool {
	return net.ParseIP(ip) != nil && strings.Contains(ip, ".")
}

// -----------------------------------------------------------------------------
// Named pipe server
// -----------------------------------------------------------------------------

// PipeCommand is the JSON structure received from the Launcher.
type PipeCommand struct {
	Command             string `json:"command"`
	PrivateKey          string `json:"private_key,omitempty"`
	Address             string `json:"address,omitempty"`
	DNS                 string `json:"dns,omitempty"`
	PeerPublicKey       string `json:"peer_public_key,omitempty"`
	PresharedKey        string `json:"preshared_key,omitempty"`
	Endpoint            string `json:"endpoint,omitempty"`
	AllowedIPs          string `json:"allowed_ips,omitempty"`
	PersistentKeepalive int    `json:"persistent_keepalive,omitempty"`
}

// PipeResponse is the JSON structure sent back to the Launcher.
type PipeResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// runPipeServer starts the named pipe server and accepts connections
// from the Launcher in a loop.
func runPipeServer() {
	pipePath := `\\.\pipe\` + PipeName

	for {
		conn, err := net.Listen("unix", pipePath)
		if err != nil {
			logger.Printf("Could not listen on pipe: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		// Accept one connection at a time.
		for {
			client, err := conn.Accept()
			if err != nil {
				logger.Printf("Pipe accept error: %v", err)
				break
			}

			// Handle the connection in a goroutine.
			go handlePipeConnection(client)
		}

		conn.Close()
	}
}

// handlePipeConnection reads a JSON command from the pipe, dispatches
// it to the appropriate handler, and writes the JSON response back.
func handlePipeConnection(conn net.Conn) {
	defer conn.Close()

	// Set a read deadline so a hung client does not block the server.
	conn.SetReadDeadline(time.Now().Add(30 * time.Second))

	decoder := json.NewDecoder(conn)
	var cmd PipeCommand
	if err := decoder.Decode(&cmd); err != nil {
		logger.Printf("Pipe decode error: %v", err)
		return
	}

	resp := dispatchCommand(cmd)

	encoder := json.NewEncoder(conn)
	if err := encoder.Encode(resp); err != nil {
		logger.Printf("Pipe encode error: %v", err)
	}
}

// dispatchCommand routes a PipeCommand to the appropriate handler.
func dispatchCommand(cmd PipeCommand) PipeResponse {
	switch cmd.Command {
	case "get-status":
		return handleGetStatus()
	case "repair":
		return handleRepair()
	case "drain":
		// NEW (2026-10-20): manual drain trigger, for the Launcher's
		// "Drain and restart" button (future). Same code path as
		// PRESHUTDOWN, but callable on demand.
		handlePreshutdown()
		return PipeResponse{Success: true}
	case "wireguard-status":
		return handleWireGuardStatus()
	case "wireguard-install":
		return handleWireGuardInstall(cmd)
	case "wireguard-uninstall":
		return handleWireGuardUninstall()
	case "wireguard-start":
		return handleWireGuardStart()
	case "wireguard-stop":
		return handleWireGuardStop()
	default:
		return PipeResponse{
			Success: false,
			Error:   fmt.Sprintf("unknown command: %s", cmd.Command),
		}
	}
}

// handleGetStatus returns the current service status.
func handleGetStatus() PipeResponse {
	mu.RLock()
	ip := currentWSLIP
	mu.RUnlock()

	// Check whether a drain is in progress.
	drainInProgress := false
	if _, err := os.Stat(DrainRequestedFile); err == nil {
		drainInProgress = true
	}

	return PipeResponse{
		Success: true,
		Data: map[string]interface{}{
			"status":            "running",
			"wsl_ip":            ip,
			"forwarding_active": ip != "",
			"ports":             PortsToForward,
			"drain_in_progress": drainInProgress,
		},
	}
}

// handleRepair triggers an immediate reconciliation.
func handleRepair() PipeResponse {
	if err := reconcile(); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	return PipeResponse{Success: true}
}

// -----------------------------------------------------------------------------
// WireGuard command handlers
// -----------------------------------------------------------------------------

// handleWireGuardStatus returns the current state of the tunnel service.
func handleWireGuardStatus() PipeResponse {
	wg, err := NewWireGuardManager()
	if err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	st, err := wg.Status()
	if err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	return PipeResponse{Success: true, Data: st}
}

// handleWireGuardInstall writes the config, installs the tunnel service,
// and starts it. This is the main entry point for enabling WireGuard.
func handleWireGuardInstall(cmd PipeCommand) PipeResponse {
	wg, err := NewWireGuardManager()
	if err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}

	cfg := &WireGuardConfig{
		PrivateKey:          cmd.PrivateKey,
		Address:             cmd.Address,
		DNS:                 cmd.DNS,
		PublicKey:           cmd.PeerPublicKey,
		PresharedKey:        cmd.PresharedKey,
		Endpoint:            cmd.Endpoint,
		AllowedIPs:          cmd.AllowedIPs,
		PersistentKeepalive: cmd.PersistentKeepalive,
	}

	if err := wg.WriteConfig(cfg); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}

	if err := wg.Install(); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}

	if err := wg.Start(); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}

	return PipeResponse{Success: true}
}

// handleWireGuardUninstall stops and removes the tunnel service.
func handleWireGuardUninstall() PipeResponse {
	wg, err := NewWireGuardManager()
	if err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	if err := wg.Uninstall(); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	_ = wg.DeleteConfig()
	return PipeResponse{Success: true}
}

// handleWireGuardStart starts the tunnel service.
func handleWireGuardStart() PipeResponse {
	wg, err := NewWireGuardManager()
	if err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	if err := wg.Start(); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	return PipeResponse{Success: true}
}

// handleWireGuardStop stops the tunnel service.
func handleWireGuardStop() PipeResponse {
	wg, err := NewWireGuardManager()
	if err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	if err := wg.Stop(); err != nil {
		return PipeResponse{Success: false, Error: err.Error()}
	}
	return PipeResponse{Success: true}
}

// -----------------------------------------------------------------------------
// Service management (install / uninstall / start / stop)
// -----------------------------------------------------------------------------

// installService registers the service with the SCM and configures the
// preshutdown timeout.
//
// Two steps that are easy to miss:
//
//   1. mgr.Config does NOT have a preshutdown timeout field. The timeout
//      is configured via ChangeServiceConfig2(SERVICE_CONFIG_PRESHUTDOWN_INFO).
//      The simplest way to do this from Go is to shell out to `sc.exe`,
//      which is what the Windows ecosystem expects.
//
//   2. Even with the timeout configured, the SCM will only deliver
//      SERVICE_CONTROL_PRESHUTDOWN if the service reports
//      SERVICE_ACCEPT_PRESHUTDOWN in its status. That is handled in
//      Execute() via the cmdsAccepted constant.
func installService() error {
	exepath, err := os.Executable()
	if err != nil {
		return err
	}

	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()

	// Check if the service already exists.
	s, err := m.OpenService(ServiceName)
	if err == nil {
		s.Close()
		return fmt.Errorf("service %s already exists", ServiceName)
	}

	// Create the service.
	s, err = m.CreateService(ServiceName, exepath, mgr.Config{
		DisplayName:      ServiceDisplayName,
		Description:      ServiceDescription,
		StartType:        mgr.StartAutomatic,
		ErrorControl:     mgr.ErrorNormal,
		ServiceStartName: "LocalSystem",
	})
	if err != nil {
		return err
	}
	defer s.Close()

	// Configure restart-on-failure.
	s.SetRecoveryActions([]mgr.RecoveryAction{
		{Type: mgr.ServiceRestart, Delay: 60 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 60 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 60 * time.Second},
	}, 86400)

	// Configure the preshutdown timeout.
	//
	// This is the step that actually enables PRESHUTDOWN delivery.
	// `sc.exe config <service> preshutdown= 60000` calls
	// ChangeServiceConfig2 with SERVICE_CONFIG_PRESHUTDOWN_INFO and a
	// 60-second timeout. Without it, Windows never sends PRESHUTDOWN
	// to the service, and the graceful drain does not happen on a
	// Windows shutdown.
	//
	// We use sc.exe rather than syscall gymnastics because sc.exe is
	// the standard Windows tool, is always present, and the failure
	// mode (exit code + stderr) is clear. If this fails, we log a
	// warning but do not abort the install: the service will still
	// forward ports and manage WireGuard. Only the graceful drain
	// is degraded, and that is logged.
	psCmd := exec.Command(
		"sc.exe", "config", ServiceName,
		"preshutdown=", fmt.Sprintf("%d", PreshutdownTimeoutMs),
	)
	psCmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: 0x08000000, // CREATE_NO_WINDOW
	}
	if out, err := psCmd.CombinedOutput(); err != nil {
		fmt.Printf(
			"WARNING: failed to set preshutdown timeout: %v — %s\n"+
				"The service is installed but will not receive PRESHUTDOWN "+
				"on Windows shutdown. Run manually:\n"+
				"  sc.exe config %s preshutdown= %d\n",
			err, string(out), ServiceName, PreshutdownTimeoutMs,
		)
	} else {
		fmt.Printf(
			"Configured preshutdown timeout: %dms\n",
			PreshutdownTimeoutMs,
		)
	}

	return nil
}

// removeService removes the service from the SCM.
func removeService() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()

	s, err := m.OpenService(ServiceName)
	if err != nil {
		return fmt.Errorf("service %s is not installed", ServiceName)
	}
	defer s.Close()

	return s.Delete()
}

// startService starts the service.
func startService() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()

	s, err := m.OpenService(ServiceName)
	if err != nil {
		return err
	}
	defer s.Close()

	return s.Start()
}

// stopService stops the service.
func stopService() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()

	s, err := m.OpenService(ServiceName)
	if err != nil {
		return err
	}
	defer s.Close()

	status, err := s.Control(svc.Stop)
	if err != nil {
		return err
	}

	timeout := time.Now().Add(10 * time.Second)
	for status.State != svc.Stopped {
		if time.Now().After(timeout) {
			return fmt.Errorf("timeout waiting for service to stop")
		}
		time.Sleep(300 * time.Millisecond)
		status, err = s.Query()
		if err != nil {
			return err
		}
	}
	return nil
}

// -----------------------------------------------------------------------------
// main
// -----------------------------------------------------------------------------

func main() {
	// -------------------------------------------------------------------------
	// WireGuard tunnel service entry point.
	//
	// When Windows starts the WireGuardTunnel$NETTRADES service, it invokes
	// this binary with:
	//
	//     nettrades-netsvc.exe /service "C:\ProgramData\NETTRADES\wireguard\nettrades.conf"
	//
	// We must detect this before doing anything else, and delegate to
	// tunnel.dll's WireGuardTunnelService. This call blocks until the
	// service is stopped by the SCM.
	// -------------------------------------------------------------------------
	if len(os.Args) == 3 && os.Args[1] == "/service" {
		if err := runTunnelService(os.Args[2]); err != nil {
			// Write to stderr and exit non-zero. The SCM will log the
			// failure in the event log.
			fmt.Fprintf(os.Stderr, "WireGuard tunnel service failed: %v\n", err)
			os.Exit(1)
		}
		return
	}

	// -------------------------------------------------------------------------
	// Service management commands (install / uninstall / start / stop).
	// -------------------------------------------------------------------------
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "install":
			if err := installService(); err != nil {
				fmt.Fprintf(os.Stderr, "Install failed: %v\n", err)
				os.Exit(1)
			}
			fmt.Println("Service installed.")
			return

		case "uninstall":
			if err := stopService(); err != nil {
				fmt.Fprintf(os.Stderr, "Stop failed: %v\n", err)
			}
			if err := removeService(); err != nil {
				fmt.Fprintf(os.Stderr, "Uninstall failed: %v\n", err)
				os.Exit(1)
			}
			fmt.Println("Service uninstalled.")
			return

		case "start":
			if err := startService(); err != nil {
				fmt.Fprintf(os.Stderr, "Start failed: %v\n", err)
				os.Exit(1)
			}
			fmt.Println("Service started.")
			return

		case "stop":
			if err := stopService(); err != nil {
				fmt.Fprintf(os.Stderr, "Stop failed: %v\n", err)
				os.Exit(1)
			}
			fmt.Println("Service stopped.")
			return
		}
	}

	// -------------------------------------------------------------------------
	// Run as a Windows service.
	// -------------------------------------------------------------------------
	isService, err := svc.IsWindowsService()
	if err != nil {
		log.Fatalf("Failed to determine if running as service: %v", err)
	}

	if isService {
		// Running as a Windows service.
		elog, err := eventlog.Open(ServiceName)
		if err != nil {
			log.Fatalf("Failed to open event log: %v", err)
		}
		defer elog.Close()

		err = svc.Run(ServiceName, &nettradesService{elog: elog})
		if err != nil {
			log.Fatalf("Service failed: %v", err)
		}
		return
	}

	// Interactive mode (for debugging). This is useful when running the
	// binary directly from a terminal to test the reconciler.
	elog := debug.New(ServiceName)
	defer elog.Close()

	fmt.Println("Running in interactive mode. Press Ctrl+C to stop.")
	svc.Run(ServiceName, &nettradesService{elog: elog})
}