import os
import json
import requests
from requests.auth import HTTPBasicAuth
from openai import OpenAI
from datetime import datetime, timedelta, timezone
from dateutil import parser
from dotenv import load_dotenv
from urllib.parse import unquote
from metrics_manager import get_metrics

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

class OpenAIManager:
    def __init__(self):
        self.model = "o3-mini"
        self.story_points_field = os.environ.get("STORY_POINTS_FIELD", "customfield_10025")
        self.jira_base_url = os.environ.get("JIRA_BASE_URL", "https://api.atlassian.net").strip()  
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

    def process_message(self, user_message: str, conversation: list = None) -> str:
        messages = [{"role": "system", "content": self.training_instructions}]
        if conversation:
            messages.extend(conversation)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[{"type": "function", "function": func} for func in self.functions],
            tool_choice="auto"
        )
        message = response.choices[0].message

        if message.tool_calls:
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

            followup = client.chat.completions.create(
                model=self.model,
                messages=followup_messages
            )
            return followup.choices[0].message.content
        else:
            return message.content

    def fetch_initiative_summary(self, initiative_key: str, start_date: str, end_date: str) -> dict:
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
        params["fields"] = f"key,summary,status,updated,description,issuetype,{os.environ.get('STORY_POINTS_FIELD', 'customfield_10025').strip()}"
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