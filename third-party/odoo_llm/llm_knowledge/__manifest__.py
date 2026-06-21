{
    "name": "LLM Knowledge",
    "summary": "RAG vector search: AI knowledge base with semantic document retrieval, embeddings, PDF parsing, and multi-store support (Qdrant, pgvector, Chroma)",
    "description": """
        Complete RAG (Retrieval-Augmented Generation) system for Odoo with document processing,
        vector search, and semantic knowledge base capabilities. Turn your documents into AI-searchable
        knowledge with support for PDFs, web pages, and text files. Compatible with Qdrant, pgvector,
        and Chroma vector stores.
    """,
    "category": "Technical",
    "version": "19.0.1.0.0",
    "depends": ["llm", "llm_store"],
    "external_dependencies": {
        "python": ["requests", "markdownify", "PyMuPDF", "numpy"],
    },
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "data": [
        "security/ir.model.access.csv",
        "data/server_actions.xml",
        
        # 1. Load Views & Actions FIRST
        "views/llm_resource_views.xml", 
        "views/llm_knowledge_collection_views.xml",
        "views/llm_knowledge_chunk_views.xml",
        
        # 2. Load Wizards
        "wizards/create_rag_resource_wizard_views.xml",
        "wizards/upload_resource_wizard_views.xml",
        
        # 3. Load Menus LAST
        "views/llm_resource_menu.xml",
        "views/menu.xml",
    ],
    "images": [
        "static/description/banner.jpeg",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
