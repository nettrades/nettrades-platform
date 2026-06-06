README-QUICKSTART.md — One-Page Deployment Cheat Sheet

A single page that tells a new developer or operator exactly what to do, in order.
markdown

# NETTRADES.AI — Quickstart Guide

## Prerequisites
- Docker and Docker Compose installed
- `git` installed
- A domain name pointing to your server's IP (for Let's Encrypt TLS)
- Ports 80 and 443 open on the firewall

## One-Command Deploy

```bash
# 1. Clone the project
git clone <your-repo-url> nettrades-app
cd nettrades-app/marketplace-platform

# 2. Generate secrets
bash .env.generator.sh > .env
chmod 600 .env

# 3. Deploy
sudo bash install-nettrades.sh

After deployment (approximately 5-10 minutes):

    Odoo: https://nettrades.ai

    Grafana: https://grafana.nettrades.ai (admin / password from .env)

    GPUStack: https://gpustack.nettrades.ai

    Forgejo: https://git.nettrades.ai

Installing Odoo Modules

    Log into Odoo at https://nettrades.ai

    Create the nettrades database

    Go to Apps → Update Apps List

    Install modules in this order:

        Standard modules: CRM, Project, Recruitment, Website, eCommerce, Sales, Accounting, Discuss, Gamification, Forum, OAuth, Instant Messaging

        Community modules: Marketplace, LLM core, LLM pgvector, LLM knowledge, LLM assistant, LLM ollama, LLM openai, LLM tool, LLM training, LLM thread, LLM MCP server

        OCA modules: Job Queue, Payment Stripe

        NETTRADES modules: nettrades_core, nettrades_ask_someone, nettrades_good_answer, nettrades_gpu_admin, nettrades_gpustack_adapter, nettrades_queue

        NETTRADES UX modules: nettrades_onboarding, nettrades_job_matching, nettrades_proposals, nettrades_lead_scoring, nettrades_research, nettrades_chatbot, nettrades_notifications, nettrades_pwa

Post-Installation

    Configure an LLM provider: Settings → Technical → AI → LLM Providers → Create "NETTRADES GPUStack"

    Set up Stripe (if using Ask Someone): Settings → Payment Providers → Stripe

    Create professional fields: NETTRADES Core → Professional Fields

Troubleshooting
Problem	Solution
Odoo returns 502	PostgreSQL is still starting; wait 30 seconds
SSL certificate not issued	Ensure DNS resolves to the server IP
GPUStack UI not loading	Check docker logs gpustack
Support

    Documentation: https://nettrades.org/docs

    Community: https://nettrades.org/community

    Issues: https://git.nettrades.ai/nettrades/nettrades-app/issues

text


Place this file at `nettrades-app/README-QUICKSTART.md`.

---

## Summary

| File | Purpose | Copy-ready? |
|------|---------|-------------|
| `marketplace-platform/config/odoo.conf` | Odoo configuration with all settings | ✅ Yes |
| `marketplace-platform/.env.generator.sh` | One-command secret generation | ✅ Yes |
| `nettrades-app/README-QUICKSTART.md` | One-page deployment cheat sheet | ✅ Yes |

These three files eliminate the remaining manual configuration steps and make the platform deployable by a new operator in under 10 minutes.