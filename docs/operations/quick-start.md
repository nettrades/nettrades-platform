
---

## File: `docs/operations/quick-start.md`

```markdown
# Quick Start – Operations

This guide provides a **5-minute** walkthrough to get NETTRADES.AI running on a single server for evaluation or small-scale production.

---

## Prerequisites

- A fresh Ubuntu 24.04 server with root access.
- A domain name pointing to your server's public IP (e.g., `nettrades.ai`).
- Ports 80 and 443 open.

---

## One-Command Installation

```bash
# Download and run the interactive installer
curl -sSL https://raw.githubusercontent.com/nettrades/nettrades-platform/main/deploy/docker/install-nettrades.sh | sudo bash