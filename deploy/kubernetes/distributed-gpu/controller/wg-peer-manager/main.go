/*
=============================================================================
Section: H – WireGuard Peer Manager
Purpose:  Syncs WireGuard peers on the controller node with Odoo's gpu.node
          table.  Uses wgctrl-go to programmatically add/remove peers.
          Runs as a DaemonSet (hostNetwork) inside the K8s cluster.
=============================================================================
*/
package main

import (
    "encoding/json"
    "log"
    "net"
    "net/http"
    "os"
    "time"

    "golang.zx2c4.com/wireguard/wgctrl"
    "golang.zx2c4.com/wireguard/wgctrl/wgtypes"
)

var client *wgctrl.Client
var odooURL string
var odooAPIKey string

func main() {
    odooURL := os.Getenv("ODOO_URL")
    if odooURL == "" {
        odooURL = "http://odoo.frontend.svc.cluster.local:8069"
    }
    odooAPIKey = os.Getenv("ODOO_API_KEY")
    var err error
    client, err = wgctrl.New()
    if err != nil {
        log.Fatalf("Failed to create wgctrl client: %v", err)
    }
    defer client.Close()

    // Start health-check HTTP server
    go func() {
        http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
            w.WriteHeader(http.StatusOK)
            w.Write([]byte("ok"))
        })
        if err := http.ListenAndServe(":8081", nil); err != nil {
            log.Printf("Health server error: %v", err)
        }
    }()

    // Main sync loop
    for {
        syncPeers(odooURL)
        time.Sleep(30 * time.Second)
    }
}

func syncPeers(odooURL string) {
    url := odooURL + "/api/v1/gpu/peers"
    req, err := http.NewRequest("GET", url, nil)
    if err != nil {
        log.Println("request error:", err)
        return
    }
    if odooAPIKey != "" {
        req.Header.Set("Authorization", "Bearer "+odooAPIKey)
    }
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        log.Println("sync error:", err)
        return
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        log.Printf("Odoo API returned status %d", resp.StatusCode)
        return
    }

    var peers []struct {
        PublicKey string `json:"public_key"`
        AllowedIP string `json:"allowed_ip"`
        Remove    bool   `json:"remove,omitempty"`
    }
    if err := json.NewDecoder(resp.Body).Decode(&peers); err != nil {
        log.Println("decode error:", err)
        return
    }

    for _, p := range peers {
        key, err := wgtypes.ParseKey(p.PublicKey)
        if err != nil {
            log.Printf("invalid key %s: %v", p.PublicKey, err)
            continue
        }
        if p.Remove {
            cfg := wgtypes.Config{
                Peers: []wgtypes.PeerConfig{{PublicKey: key, Remove: true}},
            }
            if err := client.ConfigureDevice("wg0", cfg); err != nil {
                log.Printf("remove peer %s: %v", p.PublicKey, err)
            }
        } else {
            _, ipNet, _ := net.ParseCIDR(p.AllowedIP)
            cfg := wgtypes.Config{
                Peers: []wgtypes.PeerConfig{{
                    PublicKey:         key,
                    ReplaceAllowedIPs: true,
                    AllowedIPs:        []net.IPNet{*ipNet},
                }},
            }
            if err := client.ConfigureDevice("wg0", cfg); err != nil {
                log.Printf("add/update peer %s: %v", p.PublicKey, err)
            }
        }
    }
}