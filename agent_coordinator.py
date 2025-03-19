import os
import re
import json
import hashlib
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import time

@dataclass
class QueryAnalysis:
    """
    Analysis of a natural language query for Jira analytics.
    """
    query: str
    project_keys: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    time_period: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    query_type: Optional[str] = None  # Added to better categorize queries
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    def get_hash(self) -> str:
        """Generate a hash of the query analysis for caching."""
        # Create a string representation of the analysis
        analysis_str = f"{self.query}|{','.join(sorted(self.project_keys))}|{','.join(sorted(self.metrics))}|{self.time_period}|{json.dumps(self.filters, sort_keys=True)}"
        # Generate a hash
        return hashlib.md5(analysis_str.encode()).hexdigest()

@dataclass
class ValidationResult:
    """
    Result of validating generated code.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass
class CacheEntry:
    """
    Cache entry for query results.
    """
    result: str
    timestamp: float
    attempts: int = 1

class AgentCoordinator:
    """
    Coordinates the analytics agents to process complex queries.
    """
    def __init__(self, registry=None, code_generator=None, deployer=None):
        """
        Initialize the agent coordinator.
        
        Args:
            registry: The analytics registry
            code_generator: The code generator
            deployer: The deployment manager
        """
        self.registry = registry
        self.code_generator = code_generator
        self.deployer = deployer
        
        # Initialize query cache
        self.query_cache = {}
        self.cache_ttl = 3600  # Cache TTL in seconds (1 hour)
        self.max_cache_size = 100  # Maximum number of entries in the cache
        
        # Initialize retry counter for failed queries
        self.retry_counter = {}
        self.max_retries = 3  # Maximum number of retries for a query
        
        # Load cache from disk if available
        self._load_cache()
    
    def _load_cache(self):
        """Load query cache from disk."""
        cache_path = os.path.join(os.path.dirname(__file__), "data", "query_cache.json")
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    cache_data = json.load(f)
                    for key, entry in cache_data.items():
                        self.query_cache[key] = CacheEntry(
                            result=entry["result"],
                            timestamp=entry["timestamp"],
                            attempts=entry.get("attempts", 1)
                        )
                print(f"Loaded {len(self.query_cache)} entries from query cache", flush=True)
        except Exception as e:
            print(f"Error loading query cache: {str(e)}", flush=True)
    
    def _save_cache(self):
        """Save query cache to disk."""
        cache_path = os.path.join(os.path.dirname(__file__), "data", "query_cache.json")
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            # Convert cache to serializable format
            cache_data = {}
            for key, entry in self.query_cache.items():
                cache_data[key] = {
                    "result": entry.result,
                    "timestamp": entry.timestamp,
                    "attempts": entry.attempts
                }
            
            # Write to file
            with open(cache_path, "w") as f:
                json.dump(cache_data, f)
            
            print(f"Saved {len(self.query_cache)} entries to query cache", flush=True)
        except Exception as e:
            print(f"Error saving query cache: {str(e)}", flush=True)
    
    def _clean_cache(self):
        """Clean expired entries from the cache."""
        now = time.time()
        expired_keys = [k for k, v in self.query_cache.items() if now - v.timestamp > self.cache_ttl]
        for key in expired_keys:
            del self.query_cache[key]
        
        # If cache is still too large, remove oldest entries
        if len(self.query_cache) > self.max_cache_size:
            sorted_keys = sorted(self.query_cache.keys(), key=lambda k: self.query_cache[k].timestamp)
            for key in sorted_keys[:len(self.query_cache) - self.max_cache_size]:
                del self.query_cache[key]
    
    def process_query(self, query: str, conversation: list = None) -> str:
        """
        Process a complex analytics query.
        
        Args:
            query: The natural language query
            conversation: Optional conversation history
            
        Returns:
            The analysis results as a string
        """
        # 1. Analyze the query to determine what analytics are needed
        analysis = self.analyze_query(query)
        
        # 2. Check if we have a cached result for this query
        cache_key = analysis.get_hash()
        if cache_key in self.query_cache:
            cache_entry = self.query_cache[cache_key]
            # Check if the cache entry is still valid
            if time.time() - cache_entry.timestamp <= self.cache_ttl:
                print(f"Using cached result for query: {query}", flush=True)
                return cache_entry.result
        
        # 3. Check if we have an existing endpoint that can handle this query
        endpoint = self.find_matching_endpoint(analysis)
        
        result = None
        try:
            if endpoint:
                # 4a. If we have a matching endpoint, use it
                result = self.execute_endpoint(endpoint, analysis)
            else:
                # 4b. If not, generate and deploy a new endpoint
                # Check if we've already tried this query too many times
                if cache_key in self.retry_counter and self.retry_counter[cache_key] >= self.max_retries:
                    # If we've tried too many times, use a fallback approach
                    print(f"Maximum retries reached for query: {query}, using fallback", flush=True)
                    result = self.fallback_query_handler(query, analysis)
                else:
                    # Increment retry counter
                    self.retry_counter[cache_key] = self.retry_counter.get(cache_key, 0) + 1
                    # Try to generate and deploy a new endpoint
                    result = self.generate_and_deploy(analysis)
        except Exception as e:
            print(f"Error processing query: {str(e)}", flush=True)
            # If there's an error, use the fallback handler
            result = self.fallback_query_handler(query, analysis)
        
        # 5. Cache the result if it's not an error message
        if result and not result.startswith("Error"):
            self.query_cache[cache_key] = CacheEntry(
                result=result,
                timestamp=time.time(),
                attempts=self.retry_counter.get(cache_key, 1)
            )
            # Clean and save the cache
            self._clean_cache()
            self._save_cache()
            # Reset retry counter
            if cache_key in self.retry_counter:
                del self.retry_counter[cache_key]
        
        return result if result else f"I'm sorry, I couldn't process your query: {query}"
    
    def fallback_query_handler(self, query: str, analysis: QueryAnalysis) -> str:
        """
        Handle queries that couldn't be processed by the normal pipeline.
        This is a fallback mechanism for when code generation fails.
        
        Args:
            query: The original query
            analysis: The query analysis
            
        Returns:
            A response to the query
        """
        # Determine the query type
        query_type = analysis.query_type or self._determine_query_type(query)
        
        if query_type == "release_notes":
            return self._handle_release_notes_query(query, analysis)
        elif query_type == "sprint_metrics":
            return self._handle_sprint_metrics_query(query, analysis)
        elif query_type == "story_points":
            return self._handle_story_points_query(query, analysis)
        else:
            # Generic fallback
            return (
                f"I'm analyzing your query about {', '.join(analysis.project_keys) if analysis.project_keys else 'Jira data'}. "
                f"To provide a better answer, I'll need to generate some custom analytics code. "
                f"Please try your query again, and I'll work on improving my response."
            )
    
    def _determine_query_type(self, query: str) -> str:
        """
        Determine the type of query based on the query text.
        
        Args:
            query: The query text
            
        Returns:
            The query type
        """
        query_lower = query.lower()
        
        # Check for release notes
        if "release notes" in query_lower or "changelog" in query_lower:
            return "release_notes"
        
        # Check for sprint metrics
        if "sprint" in query_lower and any(term in query_lower for term in ["velocity", "points", "churn"]):
            return "sprint_metrics"
        
        # Check for story points
        if "story points" in query_lower or "story point" in query_lower:
            return "story_points"
        
        # Default
        return "general"
    
    def _handle_release_notes_query(self, query: str, analysis: QueryAnalysis) -> str:
        """
        Handle a release notes query.
        
        Args:
            query: The query text
            analysis: The query analysis
            
        Returns:
            A response to the query
        """
        project_keys = analysis.project_keys
        time_period = analysis.time_period
        
        # Convert time period to human-readable format
        period_desc = "the last month"
        if time_period:
            if time_period.endswith("d"):
                days = int(time_period[:-1])
                period_desc = f"the last {days} days"
            elif time_period.endswith("w"):
                weeks = int(time_period[:-1])
                period_desc = f"the last {weeks} weeks"
            elif time_period.endswith("m"):
                months = int(time_period[:-1])
                period_desc = f"the last {months} months"
        
        project_str = ", ".join(project_keys) if project_keys else "all projects"
        
        return (
            f"# Release Notes for {project_str} ({period_desc})\n\n"
            f"## New Features\n"
            f"- Feature 1: Description of feature 1\n"
            f"- Feature 2: Description of feature 2\n\n"
            f"## Bug Fixes\n"
            f"- Fixed issue with X\n"
            f"- Resolved problem with Y\n\n"
            f"## Improvements\n"
            f"- Enhanced performance of Z\n"
            f"- Improved user experience for W\n\n"
            f"*Note: This is a placeholder response. To generate actual release notes, "
            f"I need to analyze the completed stories in {project_str} during {period_desc}. "
            f"Please try your query again, and I'll work on improving my response.*"
        )
    
    def _handle_sprint_metrics_query(self, query: str, analysis: QueryAnalysis) -> str:
        """
        Handle a sprint metrics query.
        
        Args:
            query: The query text
            analysis: The query analysis
            
        Returns:
            A response to the query
        """
        project_keys = analysis.project_keys
        project_str = ", ".join(project_keys) if project_keys else "all projects"
        
        return (
            f"# Sprint Metrics for {project_str}\n\n"
            f"## Summary\n"
            f"- Average Velocity: XX points per sprint\n"
            f"- Average Completion Rate: XX%\n"
            f"- Average Churn: XX points per sprint\n\n"
            f"## Details\n"
            f"| Sprint | Committed | Completed | Velocity | Churn |\n"
            f"|--------|-----------|-----------|----------|-------|\n"
            f"| Sprint 1 | XX | XX | XX | XX |\n"
            f"| Sprint 2 | XX | XX | XX | XX |\n"
            f"| Sprint 3 | XX | XX | XX | XX |\n\n"
            f"*Note: This is a placeholder response. To generate actual sprint metrics, "
            f"I need to analyze the sprint data for {project_str}. "
            f"Please try your query again, and I'll work on improving my response.*"
        )
    
    def _handle_story_points_query(self, query: str, analysis: QueryAnalysis) -> str:
        """
        Handle a story points query.
        
        Args:
            query: The query text
            analysis: The query analysis
            
        Returns:
            A response to the query
        """
        project_keys = analysis.project_keys
        project_str = ", ".join(project_keys) if project_keys else "all projects"
        
        return (
            f"# Story Points Analysis for {project_str}\n\n"
            f"## Summary\n"
            f"- Total Story Points: XX\n"
            f"- Average Story Points per Issue: XX\n"
            f"- Median Story Points per Issue: XX\n\n"
            f"## Distribution\n"
            f"- 1 point: XX issues\n"
            f"- 2 points: XX issues\n"
            f"- 3 points: XX issues\n"
            f"- 5 points: XX issues\n"
            f"- 8 points: XX issues\n\n"
            f"*Note: This is a placeholder response. To generate actual story points analysis, "
            f"I need to analyze the issue data for {project_str}. "
            f"Please try your query again, and I'll work on improving my response.*"
        )
    
    def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyze a natural language query to determine what analytics are needed.
        
        Args:
            query: The natural language query
            
        Returns:
            Analysis of the query
        """
        # Extract project keys
        project_keys = self._extract_project_keys(query)
        
        # Extract metrics
        metrics = self._extract_metrics(query)
        
        # Extract time period
        time_period = self._extract_time_period(query)
        
        # Extract filters
        filters = self._extract_filters(query)
        
        # Determine query type
        query_type = self._determine_query_type(query)
        
        # Enhanced extraction for release notes
        if query_type == "release_notes":
            # Add specific metrics for release notes
            if "story" in query.lower() or "stories" in query.lower():
                metrics.append("stories")
            if "finished" in query.lower() or "completed" in query.lower() or "done" in query.lower():
                filters["status"] = "Done"
            if "release notes" in query.lower():
                metrics.append("release_notes")
        
        return QueryAnalysis(
            query=query,
            project_keys=project_keys,
            metrics=metrics,
            time_period=time_period,
            filters=filters,
            query_type=query_type
        )
    
    def _extract_project_keys(self, query: str) -> List[str]:
        """
        Extract project keys from a query.
        
        Args:
            query: The natural language query
            
        Returns:
            List of project keys
        """
        # Look for project keys in the query (e.g., "XYZ", "ENG", etc.)
        project_keys = []
        
        # Check for "for PROJECT" pattern
        for_pattern = r'for\s+([A-Z]+)'
        for_matches = re.findall(for_pattern, query)
        project_keys.extend(for_matches)
        
        # Check for "in PROJECT" pattern
        in_pattern = r'in\s+([A-Z]+)'
        in_matches = re.findall(in_pattern, query)
        project_keys.extend(in_matches)
        
        # Check for "by PROJECT" pattern
        by_pattern = r'by\s+([A-Z]+)'
        by_matches = re.findall(by_pattern, query)
        project_keys.extend(by_matches)
        
        # Check for "PROJECT's" pattern
        possessive_pattern = r'([A-Z]+)\'s'
        possessive_matches = re.findall(possessive_pattern, query)
        project_keys.extend(possessive_matches)
        
        # Check for standalone project keys (all caps, 2-10 chars)
        standalone_pattern = r'\b([A-Z]{2,10})\b'
        standalone_matches = re.findall(standalone_pattern, query)
        project_keys.extend(standalone_matches)
        
        # Remove duplicates
        project_keys = list(set(project_keys))
        
        return project_keys
    
    def _extract_metrics(self, query: str) -> List[str]:
        """
        Extract metrics from a query.
        
        Args:
            query: The natural language query
            
        Returns:
            List of metrics
        """
        metrics = []
        query_lower = query.lower()
        
        # Check for common metrics
        if "velocity" in query_lower:
            metrics.append("velocity")
        
        if "points" in query_lower:
            if "committed" in query_lower:
                metrics.append("committed_points")
            if "completed" in query_lower or "finished" in query_lower:
                metrics.append("completed_points")
            if "points" in query_lower and not any(m in metrics for m in ["committed_points", "completed_points"]):
                metrics.append("story_points")
        
        if "churn" in query_lower:
            metrics.append("churn")
        
        # Check for release notes related metrics
        if "release" in query_lower or "notes" in query_lower or "changelog" in query_lower:
            metrics.append("release_notes")
        
        # Check for summary related metrics
        if "summary" in query_lower:
            metrics.append("summary")
        
        # Check for status related metrics
        if "status" in query_lower:
            metrics.append("status")
        
        # Check for time-related metrics
        if any(term in query_lower for term in ["time", "duration", "days", "weeks"]):
            metrics.append("time_to_completion")
        
        return metrics
    
    def _extract_time_period(self, query: str) -> Optional[str]:
        """
        Extract time period from a query.
        
        Args:
            query: The natural language query
            
        Returns:
            Time period string or None
        """
        query_lower = query.lower()
        
        # Check for "last X sprints" pattern
        sprint_pattern = r'last\s+(\d+)\s+sprint'
        sprint_match = re.search(sprint_pattern, query_lower)
        if sprint_match:
            return f"{sprint_match.group(1)}s"  # e.g., "5s" for "last 5 sprints"
        
        # Check for "last X days/weeks/months/years" pattern
        period_pattern = r'last\s+(\d+)\s+(day|week|month|year)s?'
        period_match = re.search(period_pattern, query_lower)
        if period_match:
            value = period_match.group(1)
            unit = period_match.group(2)[0].lower()  # First letter of unit (d, w, m, y)
            return f"{value}{unit}"  # e.g., "30d" for "last 30 days"
        
        # Check for "last day/week/month/year" pattern
        single_period_pattern = r'last\s+(day|week|month|year)'
        single_period_match = re.search(single_period_pattern, query_lower)
        if single_period_match:
            unit = single_period_match.group(1)[0].lower()  # First letter of unit (d, w, m, y)
            return f"1{unit}"  # e.g., "1m" for "last month"
        
        # Check for specific date ranges
        date_range_pattern = r'from\s+(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+to\s+(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)'
        date_range_match = re.search(date_range_pattern, query_lower)
        if date_range_match:
            # For now, just return a default period
            # In a real implementation, you would parse these dates
            return "custom"
        
        # Default to last 5 sprints for sprint metrics
        if any(metric in ["velocity", "committed_points", "completed_points", "churn"] for metric in self._extract_metrics(query_lower)):
            return "5s"
        
        # Default to last month for release notes
        if "release notes" in query_lower or "changelog" in query_lower:
            return "1m"
        
        # Default to last 30 days for other metrics
        return "30d"
    
    def _extract_filters(self, query: str) -> Dict[str, Any]:
        """
        Extract filters from a query.
        
        Args:
            query: The natural language query
            
        Returns:
            Dictionary of filters
        """
        filters = {}
        query_lower = query.lower()
        
        # Check for status filters
        status_pattern = r'status\s+(is|=)\s+(["\']?)(\w+)(["\']?)'
        status_match = re.search(status_pattern, query_lower)
        if status_match:
            filters["status"] = status_match.group(3)
        
        # Check for issue type filters
        type_pattern = r'type\s+(is|=)\s+(["\']?)(\w+)(["\']?)'
        type_match = re.search(type_pattern, query_lower)
        if type_match:
            filters["issuetype"] = type_match.group(3)
        
        # Infer status from context
        if "finished" in query_lower or "completed" in query_lower or "done" in query_lower:
            filters["status"] = "Done"
        elif "in progress" in query_lower:
            filters["status"] = "In Progress"
        elif "blocked" in query_lower:
            filters["status"] = "Blocked"
        elif "open" in query_lower:
            filters["status"] = "Open"
        
        # Infer issue type from context
        if "story" in query_lower or "stories" in query_lower:
            filters["issuetype"] = "Story"
        elif "bug" in query_lower or "bugs" in query_lower:
            filters["issuetype"] = "Bug"
        elif "epic" in query_lower or "epics" in query_lower:
            filters["issuetype"] = "Epic"
        elif "task" in query_lower or "tasks" in query_lower:
            filters["issuetype"] = "Task"
        
        return filters
    
    def find_matching_endpoint(self, analysis: QueryAnalysis) -> Optional[Any]:
        """
        Find an existing endpoint that can handle this query.
        
        Args:
            analysis: The query analysis
            
        Returns:
            Matching endpoint or None
        """
        if not self.registry:
            return None
        
        # Get all registered endpoints
        endpoints = self.registry.list_endpoints()
        
        # Filter endpoints that match the project keys and metrics
        matching_endpoints = []
        for endpoint in endpoints:
            capabilities = endpoint.capabilities
            
            # Check if the endpoint supports all the required project keys
            if not all(pk in capabilities.get("project_keys", []) for pk in analysis.project_keys):
                continue
            
            # Check if the endpoint supports all the required metrics
            if not all(m in capabilities.get("metrics", []) for m in analysis.metrics):
                continue
            
            # Add to matching endpoints
            matching_endpoints.append(endpoint)
        
        # If we have multiple matching endpoints, choose the most specific one
        if matching_endpoints:
            # Sort by number of supported metrics (more specific first)
            matching_endpoints.sort(key=lambda e: len(e.capabilities.get("metrics", [])), reverse=True)
            return matching_endpoints[0]
        
        return None
    
    def execute_endpoint(self, endpoint: Any, analysis: QueryAnalysis) -> str:
        """
        Execute an analytics endpoint with the given analysis.
        
        Args:
            endpoint: The endpoint to execute
            analysis: The query analysis
            
        Returns:
            The analysis results as a string
        """
        try:
            # Get the module from the endpoint
            module = endpoint.module
            
            # Call the analyze function with the appropriate parameters
            result = module.analyze(
                project_keys=analysis.project_keys,
                time_period=analysis.time_period,
                filters=analysis.filters
            )
            
            # Format the result as a string
            return self.format_result(result, analysis)
        except Exception as e:
            print(f"Error executing endpoint: {str(e)}", flush=True)
            return f"Error executing analytics: {str(e)}"
    
    def generate_and_deploy(self, analysis: QueryAnalysis) -> str:
        """
        Generate and deploy a new analytics endpoint for the given analysis.
        
        Args:
            analysis: The query analysis
            
        Returns:
            The analysis results as a string
        """
        # Store the original provider to restore it later
        original_provider = None
        if hasattr(self.code_generator, 'llm_manager') and self.code_generator.llm_manager:
            original_provider = self.code_generator.llm_manager.provider
            
        try:
            # Generate code for the endpoint
            code = self.code_generator.generate_code(analysis)
            
            # Validate the code
            validation = self.validate_code(code)
            if not validation.is_valid:
                error_msg = f"Error generating analytics code: {', '.join(validation.errors)}"
                print(error_msg, flush=True)
                return self.fallback_query_handler(analysis.query, analysis)
            
            # Create metadata for the endpoint
            metadata = {
                "name": f"Analytics for {', '.join(analysis.project_keys)}",
                "project_keys": analysis.project_keys,
                "metrics": analysis.metrics,
                "time_period": analysis.time_period,
                "filters": analysis.filters,
                "description": f"Generated analytics for query: {analysis.query}"
            }
            
            # Deploy the endpoint
            endpoint = self.deployer.deploy(code, metadata)
            
            # Execute the endpoint
            return self.execute_endpoint(endpoint, analysis)
        except Exception as e:
            print(f"Error generating and deploying analytics: {str(e)}", flush=True)
            return self.fallback_query_handler(analysis.query, analysis)
    
    def validate_code(self, code: str) -> ValidationResult:
        """
        Validate generated code.
        
        Args:
            code: The generated code
            
        Returns:
            Validation result
        """
        errors = []
        warnings = []
        
        # Check for syntax errors
        try:
            compile(code, "<string>", "exec")
        except SyntaxError as e:
            # Get more detailed error information
            line_num = e.lineno if hasattr(e, 'lineno') else 'unknown'
            col_num = e.offset if hasattr(e, 'offset') else 'unknown'
            error_line = e.text.strip() if hasattr(e, 'text') and e.text else 'unknown'
            
            error_msg = f"Syntax error: {str(e)} at line {line_num}, column {col_num}. Error line: '{error_line}'"
            print(f"Code validation error: {error_msg}", flush=True)
            errors.append(error_msg)
        
        # Check for required functions
        if "def analyze(" not in code:
            errors.append("Missing required 'analyze' function")
        
        # Check for potential security issues
        if "os.system(" in code or "subprocess" in code:
            warnings.append("Code contains potentially unsafe system calls")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _format_time_period(self, time_period: Optional[str]) -> str:
        """
        Format a time period string as a human-readable string.
        
        Args:
            time_period: The time period string (e.g., "30d", "1m", "5s")
            
        Returns:
            A human-readable time period string
        """
        if not time_period:
            return "last month"
        
        if time_period.endswith("d"):
            days = int(time_period[:-1])
            return f"last {days} days"
        elif time_period.endswith("w"):
            weeks = int(time_period[:-1])
            return f"last {weeks} weeks"
        elif time_period.endswith("m"):
            months = int(time_period[:-1])
            return f"last {months} months"
        elif time_period.endswith("y"):
            years = int(time_period[:-1])
            return f"last {years} years"
        elif time_period.endswith("s"):
            sprints = int(time_period[:-1])
            return f"last {sprints} sprints"
        else:
            return f"last {time_period}"
    
    def format_result(self, result: Dict[str, Any], analysis: QueryAnalysis) -> str:
        """
        Format the result as a string.
        
        Args:
            result: The analysis result
            analysis: The query analysis
            
        Returns:
            Formatted result as a string
        """
        # Check if the result is for release notes
        if analysis.query_type == "release_notes" or "release_notes" in analysis.metrics:
            return self.format_release_notes(result, analysis)
        
        # Check if the result is for sprint metrics
        if "sprints" in result:
            return self.format_sprint_metrics(result, analysis)
        
        # Check if the result is for story point completion time analysis
        if any(project_data.get("completion_times") for project_data in result.values() if isinstance(project_data, dict)):
            return self.format_story_point_completion_times(result, analysis)
        
        # Default formatting
        return json.dumps(result, indent=2)
    
    def format_release_notes(self, result: Dict[str, Any], analysis: QueryAnalysis) -> str:
        """
        Format release notes as a string.
        
        Args:
            result: The analysis result
            analysis: The query analysis
            
        Returns:
            Formatted release notes as a string
        """
        output = []
        
        # Get the project key (assume single project for now)
        project_key = analysis.project_keys[0] if analysis.project_keys else "Unknown"
        
        # Get the time period
        time_period = self._format_time_period(analysis.time_period)
        
        # Build the header
        output.append(f"# Release Notes for {project_key} ({time_period})")
        output.append("")
        
        # Check if we have categories in the result
        if "categories" in result:
            categories = result.get("categories", {})
            for category, issues in categories.items():
                output.append(f"## {category}")
                output.append("")
                for issue in issues:
                    key = issue.get("key", "")
                    summary = issue.get("summary", "")
                    output.append(f"- {key}: {summary}")
                output.append("")
        else:
            # Default format
            issues = result.get("issues", [])
            if issues:
                output.append("## Completed Issues")
                output.append("")
                for issue in issues:
                    key = issue.get("key", "")
                    summary = issue.get("summary", "")
                    output.append(f"- {key}: {summary}")
                output.append("")
            else:
                output.append("No issues found for this time period.")
                output.append("")
        
        return "\n".join(output)
    
    def format_sprint_metrics(self, result: Dict[str, Any], analysis: QueryAnalysis) -> str:
        """
        Format sprint metrics as a string.
        
        Args:
            result: The analysis result
            analysis: The query analysis
            
        Returns:
            Formatted sprint metrics as a string
        """
        output = []
        
        # Get the project key (assume single project for now)
        project_key = analysis.project_keys[0] if analysis.project_keys else "Unknown"
        
        # Get the sprints
        project_result = result.get(project_key, {})
        sprints = project_result.get("sprints", [])
        avg_velocity = project_result.get("average_velocity", 0)
        
        # Build the table header
        output.append(f"Below is the summary for the last {len(sprints)} sprints for {project_key}:")
        output.append(f"• Average Velocity across sprints: {avg_velocity:.2f}")
        output.append("")
        output.append("Sprint Metrics Details:")
        output.append("-----------------------------------------------------------")
        output.append("Sprint Name                       | Committed Points | Completed Points | Velocity | Churn")
        output.append("-----------------------------------------------------------")
        
        # Add rows for each sprint
        for sprint in sprints:
            name = sprint.get("name", "Unknown")
            committed = sprint.get("committed_points", 0)
            completed = sprint.get("completed_points", 0)
            velocity = completed  # Velocity is the same as completed points
            churn = sprint.get("churn", 0)
            
            output.append(f"{name:<35} | {committed:<16.1f} | {completed:<16.1f} | {velocity:<8.1f} | {churn:<5.1f}  ")
        
        output.append("-----------------------------------------------------------")
        output.append("Let me know if you need any further details or analysis!")
        
        return "\n".join(output)
    
    def format_story_point_completion_times(self, result: Dict[str, Any], analysis: QueryAnalysis) -> str:
        """
        Format story point completion time analysis as a string.
        
        Args:
            result: The analysis result
            analysis: The query analysis
            
        Returns:
            Formatted story point completion time analysis as a string
        """
        output = []
        
        # Get the project key (assume single project for now)
        project_key = analysis.project_keys[0] if analysis.project_keys else "Unknown"
        
        # Get the completion times
        project_result = result.get(project_key, {})
        completion_times = project_result.get("completion_times", {})
        time_period = project_result.get("time_period", {})
        
        # Extract time period description
        period_desc = time_period.get("description", "3 months")
        
        # Build the header
        output.append(f"Below is the analysis of story point completion times for project {project_key} in the last {period_desc}:")
        output.append("")
        output.append("Story Point Completion Time Analysis:")
        output.append("-----------------------------------------------------------")
        output.append("Story Points | Count | Avg Days | Median Days | Min Days | Max Days")
        output.append("-----------------------------------------------------------")
        
        # Add rows for each story point value
        for points, stats in sorted(completion_times.items(), key=lambda x: int(x[0])):
            count = stats.get("count", 0)
            avg_days = stats.get("avg_days")
            median_days = stats.get("median_days")
            min_days = stats.get("min_days")
            max_days = stats.get("max_days")
            
            # Format the values
            avg_str = f"{avg_days:.1f}" if avg_days is not None else "N/A"
            median_str = f"{median_days:.1f}" if median_days is not None else "N/A"
            min_str = f"{min_days:.1f}" if min_days is not None else "N/A"
            max_str = f"{max_days:.1f}" if max_days is not None else "N/A"
            
            output.append(f"{points:^12} | {count:^5} | {avg_str:^8} | {median_str:^11} | {min_str:^8} | {max_str:^8}")
        
        output.append("-----------------------------------------------------------")
        
        # Add summary and interpretation
        output.append("")
        output.append("Summary:")
        
        # Find the story point value with the most data points
        most_data_points = max(completion_times.items(), key=lambda x: x[1].get("count", 0), default=(None, {"count": 0}))
        most_data_point_value = most_data_points[0]
        most_data_point_count = most_data_points[1].get("count", 0)
        
        if most_data_point_count > 0:
            output.append(f"• The most common story point value is {most_data_point_value} with {most_data_point_count} completed stories.")
        
        # Check if there's a correlation between story points and completion time
        points_with_data = [(int(p), stats.get("avg_days")) for p, stats in completion_times.items() if stats.get("avg_days") is not None]
        if len(points_with_data) >= 2:
            points_with_data.sort(key=lambda x: x[0])
            if points_with_data[-1][1] > points_with_data[0][1]:
                output.append("• There appears to be a correlation between story point values and completion time - higher point stories take longer to complete.")
            elif points_with_data[-1][1] < points_with_data[0][1]:
                output.append("• Interestingly, higher point stories are completing faster than lower point stories on average.")
            else:
                output.append("• There doesn't appear to be a strong correlation between story point values and completion time.")
        
        output.append("")
        output.append("Let me know if you need any further details or analysis!")
        
        return "\n".join(output)
