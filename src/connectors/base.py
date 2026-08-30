# =============================================================================
# NETTRADES Universal Enterprise Proxy Framework - Base Interface
# =============================================================================
# FILE: src/core/proxy_framework/base.py
# PURPOSE: Defines the abstract interface that all enterprise connectors must
#          implement. This enables the platform to work with Odoo, Salesforce,
#          SAP, Oracle, and any other enterprise system.
#
# USAGE:
#   from proxy_framework.base import AbstractConnector
#
#   class MyConnector(AbstractConnector):
#       def authenticate(self, username, password):
#           # Implement authentication for your backend
#           pass
#
# DESIGN PRINCIPLES:
#   - Interface-Driven Design: All connectors implement the same methods.
#   - Backend Agnostic: The core engine and UI don't know which backend is used.
#   - Future-Proof: New connectors can be added without changing existing code.
#   - Transaction Safety: Each connector handles its own transaction semantics.
# =============================================================================

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from datetime import datetime


class AbstractConnector(ABC):
    """
    Abstract base class for all enterprise system connectors.
    
    All connectors must implement these methods. The core engine and
    Electron Launcher interact only through this interface.
    """
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    @abstractmethod
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user against the enterprise backend.
        
        Args:
            username: The user's username or email
            password: The user's password
            
        Returns:
            Dict containing authentication result with at least:
                - 'success': bool
                - 'user_id': unique identifier for the user
                - 'session_token': token for subsequent requests (if applicable)
                - 'username': the username
                
        Raises:
            AuthenticationError: If credentials are invalid
            ConnectionError: If the backend is unreachable
        """
        pass
    
    @abstractmethod
    def validate_session(self, token: str) -> Dict[str, Any]:
        """
        Validate an existing session token.
        
        Args:
            token: The session token to validate
            
        Returns:
            Dict containing:
                - 'valid': bool
                - 'user_id': the user's ID (if valid)
                - 'expires_at': when the session expires (if applicable)
        """
        pass
    
    @abstractmethod
    def logout(self, token: str) -> bool:
        """
        Invalidate a session token.
        
        Args:
            token: The session token to invalidate
            
        Returns:
            bool: True if the session was invalidated successfully
        """
        pass
    
    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================
    
    @abstractmethod
    def create(self, model: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new record in the enterprise system.
        
        Args:
            model: The model/object type (e.g., 'nettrades.gpu.node', 'Account')
            data: The field values for the new record
            
        Returns:
            Dict containing the created record with at least an 'id' field
        """
        pass
    
    @abstractmethod
    def read(self, model: str, record_id: Any, 
             fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Read a single record from the enterprise system.
        
        Args:
            model: The model/object type
            record_id: The unique identifier of the record
            fields: Optional list of specific fields to return
            
        Returns:
            Dict containing the record data
        """
        pass
    
    @abstractmethod
    def search(self, model: str, domain: List[Any],
               fields: Optional[List[str]] = None,
               limit: Optional[int] = None,
               offset: Optional[int] = None,
               order: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for records matching the given domain.
        
        Args:
            model: The model/object type
            domain: List of search criteria (backend-specific format)
            fields: Optional list of fields to return
            limit: Maximum number of records to return
            offset: Number of records to skip (for pagination)
            order: Sort order (backend-specific)
            
        Returns:
            List of records matching the search criteria
        """
        pass
    
    @abstractmethod
    def update(self, model: str, record_id: Any,
               data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing record.
        
        Args:
            model: The model/object type
            record_id: The unique identifier of the record
            data: The field values to update
            
        Returns:
            Dict containing the updated record
        """
        pass
    
    @abstractmethod
    def delete(self, model: str, record_id: Any) -> bool:
        """
        Delete a record from the enterprise system.
        
        Args:
            model: The model/object type
            record_id: The unique identifier of the record
            
        Returns:
            bool: True if the record was deleted successfully
        """
        pass
    
    # =========================================================================
    # AI-SPECIFIC OPERATIONS
    # =========================================================================
    
    @abstractmethod
    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an inference or training job.
        
        Args:
            job_data: Job configuration including:
                - 'type': 'inference' | 'training'
                - 'model': The model to use
                - 'prompt' or 'dataset': The input data
                - 'parameters': Additional parameters (temperature, etc.)
                
        Returns:
            Dict containing the created job with at least an 'id' field
        """
        pass
    
    @abstractmethod
    def get_job(self, job_id: Any) -> Dict[str, Any]:
        """
        Get the status and details of a job.
        
        Args:
            job_id: The unique identifier of the job
            
        Returns:
            Dict containing job details including status, result, etc.
        """
        pass
    
    @abstractmethod
    def update_job_status(self, job_id: Any, status: str,
                          result: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Update the status of a job.
        
        Args:
            job_id: The unique identifier of the job
            status: The new status ('pending', 'running', 'completed', 'failed')
            result: Optional result data (for completed jobs)
            
        Returns:
            Dict containing the updated job
        """
        pass
    
    @abstractmethod
    def list_jobs(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List jobs, optionally filtered.
        
        Args:
            filters: Optional filters (status, model, user, etc.)
            
        Returns:
            List of jobs matching the filters
        """
        pass
    
    # =========================================================================
    # GPU NODE MANAGEMENT
    # =========================================================================
    
    @abstractmethod
    def get_gpu_nodes(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Get available GPU nodes.
        
        Args:
            filters: Optional filters (status, model, owner, etc.)
            
        Returns:
            List of GPU nodes
        """
        pass
    
    @abstractmethod
    def register_gpu_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a new GPU node.
        
        Args:
            node_data: Node configuration including:
                - 'name': The node name
                - 'gpu_model': The GPU model
                - 'vram_gb': VRAM in GB
                - 'price_per_hour': Price for using this node
                
        Returns:
            Dict containing the registered node
        """
        pass
    
    @abstractmethod
    def update_gpu_node(self, node_id: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a GPU node's information.
        
        Args:
            node_id: The unique identifier of the node
            data: The fields to update
            
        Returns:
            Dict containing the updated node
        """
        pass
    
    @abstractmethod
    def heartbeat(self, node_id: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a heartbeat from a GPU node.
        
        Args:
            node_id: The unique identifier of the node
            status: Status information including:
                - 'timestamp': Current time
                - 'gpu_utilization': GPU usage percentage
                - 'memory_utilization': Memory usage percentage
                - 'temperature': GPU temperature in Celsius
                - 'is_available': Whether the node is available for jobs
                
        Returns:
            Dict containing the updated node status
        """
        pass
    
    # =========================================================================
    # MODEL MANAGEMENT
    # =========================================================================
    
    @abstractmethod
    def list_models(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List available AI models.
        
        Args:
            filters: Optional filters (type, status, etc.)
            
        Returns:
            List of models
        """
        pass
    
    @abstractmethod
    def download_model(self, model_name: str, model_type: str) -> Dict[str, Any]:
        """
        Download an AI model.
        
        Args:
            model_name: The name of the model to download
            model_type: The type of model ('hf' for Hugging Face, 'gguf' for llama.cpp)
            
        Returns:
            Dict containing the download status
        """
        pass
    
    @abstractmethod
    def delete_model(self, model_id: Any) -> bool:
        """
        Delete an AI model.
        
        Args:
            model_id: The unique identifier of the model
            
        Returns:
            bool: True if the model was deleted successfully
        """
        pass
    
    # =========================================================================
    # USER & TENANT MANAGEMENT
    # =========================================================================
    
    @abstractmethod
    def get_user(self, user_id: Any) -> Dict[str, Any]:
        """
        Get user details.
        
        Args:
            user_id: The unique identifier of the user
            
        Returns:
            Dict containing user details
        """
        pass
    
    @abstractmethod
    def get_current_user(self) -> Dict[str, Any]:
        """
        Get the currently authenticated user.
        
        Returns:
            Dict containing the current user's details
        """
        pass
    
    @abstractmethod
    def list_users(self, company_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        List users, optionally filtered by company.
        
        Args:
            company_id: Optional company/tenant filter
            
        Returns:
            List of users
        """
        pass
    
    @abstractmethod
    def get_company(self, company_id: Any) -> Dict[str, Any]:
        """
        Get company/tenant details.
        
        Args:
            company_id: The unique identifier of the company
            
        Returns:
            Dict containing company details
        """
        pass
    
    # =========================================================================
    # HEALTH & STATUS
    # =========================================================================
    
    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """
        Check the health of the backend connection.
        
        Returns:
            Dict containing:
                - 'status': 'ok' or 'error'
                - 'backend': The backend name
                - 'version': The backend version (if available)
        """
        pass
    
    # =========================================================================
    # TRANSACTION SUPPORT (Optional, for backends that support it)
    # =========================================================================
    
    def begin_transaction(self) -> str:
        """
        Begin a transaction. Returns a transaction ID.
        (Optional - not all backends support transactions.)
        """
        raise NotImplementedError("Transactions not supported by this connector")
    
    def commit_transaction(self, transaction_id: str) -> bool:
        """
        Commit a transaction.
        (Optional - not all backends support transactions.)
        """
        raise NotImplementedError("Transactions not supported by this connector")
    
    def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Rollback a transaction.
        (Optional - not all backends support transactions.)
        """
        raise NotImplementedError("Transactions not supported by this connector")