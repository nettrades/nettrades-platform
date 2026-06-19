# DEPLOYMENT TEAM PERSPECTIVE — Network Diagram

Purpose: Shows the network topology, including subnets, firewalls, VPN tunnels, and service exposure.

---

## DEPLOYMENT TEAM PERSPECTIVE — Network Diagram

```mermaid
flowchart TB
    subgraph Internet["Internet"]
        Users["End Users"]
        APIClients["API Clients"]
        JobBoards["External Job Boards"]
    end

    subgraph DMZ["??? DMZ / Edge Network"]
        Firewall["Firewall<br>━━━━━━━━━━━━━━━━<br>• Allow: 443 (HTTPS)<br>• Allow: 22 (SSH - Admin)<br>• Allow: 51820 (WireGuard UDP)<br>• Deny: All Other"]
        Traefik["Traefik Load Balancer<br>━━━━━━━━━━━━━━━━<br>• Public IP: 203.0.113.10<br>• TLS Termination<br>• Rate Limiting"]
    end

    subgraph Internal["?? Internal Network (10.0.0.0/16)"]
        direction TB
        
        subgraph Subnet1["Subnet: 10.0.1.0/24 (Services)"]
            Odoo["Odoo Service<br>10.0.1.10:8069"]
            FastAPI["FastAPI Service<br>10.0.1.11:8000"]
            GPUStack["GPUStack Service<br>10.0.1.12:8080"]
            Valkey["Valkey Service<br>10.0.1.13:6379"]
            PostgreSQL["PostgreSQL Service<br>10.0.1.14:5432"]
        end
        
        subgraph Subnet2["Subnet: 10.0.2.0/24 (GPU Nodes)"]
            GPUNode1["GPU Node 1<br>10.0.2.10<br>WireGuard: 10.0.3.10"]
            GPUNode2["GPU Node 2<br>10.0.2.11<br>WireGuard: 10.0.3.11"]
            GPUNode3["GPU Node 3<br>10.0.2.12<br>WireGuard: 10.0.3.12"]
        end
        
        subgraph Subnet3["Subnet: 10.0.3.0/24 (WireGuard VPN)"]
            WGHub["WireGuard Hub<br>10.0.3.1<br>━━━━━━━━━━━━━━━━<br>• Hub-and-Spoke Topology<br>• Encrypted Mesh"]
        end
        
        subgraph Subnet4["Subnet: 10.0.4.0/24 (Storage)"]
            Longhorn["Longhorn Storage<br>10.0.4.10"]
            Backup["Backup Server<br>10.0.4.20"]
        end
    end

    subgraph ExternalServices["External Services"]
        Stripe["Stripe API<br>api.stripe.com"]
        LLMProviders["LLM Providers<br>api.openai.com"]
    end

    %% Connections
    Users -->|HTTPS:443| Firewall
    APIClients -->|HTTPS:443| Firewall
    JobBoards -->|HTTPS:443| Firewall
    
    Firewall -->|Allow:443| Traefik
    
    Traefik -->|"/"| Odoo
    Traefik -->|"/invoke"| FastAPI
    
    Odoo -->|"Internal"| PostgreSQL
    Odoo -->|"Internal"| Valkey
    Odoo -->|"Internal"| Longhorn
    
    FastAPI -->|"Internal"| PostgreSQL
    FastAPI -->|"Internal"| GPUStack
    
    GPUStack -->|"WireGuard VPN (10.0.3.x)"| WGHub
    WGHub -->|"Encrypted Tunnel"| GPUNode1
    WGHub -->|"Encrypted Tunnel"| GPUNode2
    WGHub -->|"Encrypted Tunnel"| GPUNode3
    
    GPUNode1 -->|"WireGuard"| WGHub
    GPUNode2 -->|"WireGuard"| WGHub
    GPUNode3 -->|"WireGuard"| WGHub
    
    Odoo -->|"HTTPS"| Stripe
    FastAPI -->|"HTTPS (Fallback)"| LLMProviders
    
    PostgreSQL -->|"Backup"| Backup
    Longhorn -->|"Backup"| Backup

    classDef internet fill:#e3f2fd,stroke:#1565c0;
    classDef dmz fill:#fff3e0,stroke:#e65100;
    classDef internal fill:#e8f5e9,stroke:#2e7d32;
    classDef external fill:#fce4ec,stroke:#c62828;

    class Internet internet;
    class DMZ dmz;
    class Internal internal;
    class ExternalServices external;
