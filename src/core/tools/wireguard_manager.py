#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - WireGuard Manager
# =============================================================================
# FILE: src/core/tools/wireguard_manager.py
#
# PURPOSE:
#   Provides programmatic access to WireGuard management functions.
#   This module wraps the existing add-wireguard-user.sh script and
#   provides a Python API for the FastAPI backend.
#
# KEY FEATURES:
#   - Create WireGuard peers with automatic key generation
#   - List all peers with status
#   - Revoke peers
#   - Generate client configurations
#   - Generate QR codes for mobile setup
#
# INTEGRATION:
#   - Called by the FastAPI endpoints in app.py
#   - Uses Odoo's wireguard.peer model for data storage
#   - Communicates with the WireGuard server via wg commands
# =============================================================================

import logging
import subprocess
import re
import os
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class WireGuardManager:
    """
    Manager for WireGuard VPN operations.

    This class provides a clean API for managing WireGuard peers,
    interacting with both the WireGuard server and the Odoo database.
    """

    # =========================================================================
    # 1. Configuration
    # =========================================================================

    WG_CONFIG_PATH = '/etc/wireguard/admin/wg0.conf'
    WG_INTERFACE = 'admin-wg0'
    WG_SUBNET = os.getenv('WG_ADMIN_SUBNET', '10.10.10.0/24')
    WG_PORT = os.getenv('WG_ADMIN_PORT', '51821')
    DOMAIN = os.getenv('DOMAIN', 'localhost')

    # =========================================================================
    # 2. Peer Management
    # =========================================================================

    @classmethod
    def create_peer(cls, partner_id: int, name: str, odoo_env) -> Dict[str, Any]:
        """
        Create a new WireGuard peer.

        Args:
            partner_id: The Odoo partner ID to associate with this peer.
            name: Human-readable name for the peer.
            odoo_env: The Odoo environment (for database access).

        Returns:
            Dict containing the peer details including config and QR code.
        """
        # Use the Odoo model to create the peer
        Peer = odoo_env['wireguard.peer']
        peer = Peer.create_peer(partner_id, name)

        # Generate QR code (using qrencode)
        qr_code = cls._generate_qr_code(peer.config_file)

        return {
            'id': peer.id,
            'name': peer.name,
            'assigned_ip': peer.assigned_ip,
            'public_key': peer.public_key,
            'status': peer.status,
            'config': peer.config_file,
            'qr_code': qr_code,
            'created_at': peer.created_at.isoformat() if peer.created_at else None,
        }

    @classmethod
    def list_peers(cls, odoo_env, include_revoked: bool = False) -> List[Dict[str, Any]]:
        """
        List all WireGuard peers.

        Args:
            odoo_env: The Odoo environment.
            include_revoked: Whether to include revoked peers.

        Returns:
            List of peer dictionaries with status information.
        """
        domain = []
        if not include_revoked:
            domain.append(('status', '=', 'active'))

        peers = odoo_env['wireguard.peer'].search(domain)

        result = []
        for peer in peers:
            # Get real-time status from WireGuard
            status = cls._get_peer_status(peer.public_key)

            result.append({
                'id': peer.id,
                'name': peer.name,
                'partner_id': peer.partner_id.id,
                'partner_name': peer.partner_id.name,
                'assigned_ip': peer.assigned_ip,
                'public_key': peer.public_key,
                'status': peer.status,
                'is_online': status.get('online', False),
                'last_handshake': status.get('last_handshake'),
                'rx_mb': status.get('rx_mb', 0),
                'tx_mb': status.get('tx_mb', 0),
                'created_at': peer.created_at.isoformat() if peer.created_at else None,
            })

        return result

    @classmethod
    def revoke_peer(cls, peer_id: int, odoo_env) -> bool:
        """
        Revoke a WireGuard peer.

        Args:
            peer_id: The ID of the peer to revoke.
            odoo_env: The Odoo environment.

        Returns:
            True if successful, False otherwise.
        """
        peer = odoo_env['wireguard.peer'].browse(peer_id)
        if not peer.exists():
            raise ValueError(f"Peer with ID {peer_id} not found.")

        peer.revoke()
        return True

    @classmethod
    def get_peer_config(cls, peer_id: int, odoo_env) -> Optional[str]:
        """
        Get the client configuration for a peer.

        Args:
            peer_id: The ID of the peer.
            odoo_env: The Odoo environment.

        Returns:
            The configuration file content, or None if not found.
        """
        peer = odoo_env['wireguard.peer'].browse(peer_id)
        if not peer.exists():
            return None

        if not peer.config_file:
            peer._generate_config_file()

        return peer.config_file

    @classmethod
    def get_peer_qr_code(cls, peer_id: int, odoo_env) -> Optional[str]:
        """
        Generate a QR code for a peer's configuration.

        Args:
            peer_id: The ID of the peer.
            odoo_env: The Odoo environment.

        Returns:
            Base64-encoded PNG image data, or None if not found.
        """
        config = cls.get_peer_config(peer_id, odoo_env)
        if not config:
            return None

        return cls._generate_qr_code(config)

    # =========================================================================
    # 3. Status & Health
    # =========================================================================

    @classmethod
    def get_server_status(cls) -> Dict[str, Any]:
        """
        Get the status of the WireGuard server.

        Returns:
            Dict containing server status information.
        """
        try:
            # Get interface status
            result = subprocess.run(
                ['wg', 'show', cls.WG_INTERFACE],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            output = result.stdout

            # Parse peer count
            peers = re.findall(r'peer:\s*(\S+)', output)

            return {
                'interface': cls.WG_INTERFACE,
                'port': cls.WG_PORT,
                'peer_count': len(peers),
                'is_running': True,
            }
        except Exception as e:
            _logger.warning(f"Failed to get server status: {e}")
            return {
                'interface': cls.WG_INTERFACE,
                'port': cls.WG_PORT,
                'peer_count': 0,
                'is_running': False,
                'error': str(e),
            }

    @classmethod
    def _get_peer_status(cls, public_key: str) -> Dict[str, Any]:
        """
        Get the status of a specific peer from WireGuard.

        Args:
            public_key: The peer's public key.

        Returns:
            Dict with status information.
        """
        try:
            result = subprocess.run(
                ['wg', 'show', cls.WG_INTERFACE, 'peer', public_key],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            output = result.stdout

            status = {
                'online': False,
                'last_handshake': None,
                'rx_mb': 0,
                'tx_mb': 0,
            }

            # Parse handshake
            handshake_match = re.search(r'latest handshake:\s*(.+)', output)
            if handshake_match:
                status['last_handshake'] = handshake_match.group(1).strip()
                # Check if handshake is recent (within 3 minutes)
                try:
                    dt = datetime.strptime(status['last_handshake'], '%Y-%m-%d %H:%M:%S')
                    if (datetime.now() - dt) < timedelta(minutes=3):
                        status['online'] = True
                except ValueError:
                    pass

            # Parse transfer
            transfer_match = re.search(
                r'transfer:\s*([\d.]+)\s*([KM]iB)\s*received,\s*([\d.]+)\s*([KM]iB)\s*sent',
                output
            )
            if transfer_match:
                rx_val = float(transfer_match.group(1))
                rx_unit = transfer_match.group(2)
                tx_val = float(transfer_match.group(3))
                tx_unit = transfer_match.group(4)

                # Convert to MB
                if rx_unit == 'KiB':
                    status['rx_mb'] = rx_val / 1024
                elif rx_unit == 'MiB':
                    status['rx_mb'] = rx_val
                elif rx_unit == 'GiB':
                    status['rx_mb'] = rx_val * 1024

                if tx_unit == 'KiB':
                    status['tx_mb'] = tx_val / 1024
                elif tx_unit == 'MiB':
                    status['tx_mb'] = tx_val
                elif tx_unit == 'GiB':
                    status['tx_mb'] = tx_val * 1024

            return status
        except Exception as e:
            _logger.warning(f"Failed to get peer status: {e}")
            return {'online': False, 'error': str(e)}

    # =========================================================================
    # 4. Utilities
    # =========================================================================

    @classmethod
    def _generate_qr_code(cls, config: str) -> Optional[str]:
        """
        Generate a QR code from a WireGuard configuration.

        Args:
            config: The WireGuard configuration string.

        Returns:
            Base64-encoded PNG image data, or None if generation fails.
        """
        try:
            import qrcode
            from io import BytesIO
            import base64

            img = qrcode.make(config)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{img_str}"
        except ImportError:
            _logger.warning("qrcode module not installed. QR code generation disabled.")
            # Fallback: return a text representation
            return f"data:text/plain;base64,{base64.b64encode(config.encode()).decode('utf-8')}"
        except Exception as e:
            _logger.error(f"Failed to generate QR code: {e}")
            return None

    @classmethod
    def _get_server_public_key(cls) -> Optional[str]:
        """Get the WireGuard server's public key."""
        try:
            with open('/etc/wireguard/admin/publickey', 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    @classmethod
    def _get_server_endpoint(cls) -> str:
        """Get the server endpoint for client configuration."""
        return f"{cls.DOMAIN}:{cls.WG_PORT}"