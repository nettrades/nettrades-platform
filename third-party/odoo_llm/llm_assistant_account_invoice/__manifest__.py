{
    "name": "LLM Invoice Assistant",
    "summary": "AI-powered invoice analysis assistant with OCR document parsing",
    "description": """
        Intelligent invoice assistant that helps analyze vendor bills and invoices using AI.
        Features document parsing with OCR, automated data extraction, and smart invoice validation.
    """,
    "category": "Accounting/AI",
    "version": "19.0.1.0.0",
    "depends": [
        "account",  # Invoice model (account.move)
        "llm_assistant",  # Includes llm, llm_thread, llm_tool
        "llm_tool_ocr_mistral",  # OCR tool
    ],
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "data": [
        "data/llm_prompt_invoice_data.xml",
        "data/llm_assistant_data.xml",
        "views/account_move_views.xml",
    ],
    "images": [
        "static/description/banner.jpeg",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
