# NETTRADES Odoo Module Installation Order

## 1. Overview

This document defines the **correct order** for installing all NETTRADES Odoo modules. Modules must be installed in this sequence to satisfy dependencies and avoid "missing dependency" errors.

The installation order is divided into **five batches**, each with a specific purpose and dependency relationship.

---

## 2. Installation Order (Five Batches)

### Batch 1: Foundation Modules

These modules are **required by everything else**. Install them first.

| Module | Purpose | Dependencies |
|--------|---------|--------------|
| `queue_job` | Asynchronous job queue | None |
| `queue_job_batch` | Batch job processing | `queue_job` |
| `queue_job_cron` | Cron-based job scheduling | `queue_job` |
| `llm` | LLM integration base | None |
| `llm_tool` | Tool framework for LLMs | `llm` |
| `llm_store` | Vector store abstraction | `llm` |
| `llm_pgvector` | pgvector backend | `llm`, `llm_store` |
| `llm_knowledge` | RAG pipeline | `llm`, `llm_store` |
| `llm_assistant` | AI assistants | `llm`, `llm_tool`, `llm_store` |
| `llm_thread` | Chat interface | `llm`, `llm_assistant` |
| `llm_generate` | Content generation | `llm` |
| `llm_training` | Dataset and training job management | `llm`, `llm_store`, `llm_knowledge`, `llm_assistant` |

**Installation Command:**

```bash
# Windows PowerShell
python .\third-party\odoo\odoo-bin -c .\deploy\docker\config\odoo.conf --addons-path=.\third-party\odoo\addons,.\odoo-modules,.\third-party\odoo_llm,.\third-party\odoo_llm_compat,.\third-party\website_sale_marketplace,.\third-party\queue-19 -i queue_job,queue_job_batch,queue_job_cron,llm,llm_tool,llm_store,llm_pgvector,llm_knowledge,llm_assistant,llm_thread,llm_generate,llm_training --stop-after-init
```

```
# Linux / WSL

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=third-party/odoo/addons,odoo-modules,third-party/odoo_llm,third-party/odoo_llm_compat,third-party/website_sale_marketplace,third-party/queue-19 -i queue_job,queue_job_batch,queue_job_cron,llm,llm_tool,llm_store,llm_pgvector,llm_knowledge,llm_assistant,llm_thread,llm_generate,llm_training --stop-after-init

```

### Batch 2: NETTRADES Core

This is the central business logic module that all other NETTRADES modules depend on.

| Module | Purpose | Dependencies |
|--------|---------|--------------|
| `nettrades_core` | Core platform functionality | queue_job, llm (indirect) |

#### Dependencies:

    Users and companies management

    Karma and reputation system

    Qualification rules

    Worker agent configuration

#### Installation Command:

```bash

# Windows PowerShell
python .\third-party\odoo\odoo-bin -c .\deploy\docker\config\odoo.conf --addons-path=... -i nettrades_core --stop-after-init

# Linux / WSL
python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=... -i nettrades_core --stop-after-init

```

### Batch 3: Core NETTRADES Modules

These modules depend on nettrades_core and provide the core business functionality.

| Module | Purpose | Dependencies |
|--------|---------|--------------|
| `nettrades_gpu_admin` | GPU cluster administration | `nettrades_core` |
| `nettrades_gpustack_adapter` | GPUStack integration | `nettrades_core`, `nettrades_gpu_admin` |
| `nettrades_good_answer` | "Good Answer" voting system | `nettrades_core` |
| `nettrades_ask_someone` | Expert help marketplace | `nettrades_core` |
| `nettrades_queue` | Queue management | `nettrades_core` |
| `nettrades_notifications` | Notification system | `nettrades_core` |
| `nettrades_job_matching` | AI-powered job matching | `nettrades_core, nettrades_good_answer` |
| `nettrades_lead_scoring` | Lead scoring | `nettrades_core` |
| `nettrades_chatbot` | AI chatbot | `nettrades_core, llm_assistant` |

#### Installation Command:

bash
```
# Windows PowerShell
python .\third-party\odoo\odoo-bin -c .\deploy\docker\config\odoo.conf --addons-path=... -i nettrades_gpu_admin,nettrades_gpustack_adapter,nettrades_good_answer,nettrades_ask_someone,nettrades_queue,nettrades_notifications,nettrades_job_matching,nettrades_lead_scoring,nettrades_chatbot --stop-after-init

# Linux / WSL
python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=... -i nettrades_gpu_admin,nettrades_gpustack_adapter,nettrades_good_answer,nettrades_ask_someone,nettrades_queue,nettrades_notifications,nettrades_job_matching,nettrades_lead_scoring,nettrades_chatbot --stop-after-init
```

### Batch 4: Self-Improving System Modules

These modules form the closed-loop self-improving system and must be installed in this specific order.
| Module | Purpose | Dependencies |
|--------|---------|--------------|
| `nettrades_bridge` | Hub-and-spoke routing engine | `nettrades_core, nettrades_gpu_admin` |
| `nettrades_data_collection` | Monitor phase data collection | `nettrades_core, nettrades_good_answer, nettrades_ask_someone` |
| `nettrades_trigger` | Analyze phase trigger detection | `nettrades_data_collection` |
| `nettrades_loop` | Plan + Execute phase orchestration | `nettrades_data_collection, nettrades_trigger, llm_training, gpu_gpustack_adapter` |
| `nettrades_self_improving_config` | Administration interface | `nettrades_loop, nettrades_trigger, nettrades_data_collection` |

Installation Order (Critical!):

* nettrades_bridge must be installed first

* nettrades_data_collection must be installed before nettrades_trigger

* nettrades_trigger must be installed before nettrades_loop

* nettrades_loop must be installed before nettrades_self_improving_config

#### Installation Command:

```bash

# Windows PowerShell
python .\third-party\odoo\odoo-bin -c .\deploy\docker\config\odoo.conf --addons-path=... -i nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config --stop-after-init

# Linux / WSL
python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=... -i nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config --stop-after-init
```

### Batch 5: Additional Modules

These modules are optional and do not block other installations.

| Module | Purpose | Dependencies |
|--------|---------|--------------|
| `nettrades_fairness` | AI fairness monitoring | `nettrades_core` |
| `nettrades_onboarding` | Smart onboarding | `nettrades_core` |
| `nettrades_proposals` | Freelancer proposals | `nettrades_core, nettrades_job_matching` |
| `nettrades_research` | Research marketplace | `nettrades_core` |
| `nettrades_pwa` | Mobile PWA | `nettrades_core` |

#### Installation Command:

```bash

# Windows PowerShell
python .\third-party\odoo\odoo-bin -c .\deploy\docker\config\odoo.conf --addons-path=... -i nettrades_fairness,nettrades_onboarding,nettrades_proposals,nettrades_research,nettrades_pwa --stop-after-init

# Linux / WSL
python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=... -i nettrades_fairness,nettrades_onboarding,nettrades_proposals,nettrades_research,nettrades_pwa --stop-after-init

```

## 3. Python Dependencies

Before installing any Odoo modules, ensure these Python packages are installed:

### Required Packages

| Package | Version | Purpose |
|--------|---------|--------------|
| `torch` | Latest	PyTorch for LLM training |
| `transformers` | Latest	Hugging Face models |
| `datasets` | Latest	Hugging Face datasets |
| `accelerate` | Latest	Distributed training |
| `starlette` | >=1.0.1	Security fix (CVE-2026-48710) |
| `pgvector` | Latest	PostgreSQL vector extension |
| `numpy` | Latest	Numerical operations |
| `openai` | Latest	OpenAI API client |
| `anthropic` | Latest	Anthropic API client |

### Installation Commands

#### Windows PowerShell:

```powershell

# Install core packages
pip install torch transformers datasets accelerate

# Install odoo_llm requirements
pip install -r third-party/odoo_llm/requirements.txt

# Upgrade Starlette (security fix)
pip install --upgrade "starlette>=1.0.1"

```


#### Linux / WSL:

```bash

# Install core packages
pip install torch transformers datasets accelerate

# Install odoo_llm requirements
pip install -r third-party/odoo_llm/requirements.txt

# Upgrade Starlette (security fix)
pip install --upgrade "starlette>=1.0.1"
```

## 4. Automated Installation Script

### Windows PowerShell: install-odoo-modules.ps1

The script at C:\nettrades-platform\install-odoo-modules.ps1 automates the entire installation process:

```powershell

# Install all modules in the correct order
.\install-odoo-modules.ps1

# Force reinstall all modules
.\install-odoo-modules.ps1 -ForceReinstall

# Continue even if errors occur
.\install-odoo-modules.ps1 -StopOnError:$false

```

### Linux / WSL: scripts/phase-dev-env.sh

The script at scripts/phase-dev-env.sh sets up the complete development environment:

```bash

# Install all dependencies and modules
./scripts/phase-dev-env.sh
```

## 5. Odoo 19 Compatibility Notes


The odoo_llm modules have been updated for Odoo 19 compatibility:

| Original Code  |  Odoo 19 Fix | File |
|--------|---------|--------------|
| `models.Q(('field', '=', models.Q()))` | 	`@api.constrains('field')` |  `llm_store_collection.py, llm_resource.py, llm_assistant.py` | 
| `ondelete='restrict' `on ir.model` | 	`ondelete='cascade'` | `llm_resource.py` | 
| `auto_join=True` | 	Removed	 | `llm_assistant.py` | 
| `_sql_constraints` | 	`models.Constraint`	 | Multiple files | 
| `dimension in super().__init__()` | 	Stored in `_slots`	 | `fields.py` | 
| `@route(type='json')` | `@route(type='jsonrpc')` | 	Controller files | 

## 6. Troubleshooting

### "Odoo is currently processing another module operation"

Wait for the current operation to finish, or clear the lock:

```sql

UPDATE ir_module_module SET state='uninstalled' WHERE state='to install';
```

### "Module not found"

Ensure the module is in the addons path and the path is correct in odoo.conf.

### "Dependency missing"

Install the dependency module first. Follow the batch order above.

### "models.Q not found"

The models.Q syntax does not exist in Odoo 19. Ensure the module has been updated with @api.constrains.

### "ondelete='restrict' not supported on ir.model"

Change ondelete='restrict' to ondelete='cascade' for fields pointing to ir.model.

## 7. Summary Table

| Batch  |  Modules | Dependencies | Order |
|--------|---------|--------------|-------|
| 1 | queue_job, llm_* | None | First |
| 2 | nettrades_core | Batch 1 | Second |
| 3 | Core NETTRADES modules | Batch 2 | Third |
| 4 | Self-improving modules | Batch 3 | Fourth |
| 5 | Additional modules | Batch 2 | Last |

