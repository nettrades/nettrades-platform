# Glossary

This page defines key terms and acronyms used throughout the NETTRADES.AI platform documentation.

---

## A

### AGPL-3.0
**Affero General Public License version 3** – A strong copyleft open-source license. It requires that anyone who modifies the software and offers it as a network service (e.g., a cloud API) must release their modifications under the same license. This closes the "SaaS loophole" found in the standard GPL. In NETTRADES, the core `src/` code (orchestrator, agents, training scripts) is licensed under AGPL-3.0.

### Axolotl
A multi-GPU fine-tuning framework that supports FSDP2, DeepSpeed, and sequence parallelism for fast, scalable training of large language models. It is used in NETTRADES for multi-GPU fine-tuning on company-internal trusted networks.

---

## C

### Cilium
An eBPF-based CNI (Container Network Interface) for Kubernetes that provides high-performance networking, security, and observability. It is used in NETTRADES for WireGuard-encrypted pod-to-pod communication.

### CloudNativePG (CNPG)
A Kubernetes operator for PostgreSQL that automates deployment, high availability, backups, and failover. It is the recommended way to run PostgreSQL in the NETTRADES Kubernetes deployment.

### Contributor License Agreement (CLA)
A legal agreement that contributors sign, granting the project the right to re-license their contributions under commercial licenses. This is essential for NETTRADES's dual-licensing model.

---

## D

### Data-Juicer
An open-source data quality pipeline from Alibaba that filters, deduplicates, and removes PII from training datasets. It is optionally integrated into the NETTRADES fine-tuning pipeline.

### DEITA
**Data-Efficient Instruction Tuning** – An LLM-as-Judge scoring method that evaluates training examples on complexity, quality, and diversity. It is used in the NETTRADES fine-tuning pipeline (via distilabel) to select high-value training data.

### Docker Compose
A tool for defining and running multi-container Docker applications. NETTRADES uses it for single-VM deployments.

---

## E

### eBPF
**Extended Berkeley Packet Filter** – A technology that allows running sandboxed programs in the Linux kernel. Cilium uses eBPF for high-performance networking and security policies.

---

## F

### FastAPI
A modern Python web framework for building APIs. It is used in NETTRADES as the entry point for the LangGraph `/invoke` endpoint.

### Forgejo
A self-hosted Git service (fork of Gitea). NETTRADES uses it for project collaboration, CI/CD, and source code management.

### FSDP2
**Fully Sharded Data Parallel version 2** – A PyTorch distributed training technique that shards model parameters, gradients, and optimizer states across GPUs. It is used by Axolotl for multi-GPU training.

---

## G

### gVisor
A userspace kernel that provides syscall-level container isolation. It is used in NETTRADES for untrusted public GPU worker pools to prevent container escape attacks.

### GPUStack
An open-source GPU cluster manager that provides an OpenAI-compatible inference API, token metering, and support for multiple GPU vendors (NVIDIA, AMD, Apple Metal). It orchestrates GPU workers and models in NETTRADES.

### Grafana
An open-source observability platform for dashboards and visualization. It is used with Prometheus to monitor the NETTRADES platform.

---

## L

### LangChain
A framework for developing applications powered by language models. It provides tools for chaining LLM calls, memory, and retrieval. NETTRADES uses LangChain components within LangGraph.

### LangGraph
A framework for building stateful, multi-agent applications with durable execution and checkpointing. It is the core orchestration engine in NETTRADES, used for the Supervisor and sub-agents.

### LGPL-3.0
**Lesser General Public License version 3** – A weak copyleft license that allows linking with proprietary code as long as the LGPL-licensed code itself remains modifiable and accessible. NETTRADES Odoo modules are licensed under LGPL-3.0 to ensure compatibility with Odoo's licensing.

### llama.cpp
A CPU-only inference engine that runs quantised LLMs on CPU without GPU acceleration. It serves as the fallback inference backend in NETTRADES when no GPU is available.

### Longhorn
A distributed block storage system for Kubernetes. It provides persistent volumes for stateful services like PostgreSQL, Valkey, and Odoo filestore.

### LoRA
**Low-Rank Adaptation** – A parameter-efficient fine-tuning technique that adds small trainable matrices to the model's weights. It is used by Unsloth and Axolotl in the NETTRADES fine-tuning pipeline.

---

## M

### MCP-Odoo Bridge
**Model Context Protocol** – A bridge that allows AI agents to call Odoo JSON-RPC functions. It exposes Odoo models and methods as tools that LangGraph agents can invoke.

### MetalLB
A bare-metal load balancer for Kubernetes. It assigns external IPs to services, enabling external access to the NETTRADES platform on-premises.

### MkDocs
A static site generator for project documentation written in Markdown. It is used to build the NETTRADES documentation site.

---

## O

### OCA
**Odoo Community Association** – A non-profit organisation that maintains a large collection of high-quality Odoo modules. NETTRADES follows OCA coding standards for its Odoo modules.

### Odoo 19 CE
**Odoo Community Edition version 19** – The open-source ERP and business application platform that serves as the foundation of the NETTRADES business logic layer. It provides CRM, HR, Projects, Accounting, eCommerce, and more.

### OpenAI-Compatible API
A REST API that follows the same request/response format as OpenAI's API, making it easy to swap inference backends. GPUStack and vLLM both provide such endpoints, enabling seamless switching.

---

## P

### pgvector
A PostgreSQL extension that adds vector similarity search capabilities. It is used in NETTRADES for RAG (Retrieval-Augmented Generation) and semantic matching of skills and CVs.

### PostgresSaver
A LangGraph checkpoint saver that stores state snapshots in PostgreSQL. It enables durable execution and crash recovery in the NETTRADES agent workflows.

### Prometheus
An open-source monitoring and alerting toolkit. It collects metrics from NETTRADES components and feeds them to Grafana.

### PWA
**Progressive Web App** – A web application that can be installed on a device and work offline. NETTRADES includes a PWA manifest and service worker for mobile access.

---

## Q

### QLoRA
**Quantized LoRA** – LoRA combined with 4-bit quantization to reduce memory usage during fine-tuning. It is supported by Unsloth and Axolotl.

---

## R

### RAG
**Retrieval-Augmented Generation** – A technique that retrieves relevant context from a vector database (e.g., pgvector) and appends it to the prompt to improve LLM responses. It is used in the NETTRADES AI assistant.

### ROS 2
**Robot Operating System version 2** – A set of libraries and tools for building robot applications. NETTRADES integrates with ROS 2 for the Action Agent to plan and dispatch robotic actions.

---

## S

### Stripe
A payment processing platform used in NETTRADES for escrow payments in the "Ask Someone" expert marketplace.

---

## T

### Talos Linux
An immutable, API-driven Linux distribution designed specifically for Kubernetes. It is used in the NETTRADES enterprise-grade Kubernetes deployment.

### TEE
**Trusted Execution Environment** – Hardware-based confidential computing (e.g., NVIDIA Confidential Computing, Intel SGX, AMD SEV-SNP). NETTRADES detects and reports TEE capabilities in GPU nodes for enhanced security.

### Traefik
A modern reverse proxy and load balancer with built-in Let's Encrypt support. It serves as the ingress controller for the NETTRADES platform, routing traffic to Odoo, Grafana, GPUStack, Forgejo, and other services.

---

## U

### Unsloth
A single-GPU fine-tuning library that is 2× faster and uses 70% less VRAM than standard fine-tuning. It is the default fine-tuning backend for NETTRADES, especially for freelancers and small companies.

---

## V

### Valkey
A Redis-compatible in-memory data store (BSD-3-Clause licensed) used in NETTRADES for session storage, ORM caching, and real-time bus notifications. It replaced Redis due to licensing changes.

### vLLM
A high-throughput inference engine with PagedAttention. It is used in NETTRADES as the primary GPU inference backend when a GPU is available.

---

## W

### WireGuard
A fast, modern, kernel-level VPN with minimal attack surface. It is used in NETTRADES for network isolation between GPU nodes, with AllowedIPs enforcement to prevent unauthorised communication.

---

## Next Steps

- [Environment Variables →](environment-variables.md)
- [Database Schema →](database-schema.md)
- [Back to Appendix →](index.md)
