# NETTRADES.AI Platform

Welcome to the NETTRADES.AI documentation!

---

## 🚀 Quick Start

| I want to... | Start here |
|--------------|------------|
| **Try the platform without installing anything** | [Try It Now →](/try-it-now) |
| **Get started (any role)** | [Getting Started →](/getting-started.md) |
| **Use the platform** (as a company, freelancer, or job-seeker) | [User Guide →](/user/index.md) |
| **Develop or extend the platform** | [Developer Guide →](/developer/index.md) |
| **Deploy and run the platform** | [Operations Guide →](/operations/index.md) |
| **Contribute to the project** | [Governance →](/governance/index.md) |
| **Understand key terms** | [Glossary →](/appendix/glossary.md) |

---

## What is NETTRADES.AI?

NETTRADES.AI is an **open-source, autonomous enterprise platform** that connects companies, freelancers, job-seekers, researchers, partners, and customers.

It combines:

- **AI-powered job matching & freelancing** – LangGraph agents analyse CVs, job postings, and projects, automatically creating leads.
- **Distributed GPU marketplace** – Companies and freelancers can share idle GPUs to run inference and fine-tuning, earning tokens.
- **Self-improving AI** – A "Good Answer" voting system feeds a fine-tuning pipeline (Unsloth/Axolotl) that continuously improves field-specific models.
- **Expert marketplace ("Ask Someone")** – Users can request paid help from verified professionals with Stripe escrow.
- **Autonomous administration** – GPU health watchdog, reputation decay, utilisation alerts, and automatic Karma-based qualification.

---

## Key Features at a Glance

| Feature | Description |
|---------|-------------|
| 🤖 **AI Agents** | LangGraph-based recruitment, freelancing, lead generation, GPU management, vision, and action agents |
| 🖥️ **GPU Marketplace** | Share idle GPUs or rent capacity for inference and fine-tuning |
| 🧠 **Self-Improving AI** | "Good Answer" voting system with automated fine-tuning via Unsloth/Axolotl |
| 🧑‍🏫 **Expert Help** | "Ask Someone" – real-time expert consultations with Stripe escrow |
| 🔐 **Secure & Sovereign** | WireGuard VPN, gVisor isolation, and full on-premise deployment options |

---

## Who Is This For?

| Role | What You Can Do |
|------|-----------------|
| **Companies** | Post jobs, find candidates, manage hiring pipelines, share idle GPUs |
| **Freelancers** | Find projects, submit proposals, manage milestones, earn tokens |
| **Job Seekers** | Find jobs, apply with one click, track applications |
| **Experts** | Offer paid help, accept sessions, earn money |
| **Researchers** | Post research projects, find partners, collaborate |
| **Developers** | Build custom agents, extend Odoo modules, contribute to the platform |
| **Operators** | Deploy, manage, and scale the platform |

---

## Technology Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| **Odoo** | 19.0 CE | ERP, marketplace, CRM, HR, Projects, Accounting |
| **PostgreSQL + pgvector** | 18.1 | Business data, vector embeddings, LangGraph checkpoints |
| **Valkey** | 8 | Session storage, ORM cache, bus notifications |
| **LangGraph** | ≥1.2.0 | Multi-agent orchestration, durable execution |
| **GPUStack** | v2.1.2 | GPU cluster manager, inference engine, token metering |
| **WireGuard** | kernel module | Kernel-level network isolation |
| **gVisor** | release-20260420.0 | Syscall-level container isolation |

---

## License

| Component | License |
|-----------|---------|
| `src/` (core orchestrator, agent, training scripts) | **AGPL-3.0** |
| `odoo-modules/` (custom Odoo plugins) | **LGPL-3.0** |
| `third-party/` | Original licenses (LGPL, MIT, Apache-2.0) |

---

## Community & Support

- **GitHub Issues**: [github.com/nettrades/nettrades-platform/issues](https://github.com/nettrades/nettrades-platform/issues)
- **Discord**: [Join our community](https://discord.gg/nettrades)
- **Email**: [dev@nettrades.ai](mailto:dev@nettrades.ai)
- **Website**: [nettrades.ai](https://nettrades.ai)
