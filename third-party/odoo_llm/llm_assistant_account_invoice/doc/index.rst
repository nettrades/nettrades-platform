=======================
LLM Invoice Assistant
=======================

AI-powered invoice analysis assistant with OCR document parsing for Odoo 18.

**Module Type:** 🚀 Entry Point (Invoice Processing)

Architecture
============

::

    ┌───────────────────────────────────────────────────────────────┐
    │                       Odoo Accounting                         │
    │                    ┌───────────────┐                          │
    │                    │ account.move  │                          │
    │                    │(Vendor Bills) │                          │
    │                    └───────┬───────┘                          │
    └────────────────────────────┼──────────────────────────────────┘
                                 │
                                 ▼
          ┌───────────────────────────────────────────────────────┐
          │    ★ llm_assistant_account_invoice (This Module) ★    │
          │              Invoice Analysis Assistant                │
          │  📄 OCR Parsing │ Data Extraction │ Auto-Fill         │
          └───────────────────────────┬───────────────────────────┘
                                      │
                      ┌───────────────┼───────────────┐
                      ▼               ▼               ▼
        ┌─────────────────┐  ┌───────────────┐  ┌─────────────────┐
        │  llm_assistant  │  │llm_tool_ocr   │  │   llm_mistral   │
        │  (AI Framework) │  │   _mistral    │  │   (Provider)    │
        └────────┬────────┘  └───────────────┘  └─────────────────┘
                 │
                 ▼
        ┌─────────────────┐
        │       llm       │
        │ (Core Module)   │
        └─────────────────┘

Installation
============

What to Install
---------------

**For AI-powered invoice processing:**

.. code-block:: bash

    odoo-bin -d your_db -i llm_assistant_account_invoice

Auto-Installed Dependencies
---------------------------

- ``llm`` (core infrastructure)
- ``llm_assistant`` (AI assistant framework)
- ``llm_tool_ocr_mistral`` (OCR tool)
- ``llm_mistral`` (Mistral AI provider)
- ``account`` (Odoo accounting)

Why Use This Module?
--------------------

+----------------+----------------------------------+
| Feature        | llm_assistant_account_invoice    |
+================+==================================+
| **OCR**        | 📄 Extract text from PDFs/images |
+----------------+----------------------------------+
| **Auto-Fill**  | ✅ Populate invoice fields       |
+----------------+----------------------------------+
| **Validation** | 🔍 Check for errors              |
+----------------+----------------------------------+
| **Zero Code**  | 📝 Pure XML configuration        |
+----------------+----------------------------------+

Common Setups
-------------

+---------------------------+----------------------------------+
| I want to...              | Install                          |
+===========================+==================================+
| Process invoices with AI  | ``llm_assistant_account_invoice``|
+---------------------------+----------------------------------+
| Add chat provider         | Above + ``llm_openai`` (for GPT) |
+---------------------------+----------------------------------+

Features
========

- 📄 **OCR Document Parsing**: Extract text from invoice PDFs and images using Mistral OCR
- 🔍 **Smart Invoice Analysis**: Analyze vendor bills with AI assistance
- ✅ **Automated Validation**: Check for common invoice errors
- 📝 **Data Extraction**: Fill invoice fields from scanned documents
- 🔗 **ERP Integration**: Access related purchase orders, products, and vendor history

Installation
============

1. Install dependencies:

   - ``account`` (Odoo core)
   - ``llm_assistant``
   - ``llm_tool_ocr_mistral``

2. Install the module:

   .. code-block:: bash

      odoo-bin -d your_database -i llm_assistant_account_invoice

3. Configure Mistral provider in **Settings → LLM → Providers**

Usage
=====

Create Invoice Analysis Thread
-------------------------------

1. **Manual Way**:

   - Go to **LLM → Threads → Create**
   - Link to your invoice using the record picker
   - Select "Invoice Analysis Assistant"
   - Start chatting!

2. **Future Enhancement**: Add "Ask AI" button to invoice form

Example Conversations
---------------------

**Basic Analysis**::

   User: What is the vendor and total amount?
   Assistant: The vendor is Acme Corp and the total amount is $5,420.00

**Document Parsing**::

   User: Parse attachment 123
   Assistant: [uses llm_mistral_attachment_parser]
   Assistant: I extracted: Invoice #INV-2024-001 from Acme Corp
            Date: 2024-01-15, Total: $5,420.00
            Line items:
            - Product A: $2,000.00
            - Product B: $3,420.00

**Data Retrieval**::

   User: Find other invoices from this vendor
   Assistant: [uses odoo_record_retriever]
   Assistant: Found 3 other invoices from Acme Corp:
            - INV-2023-045: $3,200.00 (Paid)
            - INV-2023-089: $1,850.00 (Paid)
            - INV-2024-002: $4,100.00 (Draft)

**Validation**::

   User: Check if this invoice looks correct
   Assistant: I've reviewed the invoice and found:
            ✓ Vendor VAT number present
            ✓ Invoice has line items
            ⚠️ Warning: Invoice date is in the future
            ⚠️ Warning: No payment terms specified

Assistant Configuration
=======================

The Invoice Analysis Assistant includes:

Context Awareness
-----------------

- Automatically accesses invoice fields via ``related_record`` proxy
- No need to specify invoice ID in every query

Available Tools
---------------

1. **llm_tool_ocr_mistral**: Parse PDFs/images with Mistral OCR
2. **odoo_record_retriever**: Search and retrieve Odoo records
3. **odoo_record_updater**: Update invoice fields (requires consent)
4. **odoo_model_inspector**: Inspect model structure

Intelligent Instructions
------------------------

The assistant knows how to:

- Extract data from OCR results
- Validate invoice consistency
- Handle accounting workflows
- Respect user consent for updates
- Follow best practices for financial data

Module Architecture
===================

Pure Configuration Module
--------------------------

This module contains **no Python code** - just XML data files::

   llm_assistant_account_invoice/
   ├── __manifest__.py              # Dependencies and metadata
   ├── __init__.py                  # Empty (no code needed)
   ├── data/
   │   ├── llm_prompt_invoice_data.xml  # Invoice-specific prompt template
   │   └── llm_assistant_data.xml       # Assistant configuration
   ├── views/
   │   └── account_move_views.xml   # "Process with AI" button on invoice form
   └── static/
       └── description/
           └── index.html           # App store description

How It Works
------------

1. **Uses existing prompt template** from ``llm_assistant``
2. **Provides invoice-specific context** via ``default_values``
3. **References existing tools** via XML ``ref()``
4. **Leverages llm_thread** for record linking

Dependencies
============

Required Modules
----------------

- **account**: Core Odoo accounting (vendor bills)
- **llm_assistant**: Base LLM assistant framework
- **llm_tool_ocr_mistral**: Mistral OCR tool for parsing documents

Transitive Dependencies
-----------------------

These are pulled in automatically:

- ``llm``: Core LLM provider/model system
- ``llm_thread``: Thread management with record linking
- ``llm_tool``: Tool registration and consent
- ``llm_mistral``: Mistral AI provider

Configuration
=============

1. Mistral Provider Setup
--------------------------

1. Go to **Settings → LLM → Providers**
2. Find or create "Mistral AI" provider
3. Enter your API key
4. Click "Sync Models"
5. Verify OCR models appear (e.g., "mistral-ocr-latest")

2. Assistant Settings
---------------------

The assistant is pre-configured with sensible defaults:

- **Name**: Invoice Analysis Assistant
- **Code**: ``invoice_analyzer``
- **Model**: ``account.move``
- **Public**: Yes (all users can access)
- **Default**: Yes (default assistant for invoices)

Customize in **Settings → LLM → Assistants** if needed.

Security & Permissions
======================

Access Control
--------------

- **Thread creation**: Requires ``llm_thread`` permissions
- **Tool usage**: Controlled by ``llm_tool`` consent system
- **Invoice access**: Controlled by ``account`` module groups

Tool Consent
------------

- **llm_tool_ocr_mistral**: Requires consent (accesses attachments)
- **odoo_record_retriever**: No consent (read-only)
- **odoo_record_updater**: Requires consent (modifies data)

Users must approve tool execution before sensitive operations.

Customization
=============

Add Custom Instructions
-----------------------

Edit the assistant's ``default_values`` in ``data/llm_assistant_data.xml``:

.. code-block:: xml

   <field name="default_values"><![CDATA[{
       "role": "Invoice Analysis Assistant",
       "goal": "...",
       "instructions": "Your custom instructions here..."
   }]]></field>

Add More Tools
--------------

Reference additional tools in the ``tool_ids`` field:

.. code-block:: xml

   <field name="tool_ids" eval="[(6, 0, [
       ref('llm_tool_ocr_mistral.llm_tool_ocr_mistral'),
       ref('llm_tool.llm_tool_odoo_record_retriever'),
       ref('your_module.your_custom_tool'),  <!-- Add this -->
   ])]" />

Create Multiple Assistants
---------------------------

Duplicate the record with different configurations:

- Invoice Validator (read-only, no updater tool)
- Invoice Data Entry (focuses on OCR + updates)
- Invoice Approver (workflow-focused)

Best Practices
==============

For Users
---------

1. **Upload documents first**, then ask AI to parse them
2. **Review extracted data** before confirming updates
3. **Use specific questions** for better results
4. **Link threads to invoices** for context-aware responses

For Administrators
------------------

1. **Monitor tool consent**: Review which users approve updates
2. **Track assistant usage**: Check thread activity
3. **Customize instructions**: Tailor to your accounting workflows
4. **Train users**: Show examples of effective prompts

Troubleshooting
===============

"No OCR model found"
--------------------

**Solution**: Sync models from Mistral provider settings

"Mistral provider not found"
-----------------------------

**Solution**: Install and configure ``llm_mistral`` module with your API key

"Tool requires consent"
-----------------------

**Expected**: User must approve before tool executes. This is by design for security.

Thread not linked to invoice
-----------------------------

**Solution**: Use record picker to link thread to ``account.move`` record

Future Enhancements
===================

Potential additions (not yet implemented):

1. **Auto-process on attachment** - Automatically trigger AI processing when an invoice receives an attachment (PDF/image), filling in vendor, date, amounts, and line items without manual intervention
2. **Automated invoice matching** with purchase orders (3-way matching)
3. **Approval workflow tools** (approve/reject invoices)
4. **Multi-invoice analysis** (batch processing)
5. **Learning from corrections** (feedback loop)

Contributing
============

Found a bug or have a suggestion? Open an issue at:
https://github.com/apexive/odoo-llm/issues

License
=======

LGPL-3

Credits
=======

**Author**: Apexive Solutions LLC

**Website**: https://github.com/apexive/odoo-llm
