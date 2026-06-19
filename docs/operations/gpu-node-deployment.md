
---

## File 20: `docs/operations/gpu-node-deployment.md`

```markdown
# GPU Node Deployment

This guide covers deploying GPU nodes to the distributed GPU network on both Linux and Windows.

---

## Overview

GPU nodes are machines with one or more NVIDIA GPUs that participate in the distributed inference and fine-tuning network. The GPU node agent:

1. Detects available GPUs
2. Generates a hardware-bound node ID
3. Registers with the Odoo server
4. Sets up WireGuard encryption
5. Starts the GPUStack worker
6. Maintains a heartbeat and DNS watchdog

---

## Architecture Diagram

```mermaid
graph TB
    subgraph GPUNode["GPU Node"]
        Agent["NETTRADES GPU Agent"]
        WireGuard["WireGuard Tunnel"]
        GPUStack["GPUStack Worker"]
        GPU["NVIDIA GPU(s)"]
    end

    subgraph Central["NETTRADES Central"]
        Odoo["Odoo Server"]
        Controller["WireGuard Controller"]
        GPUStackServer["GPUStack Server"]
    end

    Agent --> Odoo
    Agent --> WireGuard
    WireGuard --> Controller
    Agent --> GPUStack
    GPUStack --> GPUStackServer
    GPUStack --> GPU