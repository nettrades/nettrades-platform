# Developer FAQ – Frequently Asked Questions

This page answers common questions from developers contributing to or extending the NETTRADES.AI platform.

---

## General

### What technologies does the platform use?

- **Backend**: Python (Odoo 19 CE, LangGraph, FastAPI)
- **Database**: PostgreSQL 18 with pgvector
- **Caching**: Valkey (Redis‑compatible)
- **Containerisation**: Docker and Kubernetes (Talos)
- **GPU orchestration**: GPUStack
- **Networking**: WireGuard
- **Frontend**: Odoo's Owl framework (JavaScript)

### How do I set up a development environment?

Follow the [Developer Getting Started Guide](/developer/getting-started). It covers everything from installing dependencies to running Odoo locally.

### What is the code structure?

- `src/core/` – LangGraph supervisor and sub‑agents
- `src/agent/` – Distributed GPU node agent
- `odoo-modules/` – Custom Odoo modules (LGPL‑3.0)
- `third-party/` – Vendored dependencies (do not modify)
- `deploy/` – Deployment scripts and configurations

### What are the licensing requirements?

- `src/` is AGPL‑3.0 (copyleft).
- `odoo-modules/` is LGPL‑3.0.
- Third‑party dependencies retain their own licenses.
- All contributors must sign a CLA.

See the [License Information](/governance/license) for details.

---

## Building & Extending

### How do I create a new LangGraph agent?

1. Create a new file in `src/core/agents/` (e.g., `custom_agent.py`).
2. Define your agent's state and nodes.
3. Compile the graph using `StateGraph`.
4. Register it with the supervisor in `src/core/supervisor.py`.
5. Update the intent classification to route to your agent.

Full template: [Building LangGraph Agents](/developer/building-agents).

### How do I create a new Odoo module?

1. Create a folder under `odoo-modules/` with the module name.
2. Add `__manifest__.py`, `__init__.py`, and subdirectories (`models/`, `views/`, `security/`, etc.).
3. Define your models, views, and access rights.
4. Install the module using the Odoo UI or CLI.

Full template: [Building Odoo Modules](/developer/building-odoo-modules).

### How do I extend the GPU Admin Panel dashboard?

1. Locate `odoo-modules/nettrades_gpu_admin/static/src/js/dashboard.js`.
2. Add a new Owl component.
3. Register it in the widget registry.
4. Add the template to `gpu_dashboard_templates.xml`.

### How do I integrate with the MCP‑Odoo bridge?

The bridge is already available at `third-party/mcp-odoo/`. Use the `odoo_tools.py` functions (e.g., `res_partner_search`, `crm_lead_create`) to call Odoo from your agents. Ensure you authenticate with the `ODOO_API_KEY`.

---

## API & Integration

### What authentication is required for the `/invoke` endpoint?

You need to set the `X-API-Key` header to the value of `LANGGRAPH_API_KEY` from your environment.

### How do I test the API locally?

Run Odoo and LangGraph locally, then use `curl` to send requests to `http://localhost:8000/invoke` (or the FastAPI port). Example:
```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"input": {"messages": [{"role":"user","content":"Hello"}]}}'