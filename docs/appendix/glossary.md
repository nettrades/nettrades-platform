# Glossary

This page defines key terms and acronyms used throughout the NETTRADES.AI platform documentation.

---

## A

### AGPL-3.0
**Affero General Public License version 3** – A strong copyleft open-source license. It requires that anyone who modifies the software and offers it as a network service (e.g., a cloud API) must release their modifications under the same license. This closes the "SaaS loophole" found in the standard GPL. In NETTRADES, the core `src/` code (orchestrator, agents, training scripts) is licensed under AGPL-3.0.

### Axolotl
A multi-GPU fine-tuning framework that supports FSDP2, DeepSpeed, and sequence parallelism for fast, scalable training of large language models. It is used in NETTRADES for multi-GPU fine-tuning on company-internal trusted networks.

---

## B

### Bias Score
A score from 0-10 assigned by the LLM-as-Judge indicating the degree of bias in a response. Higher scores indicate more bias. Responses with a bias score above the configurable threshold (default 3.0) are flagged for human review and filtered from training data.

### Bias Detection
The process of automatically evaluating AI responses for bias against protected attributes such as gender, race, age, disability, and religion. The fairness module uses an LLM-as-Judge to assign bias scores and flag problematic responses.

### Bridge Module (`nettrades_bridge`)
The hub-and-spoke routing module that decides whether AI requests should be processed locally or forwarded to the remote NETTRADES.ai brain. It is the core commercial engine enabling client companies to use local AI for internal operations while seamlessly accessing global services.

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

### Data Episode (`data.episode`)
A complete interaction record in the self-improving system. Each episode captures the user's input, the AI's output, and any subsequent feedback. Episodes are the primary data source for fine-tuning.

### Data Collection Module (`nettrades_data_collection`)
The Monitor phase of the self-improving MAPE loop. It collects and structures data from all platform interactions, including Good Answer votes, expert sessions, LangGraph interactions, and ROS 2 / robotics data.

### Data-Juicer
An open-source data quality pipeline from Alibaba that filters, deduplicates, and removes PII from training datasets. It is optionally integrated into the NETTRADES fine-tuning pipeline.

### DEITA
**Data-Efficient Instruction Tuning** – An LLM-as-Judge scoring method that evaluates training examples on complexity, quality, and diversity. It is used in the NETTRADES fine-tuning pipeline (via distilabel) to select high-value training data.

### Demographic Parity
A fairness metric that requires the proportion of positive outcomes to be roughly equal across groups. In recruitment, this means that the selection rate for candidates from different demographic groups should be similar. The four-fifths rule (disparate impact >= 0.8) is commonly used to assess demographic parity.

### Disparate Impact
A fairness metric that measures whether a selection practice has a disproportionately adverse impact on a protected group. The four-fifths rule states that a selection rate for any group that is less than four-fifths (80%) of the rate for the group with the highest selection rate is considered evidence of disparate impact.

### Docker Compose
A tool for defining and running multi-container Docker applications. NETTRADES uses it for single-VM deployments.

---

## E

### eBPF
**Extended Berkeley Packet Filter** – A technology that allows running sandboxed programs in the Linux kernel. Cilium uses eBPF for high-performance networking and security policies.

### Equal Opportunity
A fairness metric that requires the true positive rates to be similar across groups. In recruitment, this means that qualified candidates from all demographic groups should be equally likely to be selected.

---

## F

### Fairness & Bias Detection
The system that automatically evaluates AI responses for rationality and bias. It uses an LLM-as-Judge to score responses on two dimensions: rationality (logical coherence) and bias (degree of bias against protected attributes). Responses that fail thresholds are flagged for human review and filtered from training data.

### Fairness Module (`nettrades_fairness`)
The Odoo module that implements fairness, rationality, and bias detection. It provides configuration, evaluation, audit logging, and human review workflows.

### Fairness Flag (`nettrades.fairness.flag`)
A model that stores responses flagged for human review. Flags are created when a response exceeds the rationality or bias thresholds. Administrators can review flags, accept or reject them, and add notes.

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

### Loop Module (`nettrades_loop`)
The orchestrator of the self-improving system. It connects the Monitor, Analyze, Plan, and Execute phases of the MAPE loop, executing complete self-improvement cycles when triggers fire.

---

## M

### MAPE Loop
**Monitor, Analyze, Plan, Execute** – The foundational control loop pattern for self-adaptive systems. NETTRADES uses this pattern for its self-improving AI system.

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

### Rationality Score
A score from 0-10 assigned by the LLM-as-Judge indicating the logical coherence and reasoning quality of a response. Higher scores indicate better reasoning. Responses with a rationality score below the configurable threshold (default 7.0) are flagged for human review and filtered from training data.

### Rationality Evaluation
The process of automatically evaluating AI responses for logical coherence, reasoning quality, and freedom from logical fallacies. The fairness module uses an LLM-as-Judge to assign rationality scores and flag problematic responses.

### ROS 2
**Robot Operating System version 2** – A set of libraries and tools for building robot applications. NETTRADES integrates with ROS 2 for the Action Agent to plan and dispatch robotic actions.

---

## S

### Self-Improving System
A closed-loop learning architecture that continuously improves the platform's AI models. It collects data from interactions, detects triggers, runs fine-tuning jobs on GPUStack, and deploys improved models back to LangGraph agents.

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

### Trigger Module (`nettrades_trigger`)
The Analyze phase of the self-improving MAPE loop. It detects conditions that should trigger a self-improvement cycle, such as quality drops, success rate declines, or accumulated data volume.

### Trigger Configuration (`trigger.config`)
A configurable condition that, when met, initiates a self-improvement cycle. Trigger types include quality drop, success rate decline, data volume threshold, edge case detection, and manual trigger.

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