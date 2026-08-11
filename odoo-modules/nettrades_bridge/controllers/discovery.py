# =============================================================================
# FILE: odoo-modules/nettrades_bridge/controllers/discovery.py
# =============================================================================
# PURPOSE:
#   mDNS/Avahi discovery controller for automatic node discovery.
#   Uses python-avahi to broadcast and discover NETTRADES nodes on the local network.
#
#   This complements the existing WireGuard bridge by providing automatic
#   peer discovery without manual configuration.
# =============================================================================

import json
import socket
import threading
import time
from datetime import datetime, timedelta

from odoo import http
from odoo.http import request, Response

try:
    import avahi
    import dbus
    from dbus import DBusException
    AVAHI_AVAILABLE = True
except ImportError:
    AVAHI_AVAILABLE = False
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning('python-avahi or dbus not available. mDNS discovery disabled.')


class DiscoveryController(http.Controller):

    # =========================================================================
    # REST API Endpoints
    # =========================================================================

    @http.route('/api/bridge/discovery/peers', type='json', auth='user', methods=['GET'])
    def get_discovered_peers(self):
        """
        Get all discovered peers from the cache.
        Returns:
            List of peer dictionaries with name, host, port, last_seen
        """
        if not AVAHI_AVAILABLE:
            return {'error': 'mDNS discovery not available'}

        discovery_service = request.env['nettrades_bridge.discovery'].sudo()
        peers = discovery_service.get_peers()
        return {
            'peers': [{
                'name': p.name,
                'host': p.host,
                'port': p.port,
                'last_seen': p.last_seen.isoformat() if p.last_seen else None,
                'capabilities': p.capabilities,
            } for p in peers]
        }

    @http.route('/api/bridge/discovery/advertise', type='json', auth='user', methods=['POST'])
    def advertise_node(self, **kwargs):
        """
        Advertise this node's capabilities to the network.
        Body:
            capabilities: dict of GPU resources, model availability, etc.
        """
        if not AVAHI_AVAILABLE:
            return {'error': 'mDNS discovery not available'}

        capabilities = kwargs.get('capabilities', {})
        discovery_service = request.env['nettrades_bridge.discovery'].sudo()
        discovery_service.update_advertisement(capabilities)
        return {'success': True, 'message': 'Advertisement updated'}

    @http.route('/api/bridge/discovery/status', type='json', auth='user', methods=['GET'])
    def discovery_status(self):
        """
        Get the status of the discovery service.
        """
        if not AVAHI_AVAILABLE:
            return {'status': 'unavailable', 'message': 'mDNS not available'}

        discovery_service = request.env['nettrades_bridge.discovery'].sudo()
        return {
            'status': 'running' if discovery_service.is_running() else 'stopped',
            'peers_count': discovery_service.get_peer_count(),
            'advertised_capabilities': discovery_service.get_advertised_capabilities(),
        }


class DiscoveryService(models.Model):
    """mDNS Discovery Service - manages peer discovery and advertisement"""

    _name = 'nettrades_bridge.discovery'
    _description = 'NETTRADES Bridge Discovery'

    name = fields.Char('Name', required=True)
    host = fields.Char('Host', required=True)
    port = fields.Integer('Port', default=5353)
    last_seen = fields.Datetime('Last Seen')
    capabilities = fields.Json('Capabilities')
    peer_id = fields.Char('Peer ID', index=True)

    _sql_constraints = [
        ('unique_peer', 'unique(peer_id)', 'Peer ID must be unique'),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._discovery_thread = None
        self._running = False
        self._peers = {}
        self._advertised_capabilities = {}

    # =========================================================================
    # mDNS Service Methods
    # =========================================================================

    def start_discovery(self):
        """Start the mDNS discovery service in a background thread"""
        if not AVAHI_AVAILABLE:
            _logger.warning('Cannot start discovery: avahi not available')
            return False

        if self._running:
            return True

        self._running = True
        self._discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self._discovery_thread.start()
        _logger.info('mDNS discovery service started')
        return True

    def stop_discovery(self):
        """Stop the mDNS discovery service"""
        self._running = False
        if self._discovery_thread:
            self._discovery_thread.join(timeout=5)
        _logger.info('mDNS discovery service stopped')
        return True

    def _discovery_loop(self):
        """Main discovery loop - runs in background thread"""
        # Get DBus connection
        try:
            bus = dbus.SystemBus()
            server = dbus.Interface(
                bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER),
                avahi.DBUS_INTERFACE_SERVER
            )
            domain = server.GetDomainName()
            service_type = '_nettrades._tcp'

            # Browse for services
            browser = dbus.Interface(
                bus.get_object(avahi.DBUS_NAME,
                               server.ServiceBrowserNew(avahi.IF_UNSPEC,
                                                         avahi.PROTO_UNSPEC,
                                                         service_type,
                                                         domain,
                                                         dbus.UInt32(0))),
                avahi.DBUS_INTERFACE_SERVICE_BROWSER
            )

            # Set up signal handlers
            browser.connect_to_signal('ItemNew', self._on_service_discovered)
            browser.connect_to_signal('ItemRemove', self._on_service_removed)

            # Also advertise our own service
            self._advertise_service(bus, server)

            # Keep the thread alive
            while self._running:
                time.sleep(1)

        except DBusException as e:
            _logger.error(f'mDNS discovery error: {e}')
            self._running = False

    def _advertise_service(self, bus, server):
        """Advertise this node's NETTRADES service via mDNS"""
        try:
            # Get hostname and IP
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)

            # Create the service entry
            group = dbus.Interface(
                bus.get_object(avahi.DBUS_NAME,
                               server.EntryGroupNew()),
                avahi.DBUS_INTERFACE_ENTRY_GROUP
            )

            # Build TXT record with capabilities
            txt_data = [
                f'version={self._get_version()}',
                f'gpus={self._get_gpu_count()}',
                f'models={self._get_model_count()}',
                f'capabilities={json.dumps(self._advertised_capabilities)}',
            ]

            group.AddService(
                avahi.IF_UNSPEC,
                avahi.PROTO_UNSPEC,
                dbus.UInt32(0),
                f'NETTRADES-{hostname}',
                '_nettrades._tcp',
                '',
                '',
                dbus.UInt16(5353),
                txt_data
            )

            group.Commit()
            _logger.info(f'Advertised NETTRADES service on {ip_address}:5353')

        except DBusException as e:
            _logger.error(f'Failed to advertise service: {e}')

    def _on_service_discovered(self, interface, protocol, name, service_type, domain, flags):
        """Callback when a new service is discovered"""
        _logger.info(f'Discovered service: {name}')
        # Resolve the service to get details
        # ... (implementation for resolving service details)

    def _on_service_removed(self, interface, protocol, name, service_type, domain, flags):
        """Callback when a service is removed"""
        _logger.info(f'Service removed: {name}')
        # Remove from peers cache

    # =========================================================================
    # Peer Management Methods
    # =========================================================================

    def get_peers(self):
        """Get all discovered peers"""
        return self.search([('last_seen', '>=', datetime.now() - timedelta(minutes=5))])

    def get_peer_count(self):
        """Get the number of discovered peers"""
        return self.search_count([('last_seen', '>=', datetime.now() - timedelta(minutes=5))])

    def update_advertisement(self, capabilities):
        """Update the advertised capabilities"""
        self._advertised_capabilities.update(capabilities)
        # Re-advertise with updated capabilities
        self.stop_discovery()
        self.start_discovery()

    def get_advertised_capabilities(self):
        """Get the currently advertised capabilities"""
        return self._advertised_capabilities

    def is_running(self):
        """Check if the discovery service is running"""
        return self._running

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_version(self):
        """Get the platform version"""
        return request.env['ir.config_parameter'].sudo().get_param('nettrades.version', '1.0.0')

    def _get_gpu_count(self):
        """Get the number of available GPUs"""
        return request.env['nettrades.gpu.node'].sudo().search_count([('status', '=', 'available')])

    def _get_model_count(self):
        """Get the number of available models"""
        return request.env['nettrades.llm.model'].sudo().search_count([])