
# System Requirements

This document provides comprehensive system requirements for deploying and running the NETTRADES.AI platform.

---

## Overview

NETTRADES.AI can be deployed in two configurations:

| Configuration | Best For | Hardware Requirements |
|---------------|----------|----------------------|
| **Single VM (Docker Compose)** | Development, testing, small production | Single server |
| **Kubernetes on Talos** | Production, high availability, enterprise scaling | Multi-node cluster |

---

## Single VM Requirements

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores | 8+ cores (AMD Ryzen 9 / Intel Xeon) |
| **RAM** | 16 GB | 32+ GB |
| **Storage** | 100 GB (NVMe SSD) | 200+ GB (NVMe SSD) |
| **Network** | 100 Mbps | 1 Gbps |
| **GPU (Optional)** | NVIDIA GPU (RTX 4090, A100, etc.) | 2+ NVIDIA GPUs |

### Operating System

| OS | Version | Support |
|----|---------|---------|
| **Ubuntu** | 24.04 LTS | ✅ Full support |
| **Ubuntu** | 22.04 LTS | ✅ Full support |
| **Debian** | 12 | ✅ Full support |
| **RHEL** | 9 | ⚠️ Limited (some scripts may need adjustment) |
| **Windows Server** | 2022 | ❌ Not supported for production |

### Software Dependencies

| Software | Version | Purpose |
|----------|---------|---------|
| **Docker** | 27.x+ | Container runtime |
| **Docker Compose** | v2.x+ | Container orchestration |
| **Git** | Latest | Source control |
| **curl** | Latest | API and download utility |

### Ports

| Port | Protocol | Purpose | Required |
|------|----------|---------|----------|
| 22 | TCP | SSH | ✅ Yes (administrative) |
| 80 | TCP | HTTP (redirect to HTTPS) | ✅ Yes (Let's Encrypt) |
| 443 | TCP | HTTPS | ✅ Yes (web access) |
| 51820 | UDP | WireGuard | Optional (GPU nodes) |
| 5432 | TCP | PostgreSQL | ❌ No (internal only) |
| 8069 | TCP | Odoo | ❌ No (internal only) |
| 8000 | TCP | LangGraph API | ❌ No (internal only) |


---

## Kubernetes on Talos Requirements

### Hardware Requirements (Per Node)

| Node Type | CPU | RAM | Storage | GPU |
|-----------|-----|-----|---------|-----|
| **Control Plane** | 4 vCPU | 8 GB | 50 GB | None |
| **Worker (CPU)** | 8 vCPU | 16 GB | 100 GB | None |
| **Worker (GPU)** | 8 vCPU | 32 GB | 200 GB | 1+ NVIDIA GPU |

### Cluster Sizing

| Cluster Size | Control Planes | CPU Workers | GPU Workers |
|--------------|----------------|-------------|-------------|
| **Small** | 3 | 3 | 0-2 |
| **Medium** | 3 | 5 | 2-4 |
| **Large** | 3 | 10+ | 4+ |

### Software Dependencies

| Software | Version | Purpose |
|----------|---------|---------|
| **Talos Linux** | 1.12.6+ | Immutable Kubernetes OS |
| **talosctl** | Latest | Talos CLI |
| **kubectl** | Latest | Kubernetes CLI |
| **helm** | Latest | Package manager |
| **opentofu** | Latest | Infrastructure as Code (optional) |

### Proxmox Host Requirements (for VM deployment)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | AMD Ryzen 7 | AMD Ryzen 9 7900+ |
| **RAM** | 32 GB | 64+ GB |
| **Storage** | 500 GB | 1+ TB NVMe |
| **Network** | 1 Gbps | 10 Gbps |

### Network Bridges (Proxmox)

| Bridge | Purpose | Subnet |
|--------|---------|--------|
| `vmbr0` | Public / DMZ | DHCP / Static public IP |
| `vmbr1` | Private / Pod networking | 10.0.0.0/24 |
| `vmbr2` | Isolated / Runners | 10.0.1.0/24 |

---

## GPU Requirements

### Supported GPU Models

| Vendor | Models | Notes |
|--------|--------|-------|
| **NVIDIA** | A100, A6000, RTX 4090, RTX 6000 Ada, H100 | Full support |
| **NVIDIA** | RTX 3090, 4080, 5080 | Supported (consumer-grade) |
| **AMD** | MI250, MI300 | Limited support (experimental) |
| **Apple** | M1, M2, M3 | Limited support (Metal) |

### GPU Driver Requirements

| Vendor | Driver Version | CUDA Version | Notes |
|--------|----------------|--------------|-------|
| **NVIDIA** | 550+ | 12.4+ | Required for NVIDIA dynamo |
| **NVIDIA** | 535+ | 12.2 | Minimum for vLLM |

### VRAM Requirements

| Model Size | VRAM Required | Deployment |
|------------|---------------|------------|
| **1.5B-7B** | 4-8 GB | Single GPU |
| **8B-14B** | 8-16 GB | Single GPU (large) |
| **14B-34B** | 16-32 GB | Single GPU (A100) |
| **34B-70B** | 32-80 GB | Multi-GPU required |
| **70B+** | 80+ GB | Multi-GPU required |

---

## Network Requirements

### Domain & DNS

- **Domain name** – e.g., `nettrades.ai`
- **Wildcard DNS** – `*.nettrades.ai` should resolve to your server's IP
- **SSL** – Let's Encrypt (automatic via Traefik)

### Bandwidth

| Activity | Bandwidth | Latency |
|----------|-----------|---------|
| **Web UI** | 1-10 Mbps | < 200 ms |
| **Model Download** | 10-100 Mbps | < 500 ms |
| **Inference** | 10-100 Mbps | < 50 ms (low latency) |
| **Multi-GPU Training** | 1-10 Gbps | < 10 ms (low latency) |

---

## Storage Requirements

### Single VM

| Component | Storage | Notes |
|-----------|---------|-------|
| **PostgreSQL** | 20-100 GB | Grows with usage |
| **Odoo Filestore** | 10-50 GB | CVs, attachments, logos |
| **Models** | 10-100 GB | LLM weights (GGUF, Safetensors) |
| **Datasets** | 10-100 GB | Fine-tuning datasets |
| **Backups** | 50-200 GB | Daily database backups |

### Kubernetes

| Component | Storage Class | Size | Notes |
|-----------|---------------|------|-------|
| **PostgreSQL** | Longhorn | 100-500 GB | CNPG cluster |
| **Valkey** | Longhorn | 10-50 GB | StatefulSet |
| **Odoo Filestore** | Longhorn (RWX) | 50-200 GB | ReadWriteMany |
| **Models** | Longhorn (RWX) | 50-500 GB | Shared across workers |

---

## Environment Variables Reference

A full list of environment variables is available in the [Appendix](/appendix/environment-variables).

| Variable | Purpose | Required |
|----------|---------|----------|
| `DOMAIN` | Main domain | ✅ Yes |
| `ADMIN_EMAIL` | Admin email for Let's Encrypt | ✅ Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | ✅ Yes |
| `LANGGRAPH_API_KEY` | API key for LangGraph | ✅ Yes |


---

## Next Steps

- [Single VM Deployment →](single-vm-deployment.md)
- [Kubernetes Deployment →](kubernetes-deployment.md)
- [GPU Node Deployment →](gpu-node-deployment.md)
