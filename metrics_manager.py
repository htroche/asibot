
import os
from requests.auth import HTTPBasicAuth
import requests
from datetime import datetime, timedelta
from dateutil import parser as date_parser 

from dotenv import load_dotenv
load_dotenv()

from urllib.parse import unquote


# --------------------------
# Configuration – adjust these values!
# --------------------------
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = unquote(os.environ.get("JIRA_API_TOKEN", "").strip())
# Set the custom field key for Story Points. (This value may vary per Jira instance.)
STORY_POINTS_FIELD = os.environ.get("STORY_POINTS_FIELD", "customfield_10016")

def get_board_for_project(project_key):
    """
    Retrieve boards associated with a given project using the Jira Agile API.
    Returns the first board found.
    """
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board"
    params = {"projectKeyOrId": project_key}
    headers = {"Accept": "application/json"}
    response = requests.get(url, params=params,
                            auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                            headers=headers)
    if response.status_code != 200:
        return None, response.status_code, response.text
    data = response.json()
    boards = data.get("values", [])
    if not boards:
        return None, 404, f"No board found for project {project_key}"
    return boards[0], 200, "OK"

def get_active_sprints(board_id, max_results=50):
    """
    Retrieve active sprints for a given board using the Jira Agile API.
    """
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint"
    params = {"state": "active", "maxResults": max_results}
    headers = {"Accept": "application/json"}
    response = requests.get(url, params=params,
                            auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                            headers=headers)
    if response.status_code != 200:
        return None, response.status_code, response.text
    data = response.json()
    sprints = data.get("values", [])
    return sprints, 200, "OK"

def get_closed_sprints(board_id, max_results=50):
    """
    Retrieve closed sprints for a given board using the Jira Agile API.
    """
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint"
    params = {"state": "closed", "maxResults": max_results}
    headers = {"Accept": "application/json"}
    response = requests.get(url, params=params,
                            auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                            headers=headers)
    if response.status_code != 200:
        return None, response.status_code, response.text
    data = response.json()
    sprints = data.get("values", [])
    return sprints, 200, "OK"

def get_all_sprints(board_id, state="closed", page_size=50):
    """
    Retrieve all sprints for a given board and state (e.g. "closed" or "active")
    by paginating through the Jira Agile API.
    """
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint"
    start_at = 0
    all_sprints = []
    
    while True:
        params = {"state": state, "startAt": start_at, "maxResults": page_size}
        headers = {"Accept": "application/json"}
        response = requests.get(url, params=params,
                                auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                                headers=headers)
        if response.status_code != 200:
            return None, response.status_code, response.text
        
        data = response.json()
        sprints = data.get("values", [])
        all_sprints.extend(sprints)
        
        total = data.get("total", 0)
        # If we have fetched all sprints, break out of the loop.
        if start_at + page_size >= total:
            break
        
        start_at += page_size

    return all_sprints, 200, "OK"

def get_jira_issues_for_sprint(sprint_id, board_id):
    """
    Retrieve all Story issues for a given sprint using the Agile endpoint.
    
    This function first retrieves the board (using the project key) to determine the boardId,
    and then uses the endpoint:
        /rest/agile/1.0/board/{boardId}/sprint/{sprintId}/issue
    to fetch all issues in the sprint.
    """

    issues = []
    start_at = 0
    max_results = 50
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint/{sprint_id}/issue"
    headers = {"Accept": "application/json"}
    
    while True:
        params = {
            "startAt": start_at,
            "maxResults": max_results
        }
        response = requests.get(url, params=params,
                                auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                                headers=headers)
        if response.status_code != 200:
            return None, response.status_code, response.text
        
        data = response.json()
        issues.extend(data.get("issues", []))
        total = data.get("total", 0)
        if start_at + max_results >= total:
            break
        start_at += max_results

    return issues, 200, "OK"



def calculate_metrics_for_sprint(issues):
    """
    Calculate metrics for a sprint using the baseline date (sprint start + 2 days).
    
    - Committed story points are summed only for issues that were in the sprint as of the baseline date.
    - Completed points are summed from those committed issues that are in a "done" status.
    """
    total_committed_issues = 0
    committed_points = 0.0
    completed_points = 0.0
    completed_issues = 0

    for issue in issues:

        total_committed_issues += 1
        fields = issue.get("fields", {})
        story_points = fields.get(STORY_POINTS_FIELD) or 0
        try:
            story_points = float(story_points)
        except (ValueError, TypeError):
            story_points = 0

        committed_points += story_points

        status = fields.get("status", {})
        status_category = status.get("statusCategory", {})
        if status_category.get("key", "").lower() == "done":
            completed_points += story_points
            completed_issues += 1

    velocity = completed_points
    churn = committed_points - completed_points
    churn_rate = (churn / committed_points * 100) if committed_points > 0 else 0

    return {
        "total_committed_issues": total_committed_issues,
        "committed_points": committed_points,
        "completed_issues": completed_issues,
        "completed_points": completed_points,
        "velocity": velocity,
        "churn": churn,
        "churn_rate_percentage": churn_rate
    }


def get_metrics(project_key, num_sprints=5):
    """
    Returns sprint metrics for the last n sprints for the given project.
    
    "Last" is defined as:
      - The currently active sprint (if one exists)
      - The most recent closed sprints (i.e. those with end dates closest to today)
    
    For each sprint, committed story points are calculated as the sum of story points
    for issues that were in the sprint two days after its start (i.e. after the sprint backlog
    is effectively "frozen"). This helps account for issues added or removed during the sprint.
    """

    # Step 1: Get a board for this project.
    board, code, msg = get_board_for_project(project_key)
    if code != 200:
        return {"error": msg}, code
    board_id = board.get("id")

    # Step 2: Retrieve active and closed sprints.
    active_sprints, code_active, msg_active = get_active_sprints(board_id)
    if code_active != 200 or not active_sprints:
        active_sprint = None
    else:
        # Assume only one active sprint exists.
        active_sprint = active_sprints[0]

    closed_sprints, code_closed, msg_closed = get_all_sprints(board_id)
    if code_closed != 200:
        return {"error": msg_closed}, code_closed

    # Combine the active sprint (if present) with the closed sprints.
    combined_sprints = []
    if active_sprint:
        combined_sprints.append(active_sprint)
    # Sort closed sprints descending by endDate (most recent first)
    closed_sprints_sorted = sorted(
        closed_sprints,
        key=lambda s: date_parser.isoparse(s.get("endDate")) if s.get("endDate") else datetime.min,
        reverse=True
    )
    combined_sprints.extend(closed_sprints_sorted)
    # Take only the first num_sprints
    selected_sprints = combined_sprints[:num_sprints]

    sprint_results = []
    for sprint in selected_sprints:
        sprint_id = sprint.get("id")
        sprint_start_str = sprint.get("startDate")
        if sprint_start_str:
            try:
                sprint_start_date = date_parser.isoparse(sprint_start_str)
            except Exception:
                sprint_start_date = None
        else:
            sprint_start_date = None

        if sprint_start_date:
            baseline_date = sprint_start_date + timedelta(days=1)
        else:
            baseline_date = None

        issues, code, msg = get_jira_issues_for_sprint(sprint_id, board_id)
        if code != 200:
            sprint_results.append({
                "sprint_id": sprint_id,
                "sprint_name": sprint.get("name"),
                "error": msg
            })
            continue
        
        metrics = calculate_metrics_for_sprint(issues)

        sprint_info = {
            "sprint_id": sprint_id,
            "sprint_name": sprint.get("name"),
            "state": sprint.get("state"),
            "startDate": sprint.get("startDate"),
            "endDate": sprint.get("endDate"),
            "baseline_date": baseline_date.isoformat() if baseline_date else None,
            "metrics": metrics
        }
        sprint_results.append(sprint_info)
    
    # Calculate the average velocity only for closed sprints.
    closed_velocities = []
    for sprint in sprint_results:
        if sprint.get("state") == "closed":
            metrics = sprint.get("metrics", {})
            velocity = metrics.get("velocity")
            if velocity is not None:
                closed_velocities.append(velocity)

    average_velocity = sum(closed_velocities) / len(closed_velocities) if closed_velocities else 0


    result = {
        "project": project_key,
        "board": {"id": board_id, "name": board.get("name")},
        "sprints_analyzed": len(sprint_results),
        "sprints": sprint_results,
        "average_velocity": average_velocity
    }
    return result