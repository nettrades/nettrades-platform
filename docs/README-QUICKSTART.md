
# NETTRADES.AI – Quick Start

The front page has the installation instructions

Troubleshooting

Odoo returns 502 – Wait 30 seconds for PostgreSQL to start.

SSL certificate not issued – Ensure port 80 is open and DNS resolves correctly.

GPU not detected – Run nvidia-smi; if not available, install NVIDIA drivers.

LangGraph returns 500 – Check docker compose logs langgraph and verify PROXY_API_KEY matches ODOO_API_KEY in .env.

Proxy not responding – Run docker compose logs odoo-proxy and verify Odoo is reachable.

For more detailed help, see the Full Documentation.

Next Steps

[Single VM Deployment](operations/single-vm-deployment.md)

[Kubernetes Deployment](operations/kubernetes-deployment.md)

[GPU Node Deployment](operations/gpu-node-deployment.md)

[Developer Guide](developer/index.md)
