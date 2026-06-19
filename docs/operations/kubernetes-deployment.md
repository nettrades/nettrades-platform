
# Kubernetes on Talos Deployment

This guide walks you through deploying the NETTRADES.AI platform on a production-grade Kubernetes cluster using **Talos Linux** as the operating system and **Proxmox** as the hypervisor.

---

## Architecture Overview

```mermaid
graph TB
    subgraph Internet["🌐 Internet"]
        Users["End Users"]
    end

    subgraph Proxmox["🖥️ Proxmox Host"]
        subgraph TalosCluster["☸ Talos Kubernetes Cluster"]
            CP1["Control Plane 1<br>(4 vCPU, 8GB RAM)"]
            CP2["Control Plane 2<br>(4 vCPU, 8GB RAM)"]
            CP3["Control Plane 3<br>(4 vCPU, 8GB RAM)"]
            W1["Worker 1 (CPU)<br>(8 vCPU, 16GB RAM)"]
            W2["Worker 2 (CPU)<br>(8 vCPU, 16GB RAM)"]
            W3["Worker 3 (GPU)<br>(8 vCPU, 16GB RAM + NVIDIA GPU)"]
        end

        subgraph Storage["💾 Storage"]
            Longhorn["Longhorn<br>(Distributed Block Storage)"]
        end
    end

    subgraph Services["☸ Kubernetes Services"]
        Traefik["Traefik Ingress"]
        Odoo["Odoo 19 CE<br>(3 replicas)"]
        PG["PostgreSQL HA<br>(CloudNativePG)"]
        Valkey["Valkey Cluster"]
        LangGraph["LangGraph Agent"]
        GPUStack["GPUStack Server"]
        vLLM["vLLM (GPU)"]
        Forgejo["Forgejo Git"]
        Grafana["Grafana"]
        ArgoCD["Argo CD"]
    end

    Users --> Traefik
    Traefik --> Odoo & Grafana & LangGraph & GPUStack & Forgejo & ArgoCD
    Odoo --> PG & Valkey
    LangGraph --> GPUStack & vLLM
    GPUStack --> vLLM
    CP1 & CP2 & CP3 --> TalosCluster
    W1 & W2 & W3 --> TalosCluster
    Longhorn --> PG & Valkey & Odoo
