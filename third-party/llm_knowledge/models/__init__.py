# -*- coding: utf-8 -*-
# =============================================================================
# LLM Knowledge – Models
# =============================================================================
# FILE: third-party/odoo_llm/llm_knowledge/models/__init__.py
#
# PURPOSE:
#   This file imports all model files in the llm_knowledge module.
#   Each model must be imported here to be discovered by Odoo.
#
# IMPORTANT:
#   Do NOT include the .py extension when importing Python modules.
#   The correct syntax is: from . import filename (without .py)
#
# =============================================================================

from . import ir_attachment
from . import mail_thread
from . import llm_resource
from . import llm_resource_retriever
from . import llm_resource_parser
from . import llm_resource_http
from . import llm_resource_chunker
from . import llm_knowledge_chunk
from . import llm_knowledge_collection
from . import llm_knowledge_domain
from . import llm_embedding_model