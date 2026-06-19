# Technical Solution Architecture (Single-VM Deployment)

Networks: Docker web network (172.20.0.0/24) for public?facing services; internal network (172.21.0.0/24) for databases and inference engines.

Firewall (UFW): Allow only ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 51820 (WireGuard).

SSL: Traefik automatically obtains Let's Encrypt certificates via HTTP?01 challenge. Port 80 must be open.

---

## Technical Solution Architecture (Single-VM Deployment)

```mermaid
graph TB
    subgraph VM["Ubuntu 24.04 VM (Docker Compose)"]
        Traefik["Traefik v3.6 (reverse proxy + Let's Encrypt)"] --> Odoo & Forgejo & Grafana & LangGraph & GPUStack
        Odoo["Odoo 19 CE"] --> PG["(PostgreSQL 18 + pgvector)"] & Valkey["(Valkey 8)"]
        LangGraph["LangGraph Agent"] --> GPUStack["GPUStack Server"] & llama-cpp["llama.cpp (CPU)"] & MCP["MCP?Odoo Bridge"]
        MCP --> Odoo
    end

    User --> Traefik
