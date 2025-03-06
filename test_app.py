import pytest
from metrics_manager import calculate_metrics_for_sprint, STORY_POINTS_FIELD

# Test data: a list of issues and the expected metric results.
# In this test:
# - Issue 1: 3 story points and "done" status.
# - Issue 2: 5 story points and not "done".
# - Issue 3: None (treated as 0) and "done" status.
# Therefore:
#   total_committed_issues = 3
#   committed_points = 3 + 5 + 0 = 8.0
#   completed_points = 3 (only Issue 1 counts) => velocity = 3.0
#   churn = 8.0 - 3.0 = 5.0
#   churn_rate_percentage = (5.0/8.0)*100 = 62.5
@pytest.mark.parametrize("issues, expected", [
    (
        [
            {
                "fields": {
                    "summary": "Issue 1",
                    STORY_POINTS_FIELD: 3,
                    "status": {
                        "name": "Done",
                        "statusCategory": {"key": "done"}
                    }
                }
            },
            {
                "fields": {
                    "summary": "Issue 2",
                    STORY_POINTS_FIELD: 5,
                    "status": {
                        "name": "In Progress",
                        "statusCategory": {"key": "in_progress"}
                    }
                }
            },
            {
                "fields": {
                    "summary": "Issue 3",
                    STORY_POINTS_FIELD: None,
                    "status": {
                        "name": "Done",
                        "statusCategory": {"key": "done"}
                    }
                }
            },
        ],
        {
            "total_committed_issues": 3,
            "committed_points": 8.0,
            "completed_issues": 2,
            "completed_points": 3.0,
            "velocity": 3.0,
            "churn": 5.0,
            "churn_rate_percentage": 62.5
        }
    ),
    # Additional test cases can be added here.
])

def test_calculate_metrics_for_sprint(issues, expected):
    result = calculate_metrics_for_sprint(issues)
    
    # For floating point comparisons, use pytest.approx
    assert result["total_committed_issues"] == expected["total_committed_issues"]
    assert result["committed_points"] == pytest.approx(expected["committed_points"])
    assert result["completed_issues"] == expected["completed_issues"]
    assert result["completed_points"] == pytest.approx(expected["completed_points"])
    assert result["velocity"] == pytest.approx(expected["velocity"])
    assert result["churn"] == pytest.approx(expected["churn"])
    assert result["churn_rate_percentage"] == pytest.approx(expected["churn_rate_percentage"])

