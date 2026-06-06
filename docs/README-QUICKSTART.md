# NETTRADES.AI — Quickstart Guide

## Prerequisites
- **Docker** and **Docker Compose** installed ([Docker Engine](https://docs.docker.com/engine/install/))
- **git** installed
- A **domain name** pointing to your server's IP address (required for Let's Encrypt TLS)
- **Ports 80 and 443** open on the server firewall
- **Linux kernel ≥ 6.19.14** (or ≥ 6.18.24) to mitigate WireGuard CVE-2026-31579

## One-Command Deploy

```bash
# 1. Clone the project
git clone <your-repo-url> nettrades-app
cd nettrades-app/marketplace-platform

# 2. Generate secrets (strong random passwords for all services)
bash .env.generator.sh > .env
chmod 600 .env

# 3. Deploy
sudo bash install-nettrades.sh --auto