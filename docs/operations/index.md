# Operations Documentation

Welcome to the NETTRADES.AI operations documentation. This section is designed for system administrators, DevOps engineers, and anyone deploying or managing the platform.

---

## Overview

NETTRADES.AI can be deployed in two ways:

| Deployment Type | Best For | Complexity | Scalability |
|-----------------|----------|------------|-------------|
| **Single VM (Docker Compose)** | Small to medium deployments, testing, proof of concept | Low | Limited (single machine) |
| **Kubernetes on Talos** | Production, high availability, enterprise scaling | High | Unlimited (horizontal scaling) |

---

## Quick Start

### For a Single VM Deployment

1. Prepare an Ubuntu 24.04 VM with root access.
2. Run the one‑command installer:

```bash
curl -sSL https://raw.githubusercontent.com/nettrades/nettrades-platform/main/deploy/docker/install-nettrades.sh | sudo bash