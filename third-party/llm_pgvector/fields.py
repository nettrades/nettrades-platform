# -*- coding: utf-8 -*-
# =============================================================================
# Odoo 19 PgVector Field – Custom Vector Field for PostgreSQL pgvector
# =============================================================================
# FILE: third-party/odoo_llm/llm_pgvector/fields.py
#
# PURPOSE:
#   This module provides a custom Odoo field type for storing vector embeddings
#   using the PostgreSQL pgvector extension. It integrates seamlessly with
#   Odoo's ORM, enabling vector operations and similarity searches.
#
#   This field is used by the llm_knowledge and llm_store modules to store
#   document embeddings for RAG (Retrieval-Augmented Generation).
#
# =============================================================================
#
# ODoo 19 COMPATIBILITY NOTE:
#   In Odoo 19, the `dimension` parameter is NOT a valid field parameter for
#   the parent field class. This has been fixed by removing `dimension` from
#   the `super().__init__()` call and using the `_slots` dictionary to store
#   the dimension as an instance attribute (already defined in `_slots`).
#
#   The dimension is still accepted in the constructor to set the field's
#   `dimension` slot, which is later used to enforce vector size constraints
#   in the database (via the `CREATE COLUMN` statement).
#
# =============================================================================

import logging
import numpy as np
from pgvector import Vector
from pgvector.psycopg2 import register_vector

from odoo import fields, tools
from odoo.tools.misc import SENTINEL, Sentinel

_logger = logging.getLogger(__name__)


class PgVector(fields.Field):
    """
    PgVector field for Odoo, using pgvector extension for PostgreSQL.

    This field stores vector embeddings in PostgreSQL using the pgvector extension.
    It supports:
      - Automatic vector dimension enforcement in the database
      - Conversion between Python lists/numpy arrays and pgvector's Vector type
      - Integration with Odoo's ORM for reading/writing vector data

    :param int dimension: Optional dimension of the vector. If provided, the column
                          will be created with the specified dimension constraint.
                          This is stored in the field's `dimension` slot.
    """

    type = "pgvector"
    column_type = ("vector", "vector")

    # -------------------------------------------------------------------------
    # 1. Slots (Odoo 19 style field attributes)
    # -------------------------------------------------------------------------
    # The `dimension` slot stores the vector size for this field instance.
    # It is used in `create_column` to define the vector dimension in SQL.
    _slots = {
        "dimension": None,  # Vector dimensions (int or None)
    }

    # -------------------------------------------------------------------------
    # 2. Initialisation
    # -------------------------------------------------------------------------

    def __init__(
        self, string: str | Sentinel = SENTINEL, dimension: int | None = None, **kwargs
    ):
        """
        Initialise the PgVector field.

        Args:
            string: The field label (optional).
            dimension: The vector dimension. If None, no dimension constraint
                       is applied in the database.
            **kwargs: Additional field parameters (passed to parent).

        Odoo 19 Compatibility:
            The `dimension` parameter is NOT a valid parameter for the parent
            field class. It is stored in the `_slots` dictionary (already defined)
            and used later in `create_column`. Therefore we do NOT pass it to
            `super().__init__()`.
        """
        # Store the dimension in the field's slot (this is done automatically
        # because `_slots` is defined and Odoo's field machinery handles it).
        # However, we must NOT pass `dimension` to the super constructor.
        # The parent constructor does not accept `dimension` in Odoo 19.
        super().__init__(string=string, **kwargs)

        # The dimension is stored in the `self.dimension` slot because we defined
        # it in `_slots`. Odoo's field machinery automatically sets it from the
        # constructor argument if it matches a slot name.
        # So `self.dimension` is now available for use in `create_column`.

    # -------------------------------------------------------------------------
    # 3. Value Conversion Methods
    # -------------------------------------------------------------------------

    def convert_to_column(self, value, record, values=None, validate=True):
        """
        Convert Python value to database format using pgvector.Vector.

        This method is called when writing a value to the database.
        It ensures the value is properly formatted as a pgvector Vector object.

        Args:
            value: The Python value (list, numpy array, or None).
            record: The record being written.
            values: Additional values (unused).
            validate: Whether to validate the value (unused).

        Returns:
            The pgvector Vector object, or None if value is None.
        """
        if value is None:
            return None

        # Ensure the value is properly formatted for pgvector
        try:
            # Use Vector._to_db method from pgvector
            # This handles lists, numpy arrays, and other iterables
            return Vector._to_db(value, self.dimension)
        except (ValueError, TypeError) as e:
            _logger.warning(f"Error converting vector: {e}. Returning NULL.")
            return None

    def convert_to_cache(self, value, record, validate=True):
        """
        Convert database value to cache format.

        This method is called when reading a value from the database.
        It converts the pgvector Vector object back to a Python list or numpy array.

        Args:
            value: The database value (pgvector Vector or string representation).
            record: The record being read.
            validate: Whether to validate the value (unused).

        Returns:
            The vector as a Python list, or None if value is None.
        """
        if value is None:
            return None

        # Handle case where value is already a list or numpy array
        if isinstance(value, list) or isinstance(value, np.ndarray):
            return value

        # Safely convert from database format
        try:
            # Use Vector._from_db method from pgvector for string values
            return Vector._from_db(value)
        except (ValueError, TypeError) as e:
            _logger.warning(f"Error converting vector from DB: {e}. Returning None.")
            return None

    # -------------------------------------------------------------------------
    # 4. Database Column Creation
    # -------------------------------------------------------------------------

    def create_column(self, cr, table, column, **kwargs):
        """
        Create a vector column in the database.

        This method is called during schema creation/upgrade. It registers
        the pgvector extension and creates the column with the appropriate
        dimension constraint if specified.

        Args:
            cr: The database cursor.
            table: The table name.
            column: The column name.
            **kwargs: Additional arguments (unused).
        """
        # Register pgvector with this cursor (enables Vector type)
        register_vector(cr)

        # Build the dimension specification for SQL
        # If self.dimension is set, we create a vector with fixed size:
        #   e.g., `vector(384)` for a 384-dimensional vector.
        # If self.dimension is None, we create an unconstrained vector column.
        dim_spec = f"({self.dimension})" if self.dimension else ""

        # Add the column if it doesn't already exist
        # Using ALTER TABLE ... ADD COLUMN IF NOT EXISTS
        cr.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} vector{dim_spec}"
        )

        # Update the column type to ensure it matches the expected vector type
        # This is useful when the column already exists but was created without
        # the correct dimension constraint.
        tools.set_column_type(cr, table, column, f"vector{dim_spec}")

        _logger.info(
            f"Created/updated vector column {table}.{column} with dimension {self.dimension}"
        )