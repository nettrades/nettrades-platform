# Changelog

This page tracks notable changes to the NETTRADES.AI platform. All releases are versioned and documented.

---

## Version 0.2.0 (Upcoming)

### Added

- **Vision Agent** – Multi-modal VLM integration for image analysis.
- **Action Agent** – Robotics control via ROS 2 and VLA models.
- **Data-Juicer pipeline** – Automated quality filtering for fine-tuning datasets.
- **DEITA scoring** – LLM-as-Judge scoring for dataset quality.
- **Federated Learning module** – Cross-organisation model training (experimental).
- **`nettrades.experience` model** – Work experience storage for user profiles
- **`nettrades.review` model** – User ratings and reviews for completed projects
- **`project` dependency** added to `nettrades_core` module
- **Views for reviews** – Tree and form views for managing reviews in the admin panel

### Fixed

- **Medical screening loop** – Now correctly loops back for follow-up questions.
- **Authentication bypass** – `LANGGRAPH_API_KEY` now required (no silent bypass).
- **Indentation bug** in `gpu_cluster.py` – fixed.
- **Missing fields** on `nettrades.field` – all 30+ fields added.
- **Model registry error** – Fixed missing `nettrades.experience` and `nettrades.review` models causing `Internal Server Error`
- **`res.partner` One2many fields** – Properly linked to the new experience and review models
- **Module loading** – `nettrades_gpu_admin` module now loads without `ImportError`

### Changed

- **Moved sub-agents** from `src/agent/` to `src/core/agents/` (improved clarity).
- **Replaced N8N** with direct LangGraph calls.
- **Replaced Redis** with Valkey.
- **Replaced Kalavai** with NVIDIA dynamo.
- **`nettrades_core` module** – Updated dependencies to include `project`
- **Documentation** – Added core models reference page

---

## Version 0.1.0 (Initial Alpha)

### Added

- **LangGraph Supervisor** – Intent classification and routing.
- **Sub-Agents** – Recruitment, Freelance, Lead Gen, GPU Management.
- **Distributed GPU Agent** – WireGuard, NVIDIA dynamo integration, registration.
- **Odoo 19 CE** – Core ERP and marketplace.
- **"Ask Someone"** – Expert help marketplace with Stripe escrow.
- **"Good Answer"** – Voting and reputation system.
- **GPU Admin Panel** – Dashboard for managing GPU nodes.
- **Single-VM Deployment** – Docker Compose based.
- **Kubernetes on Talos** – Enterprise-grade deployment.
- **Documentation** – Comprehensive MkDocs site.

---

## Future Releases

### Version 1.0.0 (Planned)

- **Stable API** – Full documentation and versioning.
- **Performance tuning** – Optimised for large-scale deployments.
- **Multi-region support** – Active-active deployments across regions.

### Backlog

- **Mobile native app** – Android and iOS.
- **Microservices migration** – Split monolith into services.
- **More AI agents** – Custom agents for specific industries.

---

## How to Contribute

We welcome contributions! See our [Contributing Guide](contributing.md) for details.

---

## Next Steps

- [Contributing Guide →](contributing.md)
- [Roadmap →](roadmap.md)
- [License →](../../license.txt)
