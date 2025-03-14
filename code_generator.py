import os
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

from agent_coordinator import ValidationResult

class CodeGenerator:
    """
    Generates Python code for new analytics functions based on query requirements.
    """
    def __init__(self, llm_manager=None, template_path=None):
        """
        Initialize the code generator.
        
        Args:
            llm_manager: The LLM manager to use for code generation
            template_path: Path to the directory containing code templates
        """
        self.llm_manager = llm_manager
        self.templates = self._load_templates(template_path)
    
    def generate_code(self, analysis) -> str:
        """
        Generate code for a new analytics endpoint based on the query analysis.
        
        Args:
            analysis: The query analysis
            
        Returns:
            Generated code as a string
        """
        # Determine which template to use based on the query analysis
        template_name = self._select_template(analysis)
        template = self.templates.get(template_name, self.templates['default'])
        
        # Store the original provider to restore it later
        original_provider = None
        if self.llm_manager:
            original_provider = self.llm_manager.provider
            # Ensure we're using the Anthropic model
            self.llm_manager.switch_provider("anthropic")
        
        # Use the LLM to generate code based on the template
        system_prompt = f"""
        You are an expert Python developer specializing in Jira analytics.
        
        Your task is to generate code for a new analytics endpoint based on the following query analysis:
        ```json
        {json.dumps(analysis.to_dict(), indent=2)}
        ```
        
        Use the following template as a starting point:
        ```python
        {template}
        ```
        
        Modify the template to implement the specific analytics functionality required by the query.
        Focus on the `analyze` function and the `process_issues` function.
        
        The code should:
        1. Accept the parameters specified in the query analysis (project_keys, time_period, filters, etc.)
        2. Fetch the appropriate data from Jira
        3. Process the data to calculate the requested metrics
        4. Return the results in a structured format
        
        Make sure the code is well-documented, efficient, and handles edge cases appropriately.
        Return ONLY the complete Python code with no additional explanation or markdown formatting.
        """
        
        try:
            # Use the direct Anthropic API method if the provider is Anthropic
            if self.llm_manager.provider == "anthropic":
                response_text = self.llm_manager.process_message_with_anthropic_direct(
                    user_message=system_prompt
                )
            else:
                # Otherwise, use the standard process_message method
                response_text = self.llm_manager.process_message(
                    user_message="",
                    conversation=[{"role": "system", "content": system_prompt}]
                )
            
            # Clean up any potential markdown code block formatting
            response_text = self._clean_code_response(response_text)
            
            # Save the generated code to a debug file for inspection
            self._save_debug_code(response_text, template_name)
            
            return response_text
        except Exception as e:
            print(f"Error generating code: {str(e)}", flush=True)
            # Return a simple, valid Python code that won't cause syntax errors
            return self._get_fallback_code(template_name)
        finally:
            # Always restore the original provider, even if there's an error
            if self.llm_manager and original_provider:
                self.llm_manager.switch_provider(original_provider)
    
    def _save_debug_code(self, code: str, template_name: str) -> None:
        """
        Save the generated code to a debug file for inspection.
        
        Args:
            code: The generated code
            template_name: The name of the template used
        """
        try:
            debug_dir = os.path.join(os.path.dirname(__file__), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = os.path.join(debug_dir, f"{template_name}_{timestamp}.py")
            
            with open(debug_file, "w") as f:
                f.write(f"# Debug code generated from {template_name} template\n")
                f.write(f"# Generated at: {datetime.now().isoformat()}\n\n")
                f.write(code)
            
            print(f"Debug code saved to {debug_file}", flush=True)
        except Exception as e:
            print(f"Error saving debug code: {str(e)}", flush=True)
    
    def _get_fallback_code(self, template_name: str) -> str:
        """
        Get fallback code that won't cause syntax errors.
        
        Args:
            template_name: The name of the template that failed
            
        Returns:
            Simple, valid Python code
        """
        if template_name == 'story_point_completion_time':
            return self._get_story_point_completion_time_fallback()
        else:
            return '''
import os
from typing import Dict, List, Any

def analyze(project_keys: List[str], **kwargs) -> Dict[str, Any]:
    """
    Fallback analyze function.
    
    Args:
        project_keys: List of Jira project keys to analyze
        **kwargs: Additional parameters
        
    Returns:
        Fallback results
    """
    return {
        "error": "Code generation failed. Using fallback implementation.",
        "project_keys": project_keys
    }
'''
    
    def _get_story_point_completion_time_fallback(self) -> str:
        """
        Get fallback code for story point completion time analysis.
        
        Returns:
            Simple, valid Python code for story point completion time analysis
        """
        return '''
import os
from typing import Dict, List, Any
from datetime import datetime, timedelta

def analyze(project_keys: List[str], time_period: str = "3m", story_point_values: List[int] = None, **kwargs) -> Dict[str, Any]:
    """
    Fallback analyze function for story point completion time analysis.
    
    Args:
        project_keys: List of Jira project keys to analyze
        time_period: Time period to analyze
        story_point_values: List of story point values to analyze
        **kwargs: Additional parameters
        
    Returns:
        Fallback results
    """
    if story_point_values is None:
        story_point_values = [1, 2, 3, 5, 8]
    
    # Create a simple fallback result
    results = {}
    
    for project_key in project_keys:
        completion_times = {}
        
        for points in story_point_values:
            completion_times[str(points)] = {
                "count": 0,
                "avg_days": None,
                "median_days": None,
                "min_days": None,
                "max_days": None
            }
        
        results[project_key] = {
            "completion_times": completion_times,
            "time_period": {
                "start_date": (datetime.now() - timedelta(days=90)).isoformat(),
                "end_date": datetime.now().isoformat(),
                "description": time_period
            }
        }
    
    return results
'''
    
    def _select_template(self, analysis) -> str:
        """
        Select the appropriate template based on the query analysis.
        
        Args:
            analysis: The query analysis
            
        Returns:
            Name of the template to use
        """
        query_lower = analysis.query.lower()
        
        # Check if the query is about story point completion times
        completion_time_keywords = ["how long", "calendar days", "completion time", "time to complete"]
        if "story points" in query_lower and any(keyword in query_lower for keyword in completion_time_keywords):
            return 'story_point_completion_time'
        
        # Check if the query is about story points
        story_points_keywords = ["story points", "points", "velocity", "churn"]
        if any(keyword in query_lower for keyword in story_points_keywords):
            return 'story_points_analysis'
        
        # Check if the query is about time-based metrics
        time_keywords = ["time", "duration", "days", "weeks", "months"]
        if any(keyword in query_lower for keyword in time_keywords):
            return 'time_analysis'
        
        # Default to the default template
        return 'default'
    
    def _load_templates(self, template_path=None) -> Dict[str, str]:
        """
        Load code templates from the specified directory.
        
        Args:
            template_path: Path to the directory containing code templates
            
        Returns:
            A dictionary mapping template names to template content
        """
        templates = {}
        
        # Add default templates
        templates['default'] = self._get_default_template()
        templates['story_points_analysis'] = self._get_story_points_template()
        templates['time_analysis'] = self._get_time_analysis_template()
        templates['story_point_completion_time'] = self._get_story_point_completion_time_template()
        
        # Load templates from directory if provided
        if template_path and os.path.exists(template_path):
            for filename in os.listdir(template_path):
                if filename.endswith('.py'):
                    template_name = os.path.splitext(filename)[0]
                    with open(os.path.join(template_path, filename), 'r') as f:
                        templates[template_name] = f.read()
        
        return templates
    
    def _get_default_template(self) -> str:
        """
        Get the default code template.
        
        Returns:
            The default template as a string
        """
        return '''
import os
import concurrent.futures
import re
from requests.auth import HTTPBasicAuth
import requests
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from typing import Dict, List, Any, Optional, Union
from urllib.parse import unquote

# Configuration
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = unquote(os.environ.get("JIRA_API_TOKEN", "").strip())
STORY_POINTS_FIELD = os.environ.get("STORY_POINTS_FIELD", "customfield_10016")

def analyze(project_keys: List[str], time_period: str = "1y", filters: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
    """
    Analyze Jira data based on the provided parameters.
    
    Args:
        project_keys: List of Jira project keys to analyze
        time_period: Time period to analyze (e.g., "1y" for 1 year)
        filters: Additional filters to apply to the JQL query
        **kwargs: Additional parameters for specific analyses
        
    Returns:
        Analysis results as a dictionary
    """
    # Parse time period
    end_date = datetime.now(timezone.utc)
    start_date = parse_time_period(end_date, time_period)
    
    # Build JQL query
    jql = build_jql(project_keys, start_date, end_date, filters)
    
    # Fetch issues
    issues = fetch_issues(jql)
    
    # Process issues
    results = process_issues(issues, **kwargs)
    
    return results

def parse_time_period(end_date: datetime, time_period: str) -> datetime:
    """
    Parse a time period string into a start date.
    
    Args:
        end_date: The end date for the time period
        time_period: A string representing the time period (e.g., "1y", "6m", "2w")
        
    Returns:
        The start date for the time period
    """
    if not time_period:
        # Default to 1 year
        return end_date - timedelta(days=365)
    
    # Parse time period format (e.g., "1y", "6m", "2w", "30d")
    match = re.match(r'^(\d+)([ymwd])$', time_period.lower())
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == 'y':
            return end_date - timedelta(days=value * 365)
        elif unit == 'm':
            return end_date - timedelta(days=value * 30)
        elif unit == 'w':
            return end_date - timedelta(weeks=value)
        elif unit == 'd':
            return end_date - timedelta(days=value)
    
    # Handle "last X" format
    match = re.match(r'^last\s+(\d+)\s+(year|month|week|day)s?$', time_period.lower())
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == 'year':
            return end_date - timedelta(days=value * 365)
        elif unit == 'month':
            return end_date - timedelta(days=value * 30)
        elif unit == 'week':
            return end_date - timedelta(weeks=value)
        elif unit == 'day':
            return end_date - timedelta(days=value)
    
    # Default to 1 year if format not recognized
    return end_date - timedelta(days=365)

def build_jql(project_keys: List[str], start_date: datetime, end_date: datetime, filters: Dict[str, Any] = None) -> str:
    """
    Build a JQL query based on the provided parameters.
    
    Args:
        project_keys: List of Jira project keys to include
        start_date: Start date for the query
        end_date: End date for the query
        filters: Additional filters to apply
        
    Returns:
        A JQL query string
    """
    # Format dates for JQL
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    # Build project clause
    if len(project_keys) == 1:
        project_clause = f'project = "{project_keys[0]}"'
    else:
        project_clause = f'project in ({", ".join([f\'"{p}"\' for p in project_keys])})'
    
    # Build date clause
    date_clause = f'updated >= "{start_date_str}" AND updated <= "{end_date_str}"'
    
    # Build filter clauses
    filter_clauses = []
    if filters:
        for key, value in filters.items():
            if isinstance(value, list):
                if len(value) == 1:
                    filter_clauses.append(f'{key} = "{value[0]}"')
                else:
                    filter_clauses.append(f'{key} in ({", ".join([f\'"{v}"\' for v in value])})')
            else:
                filter_clauses.append(f'{key} = "{value}"')
    
    # Combine clauses
    jql = f'{project_clause} AND {date_clause}'
    if filter_clauses:
        jql += f' AND {" AND ".join(filter_clauses)}'
    
    return jql

def fetch_issues(jql: str, fields: str = None) -> List[Dict[str, Any]]:
    """
    Fetch issues from Jira using the provided JQL query.
    
    Args:
        jql: The JQL query to execute
        fields: Comma-separated list of fields to include
        
    Returns:
        List of issues matching the query
    """
    if fields is None:
        fields = f"key,summary,status,created,updated,resolutiondate,issuetype,{STORY_POINTS_FIELD}"
    
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    issues = []
    start_at = 0
    max_results = 100
    
    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": jql,
            "fields": fields,
            "startAt": start_at,
            "maxResults": max_results
        }
        
        try:
            response = requests.get(url, auth=auth, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            batch_issues = data.get("issues", [])
            issues.extend(batch_issues)
            
            total = data.get("total", 0)
            if start_at + len(batch_issues) >= total:
                break
                
            start_at += len(batch_issues)
        except Exception as e:
            print(f"Error fetching issues: {str(e)}", flush=True)
            break
    
    return issues

def fetch_issue_changelog(issue_key: str) -> Dict[str, Any]:
    """
    Fetch the changelog for a specific issue.
    
    Args:
        issue_key: The key of the issue to fetch the changelog for
        
    Returns:
        The changelog data
    """
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/changelog"
    
    try:
        response = requests.get(url, auth=auth, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching changelog for {issue_key}: {str(e)}", flush=True)
        return {"values": []}

def fetch_issue_changelogs_batch(issue_keys: List[str], max_workers: int = 10) -> Dict[str, Dict[str, Any]]:
    """
    Fetch changelogs for multiple issues in parallel.
    
    Args:
        issue_keys: List of issue keys to fetch changelogs for
        max_workers: Maximum number of parallel requests
        
    Returns:
        Dictionary mapping issue keys to their changelogs
    """
    changelogs = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key = {executor.submit(fetch_issue_changelog, key): key for key in issue_keys}
        
        for future in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[future]
            try:
                changelog = future.result()
                changelogs[key] = changelog
            except Exception as e:
                print(f"Error fetching changelog for {key}: {str(e)}", flush=True)
    
    return changelogs

def get_story_points(issue: Dict[str, Any]) -> Optional[float]:
    """
    Get the story points for an issue.
    
    Args:
        issue: The issue data
        
    Returns:
        The story points value, or None if not set
    """
    fields = issue.get("fields", {})
    story_points = fields.get(STORY_POINTS_FIELD)
    
    if story_points is not None:
        try:
            return float(story_points)
        except (ValueError, TypeError):
            pass
    
    return None

def process_issues(issues: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    Process the issues to generate the analysis results.
    
    Args:
        issues: The issues to process
        **kwargs: Additional parameters for specific analyses
        
    Returns:
        The analysis results
    """
    # This is a placeholder that should be replaced with specific analysis logic
    return {
        "total_issues": len(issues),
        "message": "This is a placeholder implementation. Replace with specific analysis logic."
    }
'''
    
    def _get_story_points_template(self) -> str:
        """
        Get the template for story points analysis.
        
        Returns:
            The story points analysis template as a string
        """
        return '''
# Sprint Metrics Analysis Template
import os
import re
import json
import statistics
from collections import defaultdict
from requests.auth import HTTPBasicAuth
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union
from urllib.parse import unquote

# Configuration
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = unquote(os.environ.get("JIRA_API_TOKEN", "").strip())
STORY_POINTS_FIELD = os.environ.get("STORY_POINTS_FIELD", "customfield_10016")

def analyze(project_keys: List[str], num_sprints: int = 5, **kwargs) -> Dict[str, Any]:
    """
    Analyze sprint metrics for the specified projects.
    
    Args:
        project_keys: List of Jira project keys to analyze
        num_sprints: Number of recent sprints to analyze
        **kwargs: Additional parameters
        
    Returns:
        Sprint metrics analysis results
    """
    all_results = {}
    
    for project_key in project_keys:
        # Fetch sprint data for the project
        sprints = fetch_sprints(project_key, num_sprints)
        
        # Calculate metrics for each sprint
        sprint_metrics = []
        for sprint in sprints:
            metrics = calculate_sprint_metrics(sprint)
            sprint_metrics.append(metrics)
        
        # Calculate average velocity
        completed_points = [sprint.get("completed_points", 0) for sprint in sprint_metrics]
        avg_velocity = sum(completed_points) / len(completed_points) if completed_points else 0
        
        all_results[project_key] = {
            "sprints": sprint_metrics,
            "average_velocity": avg_velocity
        }
    
    return all_results

def fetch_sprints(project_key: str, num_sprints: int) -> List[Dict[str, Any]]:
    """
    Fetch recent sprints for a project.
    
    Args:
        project_key: The Jira project key
        num_sprints: Number of recent sprints to fetch
        
    Returns:
        List of sprint data
    """
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    # First, get the board ID for the project
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board"
    params = {
        "projectKeyOrId": project_key
    }
    
    try:
        response = requests.get(url, auth=auth, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("values"):
            return []
        
        # Use the first board found
        board_id = data["values"][0]["id"]
        
        # Now fetch sprints for this board
        url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint"
        params = {
            "state": "closed",
            "maxResults": num_sprints
        }
        
        response = requests.get(url, auth=auth, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        return data.get("values", [])
    except Exception as e:
        print(f"Error fetching sprints for {project_key}: {str(e)}", flush=True)
        return []

def calculate_sprint_metrics(sprint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate metrics for a sprint.
    
    Args:
        sprint: The sprint data
        
    Returns:
        Sprint metrics
    """
    sprint_id = sprint["id"]
    sprint_name = sprint["name"]
    
    # Fetch issues for this sprint
    issues = fetch_sprint_issues(sprint_id)
    
    # Calculate metrics
    committed_points = 0
    completed_points = 0
    
    for issue in issues:
        story_points = get_story_points(issue)
        if story_points is not None:
            committed_points += story_points
            
            # Check if the issue was completed in this sprint
            if issue["fields"]["status"]["statusCategory"]["key"] == "done":
                completed_points += story_points
    
    return {
        "id": sprint_id,
        "name": sprint_name,
        "start_date": sprint.get("startDate"),
        "end_date": sprint.get("endDate"),
        "committed_points": committed_points,
        "completed_points": completed_points,
        "churn": committed_points - completed_points
    }

def fetch_sprint_issues(sprint_id: str) -> List[Dict[str, Any]]:
    """
    Fetch issues for a sprint.
    
    Args:
        sprint_id: The sprint ID
        
    Returns:
        List of issues in the sprint
    """
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    jql = f'sprint = {sprint_id}'
    fields = f"key,summary,status,issuetype,{STORY_POINTS_FIELD}"
    
    issues = []
    start_at = 0
    max_results = 100
    
    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": jql,
            "fields": fields,
            "startAt": start_at,
            "maxResults": max_results
        }
        
        try:
            response = requests.get(url, auth=auth, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            batch_issues = data.get("issues", [])
            issues.extend(batch_issues)
            
            total = data.get("total", 0)
            if start_at + len(batch_issues) >= total:
                break
                
            start_at += len(batch_issues)
        except Exception as e:
            print(f"Error fetching sprint issues: {str(e)}", flush=True)
            break
    
    return issues

def get_story_points(issue: Dict[str, Any]) -> Optional[float]:
    """
    Get the story points for an issue.
    
    Args:
        issue: The issue data
        
    Returns:
        The story points value, or None if not set
    """
    fields = issue.get("fields", {})
    story_points = fields.get(STORY_POINTS_FIELD)
    
    if story_points is not None:
        try:
            return float(story_points)
        except (ValueError, TypeError):
            pass
    
    return None
'''
    
    def _get_time_analysis_template(self) -> str:
        """
        Get the template for time analysis.
        
        Returns:
            The time analysis template as a string
        """
        return '''
# Time Analysis Template
import os
import re
from requests.auth import HTTPBasicAuth
import requests
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from typing import Dict, List, Any, Optional, Union
from urllib.parse import unquote

# Configuration
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = unquote(os.environ.get("JIRA_API_TOKEN", "").strip())
STORY_POINTS_FIELD = os.environ.get("STORY_POINTS_FIELD", "customfield_10016")

def analyze(project_keys: List[str], time_period: str = "1m", filters: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
    """
    Analyze time-based metrics for the specified projects.
    
    Args:
        project_keys: List of Jira project keys to analyze
        time_period: Time period to analyze (e.g., "1m" for 1 month)
        filters: Additional filters to apply to the JQL query
        **kwargs: Additional parameters
        
    Returns:
        Time-based metrics analysis results
    """
    # Parse time period
    end_date = datetime.now(timezone.utc)
    start_date = parse_time_period(end_date, time_period)
    
    # Build JQL query
    jql = build_jql(project_keys, start_date, end_date, filters)
    
    # Fetch issues
    issues = fetch_issues(jql)
    
    # Calculate time-based metrics
    metrics = calculate_time_metrics(issues, start_date, end_date)
    
    return {
        "time_period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "description": time_period
        },
        "projects": project_keys,
        "metrics": metrics,
        "total_issues": len(issues)
    }

def parse_time_period(end_date: datetime, time_period: str) -> datetime:
    """Parse a time period string into a start date."""
    if not time_period:
        return end_date - timedelta(days=30)
    
    match = re.match(r'^(\d+)([ymwd])$', time_period.lower())
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == 'y':
            return end_date - timedelta(days=value * 365)
        elif unit == 'm':
            return end_date - timedelta(days=value * 30)
        elif unit == 'w':
            return end_date - timedelta(weeks=value)
        elif unit == 'd':
            return end_date - timedelta(days=value)
    
    return end_date - timedelta(days=30)

def build_jql(project_keys: List[str], start_date: datetime, end_date: datetime, filters: Dict[str, Any] = None) -> str:
    """Build a JQL query based on the provided parameters."""
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    if len(project_keys) == 1:
        project_clause = f'project = "{project_keys[0]}"'
    else:
        project_clause = f'project in ({", ".join([f\'"{p}"\' for p in project_keys])})'
    
    date_clause = f'updated >= "{start_date_str}" AND updated <= "{end_date_str}"'
    
    jql = f'{project_clause} AND {date_clause}'
    
    return jql

def fetch_issues(jql: str, fields: str = None) -> List[Dict[str, Any]]:
    """Fetch issues from Jira using the provided JQL query."""
    if fields is None:
        fields = f"key,summary,status,created,updated,resolutiondate,issuetype,{STORY_POINTS_FIELD}"
    
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    issues = []
    start_at = 0
    max_results = 100
    
    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": jql,
            "fields": fields,
            "startAt": start_at,
            "maxResults": max_results
        }
        
        try:
            response = requests.get(url, auth=auth, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            batch_issues = data.get("issues", [])
            issues.extend(batch_issues)
            
            total = data.get("total", 0)
            if start_at + len(batch_issues) >= total:
                break
                
            start_at += len(batch_issues)
        except Exception as e:
            print(f"Error fetching issues: {str(e)}", flush=True)
            break
    
    return issues

def calculate_time_metrics(issues: List[Dict[str, Any]], start_date: datetime, end_date: datetime) -> Dict[str, Any]:
    """Calculate time-based metrics for the issues."""
    status_counts = {}
    type_counts = {}
    created_count = 0
    resolved_count = 0
    
    for issue in issues:
        status = issue["fields"]["status"]["name"]
        status_counts[status] = status_counts.get(status, 0) + 1
        
        issue_type = issue["fields"]["issuetype"]["name"]
        type_counts[issue_type] = type_counts.get(issue_type, 0) + 1
        
        created_date = date_parser.isoparse(issue["fields"]["created"])
        if start_date <= created_date <= end_date:
            created_count += 1
        
        if issue["fields"].get("resolutiondate"):
            resolution_date = date_parser.isoparse(issue["fields"]["resolutiondate"])
            if start_date <= resolution_date <= end_date:
                resolved_count += 1
    
    return {
        "status_counts": status_counts,
        "type_counts": type_counts,
        "created_count": created_count,
        "resolved_count": resolved_count
    }

def get_story_points(issue: Dict[str, Any]) -> Optional[float]:
    """Get the story points for an issue."""
    fields = issue.get("fields", {})
    story_points = fields.get(STORY_POINTS_FIELD)
    
    if story_points is not None:
        try:
            return float(story_points)
        except (ValueError, TypeError):
            pass
    
    return None
'''

    def _clean_code_response(self, response_text: str) -> str:
        """
        Clean up any potential markdown code block formatting in the response.
        
        Args:
            response_text: The response text from the LLM
            
        Returns:
            Cleaned code with no markdown formatting
        """
        # Remove markdown code block markers if present
        if response_text.startswith("```python"):
            response_text = response_text[len("```python"):].strip()
        elif response_text.startswith("```"):
            response_text = response_text[len("```"):].strip()
            
        if response_text.endswith("```"):
            response_text = response_text[:-len("```")].strip()
            
        return response_text
    
    def _get_story_point_completion_time_template(self) -> str:
        """
        Get the template for story point completion time analysis.
        
        Returns:
            The story point completion time analysis template as a string
        """
        return '''
# Story Point Completion Time Analysis Template
import os
import re
from requests.auth import HTTPBasicAuth
import requests
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from typing import Dict, List, Any, Optional, Union
from urllib.parse import unquote
from collections import defaultdict
import statistics

# Configuration
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = unquote(os.environ.get("JIRA_API_TOKEN", "").strip())
STORY_POINTS_FIELD = os.environ.get("STORY_POINTS_FIELD", "customfield_10016")

def analyze(project_keys: List[str], time_period: str = "3m", story_point_values: List[int] = None, **kwargs) -> Dict[str, Any]:
    """
    Analyze the average completion time for stories with different story point values.
    
    Args:
        project_keys: List of Jira project keys to analyze
        time_period: Time period to analyze (e.g., "3m" for 3 months)
        story_point_values: List of story point values to analyze (e.g., [1, 2, 3, 5])
        **kwargs: Additional parameters
        
    Returns:
        Analysis results
    """
    # Default to common story point values if not specified
    if story_point_values is None:
        story_point_values = [1, 2, 3, 5, 8]
    
    # Parse time period
    end_date = datetime.now(timezone.utc)
    start_date = parse_time_period(end_date, time_period)
    
    results = {}
    
    for project_key in project_keys:
        # Fetch completed issues for the project in the time period
        issues = fetch_completed_issues(project_key, start_date, end_date)
        
        # Calculate completion times by story point value
        completion_times = calculate_completion_times(issues, story_point_values)
        
        results[project_key] = {
            "completion_times": completion_times,
            "time_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "description": time_period
            }
        }
    
    return results

def parse_time_period(end_date: datetime, time_period: str) -> datetime:
    """
    Parse a time period string into a start date.
    
    Args:
        end_date: The end date for the time period
        time_period: A string representing the time period (e.g., "3m" for 3 months)
        
    Returns:
        The start date for the time period
    """
    if not time_period:
        # Default to 3 months
        return end_date - timedelta(days=90)
    
    # Parse time period format (e.g., "1y", "6m", "2w", "30d")
    match = re.match(r'^(\d+)([ymwd])$', time_period.lower())
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == 'y':
            return end_date - timedelta(days=value * 365)
        elif unit == 'm':
            return end_date - timedelta(days=value * 30)
        elif unit == 'w':
            return end_date - timedelta(weeks=value)
        elif unit == 'd':
            return end_date - timedelta(days=value)
    
    # Handle "last X" format
    match = re.match(r'^last\s+(\d+)\s+(year|month|week|day)s?$', time_period.lower())
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == 'year':
            return end_date - timedelta(days=value * 365)
        elif unit == 'month':
            return end_date - timedelta(days=value * 30)
        elif unit == 'week':
            return end_date - timedelta(weeks=value)
        elif unit == 'day':
            return end_date - timedelta(days=value)
    
    # Default to 3 months if format not recognized
    return end_date - timedelta(days=90)

def fetch_completed_issues(project_key: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Fetch completed issues for a project in the specified time period.
    
    Args:
        project_key: The Jira project key
        start_date: Start date for the query
        end_date: End date for the query
        
    Returns:
        List of completed issues
    """
    # Format dates for JQL
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    # Build JQL query for completed issues
    jql = f'project = "{project_key}" AND status = Done AND resolutiondate >= "{start_date_str}" AND resolutiondate <= "{end_date_str}" AND {STORY_POINTS_FIELD} IS NOT EMPTY'
    
    # Fields to fetch
    fields = f"key,summary,status,created,resolutiondate,{STORY_POINTS_FIELD}"
    
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    issues = []
    start_at = 0
    max_results = 100
    
    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": jql,
            "fields": fields,
            "startAt": start_at,
            "maxResults": max_results
        }
        
        try:
            response = requests.get(url, auth=auth, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            batch_issues = data.get("issues", [])
            issues.extend(batch_issues)
            
            total = data.get("total", 0)
            if start_at + len(batch_issues) >= total:
                break
                
            start_at += len(batch_issues)
        except Exception as e:
            print(f"Error fetching issues: {str(e)}", flush=True)
            break
    
    return issues

def get_story_points(issue: Dict[str, Any]) -> Optional[int]:
    """
    Get the story points for an issue.
    
    Args:
        issue: The issue data
        
    Returns:
        The story points value, or None if not set
    """
    fields = issue.get("fields", {})
    story_points = fields.get(STORY_POINTS_FIELD)
    
    if story_points is not None:
        try:
            return int(float(story_points))
        except (ValueError, TypeError):
            pass
    
    return None

def calculate_completion_times(issues: List[Dict[str, Any]], story_point_values: List[int]) -> Dict[str, Any]:
    """
    Calculate completion times by story point value.
    
    Args:
        issues: List of completed issues
        story_point_values: List of story point values to analyze
        
    Returns:
        Dictionary of completion times by story point value
    """
    # Group issues by story point value
    issues_by_points = defaultdict(list)
    
    for issue in issues:
        story_points = get_story_points(issue)
        if story_points is not None and story_points in story_point_values:
            issues_by_points[story_points].append(issue)
    
    # Calculate completion times for each story point value
    completion_times = {}
    
    for points in story_point_values:
        point_issues = issues_by_points.get(points, [])
        
        if not point_issues:
            completion_times[str(points)] = {
                "count": 0,
                "avg_days": None,
                "median_days": None,
                "min_days": None,
                "max_days": None
            }
            continue
        
        # Calculate days to completion for each issue
        days_to_completion = []
        
        for issue in point_issues:
            created_date = date_parser.isoparse(issue["fields"]["created"])
            resolution_date = date_parser.isoparse(issue["fields"]["resolutiondate"])
            
            # Calculate days (including partial days)
            days = (resolution_date - created_date).total_seconds() / (24 * 60 * 60)
            days_to_completion.append(days)
        
        # Calculate statistics
        completion_times[str(points)] = {
            "count": len(point_issues),
            "avg_days": statistics.mean(days_to_completion) if days_to_completion else None,
            "median_days": statistics.median(days_to_completion) if days_to_completion else None,
            "min_days": min(days_to_completion) if days_to_completion else None,
            "max_days": max(days_to_completion) if days_to_completion else None
        }
    
    return completion_times
'''
