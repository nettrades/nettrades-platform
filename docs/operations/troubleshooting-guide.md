
---

## File: `docs/operations/troubleshooting-guide.md`

```markdown
# Troubleshooting Decision Tree

This guide provides a visual, step‑by‑step approach to diagnosing common NETTRADES.AI issues.

---

## Overview

```mermaid
graph TD
    A[Issue Detected] --> B{What is the symptom?}
    
    B -->|"Odoo not responding"| C[Odoo Troubleshooting]
    B -->|"GPU node not registering"| D[GPU Node Troubleshooting]
    B -->|"WireGuard connection failed"| E[WireGuard Troubleshooting]
    B -->|"AI inference failed"| F[AI Inference Troubleshooting]
    B -->|"Database issues"| G[Database Troubleshooting]

    C --> C1["Check Docker containers"]
    C1 --> C2["Check PostgreSQL connection"]
    C2 --> C3["Check logs"]
    C3 --> C4{"Odoo running?"}
    C4 -->|Yes| C5["Check network/firewall"]
    C4 -->|No| C6["Restart Odoo"]

    D --> D1["Check API key"]
    D1 --> D2["Check WireGuard installed"]
    D2 --> D3["Check nvidia-smi"]
    D3 --> D4{"Agent logs OK?"}
    D4 -->|Yes| D5["Check Odoo registration"]
    D4 -->|No| D6["Reinstall agent"]

    E --> E1["Check wg0 interface"]
    E1 --> E2["Check allowed IPs"]
    E2 --> E3["Check endpoint"]
    E3 --> E4{"Handshake received?"}
    E4 -->|Yes| E5["Tunnel working"]
    E4 -->|No| E6["Check firewall/NAT"]

    F --> F1["Check inference backend"]
    F1 --> F2["Check model loaded"]
    F2 --> F3["Check API endpoint"]
    F3 --> F4{"Request succeeds?"}
    F4 -->|Yes| F5["Check tokens balance"]
    F4 -->|No| F6["Check GPUStack logs"]

    G --> G1["Check PostgreSQL running"]
    G1 --> G2["Check pgvector installed"]
    G2 --> G3{"Query works?"}
    G3 -->|Yes| G4["Database OK"]
    G3 -->|No| G5["Check connection string"]