# Developer Documentation

Welcome to the NETTRADES.AI developer documentation. This section is designed for developers and contributors who want to extend, customize, or contribute to the platform.

---

## What Can You Build?

### 🤖 New LangGraph Agents
Add new AI agents to handle specific business domains – recruitment, lead generation, customer service, or anything else.

[Learn about building agents →](/developer/building-agents)

### 🧩 New Odoo Modules
Extend the platform with new business functionality – new data models, views, workflows, or integrations.

[Learn about building Odoo modules →](/developer/building-odoo-modules)

### 🖥️ Custom Dashboard Widgets
Add new widgets to the GPU Admin Panel or create custom dashboards for specific user roles.

[Learn about the GPU Admin Panel →](/developer/building-odoo-modules#extending-the-gpu-admin-panel)

---

## Getting Started as a Developer

1. **Set up your development environment** – Install Python, PostgreSQL, Docker, and clone the repository.
2. **Run the platform locally** – Start Odoo and the LangGraph service.
3. **Explore the codebase** – Understand the architecture and key components.
4. **Build your first agent or module** – Use our templates and guides.

[Full developer getting started guide →](/developer/getting-started)

---

## Key Architecture Components

| Component | Location | Description |
|-----------|----------|-------------|
| **LangGraph Supervisor** | `src/core/supervisor.py` | Central orchestrator that classifies intents and routes to sub-agents |
| **FastAPI Application** | `src/core/app.py` | Entry point for AI inference requests `/invoke` |
| **Sub-Agents** | `src/core/agents/` | Specialised business agents (Recruitment, Freelance, Lead Gen, GPU Management) |
| **Distributed GPU Agent** | `src/agent/agent.py` | Runs on each GPU node, manages WireGuard and GPUStack |
| **Odoo Modules** | `odoo-modules/` | Business logic, UI, and administration |
| **MCP-Odoo Bridge** | `third-party/mcp-odoo/` | Allows AI agents to interact with Odoo data |

[Full architecture overview →](/developer/architecture)

---

## Project Status

| Component | Status | Notes |
|-----------|--------|-------|
| LangGraph Supervisor | ✅ Core logic exists | Medical screening loop needs fixing |
| Sub-Agents | ⚠️ Placeholders | Real code in `src/agent/` needs moving |
| FastAPI Application | ✅ Core endpoints exist | Authentication needs fixing |
| GPU Node Agent | ✅ Full implementation | `requirements.txt` needs fixing |
| Odoo `nettrades.field` | ⚠️ Sparse | 24+ fields missing |
| Odoo `gpu.node` | ⚠️ Sparse | 15+ fields and methods missing |
| Odoo `gpu.cluster` | ❌ Broken | Indentation bug, missing methods |
| Deployment Scripts | ✅ Full | Phase-based orchestrator works |

[Full roadmap →](/governance/roadmap)

---

## Code Style & Standards

We follow the OCA (Odoo Community Association) conventions for Odoo modules and PEP 8 for Python code.

- **Python**: PEP 8, type hints, docstrings
- **Odoo**: OCA conventions, LGPL-3.0 license for modules
- **JavaScript**: Owl framework conventions
- **XML**: Prefix XML IDs with module name

[Full style guide →](/developer/style-guide)

---

## API Reference

- [LangGraph `/invoke` API →](/developer/api-reference#langgraph-invoke-api)
- [GPU Node Registration →](/developer/api-reference#gpu-node-registration-api)
- [GPUStack Token Refresh →](/developer/api-reference#gpustack-token-refresh-api)
- [WebSocket Bus API →](/developer/api-reference#websocket-bus-api)

---

## Contributing

We welcome contributions! Please read our [Contributing Guide](/governance/contributing) before submitting PRs.

Key points:
- **CLA required** – All contributors must sign the CLA
- **LGPL-3.0 for Odoo modules** – Your contributions must be LGPL-3.0 compatible
- **AGPL-3.0 for core** – Your contributions to `src/` must be AGPL-3.0 compatible
- **Code review** – All PRs require review

---

## Need Help?

- **GitHub Issues**: [github.com/nettrades/nettrades-platform/issues](https://github.com/nettrades/nettrades-platform/issues)
- **Discord**: [Join our community](https://discord.gg/nettrades)
- **Email**: [dev@nettrades.ai](mailto:dev@nettrades.ai)