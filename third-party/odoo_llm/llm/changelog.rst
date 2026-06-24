18.0.1.5.0 (2025-11-28)
~~~~~~~~~~~~~~~~~~~~~~~

* [ADD] Added _extract_content_text() helper for extracting text from message content (handles both string and OpenAI list formats)
* [ADD] Added _dispatch("normalize_prepend_messages") call in chat() for provider-specific message normalization
* [IMP] Improved dispatch pattern consistency for prepend_messages handling

18.0.1.4.1 (2025-11-17)
~~~~~~~~~~~~~~~~~~~~~~~

* [FIX] Fixed wizard_id not being set on llm.fetch.models.line records
* [IMP] Refactored model fetching: moved logic from wizard default_get() to provider action_fetch_models()
* [IMP] Moved _determine_model_use() from wizard to provider for better extensibility
* [REM] Removed wizard write() override workaround
* [ADD] Comprehensive docstrings with extension pattern examples
* [ADD] Documented standard capability names and priority order

18.0.1.4.0 (2025-10-23)
~~~~~~~~~~~~~~~~~~~~~~~

* [MIGRATION] Migrated to Odoo 18.0
* [IMP] Updated views and manifest for compatibility

16.0.1.3.0
~~~~~~~~~~

* [BREAKING] Moved message subtypes to base module
* [ADD] Added required `llm_role` field computation with automatic migration
* [IMP] Enhanced provider dispatch mechanism
* [MIGRATION] Automatic computation of `llm_role` for existing messages
* [MIGRATION] Database migration creates indexes for performance

16.0.1.1.0 (2025-03-06)
~~~~~~~~~~~~~~~~~~~~~~~

* [ADD] Tool support framework in base LLM models
* [IMP] Enhanced provider interface to support tool execution
* [IMP] Updated model handling for function calling capabilities

16.0.1.0.0 (2025-01-02)
~~~~~~~~~~~~~~~~~~~~~~~

* [INIT] Initial release
