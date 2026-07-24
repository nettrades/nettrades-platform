# NETTRADES.AI – Quick Start

The front page has the installation instructions.

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/nettrades/nettrades-platform.git
   cd nettrades-platform
   ```

    Run the unified setup script:
    ```bash

    ./scripts/nettrades-setup.sh
    ```
    For a fully automated deployment (non-interactive):
    ```bash

    ./scripts/nettrades-setup.sh all --auto
    ```
    Access your platform at:

        Odoo: `http://localhost:8069` (admin / admin)

        Grafana: `http://localhost:3001` (admin / admin)

        LangGraph Health: `http://localhost:8000/health`

## Troubleshooting

| Issue | Solution |
|--------------|------------|
| Odoo returns 502 | Wait 30 seconds for PostgreSQL to start. |
| SSL certificate not issued | Ensure port 80 is open and DNS resolves correctly. |
| GPU not detected | Run `nvidia-smi;` if not available, install NVIDIA drivers. |
| LangGraph returns 500 | Check `docker compose logs langgraph` and verify `LANGGRAPH_API_KEY` in `.env`. |
| Password authentication failed | Ensure `db_password` in `odoo.conf` matches `POSTGRES_PASSWORD` in `.env`. Run `docker exec -it docker-postgres-1 psql -U odoo -c "ALTER USER odoo WITH PASSWORD 'odoo123';"` |
| Modules show "Activate" not "Upgrade" | Modules are not installed. Run `./scripts/install-modules.sh --force` or install via Odoo UI (Apps → Update Apps List). |
| Proxy not responding | Run `docker compose logs odoo-proxy` and verify Odoo is reachable. |
| postgres host not found | You are running Odoo outside Docker. Use `docker compose up -d` instead. |

For more detailed help, see the Full Documentation.

## Next Steps

[Single VM Deployment](operations/single-vm-deployment.md)

[Kubernetes Deployment](operations/kubernetes-deployment.md)

[GPU Node Deployment](operations/gpu-node-deployment.md)

[Developer Guide](developer/index.md)

   
   