# DEPLOYMENT TEAM PERSPECTIVE — Infrastructure Diagram (Single VM)

Purpose: Shows how all services are deployed on a single virtual machine, including container orchestration, resource allocation, and persistent storage.

---

## DEPLOYMENT TEAM PERSPECTIVE — Infrastructure Diagram (Single VM)

```mermaid
flowchart TB
    subgraph VM["??? Single Virtual Machine"]
        direction TB
        
        subgraph Host["Host OS: Ubuntu 22.04 LTS / Talos Linux"]
            CPU["CPU: 16+ Cores"]
            RAM["RAM: 64+ GB"]
            GPU["GPU: 1+ NVIDIA GPUs<br>????????????????<br>• Driver: 550+<br>• CUDA: 12.4+<br>• nvidia-container-toolkit"]
            Storage["Storage: 1+ TB NVMe SSD<br>????????????????<br>• /var/lib/docker (200GB)<br>• /mnt/longhorn (500GB)<br>• /mnt/models (300GB)"]
        end
        
        subgraph Docker["?? Docker Containers"]
            direction TB
            
            TraefikC["traefik:3.6<br>????????????????<br>• Ports: 443, 80<br>• Config: /etc/traefik"]
            
            OdooC["odoo:19.0<br>????????????????<br>• Port: 8069<br>• Volumes: ./odoo-data<br>• Depends: postgres, valkey"]
            
            LangGraphC["langgraph:latest<br>????????????????<br>• Port: 8000<br>• Volumes: ./langgraph-data<br>• Depends: postgres"]
            
            GPUStackC["gpustack:2.1<br>????????????????<br>• Port: 8080<br>• GPUs: all<br>• Volumes: ./models<br>• Depends: gpu-node-agent"]
            
            GPUNodeC["gpu-node-agent:latest<br>????????????????<br>• Privileged: true<br>• GPUs: all<br>• Volumes: /dev, /proc<br>• Network: host"]
            
            PostgresC["postgres:17<br>????????????????<br>• Port: 5432<br>• Volumes: ./postgres-data<br>• Environment: POSTGRES_*"]
            
            ValkeyC["valkey:8<br>????????????????<br>• Port: 6379<br>• Volumes: ./valkey-data"]
            
            LonghornC["longhorn:1.11<br>????????????????<br>• Port: 9500<br>• Volumes: ./longhorn-data"]
            
            PrometheusC["prometheus:v3.8<br>????????????????<br>• Port: 9090<br>• Volumes: ./prometheus-data"]
            
            GrafanaC["grafana:12.4<br>????????????????<br>• Port: 3000<br>• Volumes: ./grafana-data"]
        end
        
        subgraph Volumes["?? Host Volumes (Docker Mounts)"]
            PostgresVol["/var/lib/postgresql/data"]
            OdooVol["/var/lib/odoo/filestore"]
            ModelVol["/mnt/models"]
            LonghornVol["/mnt/longhorn"]
        end
    end

    subgraph External["?? External"]
        Internet["Internet"]
    end

    %% Connections
    Internet -->|"HTTPS:443"| TraefikC
    
    TraefikC -->|"Routes /"| OdooC
    TraefikC -->|"Routes /invoke"| LangGraphC
    
    OdooC -->|"SQL"| PostgresC
    OdooC -->|"Cache"| ValkeyC
    OdooC -->|"Files"| LonghornC
    
    LangGraphC -->|"Checkpoints"| PostgresC
    LangGraphC -->|"Inference"| GPUStackC
    
    GPUStackC -->|"Manages"| GPUNodeC
    GPUNodeC -->|"Uses"| GPU
    
    PostgresC --> PostgresVol
    OdooC --> OdooVol
    GPUStackC --> ModelVol
    LonghornC --> LonghornVol
    
    PrometheusC -->|"Scrapes"| OdooC
    PrometheusC -->|"Scrapes"| LangGraphC
    PrometheusC -->|"Scrapes"| GPUStackC
    GrafanaC -->|"Queries"| PrometheusC

    classDef vm fill:#eceff1,stroke:#37474f;
    classDef host fill:#e3f2fd,stroke:#1565c0;
    classDef docker fill:#f3e5f5,stroke:#6a1b9a;
    classDef volumes fill:#e8f5e9,stroke:#2e7d32;
    classDef external fill:#fce4ec,stroke:#c62828;

    class VM vm;
    class Host host;
    class Docker docker;
    class Volumes volumes;
    class External external;