import os
import json
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta, timezone
from dateutil import parser
from dotenv import load_dotenv
from urllib.parse import unquote
from metrics_manager import get_metrics
import litellm
from litellm import completion
from typing import List, Dict, Any, Optional, Union

load_dotenv()

class LLMManager:
    def __init__(self):
        # Load configuration from environment variables
        self.provider = os.environ.get("LLM_PROVIDER", "openai").lower()
        self.model_map = {
            "openai": os.environ.get("OPENAI_MODEL", "o3-mini"),
            "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-3-opus-20240229"),
            # Add other providers as needed
        }
        
        # Set API keys for different providers
        # LiteLLM will automatically use the appropriate environment variables
        # OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
        
        # Configure default model
        self.model = self.get_model_string()
        
        # Configure fallbacks (optional)
        self.fallbacks = self.configure_fallbacks()
        
        # Load other configuration
        self.story_points_field = os.environ.get("STORY_POINTS_FIELD", "customfield_10025")
        self.jira_base_url = os.environ.get("JIRA_BASE_URL", "https://api.atlassian.net").strip()
        
        # Load Jira fields configuration
        default_fields = "key,summary,status,updated,description,issuetype"
        self.jira_fields = os.environ.get("JIRA_FIELDS", default_fields).strip()
        
        # Ensure story points field is included for backward compatibility
        if self.story_points_field not in self.jira_fields.split(','):
            self.jira_fields += f",{self.story_points_field}"
        
        # Define functions (same as in your current implementation)
        self.functions = [
            {
                "name": "get_project_metrics",
                "description": (
                    "Fetch sprint metrics for one or more Jira projects. Returns sprint details "
                    "for each project, including sprint name, description, committed vs completed points, "
                    "churn, and average velocity for closed sprints for the last N sprints."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_keys": {"type": "array", "items": {"type": "string"}},
                        "num_sprints": {"type": "integer", "default": 5}
                    },
                    "required": ["project_keys"]
                }
            },
            {
                "name": "get_initiative_summary",
                "description": (
                    "Fetch a summary of stories for a Jira initiative (e.g., ENG-123), including "
                    "finished stories and in-progress stories for a specified date range. "
                    "Includes all stories where the initiative is an ancestor."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "initiative_key": {"type": "string", "description": "The Jira initiative key (e.g., ENG-123)."},
                        "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format (e.g., 2025-02-01)."},
                        "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format (e.g., 2025-02-21), defaults to today if unspecified."}
                    },
                    "required": ["initiative_key"]
                }
            }
        ]
        
        # Training instructions (same as in your current implementation)
        self.training_instructions = (
            f"You are a helpful assistant that provides Jira data based on natural language requests. "
            f"The current date is {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. "
            f"The Jira base URL is '{self.jira_base_url}'. "
            f"In Jira data, the field '{self.story_points_field}' represents story points for each issue. "
            "For requests like 'Give me metrics for XYZ and SPRTEAM for the last 3 sprints', "
            "extract project keys (e.g., XYZ, SPRTEAM) and number of sprints, then use get_project_metrics. "
            "For any general questions about issues in an initiative over a time period, such as "
            "'Give me a summary of all issues in blocked status for initiative PROG-162 in the last 2 weeks' "
            "or 'What stories were finished for initiative ENG-123 last week', "
            "extract the initiative key (e.g., PROG-123) and interpret the date range relative to today "
            "(e.g., 'last week' means the 7 days ending today, 'last 2 weeks' means the 14 days ending today, "
            "'last month' means the 30 days ending today, or 'from 02/01 to 02/21' for specific dates). "
            "Convert the date range to start_date and end_date in YYYY-MM-DD format (end_date defaults to today "
            "if not specified), then use get_initiative_summary to fetch all issues linked to the initiative "
            "updated in that range with all available fields (e.g., key, summary, status, updated, description, story points). "
            "Analyze the full dataset to answer the request dynamically, filtering or summarizing based on the question "
            "(e.g., use the 'status' field to identify statuses like 'Blocked', 'Done', 'In Progress', etc., "
            "and include relevant details like summary, description, or story points as relevant). "
            "Whenever an issue key (e.g., 'XYZ-123') is included in the response, format it as a clickable link "
            f"using the Jira base URL, e.g., '<{self.jira_base_url}/browse/XYZ-123>' for XYZ-123. "
            "Format responses clearly with sections or lists in a way that Slack can render as clickable links. "
            "If the request is unclear, ask for clarification."
        )
    
    def get_model_string(self) -> str:
        """
        Get the fully qualified model string for LiteLLM.
        Format: provider/model
        """
        provider = self.provider
        model = self.model_map.get(provider, "")
        
        # For OpenAI, we don't need the provider prefix as LiteLLM can infer it
        if provider == "openai":
            return model
        
        return f"{provider}/{model}"
    
    def configure_fallbacks(self) -> List[str]:
        """
        Configure fallback models in case the primary model fails.
        """
        fallback_str = os.environ.get("LLM_FALLBACKS", "")
        if not fallback_str:
            return []
        
        fallbacks = []
        for fb in fallback_str.split(","):
            fb = fb.strip()
            if "/" not in fb:
                # If provider not specified, use default provider
                if self.provider == "openai":
                    # For OpenAI, we don't need the provider prefix
                    fallbacks.append(fb)
                else:
                    fallbacks.append(f"{self.provider}/{fb}")
            else:
                # If provider is specified, check if it's OpenAI
                provider, model = fb.split("/", 1)
                if provider.lower() == "openai":
                    # For OpenAI, we don't need the provider prefix
                    fallbacks.append(model)
                else:
                    fallbacks.append(fb)
        
        return fallbacks
    
    def switch_provider(self, provider: str) -> bool:
        """
        Switch to a different LLM provider.
        """
        if provider.lower() not in self.model_map:
            return False
        
        self.provider = provider.lower()
        self.model = self.get_model_string()
        return True
    
    def process_message(self, user_message: str, conversation: list = None) -> str:
        """
        Process a user message using the configured LLM provider.
        This is the main method that replaces the OpenAI-specific implementation.
        """
        messages = [{"role": "system", "content": self.training_instructions}]
        if conversation:
            messages.extend(conversation)
        messages.append({"role": "user", "content": user_message})

        try:
            # Use LiteLLM's completion function instead of direct OpenAI call
            response = completion(
                model=self.model,
                messages=messages,
                tools=[{"type": "function", "function": func} for func in self.functions],
                tool_choice="auto",
                fallbacks=self.fallbacks
            )
            
            message = response.choices[0].message

            # Handle potential differences in tool_calls format
            if hasattr(message, 'tool_calls') and message.tool_calls:
                followup_messages = messages + [{"role": "assistant", "content": None, "tool_calls": message.tool_calls}]
                all_data = {}

                for tool_call in message.tool_calls:
                    function_call = tool_call.function
                    try:
                        arguments = json.loads(function_call.arguments)
                    except Exception as e:
                        print(f"Error parsing function arguments: {e}", flush=True)
                        arguments = {}
                    
                    if function_call.name == "get_project_metrics":
                        project_keys = arguments.get("project_keys", [])
                        num_sprints = arguments.get("num_sprints", 5)
                        for project_key in project_keys:
                            metrics = get_metrics(project_key, num_sprints)
                            all_data[project_key] = metrics
                            

                    elif function_call.name == "get_initiative_summary":
                        initiative_key = arguments.get("initiative_key", "")
                        start_date = arguments.get("start_date", "")
                        end_date = arguments.get("end_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                        all_data = self.fetch_initiative_summary(initiative_key, start_date, end_date)

                    followup_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(all_data)
                    })

                # Use LiteLLM for the followup call as well
                followup = completion(
                    model=self.model,
                    messages=followup_messages,
                    fallbacks=self.fallbacks
                )
                return followup.choices[0].message.content
            elif hasattr(message, 'function_call') and message.function_call:  # For older OpenAI format
                # Handle legacy function_call format
                function_call = message.function_call
                followup_messages = messages + [{"role": "assistant", "content": None, "function_call": function_call}]
                all_data = {}
                
                try:
                    arguments = json.loads(function_call.arguments)
                except Exception as e:
                    print(f"Error parsing function arguments: {e}", flush=True)
                    arguments = {}
                
                if function_call.name == "get_project_metrics":
                    project_keys = arguments.get("project_keys", [])
                    num_sprints = arguments.get("num_sprints", 5)
                    for project_key in project_keys:
                        metrics = get_metrics(project_key, num_sprints)
                        all_data[project_key] = metrics
                        
                elif function_call.name == "get_initiative_summary":
                    initiative_key = arguments.get("initiative_key", "")
                    start_date = arguments.get("start_date", "")
                    end_date = arguments.get("end_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                    all_data = self.fetch_initiative_summary(initiative_key, start_date, end_date)
                
                followup_messages.append({
                    "role": "function",
                    "name": function_call.name,
                    "content": json.dumps(all_data)
                })
                
                # Use LiteLLM for the followup call as well
                followup = completion(
                    model=self.model,
                    messages=followup_messages,
                    fallbacks=self.fallbacks
                )
                return followup.choices[0].message.content
            else:
                return message.content
                
        except Exception as e:
            # Log the specific error
            error_type = type(e).__name__
            print(f"LLM API error ({self.provider}): {error_type}: {str(e)}", flush=True)
            
            # Try fallback if not already using fallbacks
            if not self.fallbacks and self.provider != "openai":
                print(f"Attempting fallback to OpenAI due to {error_type}", flush=True)
                original_provider = self.provider
                self.provider = "openai"
                self.model = self.get_model_string()
                try:
                    result = self.process_message(user_message, conversation)
                    self.provider = original_provider  # Reset to original provider
                    self.model = self.get_model_string()
                    return result
                except Exception as fallback_error:
                    print(f"Fallback also failed: {str(fallback_error)}", flush=True)
                    self.provider = original_provider  # Reset to original provider
                    self.model = self.get_model_string()
            
            return f"I encountered an error: {str(e)}"
    
    def fetch_initiative_summary(self, initiative_key: str, start_date: str, end_date: str) -> dict:
        """
        Fetch a summary of stories for a Jira initiative.
        This method is the same as in the OpenAIManager class.
        """
        jira_base_url = os.environ.get("JIRA_BASE_URL").strip()
        jira_email = os.environ.get("JIRA_EMAIL").strip()
        jira_api_token = unquote(os.environ.get("JIRA_API_TOKEN", "").strip())
        headers = {"Accept": "application/json"}
        auth = HTTPBasicAuth(jira_email, jira_api_token)

        # Parse date range for comparison
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as e:
            print(f"Date parsing error: {str(e)}", flush=True)
            return {"error": f"Invalid date format: {str(e)}. Use YYYY-MM-DD."}

        # Step 1: Get Epics linked to the initiative via "Parent Link"
        jql_epics = f'"Parent Link" = {initiative_key}'
        search_url = f"{jira_base_url}/rest/api/3/search"
        params = {
            "jql": jql_epics,
            "fields": "key",
            "maxResults": 100,
            "startAt": 0
        }

        epic_keys = []
        try:
            while True:
                response = requests.get(search_url, auth=auth, headers=headers, params=params)
                print(f"Epic search URL: {response.request.url}", flush=True)
                response.raise_for_status()
                data = response.json()
                epics = data.get("issues", [])
                epic_keys.extend(epic["key"] for epic in epics)
                print(f"Found {len(epics)} epics in this batch, total so far: {len(epic_keys)}", flush=True)

                total = data.get("total", 0)
                if params["startAt"] + len(epics) >= total:
                    break
                params["startAt"] += len(epics)
        except requests.RequestException as e:
            print(f"Jira API error fetching epics: {str(e)}", flush=True)
            return {"error": str(e)}

        # Step 2: Get issues linked to those Epics updated in the date range
        if not epic_keys:
            return {
                "issues": [],
                "message": "No epics found for this initiative."
            }

        jql_issues = f'"Epic Link" in ({",".join(epic_keys)}) AND updated >= "{start_date}" AND updated <= "{end_date}"'
        params["jql"] = jql_issues
        params["fields"] = self.jira_fields
        params["startAt"] = 0

        updated_issues = []
        try:
            while True:
                response = requests.get(search_url, auth=auth, headers=headers, params=params)
                print(f"Initial issue search URL: {response.request.url}", flush=True)
                response.raise_for_status()
                data = response.json()
                issues = data.get("issues", [])
                updated_issues.extend(issues)
                print(f"Found {len(issues)} updated issues in this batch, total so far: {len(updated_issues)}", flush=True)

                total = data.get("total", 0)
                if params["startAt"] + len(issues) >= total:
                    break
                params["startAt"] += len(issues)
        except requests.RequestException as e:
            print(f"Jira API error fetching updated issues: {str(e)}", flush=True)
            return {"error": str(e)}

        # Step 3: Refine to issues with status changes in the date range using changelog
        filtered_issues = []
        for issue in updated_issues:
            issue_key = issue["key"]
            changelog_url = f"{jira_base_url}/rest/api/3/issue/{issue_key}/changelog"
            try:
                response = requests.get(changelog_url, auth=auth, headers=headers)
                print(f"Changelog URL for {issue_key}: {response.request.url}", flush=True)
                response.raise_for_status()
                changelog_data = response.json()
                histories = changelog_data.get("values", [])

                # Check if status changed within the date range
                for history in histories:
                    created = datetime.strptime(history["created"], "%Y-%m-%dT%H:%M:%S.%f%z")
                    if start <= created <= end:
                        for item in history.get("items", []):
                            if item["field"] == "status":
                                filtered_issues.append(issue)
                                print(f"Status change detected for {issue_key} on {history['created']}", flush=True)
                                break  # Stop checking this issue once a status change is found
                        if issue in filtered_issues:
                            break  # Move to next issue if already added

            except requests.RequestException as e:
                print(f"Jira API error fetching changelog for {issue_key}: {str(e)}", flush=True)
                # Skip this issue on error, continue with others

        print(f"Filtered to {len(filtered_issues)} issues with status changes between {start_date} and {end_date}", flush=True)
        return {"issues": filtered_issues}
