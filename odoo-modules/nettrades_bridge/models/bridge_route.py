# =============================================================================
# FILE: odoo-modules/nettrades_bridge/models/bridge_route.py
# =============================================================================
# PURPOSE:
#   Bridge route management for the NETTRADES Sovereign AI Router.
#   Provides:
#     1. Route decision engine – local vs remote based on admin configuration
#     2. Dynamic node registration for NVIDIA Dynamo
#     3. Load balancing across healthy Dynamo nodes
#     4. Health checking for all routes
#     5. Fallback to llama.cpp when Dynamo is unavailable
#     6. GPU marketplace integration for remote inference
#
#   ARCHITECTURE:
#     ┌─────────────────────────────────────────────────────────────────┐
#     │                    BridgeRoute (this model)                    │
#     │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
#     │  │ Route Rules │  │   Dynamo    │  │  Fallback   │           │
#     │  │ (Admin      │  │   Load      │  │  (llama.cpp)│           │
#     │  │  Config)    │  │   Balancing │  │             │           │
#     │  └─────────────┘  └─────────────┘  └─────────────┘           │
#     │         │              │              │                       │
#     │         ▼              ▼              ▼                       │
#     │  ┌─────────────────────────────────────────────────────────┐  │
#     │  │              Request Router Decision Engine             │  │
#     │  │  • Check admin rules (local vs remote)                 │  │
#     │  │  • Check GPU availability                              │  │
#     │  │  • Check cost/priority                                 │  │
#     │  │  • Route to Dynamo, llama.cpp, or remote provider     │  │
#     │  └─────────────────────────────────────────────────────────┘  │
#     └─────────────────────────────────────────────────────────────────┘
#
#   INTEGRATION WITH LANGRAPH AGENTS:
#     - The inference_tools.py agents call get_route_for_request()
#     - Agents receive the target URL and route type
#     - Agents don't need to know the routing logic
#
#   UPDATES (2026-08):
#     - Merged old routing logic (local vs remote) with new Dynamo load balancing
#     - Added route decision engine with admin-configurable rules
#     - Added support for GPU marketplace as a remote provider
#     - Added support for external API providers (OpenAI, Anthropic)
#     - All existing functionality preserved and enhanced
# =============================================================================

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import requests
import json
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class BridgeRoute(models.Model):
    _name = 'nettrades_bridge.route'
    _description = 'NETTRADES Bridge Route'
    _order = 'priority desc, name'

    # =========================================================================
    # 1. CORE FIELDS – Basic route identification
    # =========================================================================

    name = fields.Char('Route Name', required=True)
    route_type = fields.Selection([
        ('inference', 'Inference'),
        ('training', 'Training'),
        ('fine_tuning', 'Fine Tuning'),
        ('embedding', 'Embedding'),
        ('chat', 'Chat'),
        ('completion', 'Completion'),
    ], string='Route Type', required=True, default='inference')

    description = fields.Text('Description')

    is_active = fields.Boolean('Active', default=True)
    priority = fields.Integer('Priority', default=100)

    # =========================================================================
    # 2. ROUTE DECISION ENGINE – Local vs Remote (OLD LOGIC PRESERVED)
    # =========================================================================

    # ─── Routing Mode ──────────────────────────────────────────────────────────
    routing_mode = fields.Selection([
        ('local_only', 'Local Only (Sovereign AI)'),
        ('remote_only', 'Remote Only (Cloud/External)'),
        ('hybrid', 'Hybrid (Local First, Remote Fallback)'),
        ('hybrid_remote_first', 'Hybrid (Remote First, Local Fallback)'),
        ('auto', 'Auto (AI Decides)'),
    ], string='Routing Mode', required=True, default='local_only',
       help="""Controls how requests are routed:
       - Local Only: All requests stay on local infrastructure
       - Remote Only: All requests go to external providers
       - Hybrid (Local First): Try local, fallback to remote if unavailable
       - Hybrid (Remote First): Try remote, fallback to local if unavailable
       - Auto: AI agent decides based on context""")

    # ─── Local Infrastructure ──────────────────────────────────────────────────
    use_local_dynamo = fields.Boolean('Use Local Dynamo', default=True)
    use_local_llama = fields.Boolean('Use Local llama.cpp (CPU Fallback)', default=True)

    # ─── Remote Providers ─────────────────────────────────────────────────────
    use_gpu_marketplace = fields.Boolean('Use GPU Marketplace', default=False)
    use_external_api = fields.Boolean('Use External API (OpenAI/Anthropic)', default=False)

    # ─── GPU Marketplace Settings ─────────────────────────────────────────────
    marketplace_min_rating = fields.Float('Min GPU Rating', default=4.0)
    marketplace_max_price = fields.Float('Max Price per Hour ($)', default=5.0)
    marketplace_preferred_nodes = fields.Char('Preferred Nodes', help='Comma-separated node IDs')

    # ─── External API Settings ────────────────────────────────────────────────
    external_provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic'),
        ('custom', 'Custom'),
    ], string='External Provider', default='openai')
    external_api_key = fields.Char('API Key', groups='base.group_system')
    external_api_url = fields.Char('API URL')
    external_model = fields.Char('Model Name', help='e.g., gpt-4, claude-3-opus')

    # ─── Routing Conditions ──────────────────────────────────────────────────
    route_by_request_type = fields.Boolean('Route by Request Type', default=True)
    route_by_priority = fields.Boolean('Route by Priority', default=False)
    route_by_cost = fields.Boolean('Route by Cost', default=False)

    # ─── Cost Settings ────────────────────────────────────────────────────────
    local_cost_per_token = fields.Float('Local Cost per 1K Tokens ($)', default=0.001)
    remote_cost_per_token = fields.Float('Remote Cost per 1K Tokens ($)', default=0.002)

    # ─── Request Type Mapping ────────────────────────────────────────────────
    # Which request types go where
    inference_routing = fields.Selection([
        ('local', 'Local Only'),
        ('remote', 'Remote Only'),
        ('marketplace', 'GPU Marketplace'),
    ], string='Inference Routing', default='local')

    training_routing = fields.Selection([
        ('local', 'Local Only'),
        ('remote', 'Remote Only'),
        ('marketplace', 'GPU Marketplace'),
    ], string='Training Routing', default='local')

    fine_tuning_routing = fields.Selection([
        ('local', 'Local Only'),
        ('remote', 'Remote Only'),
        ('marketplace', 'GPU Marketplace'),
    ], string='Fine-Tuning Routing', default='local')

    embedding_routing = fields.Selection([
        ('local', 'Local Only'),
        ('remote', 'Remote Only'),
    ], string='Embedding Routing', default='local')

    # =========================================================================
    # 3. TARGET ROUTES – Where requests are sent (NEW LOGIC)
    # =========================================================================

    # ─── Primary Target ──────────────────────────────────────────────────────
    target_node = fields.Char('Target Node')
    target_url = fields.Char('Target URL')
    target_type = fields.Selection([
        ('dynamo', 'NVIDIA Dynamo'),
        ('llama_cpp', 'llama.cpp'),
        ('vllm', 'vLLM'),
        ('openai', 'OpenAI API'),
        ('anthropic', 'Anthropic API'),
        ('marketplace', 'GPU Marketplace'),
        ('custom', 'Custom'),
    ], string='Target Type', default='dynamo')

    # ─── Fallback Target ─────────────────────────────────────────────────────
    fallback_enabled = fields.Boolean('Fallback Enabled', default=True)
    fallback_target_url = fields.Char('Fallback URL')
    fallback_target_type = fields.Selection([
        ('dynamo', 'NVIDIA Dynamo'),
        ('llama_cpp', 'llama.cpp'),
        ('vllm', 'vLLM'),
        ('openai', 'OpenAI API'),
        ('anthropic', 'Anthropic API'),
        ('marketplace', 'GPU Marketplace'),
        ('custom', 'Custom'),
    ], string='Fallback Type', default='llama_cpp')

    # ─── Configuration ──────────────────────────────────────────────────────
    config = fields.Json('Configuration')

    # =========================================================================
    # 4. LOAD BALANCING (NEW LOGIC)
    # =========================================================================

    load_balancing_enabled = fields.Boolean('Load Balancing Enabled', default=True)
    load_balancing_strategy = fields.Selection([
        ('round_robin', 'Round Robin'),
        ('least_connections', 'Least Connections'),
        ('random', 'Random'),
        ('weighted', 'Weighted'),
        ('priority', 'Priority Based'),
    ], string='Load Balancing Strategy', default='round_robin')
    weight = fields.Integer('Weight', default=100)

    # =========================================================================
    # 5. HEALTH CHECK (NEW LOGIC)
    # =========================================================================

    health_check_enabled = fields.Boolean('Health Check Enabled', default=True)
    health_check_endpoint = fields.Char('Health Check Endpoint', default='/health')
    health_check_interval = fields.Integer('Health Check Interval (s)', default=30)
    health_check_timeout = fields.Integer('Health Check Timeout (s)', default=5)
    last_health_check = fields.Datetime('Last Health Check')
    health_status = fields.Selection([
        ('healthy', 'Healthy'),
        ('unhealthy', 'Unhealthy'),
        ('unknown', 'Unknown'),
    ], string='Health Status', default='unknown', compute='_compute_health_status', store=True)

    # =========================================================================
    # 6. GPU REQUIREMENTS
    # =========================================================================

    min_gpu_memory = fields.Integer('Min GPU Memory (GB)')
    min_compute_capability = fields.Char('Min Compute Capability')
    required_gpu_count = fields.Integer('Required GPU Count', default=1)

    # =========================================================================
    # 7. AUTHENTICATION
    # =========================================================================

    api_key = fields.Char('API Key', groups='base.group_system')

    # =========================================================================
    # 8. TIMESTAMPS
    # =========================================================================

    created_at = fields.Datetime('Created At', default=fields.Datetime.now)
    updated_at = fields.Datetime('Updated At')

    # =========================================================================
    # 9. COMPUTED FIELDS
    # =========================================================================

    @api.depends('last_health_check', 'health_check_enabled')
    def _compute_health_status(self):
        for record in self:
            if not record.health_check_enabled:
                record.health_status = 'unknown'
                continue
            if record.last_health_check:
                time_diff = fields.Datetime.now() - record.last_health_check
                if time_diff.total_seconds() > record.health_check_interval * 2:
                    record.health_status = 'unhealthy'
                else:
                    record.health_status = 'healthy'
            else:
                record.health_status = 'unknown'

    # =========================================================================
    # 10. ROUTE DECISION ENGINE – THE CORE LOGIC
    # =========================================================================

    @api.model
    def get_route_for_request(self, request_type='inference', request_data=None):
        """
        Main entry point for route decisions.
        Called by LangGraph agents (inference_tools.py) to determine where
        to send a request.

        Args:
            request_type: 'inference', 'training', 'fine_tuning', 'embedding'
            request_data: dict with additional context (priority, cost, etc.)

        Returns:
            dict: {
                'target_url': 'http://...',
                'target_type': 'dynamo' | 'llama_cpp' | 'openai' | 'marketplace',
                'api_key': '...',
                'route_id': id,
                'routing_mode': 'local' | 'remote' | 'marketplace',
                'fallback_url': 'http://...',  # optional
            }
        """
        # Get active routes for this request type
        routes = self.search([
            ('is_active', '=', True),
            ('route_type', '=', request_type),
        ])

        if not routes:
            _logger.warning(f'No active routes found for request type: {request_type}')
            return self._get_default_route()

        # Filter by priority if request has priority
        if request_data and request_data.get('priority'):
            priority = request_data.get('priority')
            routes = routes.filtered(lambda r: r.priority >= priority)

        # Get the best route based on routing mode
        route = routes[0]  # Default to highest priority

        # Apply routing decision
        decision = route._make_routing_decision(request_type, request_data)

        return decision

    def _make_routing_decision(self, request_type, request_data):
        """
        Make a routing decision based on the route's configuration.
        This is the core decision engine that combines old and new logic.
        """
        self.ensure_one()

        # Step 1: Determine the routing mode for this request type
        routing_mode = self._get_routing_mode_for_type(request_type)

        # Step 2: Check if local infrastructure is available
        local_available = self._is_local_available()

        # Step 3: Check if remote/marketplace is available
        remote_available = self._is_remote_available()

        # Step 4: Make the decision
        result = {
            'route_id': self.id,
            'routing_mode': routing_mode,
        }

        if routing_mode == 'local_only':
            result.update(self._get_local_target())

        elif routing_mode == 'remote_only':
            result.update(self._get_remote_target())

        elif routing_mode == 'hybrid':
            if local_available:
                result.update(self._get_local_target())
                result['fallback_url'] = self._get_remote_target().get('target_url')
            else:
                result.update(self._get_remote_target())

        elif routing_mode == 'hybrid_remote_first':
            if remote_available:
                result.update(self._get_remote_target())
                result['fallback_url'] = self._get_local_target().get('target_url')
            else:
                result.update(self._get_local_target())

        elif routing_mode == 'auto':
            # Let the AI agent decide based on context
            result.update(self._get_auto_target(request_type, request_data))

        else:
            # Default to local
            result.update(self._get_local_target())

        return result

    def _get_routing_mode_for_type(self, request_type):
        """Get the routing mode for a specific request type."""
        mapping = {
            'inference': self.inference_routing,
            'training': self.training_routing,
            'fine_tuning': self.fine_tuning_routing,
            'embedding': self.embedding_routing,
        }
        mode = mapping.get(request_type, 'local')

        # Convert to full routing mode
        if mode == 'local':
            return 'local_only'
        elif mode == 'remote':
            return 'remote_only'
        elif mode == 'marketplace':
            return 'remote_only'  # Marketplace is treated as remote
        return 'local_only'

    def _is_local_available(self):
        """Check if local infrastructure is available."""
        # Check if Dynamo is healthy
        if self.use_local_dynamo:
            dynamo_healthy = self._check_dynamo_health()
            if dynamo_healthy:
                return True

        # Check if llama.cpp is available as fallback
        if self.use_local_llama:
            llama_healthy = self._check_llama_health()
            if llama_healthy:
                return True

        return False

    def _is_remote_available(self):
        """Check if remote infrastructure is available."""
        if self.use_gpu_marketplace:
            return True
        if self.use_external_api and self.external_api_key:
            return True
        return False

    def _get_local_target(self):
        """Get the local target (Dynamo or llama.cpp)."""
        # First try Dynamo with load balancing
        if self.use_local_dynamo:
            dynamo_result = self.get_next_dynamo_target()
            if dynamo_result:
                return {
                    'target_url': dynamo_result['url'],
                    'target_type': 'dynamo',
                    'api_key': self.api_key or '',
                }

        # Fallback to llama.cpp
        if self.use_local_llama:
            return {
                'target_url': self._get_llama_url(),
                'target_type': 'llama_cpp',
                'api_key': '',
            }

        # Ultimate fallback
        return {
            'target_url': 'http://llama-cpp:8080/v1',
            'target_type': 'llama_cpp',
            'api_key': '',
        }

    def _get_remote_target(self):
        """Get the remote target (marketplace or external API)."""
        if self.use_gpu_marketplace:
            return self._get_marketplace_target()
        elif self.use_external_api:
            return self._get_external_api_target()
        else:
            # Fallback to local
            return self._get_local_target()

    def _get_marketplace_target(self):
        """Get a target from the GPU marketplace."""
        # Query the GPU marketplace for available nodes
        try:
            marketplace_nodes = self.env['nettrades_gpu.node'].search([
                ('status', '=', 'available'),
                ('is_active', '=', True),
            ])

            if marketplace_nodes:
                # Filter by rating and price
                if self.marketplace_min_rating:
                    marketplace_nodes = marketplace_nodes.filtered(
                        lambda n: n.rating >= self.marketplace_min_rating
                    )
                if self.marketplace_max_price:
                    marketplace_nodes = marketplace_nodes.filtered(
                        lambda n: n.price_per_hour <= self.marketplace_max_price
                    )

                if marketplace_nodes:
                    # Pick the best one (lowest price, highest rating)
                    node = marketplace_nodes.sorted(
                        key=lambda n: (n.price_per_hour, -n.rating)
                    )[0]
                    return {
                        'target_url': f'http://{node.ip_address}:{node.port}/v1',
                        'target_type': 'marketplace',
                        'api_key': node.api_key or '',
                        'node_id': node.id,
                        'node_name': node.name,
                    }
        except Exception as e:
            _logger.error(f'Error getting marketplace target: {e}')

        # Fallback to local
        return self._get_local_target()

    def _get_external_api_target(self):
        """Get an external API target (OpenAI, Anthropic, etc.)."""
        if self.external_provider == 'openai':
            return {
                'target_url': 'https://api.openai.com/v1',
                'target_type': 'openai',
                'api_key': self.external_api_key,
                'model': self.external_model or 'gpt-4',
            }
        elif self.external_provider == 'anthropic':
            return {
                'target_url': 'https://api.anthropic.com/v1',
                'target_type': 'anthropic',
                'api_key': self.external_api_key,
                'model': self.external_model or 'claude-3-opus-20240229',
            }
        elif self.external_provider == 'custom' and self.external_api_url:
            return {
                'target_url': self.external_api_url,
                'target_type': 'custom',
                'api_key': self.external_api_key,
                'model': self.external_model or '',
            }
        else:
            return self._get_local_target()

    def _get_auto_target(self, request_type, request_data):
        """
        AI-driven routing decision.
        This delegates to the LangGraph agent to decide.
        """
        # For auto mode, we return both options and let the agent decide
        # The agent will call back with the final decision
        local_target = self._get_local_target()
        remote_target = self._get_remote_target()

        return {
            'target_url': local_target['target_url'],
            'target_type': local_target['target_type'],
            'api_key': local_target.get('api_key', ''),
            'candidates': [
                local_target,
                remote_target,
            ],
            'decision_mode': 'auto',
        }

    # =========================================================================
    # 11. DYNAMO LOAD BALANCING (NEW LOGIC)
    # =========================================================================

    def get_next_dynamo_target(self):
        """
        Get the next Dynamo target based on load balancing strategy.
        Returns a dict with url and node info, or None if no healthy nodes.
        """
        # Get all active Dynamo routes
        dynamo_routes = self.search([
            ('is_active', '=', True),
            ('target_type', '=', 'dynamo'),
            ('health_status', '=', 'healthy'),
        ])

        if not dynamo_routes:
            return None

        # Apply load balancing strategy
        if self.load_balancing_strategy == 'round_robin':
            return self._round_robin_select(dynamo_routes)
        elif self.load_balancing_strategy == 'weighted':
            return self._weighted_select(dynamo_routes)
        elif self.load_balancing_strategy == 'random':
            return self._random_select(dynamo_routes)
        elif self.load_balancing_strategy == 'priority':
            return self._priority_select(dynamo_routes)
        else:
            return self._round_robin_select(dynamo_routes)

    def _round_robin_select(self, routes):
        """Round-robin selection."""
        # Track last used in context
        last_used = self.env.context.get('last_route_id')
        if last_used:
            for i, route in enumerate(routes):
                if route.id == last_used and i + 1 < len(routes):
                    return {
                        'url': routes[i + 1].target_url,
                        'route_id': routes[i + 1].id,
                        'node_name': routes[i + 1].target_node,
                    }
        return {
            'url': routes[0].target_url,
            'route_id': routes[0].id,
            'node_name': routes[0].target_node,
        }

    def _weighted_select(self, routes):
        """Weighted random selection."""
        total_weight = sum(r.weight for r in routes)
        target = random.randint(0, total_weight - 1)
        cumulative = 0
        for route in routes:
            cumulative += route.weight
            if target < cumulative:
                return {
                    'url': route.target_url,
                    'route_id': route.id,
                    'node_name': route.target_node,
                }
        return {
            'url': routes[0].target_url,
            'route_id': routes[0].id,
            'node_name': routes[0].target_node,
        }

    def _random_select(self, routes):
        """Random selection."""
        route = random.choice(routes)
        return {
            'url': route.target_url,
            'route_id': route.id,
            'node_name': route.target_node,
        }

    def _priority_select(self, routes):
        """Priority-based selection (highest priority first)."""
        route = routes.sorted(key=lambda r: -r.priority)[0]
        return {
            'url': route.target_url,
            'route_id': route.id,
            'node_name': route.target_node,
        }

    # =========================================================================
    # 12. DYNAMO NODE REGISTRATION (NEW LOGIC)
    # =========================================================================

    @api.model
    def register_dynamo_node(self, node_name, node_url, capabilities=None):
        """
        Register a new Dynamo node dynamically.
        Called by the launcher when a new node is discovered.
        """
        capabilities = capabilities or {}

        # Check if route already exists
        existing = self.search([('name', '=', f'dynamo-{node_name}')])
        if existing:
            existing.write({
                'target_url': node_url,
                'config': capabilities,
                'is_active': True,
                'updated_at': fields.Datetime.now(),
            })
            _logger.info(f'Updated Dynamo node: {node_name}')
            return existing

        # Create new route
        route = self.create({
            'name': f'dynamo-{node_name}',
            'route_type': 'inference',
            'target_node': node_name,
            'target_url': node_url,
            'target_type': 'dynamo',
            'config': capabilities,
            'is_active': True,
            'load_balancing_enabled': True,
            'load_balancing_strategy': 'round_robin',
            'min_gpu_memory': capabilities.get('gpu_memory', 0),
            'min_compute_capability': capabilities.get('compute_capability', ''),
            'required_gpu_count': capabilities.get('gpu_count', 1),
            'health_check_enabled': True,
            'routing_mode': 'local_only',
            'inference_routing': 'local',
            'training_routing': 'local',
            'fine_tuning_routing': 'local',
            'embedding_routing': 'local',
        })
        _logger.info(f'Registered Dynamo node: {node_name}')
        return route

    def unregister_dynamo_node(self, node_name):
        """Unregister a Dynamo node."""
        routes = self.search([('name', '=', f'dynamo-{node_name}')])
        if routes:
            routes.write({'is_active': False})
            _logger.info(f'Unregistered Dynamo node: {node_name}')
        return True

    # =========================================================================
    # 13. HEALTH CHECK (NEW LOGIC)
    # =========================================================================

    @api.model
    def check_all_health(self):
        """Check health of all active routes."""
        routes = self.search([('is_active', '=', True), ('health_check_enabled', '=', True)])
        for route in routes:
            route.check_health()
        return True

    def check_health(self):
        """Check health of this route."""
        self.ensure_one()
        if not self.health_check_enabled or not self.is_active:
            return

        try:
            url = f"{self.target_url}{self.health_check_endpoint}"
            response = requests.get(
                url,
                timeout=self.health_check_timeout,
                headers={'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
            )
            if response.status_code == 200:
                self.health_status = 'healthy'
            else:
                self.health_status = 'unhealthy'
        except Exception as e:
            _logger.warning(f'Health check failed for route {self.name}: {e}')
            self.health_status = 'unhealthy'

        self.last_health_check = fields.Datetime.now()
        return self.health_status == 'healthy'

    # =========================================================================
    # 14. HELPER METHODS
    # =========================================================================

    def _check_dynamo_health(self):
        """Check if Dynamo is healthy."""
        try:
            response = requests.get('http://dynamo:8000/health', timeout=5)
            return response.status_code == 200
        except:
            return False

    def _check_llama_health(self):
        """Check if llama.cpp is healthy."""
        try:
            response = requests.get('http://llama-cpp:8080/health', timeout=5)
            return response.status_code == 200
        except:
            return False

    def _get_llama_url(self):
        """Get the llama.cpp URL."""
        return 'http://llama-cpp:8080/v1'

    def _get_default_route(self):
        """Get a default route when no routes are configured."""
        return {
            'target_url': 'http://llama-cpp:8080/v1',
            'target_type': 'llama_cpp',
            'api_key': '',
            'route_id': None,
            'routing_mode': 'local_only',
        }

    # =========================================================================
    # 15. CONSTRAINTS
    # =========================================================================

    @api.constrains('target_url')
    def _check_target_url(self):
        for record in self:
            if record.target_url and not record.target_url.startswith(('http://', 'https://')):
                raise ValidationError(_('Target URL must start with http:// or https://'))

    @api.constrains('external_api_key', 'use_external_api')
    def _check_external_api_key(self):
        for record in self:
            if record.use_external_api and not record.external_api_key:
                raise ValidationError(_('API key is required when using external API'))