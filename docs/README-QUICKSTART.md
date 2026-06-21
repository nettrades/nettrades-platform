
# NETTRADES.AI – Quick Start

This guide provides the fastest way to get the platform running on a single Ubuntu 24.04 VM.

---

## One-Command Deployment

```bash
# Download and run the interactive installer
curl -sSL https://raw.githubusercontent.com/nettrades/nettrades-platform/main/deploy/docker/install-nettrades.sh | sudo bash
```

Follow the interactive wizard. It will auto-detect your hardware, ask for your domain, generate passwords, and start all services.

After ~10-20 minutes, you'll have:

Odoo 19 CE – https://<your-domain>

Grafana – https://grafana.<your-domain>

GPUStack – https://gpustack.<your-domain>

Forgejo – https://git.<your-domain>

LangGraph Agent – https://langgraph.<your-domain>

llama.cpp (CPU inference) or vLLM (GPU inference) – auto‑detected.

All services are secured with Let's Encrypt TLS.

## Manual Setup (if you prefer step-by-step)

#### Clone the repository

```bash

git clone https://github.com/nettrades/nettrades-platform.git
cd nettrades-platform
```


#### Run the deployment script

```bash

sudo bash deploy/docker/install-nettrades.sh

```
#### Follow the prompts

You will be asked for:

Your domain name (e.g., nettrades.ai)

Your admin email (for Let's Encrypt)

Confirmation of auto‑detected hardware (CPU cores, RAM, GPU presence)

Wait for the stack to start (10-20 minutes)

Log in to Odoo at https://<your-domain> and create your admin account.

## Troubleshooting

Odoo returns 502 – Wait 30 seconds for PostgreSQL to start.

SSL certificate not issued – Ensure port 80 is open and DNS resolves correctly.

GPU not detected – Run nvidia-smi; if not available, install NVIDIA drivers.

For more detailed help, see the Full Documentation.


## Next Steps

[Single VM Deployment ](operations/single-vm-deployment)

[Kubernetes Deployment](operations/kubernetes-deployment)

[GPU Node Deployment](operations/gpu-node-deployment)

[Developer Guide](developer/)
    
Follow the interactive wizard. It will auto‑detect your hardware, ask for your domain, generate passwords, and start all services.

After ~10-20 minutes, you'll have:

Odoo 19 CE – https://<your-domain>

Grafana – https://grafana.<your-domain>

GPUStack – https://gpustack.<your-domain>

Forgejo – https://git.<your-domain>

LangGraph Agent – https://langgraph.<your-domain>

llama.cpp (CPU inference) or vLLM (GPU inference) – auto‑detected.

All services are secured with Let's Encrypt TLS.
Manual Setup (if you prefer step‑by‑step)

Clone the repository

```bash

git clone https://github.com/nettrades/nettrades-platform.git
cd nettrades-platform
```

Run the deployment script

```bash

sudo bash deploy/docker/install-nettrades.sh

```
Follow the prompts

You will be asked for:

Your domain name (e.g., nettrades.ai)

Your admin email (for Let's Encrypt)

Confirmation of auto‑detected hardware (CPU cores, RAM, GPU presence)

Wait for the stack to start (10‑20 minutes)

Log in to Odoo at https://<your-domain> and create your admin account.

Troubleshooting

Odoo returns 502 – Wait 30 seconds for PostgreSQL to start.

SSL certificate not issued – Ensure port 80 is open and DNS resolves correctly.

GPU not detected – Run nvidia-smi; if not available, install NVIDIA drivers.

For more detailed help, see the Full Documentation.
Next Steps

Single VM Deployment (full guide)

Kubernetes Deployment

GPU Node Deployment

Developer Guide