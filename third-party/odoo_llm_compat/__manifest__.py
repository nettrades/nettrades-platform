# -*- coding: utf-8 -*-
# =============================================================================
# Section: A-F – Odoo LLM Compatibility shim (Odoo 19.0)
# Purpose:  This module is a marker that allows the community LLM package
#           (apexive/odoo-llm) to be recognised under Odoo 19.0.
#           The LLM modules are currently versioned for 18.0, but they are
#           compatible with 19.0 after updating the manifest version.
# =============================================================================
{
    'name': 'Odoo LLM Compatibility (19.0)',
    'version': '1.0',
    'category': 'Hidden',
    'depends': ['base'],
    'installable': True,
    'auto_install': True,
}