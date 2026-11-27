# -*- coding: utf-8 -*-
# FILE: odoo-modules/nettrades_bridge/__init__.py
import logging
import threading
_logger = logging.getLogger(__name__)

from . import models
from . import controllers


def post_load():
    """
    Start the mDNS discovery service in a background thread for every
    database. This makes the hub discoverable even when the NETTRADES
    Launcher is not running (headless server deployments).
    """
    try:
        import odoo
        from odoo import api, SUPERUSER_ID

        def _start_discovery_for_db(db_name):
            """Start discovery for a single database."""
            try:
                registry = odoo.registry(db_name)
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    service = env['nettrades_bridge.discovery'].sudo()
                    if not service.is_running():
                        service.start_discovery()
                        _logger.info(
                            "NETTRADES Bridge: mDNS discovery started for db '%s'",
                            db_name,
                        )
            except Exception as e:
                _logger.warning(
                    "NETTRADES Bridge: discovery start failed for db '%s': %s",
                    db_name, e,
                )

        # Start discovery for every database in the filestore
        import odoo.service.db as db_service
        db_names = db_service.list_dbs(force=True)
        for db_name in db_names:
            t = threading.Thread(
                target=_start_discovery_for_db,
                args=(db_name,),
                daemon=True,
            )
            t.start()

        _logger.info(
            "NETTRADES Bridge: post_load hook started discovery for %d database(s)",
            len(db_names),
        )
    except Exception as e:
        _logger.warning("NETTRADES Bridge: post_load hook failed: %s", e)