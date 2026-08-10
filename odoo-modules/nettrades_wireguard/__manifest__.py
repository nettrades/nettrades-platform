# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES WireGuard Management
# =============================================================================
# FILE: odoo-modules/nettrades_wireguard/__manifest__.py
#
# PURPOSE:
#   This module adds WireGuard peer management to Odoo.
#   Peers are linked to res.partner records, so user permissions are
#   managed through Odoo's existing security model.
#
# DEPENDENCIES:
#   - base
#   - nettrades_core (for user/partner extensions)
# =============================================================================

{
    'name': 'NETTRADES WireGuard',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'WireGuard VPN peer management',
    'description': """
        Manages WireGuard VPN peers linked to Odoo users.
        Provides:
        - Peer creation with automatic key generation
        - Peer status tracking (active/revoked)
        - Integration with Odoo's permission model
        - API endpoints for the launcher
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'nettrades_core',
    ],
    'data': [
        'security/wireguard_security.xml',
        'security/ir.model.access.csv',
        'views/wireguard_peer_views.xml',
        'views/wireguard_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}