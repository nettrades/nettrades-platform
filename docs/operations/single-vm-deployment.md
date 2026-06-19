
---

## File: `docs/operations/single-vm-deployment.md` (With Architecture Diagram)

```markdown
# Single VM Deployment (Docker Compose)

This guide walks you through deploying the NETTRADES.AI platform on a single Ubuntu 24.04 virtual machine using Docker Compose.

---

## Architecture Diagram

```mermaid
graph TB
    subgraph VM["Ubuntu 24.04 VM (Docker Compose)"]
        Traefik["Traefik v3.6 (reverse proxy + Let's Encrypt)"] --> Odoo & Forgejo & Grafana & LangGraph & GPUStack
        Odoo["Odoo 19 CE"] --> PG["PostgreSQL 17 + pgvector"] & Valkey["Valkey 8"]
        LangGraph["LangGraph Agent"] --> GPUStack["GPUStack Server"] & llama-cpp["llama.cpp (CPU)"] & MCP["MCP-Odoo Bridge"]
        MCP --> Odoo
    end

    User --> Traefik