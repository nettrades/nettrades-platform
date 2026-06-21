==========================================
Letta Integration for Odoo LLM
==========================================

Stateful AI agents with persistent memory.

**Module Type:** 🔌 Extension (Stateful AI Agents)

Architecture
============

::

    ┌───────────────────────────────────────────────────────────────┐
    │                      Application Layer                        │
    │        ┌───────────────┐           ┌───────────────┐         │
    │        │ llm_assistant │           │  llm_thread   │         │
    │        └───────┬───────┘           └───────┬───────┘         │
    └────────────────┼───────────────────────────┼─────────────────┘
                     └─────────────┬─────────────┘
                                   ▼
                  ┌───────────────────────────────────────────┐
                  │       ★ llm_letta (This Module) ★         │
                  │           Letta AI Integration            │
                  │  🧠 Memory │ MCP Tools │ Stateful Agents  │
                  └─────────────────────┬─────────────────────┘
                            ┌───────────┴───────────┐
                            ▼                       ▼
        ┌───────────────────────────┐   ┌───────────────────────────┐
        │           llm             │   │       Letta Server        │
        │    (Core Base Module)     │   │ (localhost:8283 or Cloud) │
        └───────────────────────────┘   │  🧠 Persistent memory     │
                                        └───────────────────────────┘

Installation
============

What to Install
---------------

**For stateful AI agents:**

.. code-block:: bash

    # Install Python client
    pip install git+https://github.com/apexive/letta-python.git@main

    # Start Letta server (Docker)
    docker compose up letta -d

    # Install the Odoo module
    odoo-bin -d your_db -i llm_letta,llm_mcp_server

Auto-Installed Dependencies
---------------------------

- ``llm`` (core infrastructure)
- ``llm_thread`` (conversation management)

Why Choose Letta?
-----------------

+------------------+-------------------------------+
| Feature          | Letta                         |
+==================+===============================+
| **Memory**       | 🧠 Persistent across sessions |
+------------------+-------------------------------+
| **State**        | 💾 Stateful agents per thread |
+------------------+-------------------------------+
| **Tools**        | 🔧 MCP tool integration       |
+------------------+-------------------------------+
| **Context**      | 📚 Long-term awareness        |
+------------------+-------------------------------+

Common Setups
-------------

+-------------------------+----------------------------------------------+
| I want to...            | Install                                      |
+=========================+==============================================+
| Stateful agents         | ``llm_letta`` + ``llm_mcp_server``           |
+-------------------------+----------------------------------------------+
| Memory + tools          | ``llm_assistant`` + ``llm_letta`` +          |
|                         | ``llm_mcp_server``                           |
+-------------------------+----------------------------------------------+

Features
========

- **Persistent Memory**: Agents maintain context across sessions
- **Stateful Agents**: Dedicated agent per Odoo thread
- **MCP Tool Integration**: Zero-config Odoo tool access
- **Auto-sync**: Tools automatically synchronized
- **Flexible Deployment**: Self-hosted or Letta Cloud

Configuration
=============

Local Server (Default)
----------------------

The default "Letta (Local)" provider connects to ``localhost:8283`` - no API key needed.

Letta Cloud
-----------

1. Get API token from `Letta Cloud <https://app.letta.com>`_
2. Configure provider with API key
3. Use "Fetch Models" to sync available models

Technical Specifications
========================

- **Version**: 18.0.1.0.0
- **License**: LGPL-3
- **Dependencies**: ``llm``, ``llm_thread``, ``llm_mcp_server``
- **Python Package**: ``letta`` (apexive fork)
- **External**: Letta Server 0.11.7+

Related Modules
===============

- **``llm``** - Core infrastructure
- **``llm_thread``** - Conversation management
- **``llm_mcp_server``** - MCP tool server
- **``llm_assistant``** - AI assistants

License
=======

LGPL-3

----

*© 2025 Apexive Solutions LLC*
