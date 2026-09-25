# NETTRADES Platform — Component Map

**Purpose:** Flat navigation aid. File → purpose. Model → module. Route →
handler. Find things fast without reading directory trees.

**Companion:** `ARCHITECTURE-CURRENT.md` for the structure, this document
for the map.

---

## 1. Odoo Modules (13 installed)

| Module | Root | Primary models |
|---|---|---|
| `nettrades_core` | `odoo-modules/nettrades_core/` | `nettrades.field`, `nettrades.secrets`, `nettrades.vote` |
| `nettrades_queue` | `odoo-modules/nettrades_queue/` | (adapter over `queue_job`) |
| `nettrades_notifications` | `odoo-modules/nettrades_notifications/` | `user.notification` |
| `nettrades_llm_config` | `odoo-modules/nettrades_llm_config/` | `nettrades.llm.company.config` |
| `nettrades_ask_someone` | `odoo-modules/nettrades_ask_someone/` | `expert.session`, `expert.agreement`, `escrow.hold`, `ask.someone.config` |
| `nettrades_good_answer` | `odoo-modules/nettrades_good_answer/` | `good.answer.vote`, `user.field.reputation`, `qualified.professional`, `ft.dataset`*, `ft.training.job`*, `llm.feedback`* |
| `nettrades_fairness` | `odoo-modules/nettrades_fairness/` | `nettrades.fairness.config`, `nettrades.fairness.field.config`, `nettrades.fairness.audit`, `nettrades.fairness.flag`, `nettrades.fairness.evaluator`, `nettrades.fairness.metrics` |
| `nettrades_data_collection` | `odoo-modules/nettrades_data_collection/` | `data.episode`, `data.annotation`, `data.feedback`, `data.metric`, `data.edge_case`, `data.collector`, `simulation.dataset` |
| `nettrades_self_improving` | `odoo-modules/nettrades_self_improving/` | `trigger.config`, `trigger.event`, `training.pipeline`, `loop.cycle`, `loop.orchestrator`, `self.improving.config` |
| `nettrades_gpu_admin` | `odoo-modules/nettrades_gpu_admin/` | `gpu.cluster`, `gpu.node`, `gpu.cluster.subnet`, `gpu.credit`, `gpu.pricing`, `gpu.registration.token`, `gpu.sharing.schedule`, `gpu.token.economics`, `multimodal.config` |
| `nettrades_bridge` | `odoo-modules/nettrades_bridge/` | `nettrades.bridge.config`, `nettrades.bridge.company.config`, `nettrades.bridge.routing` |
| `nettrades_wireguard` | `odoo-modules/nettrades_wireguard/` | `wireguard.peer` |
| `nettrades_onboarding` | `odoo-modules/nettrades_onboarding/` | (onboarding flows) |

\* `ft.*` and `llm.feedback` are the older training pipeline. They coexist
with `llm.training.dataset` / `llm.training.job` (from the third-party
`llm_training` module). See `KNOWN-ISSUES.md` for the reconciliation plan.

---

## 2. `nettrades_gpu_admin` — Detailed Map

| File | Contains |
|---|---|
| `models/gpu_cluster.py` | `gpu.cluster` — trust mode, WireGuard keys, subnet, layer config (planned), recompute_layers (planned), drain_and_restart_for_node (planned) |
| `models/gpu_node.py` | `gpu.node` — hardware inventory, WireGuard pubkey, pool, runtime, reputation, inference_capability (planned) |
| `models/gpu_cluster_subnet.py` | `gpu.cluster.subnet` — CIDR subnets for network scans |
| `models/gpu_credit.py` | `gpu.credit` — internal credits per user |
| `models/gpu_pricing.py` | `gpu.pricing` — base price, demand/supply factors, history |
| `models/gpu_registration_token.py` | `gpu.registration.token` — token hash, lifecycle, validation |
| `models/gpu_sharing_schedule.py` | `gpu.sharing.schedule` — time-based public sharing |
| `models/gpu_token_economics.py` | `gpu.token.economics` — earn rate, payout schedule |
| `models/multimodal_config.py` | `multimodal.config` — enable_multimodal, enable_robotics, enable_iot, enable_edge_deployment |
| `models/res_partner.py` | Extension of `res.partner` adding `gpu_nodes` One2many. Commented out in `__init__.py`. |
| `controllers/main.py` | HTTP controller: `/api/v1/gpu/register`, `/api/v1/gpu/peers`, `/api/v1/admin/scan_network`, `/api/v1/admin/install_node`, `/api/v1/admin/remove_node`, `/api/v1/admin/finetune/*` |
| `data/cron.xml` | Two crons: `cron_gpu_health_watchdog`, `cron_gpu_utilisation_alert` |
| `security/groups.xml` | `group_gpu_administrator`, `group_gpu_operator` |
| `security/ir.model.access.csv` | CRUD permissions per model per group |
| `security/gpu_admin_security.xml` | 8 record rules for company isolation |
| `security/gpu_registration_token_security.xml` | 1 record rule for token company isolation |
| `views/gpu_cluster_views.xml` | Cluster form (active), plus `menu_gpu_root` and cluster actions |
| `views/gpu_node_views.xml` | Node form. **Has duplicate notebook pages — do not enable until fixed.** |
| `views/gpu_registration_token_views.xml` | Token form. **References non-existent `cluster_id` — do not enable until fixed.** |
| `views/gpu_schedule_views.xml` | Schedule form. **References wrong field names — do not enable until fixed.** |
| `views/gpu_token_economics_views.xml` | Token economics form. **References completely wrong fields — do not enable until fixed.** |
| `views/multimodal_config_views.xml` | Multimodal config form. **Wrong field names + Odoo 16 `attrs=` — do not enable until fixed.** |
| `views/menu_items.xml` | Menu definitions. **Uses `<act_window>` (removed in Odoo 17) and duplicates `menu_gpu_root`.** |
| `views/gpu_dashboard_templates.xml` | QWeb templates for Owl components. Templates are fine; the JS that consumes them is not. |
| `static/src/js/dashboard.js` | Owl component. Calls missing methods on `gpu.cluster`. |
| `static/src/js/wireguard_manager.js` | Owl component. Calls wrong method names. |
| `static/src/js/node_manager.js` | Owl component. Reads `pool` instead of `gpu_pool`; uses `env.user.companyId` incorrectly. |

---

## 3. `src/core/` — Map

| File | Purpose |
|---|---|
| `app.py` | FastAPI application. Lifespan starts the health monitor. `/nodes`, `/nodes/{id}/health` endpoints. |
| `supervisor.py` | LangGraph supervisor graph. `classify`, `medical_screening`, `bridge_route`, `route`, `post_process`. |
| `hardware_detection.py` | Cross-platform GPU/CPU/RAM detection. |
| `node_health.py` | `NodeHealthMonitor` — asyncio, Prometheus metrics, hysteresis. |
| `bridge_integration.py` | `BridgeService` — hub-and-spoke routing. |
| `self_improving_integration.py` | `SelfImprovingService` — writes episodes to `data.episode` via proxy. |
| `inference_tools.py` | `get_inference_route()` — calls the bridge to select a route. |
| `discovery/gpu_scanner.py` | Subnet scan for GPU discovery. **Written as Odoo `AbstractModel` — needs restructuring.** |
| `agents/recruitment_agent.py` | Recruitment sub-agent. |
| `agents/freelance_agent.py` | Freelance sub-agent. |
| `agents/lead_gen_agent.py` | Lead-generation sub-agent. |
| `agents/gpu_management_agent.py` | GPU management sub-agent. |
| `agents/gpu_marketplace_agent.py` | GPU marketplace sub-agent. |
| `agents/ask_someone_agent.py` | Expert marketplace sub-agent. |
| `agents/good_answer_agent.py` | Quality scoring sub-agent. |
| `agents/vision_agent.py` | Multimodal + robotics sub-agent. |
| `agents/action_agent.py` | Robotic action sub-agent. |
| `middleware/metrics.py` | Prometheus metrics middleware. |
| `middleware/auth.py` | JWT auth middleware (unused in current deployment). |
| `security/prompt_injection.py` | Prompt-injection sanitization. |
| `routes/__init__.py` | Router registry. |
| `routes/health.py` | `/health`. |
| `routes/metrics.py` | `/metrics`. |
| `routes/invoke.py` | `/invoke` — main inference endpoint. |
| `routes/threads.py` | `/threads`, `/threads/{id}/state`, `/threads/{id}/runs`, `/runs`. |
| `routes/assistants.py` | `/assistants`. |
| `routes/wireguard.py` | `/api/wireguard/*`. |
| `routes/_shared.py` | `get_graph()`, `record_metrics()`. |
| `tools/__init__.py` | Exports `get_inference_backend`. |
| `tools/inference.py` | Detects Dynamo health in a background thread; returns GPU or CPU. |
| `tools/llm_factory.py` | `LLMFactory.get_llm(company_id, intent)` — reads from `nettrades.llm.company.config`. |
| `tools/odoo_tools.py` | Async JSON-RPC helpers for Odoo models. |
| `tools/wireguard_manager.py` | `WireGuardManager` — peer create/list/revoke, QR code generation. |
| `tools/ros2_tools.py` | ROS2 telemetry. **Uses `self.env` outside a model — needs restructuring.** |
| `tools/inference_tools.py` | Route selection helper. |
| `odoo_proxy/main.py` | FastAPI proxy. **Whitelist not enforced in `/jsonrpc`.** |
| `odoo_proxy/auth.py` | `/auth/login`, `/auth/logout`, `/auth/status`. **Sessions not stored.** |
| `odoo_proxy/mode.py` | Red/Yellow/Green modes. |
| `odoo_proxy/requirements.txt` | Dependencies. Missing several (see `KNOWN-ISSUES.md`). |

---

## 4. `src/connectors/` — Map

| File | Purpose |
|---|---|
| `__init__.py` | Exports `AbstractConnector`, `ConnectorRegistry`, and the concrete connectors |
| `base.py` | `AbstractConnector` — the interface all connectors implement |
| `registry.py` | `ConnectorRegistry` — resolves connector classes by name |
| `exceptions.py` | `ConnectorError`, `ConnectorNotFoundError`, `ConnectorAuthenticationError`, `ConnectorConnectionError` |
| `odoo.py` | `OdooConnector` — JSON-RPC to Odoo via the proxy |
| `salesforce.py` | `SalesforceConnector` — OAuth 2.0, SOQL. **Incomplete.** |
| `sap.py` | `SAPConnector` — stub. |

---

## 5. Docker Compose Services

| Service | Container | Published port | Purpose |
|---|---|---|---|
| `traefik` | `docker-traefik-1` | 80, 443 | Reverse proxy |
| `postgres` | `docker-postgres-1` | internal 5432 | PostgreSQL 17 + pgvector |
| `postgres-exporter` | `docker-postgres-exporter-1` | internal 9187 | Prometheus metrics for Postgres |
| `valkey` | `valkey` | internal 6379 | In-memory store |
| `odoo` | `odoo` | 8069 | Odoo CE 19 |
| `langgraph-server` | `langgraph-server` | 8000 | LangGraph supervisor |
| `nettrades-ui` | `nettrades-ui` | 3002 | AI Chat UI |
| `redirector` | `redirector` | internal 80 | Default landing page |
| `odoo-proxy` | `odoo-proxy` | 8090 | Enterprise Gateway |
| `dynamo` | `dynamo` | 8001 | NVIDIA Dynamo frontend |
| `llama-cpp` | `llama-cpp` | 8080 | Single-node llama.cpp |
| `self-improving` | `self-improving` | (profile) | Unsloth training |
| `prometheus` | `prometheus` | 9090 | Metrics |
| `grafana` | `grafana` | 3001 | Dashboards |
| `node_exporter` | `node_exporter` | internal 9100 | System metrics |
| `wireguard-internal` | `wireguard-internal` | 51820/udp | Internal VPN |

**Not yet in docker-compose:** `llama-rpc-master`, `llama-rpc-worker-cuda`.
Planned under `--profile rpc`.

---

## 6. Scripts

| File | Purpose |
|---|---|
| `scripts/nettrades-setup.sh` | Master orchestrator (phases 0–5) |
| `scripts/prepare-odoo-addons.sh` | Copies modules to build context; validates manifests |
| `scripts/install-modules.sh` | Installs modules one at a time in dependency order |
| `scripts/audit-views.py` | Scans views for field-reference errors |
| `scripts/smoke-test-module.sh` | Runtime smoke test for a module |
| `scripts/download-model.sh` | Downloads a model from ModelScope mirror |
| `scripts/backup.sh` | Backup |
| `scripts/restore.sh` | Restore |
| `scripts/wireguard-manager.sh` | WireGuard peer management on the host |

---

## 7. Documentation Files

| File | Status |
|---|---|
| `HANDOFF.md` | Current. Updated 2026-09-21. |
| `KNOWN-ISSUES.md` | Current. Updated 2026-09-21. |
| `DECISIONS.md` | Current. ADRs 001–010. |
| `ARCHITECTURE-AND-PLAN.md` | **Partially outdated.** Contains both current and future sections mixed. Superseded by `ARCHITECTURE-CURRENT.md` and `ARCHITECTURE-FUTURE.md`. |
| `ARCHITECTURE-CURRENT.md` | Current (this session). |
| `ARCHITECTURE-FUTURE.md` | Current (this session). Aspirational. |
| `COMPONENT-MAP.md` | Current (this session). This file. |
| `BUG-CATALOG.md` | Current (this session). |
| `ENVIRONMENT.md` | Current. |
| `VERIFICATION.md` | Current. Acceptance criteria. |
| `README-AGENT.md` | Current. Rules for AI agents. |
| `sitemap.md` | Current. List of raw doc URLs. |

---

## 8. Where to Find Things Fast

- **"How do agents talk to Odoo?"** → `src/connectors/odoo.py` calls
  `src/core/odoo_proxy/main.py` `/jsonrpc`.
- **"Where is the model whitelist?"** → `src/core/odoo_proxy/main.py`,
  `ALLOWED_MODELS` set.
- **"How do I register a GPU node?"** → `POST /api/v1/gpu/register` in
  `odoo-modules/nettrades_gpu_admin/controllers/main.py`.
- **"Where does the health monitor run?"** → `src/core/node_health.py`,
  started in `src/core/app.py` lifespan.
- **"How does the supervisor choose a backend?"** → `_select_inference_track()`
  in `src/core/supervisor.py`.
- **"Where is the self-improving loop?"** → `odoo-modules/nettrades_self_improving/`,
  primarily `models/loop_orchestrator.py`.
- **"Where does the fairness module integrate with episodes?"** →
  `nettrades_fairness/models/fairness_evaluator.py`, `_store_evaluation()`
  writes `fairness_score` to `data.episode`.
- **"Where is the training pipeline?"** → `nettrades_self_improving/models/training_pipeline.py`,
  `create_dataset()` and `submit_training_job()`.