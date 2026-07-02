import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migration script for llm_generate module refactoring

    This migration handles the refactoring of the generation system:
    - Providers now return tuple format (output_dict, urls_list)
    - URLs now include metadata (content_type, filename, etc.)
    - Schemas are stored in model details field instead of separate fields
    """

    _logger.info("Starting llm_generate module refactoring migration")

    # Migrate any existing models that still use separate input_schema/output_schema fields
    # Move them to the details field
    cr.execute("""
        UPDATE llm_model
        SET details = COALESCE(details, '{}')::jsonb ||
                     CASE
                         WHEN input_schema IS NOT NULL OR output_schema IS NOT NULL THEN
                             jsonb_build_object(
                                 'input_schema',
                                 CASE WHEN input_schema IS NOT NULL THEN input_schema::jsonb ELSE NULL END,
                                 'output_schema',
                                 CASE WHEN output_schema IS NOT NULL THEN output_schema::jsonb ELSE NULL END
                             )
                         ELSE '{}'::jsonb
                     END
        WHERE input_schema IS NOT NULL OR output_schema IS NOT NULL
    """)

    # Log how many models were migrated
    cr.execute("""
        SELECT COUNT(*) FROM llm_model
        WHERE input_schema IS NOT NULL OR output_schema IS NOT NULL
    """)
    count = cr.fetchone()[0]

    if count > 0:
        _logger.info(f"Migrated {count} models to use details field for schemas")

    _logger.info("Completed llm_generate module refactoring migration")
