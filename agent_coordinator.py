import os
import re
import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict

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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

@dataclass
class ValidationResult:
    """
    Result of validating generated code.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

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
    
    def process_query(self, query: str) -> str:
        """
        Process a complex analytics query.
        
        Args:
            query: The natural language query
            
        Returns:
            The analysis results as a string
        """
        # 1. Analyze the query to determine what analytics are needed
        analysis = self.analyze_query(query)
        
        # 2. Check if we have an existing endpoint that can handle this query
        endpoint = self.find_matching_endpoint(analysis)
        
        if endpoint:
            # 3a. If we have a matching endpoint, use it
            return self.execute_endpoint(endpoint, analysis)
        else:
            # 3b. If not, generate and deploy a new endpoint
            return self.generate_and_deploy(analysis)
    
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
        
        return QueryAnalysis(
            query=query,
            project_keys=project_keys,
            metrics=metrics,
            time_period=time_period,
            filters=filters
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
        
        # Check for common metrics
        if "velocity" in query.lower():
            metrics.append("velocity")
        
        if "points" in query.lower():
            if "committed" in query.lower():
                metrics.append("committed_points")
            if "completed" in query.lower() or "finished" in query.lower():
                metrics.append("completed_points")
            if "points" in query.lower() and not any(m in metrics for m in ["committed_points", "completed_points"]):
                metrics.append("story_points")
        
        if "churn" in query.lower():
            metrics.append("churn")
        
        return metrics
    
    def _extract_time_period(self, query: str) -> Optional[str]:
        """
        Extract time period from a query.
        
        Args:
            query: The natural language query
            
        Returns:
            Time period string or None
        """
        # Check for "last X sprints" pattern
        sprint_pattern = r'last\s+(\d+)\s+sprint'
        sprint_match = re.search(sprint_pattern, query, re.IGNORECASE)
        if sprint_match:
            return f"{sprint_match.group(1)}s"  # e.g., "5s" for "last 5 sprints"
        
        # Check for "last X days/weeks/months/years" pattern
        period_pattern = r'last\s+(\d+)\s+(day|week|month|year)s?'
        period_match = re.search(period_pattern, query, re.IGNORECASE)
        if period_match:
            value = period_match.group(1)
            unit = period_match.group(2)[0].lower()  # First letter of unit (d, w, m, y)
            return f"{value}{unit}"  # e.g., "30d" for "last 30 days"
        
        # Default to last 5 sprints for sprint metrics
        if any(metric in ["velocity", "committed_points", "completed_points", "churn"] for metric in self._extract_metrics(query)):
            return "5s"
        
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
        
        # Check for status filters
        status_pattern = r'status\s+(is|=)\s+(["\']?)(\w+)(["\']?)'
        status_match = re.search(status_pattern, query, re.IGNORECASE)
        if status_match:
            filters["status"] = status_match.group(3)
        
        # Check for issue type filters
        type_pattern = r'type\s+(is|=)\s+(["\']?)(\w+)(["\']?)'
        type_match = re.search(type_pattern, query, re.IGNORECASE)
        if type_match:
            filters["issuetype"] = type_match.group(3)
        
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
                return f"Error generating analytics code: {', '.join(validation.errors)}"
            
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
            return f"Error generating and deploying analytics: {str(e)}"
    
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
    
    def format_result(self, result: Dict[str, Any], analysis: QueryAnalysis) -> str:
        """
        Format the result as a string.
        
        Args:
            result: The analysis result
            analysis: The query analysis
            
        Returns:
            Formatted result as a string
        """
        # Check if the result is for sprint metrics
        if "sprints" in result:
            return self.format_sprint_metrics(result, analysis)
        
        # Check if the result is for story point completion time analysis
        if any(project_data.get("completion_times") for project_data in result.values() if isinstance(project_data, dict)):
            return self.format_story_point_completion_times(result, analysis)
        
        # Default formatting
        return json.dumps(result, indent=2)
    
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
