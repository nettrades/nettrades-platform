// =============================================================================
// FILE: nettrades-netsvc/wireguard.go
// PURPOSE:
//   Manages WireGuard tunnels using the official WireGuard embeddable
//   service (tunnel.dll). The NETTRADES service creates a child service
//   named WireGuardTunnel$NETTRADES with the parameters required by
//   WireGuard's embeddable service documentation.
//
// ARCHITECTURE:
//   The tunnel.dll embeddable service works by installing a Windows
//   service whose executable path includes "/service <configfile>".
//   When Windows starts that service, it invokes our binary with the
//   /service argument. Our main() detects this and delegates to
//   WireGuardTunnelService() exported by tunnel.dll.
//
//   This file provides:
//     - WireGuardManager: creates/removes/starts/stops the tunnel service
//     - WireGuardConfig: the parsed wg-quick(8) configuration
//     - runTunnelService(): the /service entry point
//
// DEPENDENCIES:
//   tunnel.dll and wireguard.dll must be in the same directory as the
//   service executable. They are downloaded from:
//     https://download.wireguard.com/wireguard-nt/
//     https://git.zx2c4.com/wireguard-windows/about/embeddable-dll-service/README.md
//
// SECURITY:
//   The config file contains the WireGuard private key. It is written to
//   C:\ProgramData\NETTRADES\wireguard\nettrades.conf with restrictive
//   permissions. For production, use the .conf.dpapi format which
//   encrypts the private key with DPAPI under the LocalSystem account.
// =============================================================================

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

// -----------------------------------------------------------------------------
// Constants
// -----------------------------------------------------------------------------

const (
	// TunnelName is the name used in the service name
	// WireGuardTunnel$NETTRADES and the config filename.
	TunnelName = "NETTRADES"

	// TunnelServicePrefix is the required prefix for WireGuard tunnel
	// services. The embeddable service documentation specifies
	// "WireGuardTunnel$SomeTunnelName".
	TunnelServicePrefix = "WireGuardTunnel$"

	// TunnelServiceName is the full Windows service name.
	TunnelServiceName = TunnelServicePrefix + TunnelName

	// WireGuardConfigDir is where the config file is stored. It must be
	// readable by LocalSystem (the tunnel service's account).
	WireGuardConfigDir = `C:\ProgramData\NETTRADES\wireguard`

	// WireGuardConfigFile is the plaintext wg-quick(8) configuration.
	WireGuardConfigFile = "nettrades.conf"

	// TunnelDLLName is the embeddable service DLL.
	TunnelDLLName = "tunnel.dll"

	// WireGuardDLLName is the WireGuard NT driver DLL required by tunnel.dll.
	WireGuardDLLName = "wireguard.dll"
)

// -----------------------------------------------------------------------------
// WireGuardConfig — the wg-quick(8) configuration
// -----------------------------------------------------------------------------

// WireGuardConfig holds the fields of a standard wg-quick(8) config file.
// It maps directly to the [Interface] and [Peer] sections that the
// WireGuard tunnel service parses.
type WireGuardConfig struct {
	// [Interface] section
	PrivateKey string // base64-encoded private key
	Address    string // e.g. "10.0.0.2/32"
	DNS        string // e.g. "8.8.8.8, 1.1.1.1" (optional)
	MTU        int    // optional

	// [Peer] section
	PublicKey           string // base64-encoded server public key
	PresharedKey        string // optional
	Endpoint            string // e.g. "vpn.example.com:51820"
	AllowedIPs          string // e.g. "0.0.0.0/0, ::/0"
	PersistentKeepalive int    // seconds, e.g. 25
}

// Render produces the wg-quick(8) text representation.
func (c *WireGuardConfig) Render() string {
	var b strings.Builder
	b.WriteString("[Interface]\n")
	b.WriteString(fmt.Sprintf("PrivateKey = %s\n", c.PrivateKey))
	b.WriteString(fmt.Sprintf("Address = %s\n", c.Address))
	if c.DNS != "" {
		b.WriteString(fmt.Sprintf("DNS = %s\n", c.DNS))
	}
	if c.MTU > 0 {
		b.WriteString(fmt.Sprintf("MTU = %d\n", c.MTU))
	}
	b.WriteString("\n[Peer]\n")
	b.WriteString(fmt.Sprintf("PublicKey = %s\n", c.PublicKey))
	if c.PresharedKey != "" {
		b.WriteString(fmt.Sprintf("PresharedKey = %s\n", c.PresharedKey))
	}
	b.WriteString(fmt.Sprintf("Endpoint = %s\n", c.Endpoint))
	b.WriteString(fmt.Sprintf("AllowedIPs = %s\n", c.AllowedIPs))
	if c.PersistentKeepalive > 0 {
		b.WriteString(fmt.Sprintf("PersistentKeepalive = %d\n", c.PersistentKeepalive))
	}
	return b.String()
}

// -----------------------------------------------------------------------------
// WireGuardStatus — the tunnel service state
// -----------------------------------------------------------------------------

type WireGuardStatus struct {
	Installed bool   `json:"installed"`
	Running   bool   `json:"running"`
	State     string `json:"state"`
	ConfigPath string `json:"config_path,omitempty"`
}

// -----------------------------------------------------------------------------
// WireGuardManager
// -----------------------------------------------------------------------------

// WireGuardManager manages the lifecycle of the NETTRADES WireGuard tunnel.
type WireGuardManager struct {
	configPath string
	exePath    string
}

// NewWireGuardManager creates a manager bound to the running executable.
func NewWireGuardManager() (*WireGuardManager, error) {
	exePath, err := os.Executable()
	if err != nil {
		return nil, fmt.Errorf("could not determine executable path: %w", err)
	}
	if err := os.MkdirAll(WireGuardConfigDir, 0755); err != nil {
		return nil, fmt.Errorf("could not create config dir: %w", err)
	}
	return &WireGuardManager{
		configPath: filepath.Join(WireGuardConfigDir, WireGuardConfigFile),
		exePath:    exePath,
	}, nil
}

// ConfigPath returns the path of the plaintext config file.
func (wg *WireGuardManager) ConfigPath() string { return wg.configPath }

// -----------------------------------------------------------------------------
// Config file management
// -----------------------------------------------------------------------------

// WriteConfig writes the wg-quick(8) configuration to disk and restricts
// its permissions so only SYSTEM and Administrators can read it.
func (wg *WireGuardManager) WriteConfig(cfg *WireGuardConfig) error {
	if cfg.PrivateKey == "" || cfg.PublicKey == "" || cfg.Endpoint == "" {
		return fmt.Errorf("config missing required fields (PrivateKey, PublicKey, Endpoint)")
	}
	body := cfg.Render()
	if err := os.WriteFile(wg.configPath, []byte(body), 0600); err != nil {
		return fmt.Errorf("could not write config: %w", err)
	}
	// Lock down ACL: only SYSTEM and Administrators.
	_ = restrictToSystemAndAdmins(wg.configPath)
	return nil
}

// ReadConfig loads the plaintext config file. It is used by the status
// endpoint and by the Launcher's management UI.
func (wg *WireGuardManager) ReadConfig() (*WireGuardConfig, error) {
	data, err := os.ReadFile(wg.configPath)
	if err != nil {
		return nil, err
	}
	return parseWgQuick(string(data)), nil
}

// DeleteConfig removes the config file.
func (wg *WireGuardManager) DeleteConfig() error {
	err := os.Remove(wg.configPath)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// -----------------------------------------------------------------------------
// Service lifecycle
// -----------------------------------------------------------------------------

// Install creates (or updates) the WireGuardTunnel$NETTRADES service.
//
// The service name MUST follow the WireGuardTunnel$<name> pattern. The
// binary path MUST include the /service argument and the config file.
// The SidType MUST be SERVICE_SID_TYPE_UNRESTRICTED. These are all
// requirements of the embeddable service documentation.
func (wg *WireGuardManager) Install() error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("could not connect to service manager: %w", err)
	}
	defer m.Disconnect()

	// The binary path is:
	//   "C:\path\to\svc.exe" /service "C:\path\to\nettrades.conf"
	// This is exactly what the WireGuard embeddable service documentation
	// specifies for the Executable field.
	binaryPath := fmt.Sprintf(`"%s" /service "%s"`, wg.exePath, wg.configPath)

	cfg := mgr.Config{
		DisplayName:  "NETTRADES WireGuard Tunnel",
		Description:  "WireGuard tunnel managed by the NETTRADES service.",
		StartType:    mgr.StartManual, // we start it explicitly; not at boot
		ErrorControl: mgr.ErrorNormal,
		Dependencies: []string{"Nsi", "TcpIp"},
		SidType:      windows.SERVICE_SID_TYPE_UNRESTRICTED,
	}

	// Try to open an existing service first.
	existing, err := m.OpenService(TunnelServiceName)
	if err == nil {
		// Service exists — update its configuration.
		defer existing.Close()

		// Stop it if running, so we can update the binary path and config.
		if status, qerr := existing.Query(); qerr == nil {
			if status.State != svc.Stopped {
				_, _ = existing.Control(svc.Stop)
				waitForState(existing, svc.Stopped, 10*time.Second)
			}
		}

		currentCfg, cerr := existing.Config()
		if cerr != nil {
			return fmt.Errorf("could not read existing service config: %w", cerr)
		}
		currentCfg.BinaryPathName = binaryPath
		currentCfg.DisplayName = cfg.DisplayName
		currentCfg.Description = cfg.Description
		currentCfg.Dependencies = cfg.Dependencies
		currentCfg.SidType = cfg.SidType

		if err := existing.UpdateConfig(currentCfg); err != nil {
			return fmt.Errorf("could not update service config: %w", err)
		}
		return nil
	}

	// Service does not exist — create it.
	s, err := m.CreateService(TunnelServiceName, binaryPath, cfg)
	if err != nil {
		return fmt.Errorf("could not create tunnel service: %w", err)
	}
	defer s.Close()
	return nil
}

// Start starts the tunnel service. Windows will invoke our binary with
// /service <configPath>, and our main() will call WireGuardTunnelService.
func (wg *WireGuardManager) Start() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()
	s, err := m.OpenService(TunnelServiceName)
	if err != nil {
		return fmt.Errorf("tunnel service not installed: %w", err)
	}
	defer s.Close()
	return s.Start()
}

// Stop stops the tunnel service.
func (wg *WireGuardManager) Stop() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()
	s, err := m.OpenService(TunnelServiceName)
	if err != nil {
		return err
	}
	defer s.Close()
	_, err = s.Control(svc.Stop)
	return err
}

// Uninstall stops and removes the tunnel service.
func (wg *WireGuardManager) Uninstall() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()
	s, err := m.OpenService(TunnelServiceName)
	if err != nil {
		if err == windows.ERROR_SERVICE_DOES_NOT_EXIST {
			return nil
		}
		return err
	}
	defer s.Close()
	if status, qerr := s.Query(); qerr == nil && status.State != svc.Stopped {
		_, _ = s.Control(svc.Stop)
		waitForState(s, svc.Stopped, 15*time.Second)
	}
	return s.Delete()
}

// Status reports the state of the tunnel service.
func (wg *WireGuardManager) Status() (*WireGuardStatus, error) {
	st := &WireGuardStatus{ConfigPath: wg.configPath}

	m, err := mgr.Connect()
	if err != nil {
		return st, err
	}
	defer m.Disconnect()

	s, err := m.OpenService(TunnelServiceName)
	if err != nil {
		if err == windows.ERROR_SERVICE_DOES_NOT_EXIST {
			st.State = "not_installed"
			return st, nil
		}
		return st, err
	}
	defer s.Close()

	st.Installed = true
	status, err := s.Query()
	if err != nil {
		return st, err
	}
	st.Running = status.State == svc.Running
	st.State = stateName(status.State)
	return st, nil
}

// -----------------------------------------------------------------------------
// /service entry point
// -----------------------------------------------------------------------------

// runTunnelService is called by main() when the process is started with
// `/service <configfile>`. It loads tunnel.dll from the executable's
// directory and calls the exported WireGuardTunnelService function.
//
// The WireGuardTunnelService function is a Go function exported as a
// C-shared library. It takes a GoString (pointer + length), NOT a
// null-terminated C string. This is a common source of crashes when
// integrating with the embeddable DLL service.
//
// This function blocks until the tunnel service is stopped by the SCM.
func runTunnelService(configFile string) error {
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("could not locate executable: %w", err)
	}
	dllPath := filepath.Join(filepath.Dir(exePath), TunnelDLLName)

	if _, err := os.Stat(dllPath); err != nil {
		return fmt.Errorf("%s not found next to executable (%s): %w",
			TunnelDLLName, dllPath, err)
	}

	tunnelDLL := syscall.NewLazyDLL(dllPath)
	if err := tunnelDLL.Load(); err != nil {
		return fmt.Errorf("could not load %s: %w", TunnelDLLName, err)
	}

	proc := tunnelDLL.NewProc("WireGuardTunnelService")
	if err := proc.Find(); err != nil {
		return fmt.Errorf("WireGuardTunnelService not exported by %s: %w",
			TunnelDLLName, err)
	}

	// The WireGuardTunnelService function is a Go function exported as
	// a C-shared library. It takes a GoString, not a UTF-16 pointer.
	//
	// We must NOT pass a UTF-16 pointer. The GoString expects a UTF-8
	// byte array (the Go string representation).
	//
	// The struct layout on 64-bit Windows is:
	//   type GoString struct {
	//       str *byte  // pointer to the string data
	//       len int    // length of the string
	//   }
	//
	// The struct is passed by value. In Go assembly terms, this is
	// two machine words (pointer + int).
	//
	// We use syscall.Syscall to call the function with the correct
	// calling convention. The function is declared as:
	//
	//   BOOL (_cdecl *tunnel_proc)(_In_ LPCWSTR conf_file);
	//
	// Wait — the C# example shows:
	//
	//   [DllImport("tunnel.dll", EntryPoint = "WireGuardTunnelService",
	//       CallingConvention = CallingConvention.Cdecl)]
	//   private static extern bool WireGuardTunnelService(GoString configFile);
	//
	// and the GoString is defined as:
	//
	//   [StructLayout(LayoutKind.Sequential)]
	//   public struct GoString {
	//       public IntPtr str;
	//       public int len;
	//   }
	//
	// This means the function takes a GoString, not a UTF-16 pointer.
	// The GoString contains a pointer to the UTF-8 encoded config file
	// path and its length.

	// Encode the config file path as UTF-8.
	configBytes := []byte(configFile)

	// Build the GoString struct on the stack. We use a byte slice
	// so the pointer remains valid for the duration of the call.
	// The struct layout is pointer (8 bytes) + int (8 bytes on 64-bit).
	type goString struct {
		str *byte
		len int
	}

	gs := goString{
		str: &configBytes[0],
		len: len(configBytes),
	}

	// Call the function with the GoString passed by value.
	// On 64-bit Windows, the first argument is passed in RCX.
	// The GoString is 16 bytes, which fits in two registers (RCX and RDX).
	ret, _, callErr := proc.Call(uintptr(unsafe.Pointer(&gs)))
		if ret == 0 {
			if callErr != nil && callErr != syscall.Errno(0) {
				return fmt.Errorf("WireGuardTunnelService returned failure: %v", callErr)
			}
			return fmt.Errorf("WireGuardTunnelService returned failure (0)")
		}
		return nil
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

// restrictToSystemAndAdmins applies a restrictive DACL to the given file
// so that only SYSTEM and the Administrators group can read it. This
// protects the WireGuard private key at rest.
func restrictToSystemAndAdmins(path string) error {
	// Use icacls as the simplest portable mechanism. In a future version
	// this can be replaced with a direct SetNamedSecurityInfo call.
	return runHidden("icacls", path, "/inheritance:r",
		"/grant:r", `SYSTEM:(R)`,
		"/grant:r", `BUILTIN\Administrators:(R)`)
}

// waitForState polls the service until it reaches the desired state or
// the timeout expires. Used before updating or deleting a service.
func waitForState(s *mgr.Service, desired svc.State, timeout time.Duration) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		st, err := s.Query()
		if err != nil {
			return
		}
		if st.State == desired {
			return
		}
		time.Sleep(300 * time.Millisecond)
	}
}

// stateName converts an svc.State to a human-readable string.
func stateName(s svc.State) string {
	switch s {
	case svc.Stopped:
		return "stopped"
	case svc.StartPending:
		return "start_pending"
	case svc.StopPending:
		return "stop_pending"
	case svc.Running:
		return "running"
	case svc.ContinuePending:
		return "continue_pending"
	case svc.PausePending:
		return "pause_pending"
	case svc.Paused:
		return "paused"
	default:
		return "unknown"
	}
}

// parseWgQuick parses a wg-quick(8) configuration string into a
// WireGuardConfig. It is intentionally forgiving: unknown keys are
// ignored, and comments (#) are stripped.
func parseWgQuick(text string) *WireGuardConfig {
	cfg := &WireGuardConfig{}
	section := ""
	for _, raw := range strings.Split(text, "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.ToLower(strings.Trim(line, "[] "))
			continue
		}
		eq := strings.Index(line, "=")
		if eq < 0 {
			continue
		}
		key := strings.TrimSpace(line[:eq])
		val := strings.TrimSpace(line[eq+1:])
		switch strings.ToLower(section) {
		case "interface":
			switch key {
			case "PrivateKey":
				cfg.PrivateKey = val
			case "Address":
				cfg.Address = val
			case "DNS":
				cfg.DNS = val
			case "MTU":
				fmt.Sscanf(val, "%d", &cfg.MTU)
			}
		case "peer":
			switch key {
			case "PublicKey":
				cfg.PublicKey = val
			case "PresharedKey":
				cfg.PresharedKey = val
			case "Endpoint":
				cfg.Endpoint = val
			case "AllowedIPs":
				cfg.AllowedIPs = val
			case "PersistentKeepalive":
				fmt.Sscanf(val, "%d", &cfg.PersistentKeepalive)
			}
		}
	}
	return cfg
}