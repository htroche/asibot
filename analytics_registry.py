import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict

@dataclass
class AnalyticsEndpoint:
    """
    Represents an analytics endpoint.
    """
    id: str
    name: str
    path: str
    capabilities: Dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now())
    module: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        # Remove module as it's not serializable
        result.pop("module", None)
        # Convert datetime to string
        result["created_at"] = result["created_at"].isoformat()
        return result

class AnalyticsRegistry:
    """
    Registry for analytics endpoints.
    """
    def __init__(self, db_path: str = None):
        """
        Initialize the analytics registry.
        
        Args:
            db_path: Path to the registry database file
        """
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "data", "analytics_registry.json")
        self.endpoints: Dict[str, AnalyticsEndpoint] = {}
        self.load()
    
    def register_endpoint(self, endpoint: AnalyticsEndpoint) -> None:
        """
        Register an analytics endpoint.
        
        Args:
            endpoint: The endpoint to register
        """
        self.endpoints[endpoint.id] = endpoint
        self.save()
    
    def unregister_endpoint(self, endpoint_id: str) -> bool:
        """
        Unregister an analytics endpoint.
        
        Args:
            endpoint_id: The ID of the endpoint to unregister
            
        Returns:
            True if the endpoint was unregistered, False otherwise
        """
        if endpoint_id in self.endpoints:
            del self.endpoints[endpoint_id]
            self.save()
            return True
        return False
    
    def get_endpoint(self, endpoint_id: str) -> Optional[AnalyticsEndpoint]:
        """
        Get an analytics endpoint by ID.
        
        Args:
            endpoint_id: The ID of the endpoint to get
            
        Returns:
            The endpoint, or None if not found
        """
        return self.endpoints.get(endpoint_id)
    
    def list_endpoints(self) -> List[AnalyticsEndpoint]:
        """
        List all registered endpoints.
        
        Returns:
            List of endpoints
        """
        return list(self.endpoints.values())
    
    def find_endpoints(self, project_key: str = None, metrics: List[str] = None) -> List[AnalyticsEndpoint]:
        """
        Find endpoints that match the given criteria.
        
        Args:
            project_key: Project key to match
            metrics: List of metrics to match
            
        Returns:
            List of matching endpoints
        """
        results = []
        
        for endpoint in self.endpoints.values():
            capabilities = endpoint.capabilities
            
            # Check project key
            if project_key and project_key not in capabilities.get("project_keys", []):
                continue
            
            # Check metrics
            if metrics and not all(m in capabilities.get("metrics", []) for m in metrics):
                continue
            
            results.append(endpoint)
        
        return results
    
    def load(self) -> None:
        """
        Load the registry from the database file.
        """
        if not os.path.exists(self.db_path):
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            return
        
        try:
            with open(self.db_path, "r") as f:
                data = json.load(f)
            
            self.endpoints = {}
            for endpoint_data in data:
                # Convert string to datetime
                if "created_at" in endpoint_data:
                    try:
                        endpoint_data["created_at"] = datetime.fromisoformat(endpoint_data["created_at"])
                    except ValueError:
                        endpoint_data["created_at"] = datetime.now()
                
                endpoint = AnalyticsEndpoint(**endpoint_data)
                
                # Load the module if the path exists
                if os.path.exists(endpoint.path):
                    try:
                        # Import the module
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(endpoint.id, endpoint.path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        endpoint.module = module
                    except Exception as e:
                        print(f"Error loading module for endpoint {endpoint.id}: {str(e)}", flush=True)
                
                self.endpoints[endpoint.id] = endpoint
        except Exception as e:
            print(f"Error loading analytics registry: {str(e)}", flush=True)
    
    def save(self) -> None:
        """
        Save the registry to the database file.
        """
        try:
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Convert endpoints to dictionaries
            data = [endpoint.to_dict() for endpoint in self.endpoints.values()]
            
            # Save to file
            with open(self.db_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving analytics registry: {str(e)}", flush=True)
