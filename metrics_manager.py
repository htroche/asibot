
import os
import concurrent.futures
from requests.auth import HTTPBasicAuth
import requests
from datetime import datetime, timedelta, timezone
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


def get_issue_changelog_batch(issue_keys, max_workers=10):
    """
    Fetch changelogs for multiple issues in parallel.
    
    Args:
        issue_keys: List of issue keys to fetch changelogs for
        max_workers: Maximum number of parallel requests
        
    Returns:
        Dictionary mapping issue keys to their changelogs
    """
    changelogs = {}
    
    def fetch_single_changelog(issue_key):
        url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/changelog"
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(
                url, 
                auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                headers=headers
            )
            if response.status_code == 200:
                return issue_key, response.json()
            else:
                print(f"Error fetching changelog for {issue_key}: {response.status_code}", flush=True)
                return issue_key, None
        except Exception as e:
            print(f"Exception fetching changelog for {issue_key}: {str(e)}", flush=True)
            return issue_key, None
    
    # Use ThreadPoolExecutor to fetch changelogs in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all requests
        future_to_key = {
            executor.submit(fetch_single_changelog, key): key 
            for key in issue_keys
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_key):
            key, changelog = future.result()
            if changelog:
                changelogs[key] = changelog
    
    return changelogs



def calculate_metrics_for_sprint(issues, sprint_start_date, sprint_end_date, batch_size=20, max_workers=10):
    """
    Calculate metrics for a sprint, counting only issues that were completed during the sprint.
    Uses batch processing and parallel requests for changelog fetching.
    
    Args:
        issues: List of issues in the sprint
        sprint_start_date: Start date of the sprint
        sprint_end_date: End date of the sprint
        batch_size: Number of issues to process in each batch
        max_workers: Maximum number of parallel requests
    """
    total_committed_issues = 0
    committed_points = 0.0
    completed_points = 0.0
    completed_issues = 0
    
    # First pass: Count all committed issues and identify potentially completed ones
    potentially_done_issues = []
    
    for issue in issues:
        issue_key = issue.get("key")
        total_committed_issues += 1
        fields = issue.get("fields", {})
        story_points = fields.get(STORY_POINTS_FIELD) or 0
        try:
            story_points = float(story_points)
        except (ValueError, TypeError):
            story_points = 0
            
        committed_points += story_points
        
        # Check if issue is currently done - if so, we need to verify when it was completed
        status = fields.get("status", {})
        status_category = status.get("statusCategory", {})
        if status_category.get("key", "").lower() == "done":
            potentially_done_issues.append({
                "key": issue_key,
                "story_points": story_points,
                "issue": issue
            })
    
    print(f"Found {len(potentially_done_issues)} potentially completed issues out of {total_committed_issues} total issues", flush=True)
    
    # Process potentially done issues in batches
    for i in range(0, len(potentially_done_issues), batch_size):
        batch = potentially_done_issues[i:i+batch_size]
        batch_keys = [issue["key"] for issue in batch]
        
        print(f"Processing batch {i//batch_size + 1} with {len(batch)} issues", flush=True)
        
        # Fetch changelogs for this batch in parallel
        changelogs_batch = get_issue_changelog_batch(batch_keys, max_workers)
        
        # Process each issue in the batch
        for issue_data in batch:
            issue_key = issue_data["key"]
            story_points = issue_data["story_points"]
            
            changelog = changelogs_batch.get(issue_key)
            if changelog:
                # Check if issue was completed during this sprint
                completed_in_sprint = False
                
                for history in changelog.get("values", []):
                    created_str = history.get("created")
                    if not created_str:
                        continue
                        
                    try:
                        created = date_parser.isoparse(created_str)
                        
                        # Check if this change happened during the sprint
                        if sprint_start_date <= created <= sprint_end_date:
                            for item in history.get("items", []):
                                if item.get("field") == "status":
                                    to_status = item.get("toString", "")
                                    to_status_lower = to_status.lower()
                                    
                                    # Check if this transition was to a "Done" status
                                    # Adjust these keywords based on your Jira workflow
                                    done_keywords = ["done", "closed", "complete", "resolved", "finished"]
                                    if any(keyword in to_status_lower for keyword in done_keywords):
                                        completed_in_sprint = True
                                        break
                            
                            if completed_in_sprint:
                                break
                    except Exception as e:
                        print(f"Error parsing changelog date for {issue_key}: {str(e)}", flush=True)
                
                if completed_in_sprint:
                    completed_points += story_points
                    completed_issues += 1
                    print(f"Issue {issue_key} was completed during the sprint", flush=True)
                else:
                    print(f"Issue {issue_key} is done now but was NOT completed during the sprint", flush=True)
    
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

        # Parse sprint end date
        sprint_end_str = sprint.get("endDate")
        sprint_end_date = None
        if sprint_end_str:
            try:
                sprint_end_date = date_parser.isoparse(sprint_end_str)
            except Exception as e:
                print(f"Error parsing sprint end date: {e}", flush=True)
                sprint_end_date = None
        
        # For active sprints, use current time as end date
        if not sprint_end_date:
            sprint_end_date = datetime.now(timezone.utc)
            print(f"Using current time as end date for active sprint", flush=True)
        
        issues, code, msg = get_jira_issues_for_sprint(sprint_id, board_id)
        if code != 200:
            sprint_results.append({
                "sprint_id": sprint_id,
                "sprint_name": sprint.get("name"),
                "error": msg
            })
            continue
        
        print(f"Processing sprint: {sprint.get('name')}", flush=True)
        print(f"Sprint dates: {sprint_start_date} to {sprint_end_date}", flush=True)
        
        # Use the updated function with batch processing and parallel requests
        metrics = calculate_metrics_for_sprint(
            issues, 
            sprint_start_date, 
            sprint_end_date,
            batch_size=20,
            max_workers=10
        )

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
