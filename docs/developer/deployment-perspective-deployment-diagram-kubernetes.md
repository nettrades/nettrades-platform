# DEPLOYMENT TEAM PERSPECTIVE — Deployment Diagram (Kubernetes)

Purpose: Shows the physical deployment of all containers on a Kubernetes cluster, including namespaces, pod placements, and persistent volumes.

---

## DEPLOYMENT TEAM PERSPECTIVE — Deployment Diagram (Kubernetes)

```mermaid
flowchart TB
    subgraph K8s["? Kubernetes Cluster (Talos Linux)"]
        direction TB
        
        subgraph Namespace["Namespace: nettrades"]
            
            subgraph EdgePods["Edge Layer Pods"]
                TraefikPod["Traefik Pod<br>━━━━━━━━━━━━━━━━<br>• Container: traefik:3.6<br>• Ports: 443 (HTTPS), 80 (HTTP)<br>• Service: LoadBalancer<br>• ConfigMap: traefik-config"]
            end
            
            subgraph AppPods["Application Pods"]
                OdooPod["Odoo Pod<br>━━━━━━━━━━━━━━━━<br>• Container: odoo:19.0<br>• Port: 8069<br>• Service: ClusterIP<br>• PVC: odoo-filestore<br>• ConfigMap: odoo-config<br>• Secrets: odoo-secrets"]
                
                LangGraphPod["LangGraph Pod<br>━━━━━━━━━━━━━━━━<br>• Container: langgraph:latest<br>• Port: 8000<br>• Service: ClusterIP<br>• ConfigMap: langgraph-config"]
                
                NVIDIADynamoPod["NVIDIA Dynamo Pod<br>━━━━━━━━━━━━━━━━<br>• Container: NVIDIAdynamo:2.1<br>• Port: 8080<br>• Service: ClusterIP<br>• GPU: nvidia.com/gpu: 1<br>• PVC: NVIDIAdynamo-models"]
                
                MLPipelinePod["ML Pipeline Pod<br>━━━━━━━━━━━━━━━━<br>• Container: ml-pipeline:latest<br>• GPU: nvidia.com/gpu: 1 (optional)<br>• PVC: ml-datasets<br>• Triggered by CronJob"]
            end
            
            subgraph DataPods["Data Layer Pods"]
                PostgresPod["PostgreSQL Pod<br>━━━━━━━━━━━━━━━━<br>• Container: postgres:17<br>• Port: 5432<br>• Service: ClusterIP<br>• PVC: postgres-data (50GB)<br>• StatefulSet with HA"]
                
                ValkeyPod["Valkey Pod<br>━━━━━━━━━━━━━━━━<br>• Container: valkey:8<br>• Port: 6379<br>• Service: ClusterIP<br>• PVC: valkey-data (10GB)"]
                
                LonghornPod["Longhorn Pod<br>━━━━━━━━━━━━━━━━<br>• Container: longhorn:1.11<br>• Port: 9500<br>• Service: ClusterIP<br>• PVC: longhorn-storage (1TB)<br>• DaemonSet on each node"]
            end
            
            subgraph MonitoringPods["Monitoring Pods"]
                PrometheusPod["Prometheus Pod<br>━━━━━━━━━━━━━━━━<br>• Container: prometheus:v3.8<br>• Port: 9090<br>• Service: ClusterIP<br>• PVC: prometheus-data"]
                
                GrafanaPod["Grafana Pod<br>━━━━━━━━━━━━━━━━<br>• Container: grafana:12.4<br>• Port: 3000<br>• Service: ClusterIP<br>• PVC: grafana-data"]
            end
        end
        
        subgraph Storage["?? Persistent Volumes"]
            PV1["PV: postgres-data<br>━━━━━━━━━━━━━━━━<br>• 50GB NVMe SSD<br>• ReadWriteOnce"]
            PV2["PV: longhorn-storage<br>━━━━━━━━━━━━━━━━<br>• 1TB NVMe SSD<br>• ReadWriteMany"]
            PV3["PV: model-storage<br>━━━━━━━━━━━━━━━━<br>• 200GB NVMe SSD<br>• ReadWriteOnce"]
        end
        
        subgraph Nodes["??? Physical Nodes"]
            Node1["Node 1 (Control Plane)<br>━━━━━━━━━━━━━━━━<br>• 8 vCPU, 32GB RAM<br>• 100GB SSD"]
            Node2["Node 2 (GPU Worker)<br>━━━━━━━━━━━━━━━━<br>• 16 vCPU, 64GB RAM<br>• 1x NVIDIA A100 (80GB)<br>• 500GB NVMe SSD"]
            Node3["Node 3 (GPU Worker)<br>━━━━━━━━━━━━━━━━<br>• 16 vCPU, 64GB RAM<br>• 1x NVIDIA A100 (80GB)<br>• 500GB NVMe SSD"]
        end
    end

    subgraph External["?? External"]
        Internet["Internet"]
        Stripe["Stripe API"]
    end

    %% Connections
    Internet -->|"HTTPS (443)"| TraefikPod
    TraefikPod -->|"Routes to"| OdooPod
    TraefikPod -->|"Routes /invoke to"| LangGraphPod
    
    OdooPod -->|"SQL"| PostgresPod
    OdooPod -->|"Cache"| ValkeyPod
    OdooPod -->|"Files"| LonghornPod
    
    NVIDIADynamoPod -->|"Checkpoints"| PostgresPod
    LangGraphPod -->|"Inference"| NVIDIADynamoPod
    
    NVIDIADynamoPod -->|"GPU Acceleration"| Node2
    NVIDIADynamoPod -->|"GPU Acceleration"| Node3
    
    MLPipelinePod -->|"Training"| Node2
    MLPipelinePod -->|"Datasets"| LonghornPod
    
    OdooPod -->|"Payments"| Stripe
    
    PrometheusPod -->|"Scrapes"| OdooPod
    PrometheusPod -->|"Scrapes"| LangGraphPod
    PrometheusPod -->|"Scrapes"| NVIDIADynamoPod
    GrafanaPod -->|"Queries"| PrometheusPod

    PostgresPod --> PV1
    LonghornPod --> PV2
    NVIDIADynamoPod --> PV3

    classDef external fill:#e3f2fd,stroke:#1565c0;
    classDef edge fill:#fff3e0,stroke:#e65100;
    classDef app fill:#f3e5f5,stroke:#6a1b9a;
    classDef data fill:#e8f5e9,stroke:#2e7d32;
    classDef monitoring fill:#fce4ec,stroke:#c62828;
    classDef storage fill:#ede7f6,stroke:#4527a0;
    classDef nodes fill:#eceff1,stroke:#37474f;

    class External external;
    class EdgePods edge;
    class AppPods app;
    class DataPods data;
    class MonitoringPods monitoring;
    class Storage storage;
    class Nodes nodes;

```
