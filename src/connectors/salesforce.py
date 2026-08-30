# =============================================================================
# NETTRADES Universal Enterprise Proxy Framework - Salesforce Connector
# =============================================================================
# FILE: src/core/proxy_framework/connectors/salesforce.py
# PURPOSE: Implements the AbstractEnterpriseConnector interface for Salesforce.
#          This connector uses Salesforce's REST API to interact with the
#          Salesforce backend.
#
# FEATURES:
#   - OAuth 2.0 authentication
#   - Full CRUD operations on Salesforce objects
#   - SOQL query support
#   - AI-specific operations mapped to custom Salesforce objects
# =============================================================================

import logging
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime
from ..base import AbstractEnterpriseConnector

logger = logging.getLogger(__name__)


class SalesforceConnector(AbstractEnterpriseConnector):
    """
    Connector for Salesforce backend using REST API.
    
    This connector communicates with Salesforce via its REST API,
    providing a clean interface for all operations.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Salesforce connector with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - 'instance_url': The Salesforce instance URL
                - 'client_id': OAuth client ID
                - 'client_secret': OAuth client secret
                - 'username': Salesforce username
                - 'password': Salesforce password (and security token)
        """
        self.instance_url = config.get('instance_url')
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        self.username = config.get('username')
        self.password = config.get('password')
        self.access_token = None
        self.instance_url = None
        self._authenticated = False
        self.session = requests.Session()
        
        logger.info(f"SalesforceConnector initialized")
    
    def _request(self, method: str, path: str,
                 data: Optional[Dict] = None,
                 params: Optional[Dict] = None) -> Dict:
        """
        Make an authenticated request to Salesforce REST API.
        """
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        url = f"{self.instance_url}{path}"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        
        try:
            response = self.session.request(method, url, json=data,
                                            params=params, headers=headers,
                                            timeout=30)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.RequestException as e:
            logger.error(f"Salesforce request failed: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise
    
    # =========================================================================
    # Authentication
    # =========================================================================
    
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate with Salesforce using OAuth 2.0 password flow.
        """
        self.username = username or self.username
        self.password = password or self.password
        
        auth_url = f"{self.instance_url}/services/oauth2/token"
        data = {
            'grant_type': 'password',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'username': self.username,
            'password': self.password,
        }
        
        try:
            response = requests.post(auth_url, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            self.access_token = result.get('access_token')
            self.instance_url = result.get('instance_url')
            self._authenticated = True
            
            logger.info(f"Salesforce authentication successful")
            return {
                'success': True,
                'access_token': self.access_token,
                'instance_url': self.instance_url,
                'user_id': result.get('id'),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Salesforce authentication failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }
    
    def validate_session(self, token: str) -> Dict[str, Any]:
        """
        Validate a Salesforce session token.
        """
        # In production, validate against Salesforce's /services/oauth2/userinfo
        return {
            'valid': self._authenticated,
            'user_id': None,
        }
    
    def logout(self, token: str) -> bool:
        """
        Logout and invalidate the session.
        """
        self._authenticated = False
        self.access_token = None
        logger.info("Salesforce logout")
        return True
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def create(self, model: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a record in Salesforce.
        """
        result = self._request('POST', f'/services/data/v58.0/sobjects/{model}/', data)
        return {'id': result.get('id'), **data}
    
    def read(self, model: str, record_id: Any,
             fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Read a record from Salesforce.
        """
        path = f'/services/data/v58.0/sobjects/{model}/{record_id}'
        if fields:
            path += '?' + '&'.join([f'fields={f}' for f in fields])
        return self._request('GET', path)
    
    def search(self, model: str, domain: List[Any],
               fields: Optional[List[str]] = None,
               limit: Optional[int] = None,
               offset: Optional[int] = None,
               order: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for records using SOQL.
        """
        # Convert domain to SOQL WHERE clause (simplified)
        # This is a basic conversion - production code would handle more complex domains
        where_clauses = []
        for condition in domain:
            if len(condition) == 3:
                field, operator, value = condition
                if operator == '=':
                    where_clauses.append(f"{field} = '{value}'")
                elif operator == '!=':
                    where_clauses.append(f"{field} != '{value}'")
                elif operator == 'like':
                    where_clauses.append(f"{field} LIKE '%{value}%'")
                elif operator == 'in':
                    if isinstance(value, list):
                        values = "', '".join(value)
                        where_clauses.append(f"{field} IN ('{values}')")
        
        where = ' WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''
        select_fields = ', '.join(fields or ['Id', 'Name'])
        soql = f"SELECT {select_fields} FROM {model}{where}"
        
        if order:
            soql += f" ORDER BY {order}"
        if limit:
            soql += f" LIMIT {limit}"
        if offset:
            soql += f" OFFSET {offset}"
        
        path = f'/services/data/v58.0/query?q={soql}'
        result = self._request('GET', path)
        return result.get('records', [])
    
    def update(self, model: str, record_id: Any,
               data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a record in Salesforce.
        """
        self._request('PATCH', f'/services/data/v58.0/sobjects/{model}/{record_id}', data)
        return self.read(model, record_id)
    
    def delete(self, model: str, record_id: Any) -> bool:
        """
        Delete a record from Salesforce.
        """
        self._request('DELETE', f'/services/data/v58.0/sobjects/{model}/{record_id}')
        return True
    
    # =========================================================================
    # AI-Specific Operations
    # =========================================================================
    
    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a job in Salesforce (mapped to AI_Job__c)."""
        # Map fields to Salesforce custom object
        sf_data = {
            'Name': job_data.get('name', 'AI Job'),
            'Type__c': job_data.get('type', 'inference'),
            'Model__c': job_data.get('model', ''),
            'Status__c': 'Pending',
            'Prompt__c': job_data.get('prompt', ''),
        }
        if job_data.get('parameters'):
            sf_data['Parameters__c'] = str(job_data.get('parameters'))
        return self.create('AI_Job__c', sf_data)
    
    def get_job(self, job_id: Any) -> Dict[str, Any]:
        """Get a job from Salesforce."""
        return self.read('AI_Job__c', job_id)
    
    def update_job_status(self, job_id: Any, status: str,
                          result: Optional[Dict] = None) -> Dict[str, Any]:
        """Update job status in Salesforce."""
        data = {'Status__c': status}
        if result:
            data['Result__c'] = str(result)
        return self.update('AI_Job__c', job_id, data)
    
    def list_jobs(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """List jobs from Salesforce."""
        domain = []
        if filters:
            for key, value in filters.items():
                # Map filter keys to Salesforce field names
                sf_key = f"{key}__c" if not key.endswith('__c') else key
                domain.append((sf_key, '=', value))
        return self.search('AI_Job__c', domain)
    
    # =========================================================================
    # GPU Node Management
    # =========================================================================
    
    def get_gpu_nodes(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Get GPU nodes (mapped to GPU_Node__c)."""
        domain = []
        if filters:
            for key, value in filters.items():
                domain.append((key, '=', value))
        return self.search('GPU_Node__c', domain)
    
    def register_gpu_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register a GPU node in Salesforce."""
        sf_data = {
            'Name': node_data.get('name', 'GPU Node'),
            'GPU_Model__c': node_data.get('gpu_model', ''),
            'VRAM_GB__c': node_data.get('vram_gb', 0),
            'Price_Per_Hour__c': node_data.get('price_per_hour', 0),
            'Status__c': 'Available',
            'Owner__c': node_data.get('owner_id', ''),
        }
        return self.create('GPU_Node__c', sf_data)
    
    def update_gpu_node(self, node_id: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a GPU node in Salesforce."""
        sf_data = {}
        if 'status' in data:
            sf_data['Status__c'] = data['status']
        if 'name' in data:
            sf_data['Name'] = data['name']
        if 'price_per_hour' in data:
            sf_data['Price_Per_Hour__c'] = data['price_per_hour']
        return self.update('GPU_Node__c', node_id, sf_data)
    
    def heartbeat(self, node_id: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        """Send a heartbeat to Salesforce."""
        sf_data = {
            'Last_Heartbeat__c': status.get('timestamp', datetime.now().isoformat()),
            'GPU_Utilization__c': status.get('gpu_utilization', 0),
            'Memory_Utilization__c': status.get('memory_utilization', 0),
            'Temperature__c': status.get('temperature', 0),
            'Is_Available__c': status.get('is_available', True),
        }
        return self.update('GPU_Node__c', node_id, sf_data)
    
    # =========================================================================
    # Model Management
    # =========================================================================
    
    def list_models(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """List models (mapped to AI_Model__c)."""
        domain = []
        if filters:
            for key, value in filters.items():
                domain.append((key, '=', value))
        return self.search('AI_Model__c', domain)
    
    def download_model(self, model_name: str, model_type: str) -> Dict[str, Any]:
        """Download a model (creates a download job)."""
        job_data = {
            'name': f"Download {model_name}",
            'type': 'download_model',
            'model': model_name,
            'parameters': {'model_type': model_type},
        }
        return self.create_job(job_data)
    
    def delete_model(self, model_id: Any) -> bool:
        """Delete a model from Salesforce."""
        return self.delete('AI_Model__c', model_id)
    
    # =========================================================================
    # User & Tenant Management
    # =========================================================================
    
    def get_user(self, user_id: Any) -> Dict[str, Any]:
        """Get a user from Salesforce."""
        return self.read('User', user_id)
    
    def get_current_user(self) -> Dict[str, Any]:
        """Get the currently authenticated user."""
        if not self.access_token:
            raise Exception("Not authenticated")
        # Salesforce doesn't have a direct "get current user" endpoint
        # We use the userinfo endpoint
        result = self._request('GET', '/services/oauth2/userinfo')
        return result
    
    def list_users(self, company_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """List users from Salesforce."""
        domain = []
        if company_id:
            domain.append(('AccountId', '=', company_id))
        return self.search('User', domain)
    
    def get_company(self, company_id: Any) -> Dict[str, Any]:
        """Get a company/account from Salesforce."""
        return self.read('Account', company_id)
    
    # =========================================================================
    # Health
    # =========================================================================
    
    def health(self) -> Dict[str, Any]:
        """Check the health of the Salesforce connection."""
        if not self.access_token:
            return {
                'status': 'error',
                'backend': 'salesforce',
                'error': 'Not authenticated',
            }
        
        try:
            # Try to get the API version
            result = self._request('GET', '/services/data/v58.0/')
            return {
                'status': 'ok',
                'backend': 'salesforce',
                'version': '58.0',
                'authenticated': self._authenticated,
            }
        except Exception as e:
            logger.error(f"Salesforce health check failed: {e}")
            return {
                'status': 'error',
                'backend': 'salesforce',
                'error': str(e),
            }