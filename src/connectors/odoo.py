# =============================================================================
# NETTRADES Universal Enterprise Proxy Framework - Odoo Connector
# =============================================================================
# FILE: src/core/proxy_framework/connectors/odoo.py
# PURPOSE: Implements the AbstractEnterpriseConnector interface for Odoo.
#          This connector uses Odoo's JSON-RPC API to interact with the
#          Odoo backend.
#
# CRITICAL FIX (2026-08):
#   - The connector now uses a FIXED internal Odoo user (admin) for ALL
#     data operations. This ensures that LangGraph agents and other services
#     always have a consistent, authenticated session.
#   - The authenticate() method is used ONLY for the login endpoint to
#     validate user credentials. It does NOT change the connector's state.
#   - This preserves the original odoo_proxy behaviour and prevents
#     authentication failures when multiple users are logged in.
#
# FEATURES:
#   - Full CRUD operations on any Odoo model
#   - Authentication via Odoo's login method (separate from internal state)
#   - Session management
#   - AI-specific operations (jobs, GPU nodes, models)
#   - Transaction support via Odoo's savepoints
# =============================================================================

import json
import logging
import requests
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from ..base import AbstractEnterpriseConnector

logger = logging.getLogger(__name__)


class OdooConnector(AbstractEnterpriseConnector):
    """
    Connector for Odoo backend using JSON-RPC.
    
    This connector communicates with Odoo via its JSON-RPC API,
    providing a clean interface for all operations.
    
    IMPORTANT: This connector uses a FIXED internal Odoo user for all
    data operations. The authenticate() method is only for validating
    user credentials and does not change the connector's state.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Odoo connector with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - 'base_url': The Odoo base URL (default: http://odoo:8069)
                - 'db': The database name (default: odoo)
                - 'username': Internal Odoo username (default: admin)
                - 'password': Internal Odoo password (default: admin)
        """
        self.base_url = config.get('base_url', 'http://odoo:8069')
        self.db = config.get('db', 'odoo')
        self.internal_username = config.get('username', 'admin')
        self.internal_password = config.get('password', 'admin')
        self.uid = None
        self._authenticated = False
        self._models_cache = {}
        self._transaction_id = None
        
        logger.info(f"OdooConnector initialized with URL: {self.base_url}")
        
        # Authenticate with the internal user on startup
        self._authenticate_internal()
    
    def _rpc(self, service: str, method: str, *args) -> Any:
        """
        Make a JSON-RPC call to Odoo.
        
        Args:
            service: The service name ('common', 'object')
            method: The method name ('login', 'execute_kw', etc.)
            *args: Arguments for the method
            
        Returns:
            The result of the RPC call
        """
        url = f"{self.base_url}/jsonrpc"
        payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'service': service,
                'method': method,
                'args': args,
            },
            'id': 1,
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get('error'):
                error = result['error']
                logger.error(f"Odoo RPC error: {error}")
                raise Exception(f"Odoo error: {error.get('message', 'Unknown error')}")
            
            return result.get('result')
        except requests.exceptions.RequestException as e:
            logger.error(f"Odoo RPC request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Odoo: {e}")
            raise
    
    def _authenticate_internal(self) -> None:
        """
        Authenticate with the internal Odoo user.
        
        This is called once on startup and whenever the session expires.
        """
        try:
            uid = self._rpc('common', 'login', self.db,
                            self.internal_username, self.internal_password)
            if uid:
                self.uid = uid
                self._authenticated = True
                logger.info(f"Internal Odoo user authenticated (UID: {uid})")
            else:
                raise Exception("Internal Odoo authentication failed")
        except Exception as e:
            logger.error(f"Internal Odoo authentication error: {e}")
            raise
    
    def _ensure_authenticated(self) -> None:
        """
        Ensure that the internal authentication is active.
        
        If the session has expired, re-authenticate.
        """
        if not self._authenticated or not self.uid:
            self._authenticate_internal()
    
    def _execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """
        Execute a method on an Odoo model using the internal user.
        
        This is the primary method used for all data operations.
        """
        self._ensure_authenticated()
        return self._rpc('object', 'execute_kw', self.db, self.uid,
                         self.internal_password, model, method, list(args), kwargs)
    
    # =========================================================================
    # Authentication (for user login - does NOT change internal state)
    # =========================================================================
    
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Validate a user's credentials against Odoo.
        
        This method is used ONLY for the /api/v1/auth/login endpoint.
        It does NOT change the connector's internal authentication state.
        
        Args:
            username: The username
            password: The password
            
        Returns:
            Dict containing authentication result
        """
        try:
            uid = self._rpc('common', 'login', self.db, username, password)
            if uid:
                logger.info(f"User '{username}' validated successfully (UID: {uid})")
                return {
                    'success': True,
                    'user_id': uid,
                    'username': username,
                    'db': self.db,
                }
            else:
                logger.warning(f"User validation failed for '{username}'")
                return {
                    'success': False,
                    'error': 'Invalid credentials',
                }
        except Exception as e:
            logger.error(f"User validation error: {e}")
            return {
                'success': False,
                'error': str(e),
            }
    
    def validate_session(self, token: str) -> Dict[str, Any]:
        """
        Validate a session token.
        
        For Odoo, we check if the token corresponds to a valid user.
        """
        # In a real implementation, you'd validate against Odoo's session store
        # For now, we just check if the internal user is authenticated
        return {
            'valid': self._authenticated,
            'user_id': self.uid if self._authenticated else None,
        }
    
    def logout(self, token: str) -> bool:
        """
        Logout and invalidate the session.
        
        For the internal Odoo connector, we only re-authenticate.
        """
        self._authenticated = False
        self._authenticate_internal()
        return True
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def create(self, model: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new record in Odoo.
        
        Args:
            model: The model name (e.g., 'nettrades.gpu.node')
            data: The field values
            
        Returns:
            Dict containing the created record
        """
        record_id = self._execute(model, 'create', data)
        return self.read(model, record_id)
    
    def read(self, model: str, record_id: Any,
             fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Read a single record from Odoo.
        """
        result = self._execute(model, 'read', [record_id], fields or [])
        return result[0] if result else {}
    
    def search(self, model: str, domain: List[Any],
               fields: Optional[List[str]] = None,
               limit: Optional[int] = None,
               offset: Optional[int] = None,
               order: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for records in Odoo.
        """
        kwargs = {}
        if fields:
            kwargs['fields'] = fields
        if limit:
            kwargs['limit'] = limit
        if offset:
            kwargs['offset'] = offset
        if order:
            kwargs['order'] = order
        
        return self._execute(model, 'search_read', domain, kwargs)
    
    def update(self, model: str, record_id: Any,
               data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a record in Odoo.
        """
        self._execute(model, 'write', [record_id], data)
        return self.read(model, record_id)
    
    def delete(self, model: str, record_id: Any) -> bool:
        """
        Delete a record from Odoo.
        """
        result = self._execute(model, 'unlink', [record_id])
        return bool(result)
    
    # =========================================================================
    # AI-Specific Operations
    # =========================================================================
    
    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an inference or training job.
        """
        return self.create('nettrades.job', job_data)
    
    def get_job(self, job_id: Any) -> Dict[str, Any]:
        """
        Get job details.
        """
        return self.read('nettrades.job', job_id)
    
    def update_job_status(self, job_id: Any, status: str,
                          result: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Update job status.
        """
        data = {'status': status}
        if result:
            data['result'] = json.dumps(result)
        return self.update('nettrades.job', job_id, data)
    
    def list_jobs(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List jobs with optional filters.
        """
        domain = []
        if filters:
            for key, value in filters.items():
                domain.append((key, '=', value))
        return self.search('nettrades.job', domain)
    
    # =========================================================================
    # GPU Node Management
    # =========================================================================
    
    def get_gpu_nodes(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Get GPU nodes.
        """
        domain = []
        if filters:
            for key, value in filters.items():
                domain.append((key, '=', value))
        return self.search('nettrades.gpu.node', domain)
    
    def register_gpu_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a new GPU node.
        """
        return self.create('nettrades.gpu.node', node_data)
    
    def update_gpu_node(self, node_id: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a GPU node.
        """
        return self.update('nettrades.gpu.node', node_id, data)
    
    def heartbeat(self, node_id: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a heartbeat from a GPU node.
        """
        data = {
            'last_heartbeat': status.get('timestamp', datetime.now().isoformat()),
            'gpu_utilization': status.get('gpu_utilization', 0),
            'memory_utilization': status.get('memory_utilization', 0),
            'temperature': status.get('temperature', 0),
            'is_available': status.get('is_available', True),
        }
        return self.update('nettrades.gpu.node', node_id, data)
    
    # =========================================================================
    # Model Management
    # =========================================================================
    
    def list_models(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List AI models.
        """
        domain = []
        if filters:
            for key, value in filters.items():
                domain.append((key, '=', value))
        return self.search('nettrades.model', domain)
    
    def download_model(self, model_name: str, model_type: str) -> Dict[str, Any]:
        """
        Download an AI model.
        """
        job_data = {
            'type': 'download_model',
            'model_name': model_name,
            'model_type': model_type,
            'status': 'pending',
        }
        return self.create_job(job_data)
    
    def delete_model(self, model_id: Any) -> bool:
        """
        Delete an AI model.
        """
        return self.delete('nettrades.model', model_id)
    
    # =========================================================================
    # User & Tenant Management
    # =========================================================================
    
    def get_user(self, user_id: Any) -> Dict[str, Any]:
        """
        Get user details.
        """
        return self.read('res.users', user_id)
    
    def get_current_user(self) -> Dict[str, Any]:
        """
        Get the currently authenticated user.
        
        Note: This returns the INTERNAL Odoo user, not the logged-in user.
        For per-user information, use the authenticated session from the request.
        """
        if not self.uid:
            raise Exception("Not authenticated")
        return self.get_user(self.uid)
    
    def list_users(self, company_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        List users.
        """
        domain = []
        if company_id:
            domain.append(('company_id', '=', company_id))
        return self.search('res.users', domain,
                           fields=['id', 'name', 'login', 'email', 'company_id'])
    
    def get_company(self, company_id: Any) -> Dict[str, Any]:
        """
        Get company details.
        """
        return self.read('res.company', company_id)
    
    # =========================================================================
    # Health
    # =========================================================================
    
    def health(self) -> Dict[str, Any]:
        """
        Check the health of the Odoo connection.
        """
        try:
            self._ensure_authenticated()
            version = self._rpc('common', 'version')
            return {
                'status': 'ok',
                'backend': 'odoo',
                'version': version.get('server_version', 'unknown'),
                'database': self.db,
                'authenticated': self._authenticated,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'error',
                'backend': 'odoo',
                'error': str(e),
            }
    
    # =========================================================================
    # Transaction Support
    # =========================================================================
    
    def begin_transaction(self) -> str:
        """
        Begin a transaction using Odoo's savepoint.
        """
        import uuid
        self._transaction_id = str(uuid.uuid4())
        self._execute('ir.model', 'execute', 'BEGIN')
        logger.info(f"Transaction started: {self._transaction_id}")
        return self._transaction_id
    
    def commit_transaction(self, transaction_id: str) -> bool:
        """
        Commit a transaction.
        """
        if transaction_id != self._transaction_id:
            raise ValueError("Invalid transaction ID")
        self._execute('ir.model', 'execute', 'COMMIT')
        self._transaction_id = None
        logger.info("Transaction committed")
        return True
    
    def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Rollback a transaction.
        """
        if transaction_id != self._transaction_id:
            raise ValueError("Invalid transaction ID")
        self._execute('ir.model', 'execute', 'ROLLBACK')
        self._transaction_id = None
        logger.info("Transaction rolled back")
        return True