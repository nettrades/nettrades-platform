# Architecture Overview

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## System Architecture Diagram

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        Web["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        ChatWidget["AI Chatbot Widget"]
        VSCode["VS Code Extension"]
    end

    subgraph Integration["Integration & Orchestration Layer"]
        Supervisor["LangGraph Supervisor Agent"]
        Agents["Specialised Sub-Agents"]
        MCP["MCP-Odoo Bridge"]
    end

    subgraph AI["AI Inference & Training Layer"]
        Router["Provider Router Logic"]
        GPUStack["GPUStack Server(s)"]
        Workers["GPUStack Workers (vLLM, llama.cpp)"]
        FineTune["Fine-Tuning Jobs (Axolotl/Unsloth)"]
        External["External LLM APIs"]
    end

    subgraph Core["Core Odoo 19 CE Layer"]
        Odoo["Odoo 19 CE Instance"]
        Modules["Custom NETTRADES Modules"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL 18 + pgvector"]
        Valkey["Valkey 8"]
        S3["MinIO / S3 (Models & Backups)"]
    end

    subgraph Security["Security & Network Layer"]
        WG["WireGuard Mesh/Hub-Spoke"]
        gVisor["gVisor Container Runtime"]
        TEE["TEE / Confidential Computing"]
    end

    Frontend --> Core
    Frontend -->|Direct API Call| Integration
    Integration --> MCP --> Core
    Integration --> Router --> AI
    AI --> GPUStack --> Workers
    AI --> FineTune
    AI --> External
    Core --> Data
    Core -. Orchestrates .-> Security
    Security -. Secures .-> AI