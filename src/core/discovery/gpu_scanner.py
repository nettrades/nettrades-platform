#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: src/core/discovery/gpu_scanner.py
# =============================================================================
# PURPOSE:
#   Periodically scan registered subnets for new GPU nodes and trigger
#   registration if a node responds to a discovery probe.
#   This complements the MQTT-based auto‑discovery.
# =============================================================================

import os
import json
import logging
import time
import subprocess
import ipaddress
import requests
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class GpuScanner(models.AbstractModel):
    _name = 'gpu.scanner'
    _description = 'GPU Subnet Scanner'

    @api.model
    def scan_subnets(self):
        """
        Scan all registered subnets and attempt to discover new GPU nodes.
        This is intended to be called by a cron job.
        """
        Subnet = self.env['gpu.cluster.subnet']
        subnets = Subnet.search([])
        discovered = []
        for subnet in subnets:
            network = ipaddress.ip_network(subnet.subnet)
            # For each IP in the subnet, try to connect to a discovery port
            # (e.g., a lightweight agent listening on port 9090)
            for ip in network.hosts():
                # Skip known nodes (already registered)
                existing = self.env['gpu.node'].search([('ip_address', '=', str(ip))])
                if existing:
                    continue
                try:
                    # Simple probe: check if port 9090 is open (or use a custom HTTP probe)
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((str(ip), 9090))
                    sock.close()
                    if result == 0:
                        # Probe success: attempt to register the node
                        # This would require the node to have a token pre‑configured
                        # or we could generate a temporary token.
                        # For simplicity, we log and note.
                        _logger.info("New GPU node detected at %s", ip)
                        discovered.append(str(ip))
                except Exception as e:
                    _logger.debug("Scan failed for %s: %s", ip, e)
        return discovered