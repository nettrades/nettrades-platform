# Project Governance & Architecture Policy

**Version:** 3.0  
**Last Updated:** November 2026

This document describes how the NETTRADES project is governed, how engineering decisions are verified, and how contributors participate in the project's technical direction.

---

## Strategic Overview
NETTRADES is an enterprise-grade sovereign AI infrastructure platform built for data autonomy. The project is owned, maintained, and commercially licensed by **NETTRADES LIMITED** (UK Company No. 08160657), a company incorporated in England and Wales.

---

## Core Principles
- **Ethical Primacy:** Every license, deployment, and commercial agreement is strictly overridden by our [ETHICAL-STATEMENT.md](ETHICAL-STATEMENT.md).
- **Source-Available & Responsible AI:** Core components are distributed under **BUSL-1.1** (with generous free grants for individuals, SMEs up to 5 Spokes, schools, universities, and hospitals), converting after 4 years to **Open RAIL-S**.
- **Sovereign Privacy:** Organizations retain full control over their model weights, local inference nodes, and internal databases.
- **Defensive Patent Integrity:** NETTRADES LIMITED maintains pending patent protections (`LEGAL/PATENTS.md`) to safeguard the architecture and enforce ethical compliance.

---

## Project Roles

### 1. Maintainers (NETTRADES LIMITED)
NETTRADES LIMITED oversees product architecture, security audits, patent management, ethical enforcement, and commercial licensing. Maintainers review and merge pull requests and enforce mandatory Contributor License Agreement (`CLA`) verification.

### 2. Contributors
Independent developers and organizations who improve the codebase, test hardware compatibility, or submit documentation fixes. All contributors must sign `LEGAL/Contributor-License-Agreement.md` prior to merging.

---

## Technical Licensing Architecture

| Repository Component | Public License Tier | Commercial Tier |
| :--- | :--- | :--- |
| NETTRADES Platform (`src/`, `odoo-modules/`, `installer/`) | **BUSL-1.1** (Free up to 1 Sub-Hub & 5 Spokes; unlimited for schools/universities/hospitals) → **Open RAIL-S** after 4 years | Paid Commercial EULA (`COMMERCIAL-LICENSE.md`) |
| Third-Party Dependencies | Original Upstream Licenses (`OPEN-SOURCE-NOTICES.txt`) | Original Upstream Licenses |

---

## Questions and Governance
- **GitHub Discussions: https://github.com/nettrades/nettrades-platform/discussions**
- **Legal & Governance Inquiries:** legal@nettrades.ai
- **Ethical Reports:** ethical@nettrades.ai
