# NETTRADES.AI Platform

Welcome to the NETTRADES.AI documentation!

## Quick Start

| I want to... | Start here |
|--------------|------------|
| **Try the platform without installing anything** | [Try It Now →](try-it-now.md) |
| **Get started (any role)** | [Getting Started →](getting-started.md) |
| **Use the platform** (as a company, freelancer, or job-seeker) | [User Guide →](user/index.md) |
| **Develop or extend the platform** | [Developer Guide →](developer/index.md) |
| **Deploy and run the platform** | [Operations Guide →](operations/index.md) |
| **Contribute to the project** | [Governance →](governance/index.md) |
| **Understand key terms** | [Glossary →](appendix/glossary.md) |

---

## What is NETTRADES.AI?

NETTRADES.AI is an **open-source, autonomous enterprise platform** that builds **Sovereign AI Infrastructure** using spare GPU capacity. It acts as a **Sovereign AI Router** that lets organisations securely control their AI infrastructure from a single dashboard.

Organisations can decide to keep everything local or decide which types of requests are processed locally and which types of requests are routed to remote providers or a GPU marketplace, at peak time, based on administrative settings.

### Core Capabilities

- **🧠 Sovereign AI Router** – Route requests between local and remote brains based on intent, company policy and GPU capacity
- **🎮 NVIDIA Dynamo** – Production-grade distributed inference with vLLM and llama.cpp fallback
- **🤖 Agentic AI** – LangGraph-based multi-agent system for autonomous enterprise operations
- **💰 Distributed GPU Marketplace** – Companies and freelancers can share idle GPUs to run inference and fine-tuning, earning tokens
- **📊 Self-Improving AI** – "Good Answer" voting system feeds a fine-tuning pipeline (Unsloth/Axolotl) that continuously improves field-specific models
- **🙋 Expert Marketplace ("Ask Someone")** – Users can request paid help from verified professionals with Stripe escrow
- **⚖️ Fairness & Bias Detection** – AI responses are evaluated for rationality and bias, with configurable thresholds and automated filtering
- **🔒 Secure & Sovereign** – WireGuard VPN, gVisor isolation, and full on-premise deployment options
- **🎮 Steam-like Launcher** – One-click deployment, GPU detection, model management, node discovery, and WireGuard VPN management

---

## Key Features at a Glance

| Feature | Description |
|---------|-------------|
| **🤖 AI Agents** | LangGraph-based recruitment, freelancing, lead generation, GPU management, vision, and action agents |
| **🎮 GPU Marketplace** | Share idle GPUs or rent capacity for inference and fine-tuning |
| **🧠 Self-Improving AI** | "Good Answer" voting system with automated fine-tuning via Unsloth/Axolotl |
| **🙋 Expert Help** | "Ask Someone" – real-time expert consultations with Stripe escrow |
| **⚖️ Fairness & Bias** | LLM-as-Judge rationality and bias evaluation with automated filtering |
| **🔒 Secure & Sovereign** | WireGuard VPN, gVisor isolation, and full on-premise deployment options |
| **🎮 Launcher** | Steam-like interface for one-click deployment, GPU management, and chat |
| **🌐 mDNS Discovery** | Automatic discovery of other NETTRADES nodes on your network |

---

## Who Is This For?

| Role | What You Can Do |
|------|-----------------|
| **🏢 Companies** | Post jobs, find candidates, manage hiring pipelines, share idle GPUs, run sovereign AI |
| **💼 Freelancers** | Find projects, submit proposals, manage milestones, earn tokens |
| **👨‍💻 Job Seekers** | Find jobs, apply with one click, track applications |
| **👨‍🔬 Experts** | Offer paid help, accept sessions, earn money |
| **🔬 Researchers** | Post research projects, find partners, collaborate |
| **👨‍💻 Developers** | Build custom agents, extend Odoo modules, contribute to the platform |
| **⚙️ Operators** | Deploy, manage, and scale the platform |
| **🏠 Home Users** | Chat with AI, run local models, earn passive income by sharing GPU |

---

## Technology Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| **Odoo** | 19.0 CE | ERP, marketplace, CRM, HR, Projects, Accounting |
| **PostgreSQL + pgvector** | 17 | Business data, vector embeddings, LangGraph checkpoints |
| **Valkey** | 8 | Session storage, ORM cache, bus notifications |
| **LangGraph** | ≥1.2.0 | Multi-agent orchestration, durable execution |
| **NVIDIA Dynamo** | 1.2.1 | Distributed inference engine with vLLM and llama.cpp |
| **vLLM** | Latest | GPU-accelerated inference |
| **llama.cpp** | Latest | CPU inference fallback |
| **Traefik** | v3.6.13 | Reverse proxy with Let's Encrypt SSL |
| **WireGuard** | kernel | VPN mesh for secure node-to-node communication |
| **gVisor** | Latest | Container isolation for security hardening |
| **Prometheus** | Latest | Metrics collection and monitoring |
| **Grafana** | Latest | Visualisation and dashboards |
| **mDNS/Avahi** | Latest | Automatic node discovery |

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                          NETTRADES LAUNCHER (Electron)             │
│                   Primary Interface – Steam-like Experience        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌─────────┐│
│ │  🏠 HOME   │ │  💬 CHAT │ │ 🎮 MODELS │ │ 🌐 NETWORK │ │💰 MARKET││
│ │  Dashboard │ │  AI Chat │ │ Library  │ │ Nodes/VPN  │ │ GPUs    ││
│ └────────────┘ └──────────┘ └──────────┘ └────────────┘ └─────────┘│
│                                                                    │
│ ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌────────────┐ ┌───────────┐│
│ │🎯 TRAIN │ │ 🤖 AGENTS │ │ 📋 QUEUE │ │ 📈 MONITOR │ │ ⚙️ SETUP  ││
│ │Fine-Tune │ │ Manage    │ │ Tasks   │ │ Health     │ │ Deploy    ││
│ └──────────┘ └───────────┘ └─────────┘ └────────────┘ └───────────┘│
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────┐
│                            BACKEND SERVICES                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ ┌───────────┐ ┌────────────┐ ┌───────────┐┌───────────┐ ┌─────────┐│
│ │ ODOO      │ │ LANGGRAPH  │ │ DYNAMO    ││ LLAMA.CPP │ │POSTGRES ││
│ │ 19 CE     │ │ Agents     │ │ NVIDIA    ││ Fallback  │ │+pgvector││
│ │ Governance│ │Orchestrator│ │ Inference ││ CPU       │ │ RAG     ││
│ └───────────┘ └────────────┘ └───────────┘└───────────┘ └─────────┘│
│                                                                    │
│ ┌────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│ │ VALKEY │ │ TRAEFIK  │ │ PROMETHEUS │ │ GRAFANA    │ │ WIREGUARD│ │
│ │ Cache  │ │ Proxy/SSL│ │ Metrics    │ │ Dashboards │ │ VPN Mesh │ │
│ └────────┘ └──────────┘ └────────────┘ └────────────┘ └──────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```


---

## Hub-and-Spoke Architecture

The NETTRADES platform uses a hub-and-spoke architecture:

- **Hub (nettrades.ai)**: Runs the full platform with GPU marketplace, training, and global services
- **Client Company Spokes**: Full platform installation managed by company administrators
- **Home User Spokes**: Mini-hub with launcher for distributed inference

All communication is secured via WireGuard VPN, ensuring data never leaves the trusted network.

---

## Next Steps

- [Getting Started](getting-started.md) – Choose your path
- [User Guide](user/index.md) – Full user documentation
- [Developer Guide](developer/index.md) – Build and extend
- [Operations Guide](operations/index.md) – Deploy and manage