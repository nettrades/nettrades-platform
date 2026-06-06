# NETTRADES.AI Licensing Guide

## What is covered by AGPL-3.0?

The NETTRADES Core, located in this `/nettrades-core` directory.  This
includes the LangGraph supervisor, the four business sub-agents, the
inference auto-detection tools, and the Odoo tool-calling wrappers.
These components are licensed under the GNU Affero General Public License,
Version 3 (AGPL-3.0).  This is a strong copyleft license that is OSI-
approved and trusted by the open-source community.

## What you can do under AGPL-3.0

- Run NETTRADES internally within your company for any purpose.
- Use it to run AI inference and fine-tuning on your own GPUs.
- Modify the code and use your modifications internally.
- Distribute your modifications (as long as they remain AGPL-3.0).

## When do you need a commercial license?

- If you want to embed NETTRADES in a proprietary product.
- If you want to offer NETTRADES as a closed-source SaaS.
- If you want to remove the AGPL-3.0 copyleft requirements.
- Enterprise support, indemnification, and managed hosting are also
  available under the commercial license.

Please contact licensing@nettrades.ai for terms and pricing.

## What about the Odoo modules?

The custom Odoo modules in /addons/nettrades_* are licensed under LGPL-3.0.
This is compatible with Odoo's own LGPL-3.0 license and with the AGPL-3.0
license that covers the NETTRADES Core.

## What about third-party components?

Every third-party component (Odoo, GPUStack, LangGraph, WireGuard, etc.)
retains its original open-source license.  See OPEN-SOURCE-NOTICES.txt.