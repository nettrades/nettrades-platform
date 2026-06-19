# Developer Troubleshooting

This document helps developers diagnose and fix common issues when working on the NETTRADES.AI codebase.

---

## Overview

This guide covers issues specific to developers, such as:

- Setting up the development environment
- Running Odoo and LangGraph locally
- Debugging agents and Odoo modules
- Common import and dependency issues

---

## General Developer Issues

### 1. Import "odoo" could not be resolved Pylance (reportMissingImports)

**Symptom:** VS Code shows `Import "odoo" could not be resolved` for Odoo module imports.

**Solution:**
1. Open `.vscode/settings.json` and add:
   ```json
   {
       "python.analysis.extraPaths": [
           "./third-party/odoo",
           "./third-party/odoo_llm",
           "./third-party/odoo_llm_compat"
       ],
       "python.autoComplete.extraPaths": [
           "./third-party/odoo",
           "./third-party/odoo_llm",
           "./third-party/odoo_llm_compat"
       ]
   }