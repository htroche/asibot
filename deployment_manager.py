import os
import uuid
import importlib.util
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

from analytics_registry import AnalyticsEndpoint

class DeploymentManager:
    """
    Manages the deployment of generated analytics code.
    """
    def __init__(self, base_path: str, registry=None):
        """
        Initialize the deployment manager.
        
        Args:
            base_path: Path to the directory where analytics code will be deployed
            registry: The analytics registry
        """
        self.base_path = base_path
        self.registry = registry
        
        # Create the base directory if it doesn't exist
        os.makedirs(base_path, exist_ok=True)
    
    def deploy(self, code: str, metadata: Dict[str, Any]) -> AnalyticsEndpoint:
        """
        Deploy a new analytics endpoint.
        
        Args:
            code: The Python code to deploy
            metadata: Metadata for the endpoint
            
        Returns:
            The deployed endpoint
        """
        # Generate a unique ID for the endpoint
        endpoint_id = str(uuid.uuid4())
        
        # Create a directory for the endpoint
        endpoint_dir = os.path.join(self.base_path, endpoint_id)
        os.makedirs(endpoint_dir, exist_ok=True)
        
        # Create the Python file
        file_path = os.path.join(endpoint_dir, "analytics.py")
        with open(file_path, "w") as f:
            f.write(code)
        
        # Create a metadata file
        metadata_path = os.path.join(endpoint_dir, "metadata.json")
        with open(metadata_path, "w") as f:
            import json
            json.dump(metadata, f, indent=2)
        
        # Load the module
        module = self._load_module(file_path, endpoint_id)
        
        # Create the endpoint
        endpoint = AnalyticsEndpoint(
            id=endpoint_id,
            name=metadata.get("name", "Unnamed endpoint"),
            path=file_path,
            capabilities={
                "project_keys": metadata.get("project_keys", []),
                "metrics": metadata.get("metrics", []),
                "time_period": metadata.get("time_period"),
                "filters": metadata.get("filters", {}),
                "description": metadata.get("description", "")
            },
            created_at=datetime.now()
        )
        
        # Set the module
        endpoint.module = module
        
        return endpoint
    
    def _load_module(self, file_path: str, module_name: str) -> Any:
        """
        Load a Python module from a file.
        
        Args:
            file_path: Path to the Python file
            module_name: Name for the module
            
        Returns:
            The loaded module
        """
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            print(f"Error loading module: {str(e)}", flush=True)
            raise
    
    def undeploy(self, endpoint_id: str) -> bool:
        """
        Undeploy an analytics endpoint.
        
        Args:
            endpoint_id: The ID of the endpoint to undeploy
            
        Returns:
            True if the endpoint was undeployed, False otherwise
        """
        # Get the endpoint from the registry
        if self.registry:
            endpoint = self.registry.get_endpoint(endpoint_id)
            if not endpoint:
                return False
            
            # Unregister the endpoint
            self.registry.unregister_endpoint(endpoint_id)
        
        # Delete the endpoint directory
        endpoint_dir = os.path.join(self.base_path, endpoint_id)
        if os.path.exists(endpoint_dir):
            import shutil
            shutil.rmtree(endpoint_dir)
            return True
        
        return False
    
    def update(self, endpoint_id: str, code: str, metadata: Dict[str, Any]) -> Optional[AnalyticsEndpoint]:
        """
        Update an existing analytics endpoint.
        
        Args:
            endpoint_id: The ID of the endpoint to update
            code: The new Python code
            metadata: The new metadata
            
        Returns:
            The updated endpoint, or None if the endpoint was not found
        """
        # Get the endpoint from the registry
        if not self.registry:
            return None
        
        endpoint = self.registry.get_endpoint(endpoint_id)
        if not endpoint:
            return None
        
        # Update the Python file
        with open(endpoint.path, "w") as f:
            f.write(code)
        
        # Update the metadata file
        metadata_path = os.path.join(os.path.dirname(endpoint.path), "metadata.json")
        with open(metadata_path, "w") as f:
            import json
            json.dump(metadata, f, indent=2)
        
        # Reload the module
        module = self._load_module(endpoint.path, endpoint_id)
        
        # Update the endpoint
        endpoint.name = metadata.get("name", endpoint.name)
        endpoint.capabilities = {
            "project_keys": metadata.get("project_keys", []),
            "metrics": metadata.get("metrics", []),
            "time_period": metadata.get("time_period"),
            "filters": metadata.get("filters", {}),
            "description": metadata.get("description", "")
        }
        endpoint.module = module
        
        # Update the registry
        self.registry.register_endpoint(endpoint)
        
        return endpoint
    
    def list_endpoints(self) -> List[str]:
        """
        List all deployed endpoints.
        
        Returns:
            List of endpoint IDs
        """
        endpoints = []
        
        for item in os.listdir(self.base_path):
            item_path = os.path.join(self.base_path, item)
            if os.path.isdir(item_path):
                # Check if it contains an analytics.py file
                if os.path.exists(os.path.join(item_path, "analytics.py")):
                    endpoints.append(item)
        
        return endpoints
