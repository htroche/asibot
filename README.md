# Asibot

**Asibot** is an open-source Slack bot that integrates with Jira to provide project metrics and initiative summaries via direct messages (DMs). Built with **Flask**, **OpenAI**, and the **Slack SDK**, it allows users to query Jira data in real-time by sending natural language messages directly to the bot. Whether you want sprint metrics for a project or a summary of issues with status changes for an initiative, Asibot responds in your DMs with a clean, formatted reply.

## Features

- **Direct Messages:** DM the bot with queries like `"metrics for XYZ last 3 sprints"` or `"summary of all issues in blocked status for initiative PROG-123 in the last 2 weeks"`.
- **Jira Integration:** Fetches project metrics and initiative issues, including status changes within a date range.
- **Pagination:** Handles >100 issues/epics with Jira’s API.
- **Slack Blocks:** Responses are formatted in a single Slack Block Kit section for clarity.
- **OpenAI-Powered:** Uses OpenAI to interpret queries and format responses dynamically.
- **Production-Ready:** Configurable debug mode and threading to handle Slack’s 3-second event timeout.

## Prerequisites

- **Python:** 3.9+ (tested with 3.9-slim in Docker).
- **Slack Workspace:** With admin access to create/install an app.
- **Jira Instance:** With API token access (e.g., Atlassian Cloud).
- **OpenAI Account:** With an API key.
- **Google Cloud Platform (GCP):** Optional, for Cloud Run deployment (or any hosting service).

## Installation

### 1. Clone the Repository

git clone https://github.com/htroche/Asibot.git
cd Asibot

### 2. Set Up Environment Variables

Create a .env file in the project root with these variables:


JIRA_BASE_URL=https://your-jira-instance.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token
OPENAI_API_KEY=your-openai-api-key
STORY_POINTS_FIELD=customfield_10025  # Your Jira story points field ID
SLACK_SIGNING_SECRET=your-slack-signing-secret
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
PYTHONUNBUFFERED=1  # For Cloud Run logging
Jira API Token: Generate at id.atlassian.com.
OpenAI API Key: From platform.openai.com.
Slack Secrets: See Slack Setup below.

### 3. Install Dependencies

pip install -r requirements.txt
Contents of requirements.txt:


flask==2.3.2
requests==2.31.0
slack-sdk==3.27.1
openai==1.10.0
python-dotenv==1.0.0

### 4. Slack Setup
**Create a Slack App**
Go to api.slack.com/apps and click Create New App > From scratch.
Name: "Asibot", Workspace: Your workspace.
Bot User
Navigate to Features > Bot Users and add a bot user (e.g., Display Name: "Asibot", Username: @Asibot).
OAuth Scopes
Go to OAuth & Permissions > Bot Token Scopes and add:
chat:write (to send messages as the bot)
im:read (to read DMs sent to the bot)
im:write (to open DM channels)
users:read (optional, to identify users)
Reinstall the app to your workspace after adding scopes.

Event Subscriptions
Go to Features > Event Subscriptions and enable Events.
Request URL: https://your-app-url.com/slack/events
Subscribe to Bot Events: message.im
Get Secrets
OAuth & Permissions: Copy the Bot User OAuth Token (xoxb-...) to SLACK_BOT_TOKEN.
Basic Information: Copy the Signing Secret to SLACK_SIGNING_SECRET.

### 5. Run Locally

python app.py
Default port: 5000. Set FLASK_DEBUG=true for debug mode locally.

### 6. Deploy to Production (Cloud Run)
Dockerfile
Copy
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]

### Build and Deploy

docker build --platform linux/amd64 -t asibot .
docker tag asibot gcr.io/your-project-id/asibot
docker push gcr.io/your-project-id/asibot
gcloud run deploy asibot \
  --image gcr.io/your-project-id/asibot \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "JIRA_BASE_URL=https://your-jira-instance.atlassian.net,JIRA_EMAIL=your-email@example.com,JIRA_API_TOKEN=your-api-token,OPENAI_API_KEY=your-openai-key,STORY_POINTS_FIELD=customfield_10016,SERVICE_BASE_URL=https://your-app-url.com,PYTHONUNBUFFERED=1,SLACK_SIGNING_SECRET=your-signing-secret,SLACK_BOT_TOKEN=xoxb-your-bot-token"
Replace your-project-id and your-app-url.com with your GCP project ID and deployed URL.

### Usage
**Direct Messages**
Example 1:
DM @Asibot: "metrics for XYZ last 3 sprints"
Returns sprint metrics for project XYZ.

Example 2:
DM @Asibot: "summary of all issues in blocked status for initiative PROG-123 in the last 2 weeks"
Summarizes issues with status changes to/from "Blocked" for PROG-123.

Example 3:
DM @Asibot: "What stories had their status changed last week for initiative PROG-123?"
Lists stories with status changes in the specified period.

Response Format
Responses are returned as a single Slack Block with clickable Jira links (e.g., <https://your-jira-instance.atlassian.net/browse/XYZ-123>).

### Project Structure
Asibot/
├── app.py              # Flask app with Slack event endpoint
├── openai_manager.py   # OpenAI and Jira logic
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container definition
├── .env                # Environment variables (not tracked)
└── README.md           # This file

### Configuration Details
Jira: Uses Parent Link and Epic Link for initiative-to-epic-to-issue hierarchy. Customize STORY_POINTS_FIELD if your Jira instance uses a different custom field.
OpenAI: Requires a valid API key and model (default: o3-mini).
Slack: Handles DMs via the Events API, with threading to avoid timeouts.
Troubleshooting
"Sending messages to this app has been turned off":
Ensure the bot user is added, scopes are set (im:read, im:write, chat:write), and the app is reinstalled.

Infinite Loop in DMs:
Verify that the bot_user_id filter is working (logs should show "Ignoring message from bot").

Timeout Errors:
Check logs for slow OpenAI/Jira calls; threading should mitigate this (endpoint returns within 3 seconds).

Debug Mode:
Don’t set FLASK_DEBUG in production (defaults to False).

### Contributing
Fork the Repo:
git fork https://github.com/yourusername/Asibot.git

Create a Branch:
git checkout -b feature/your-feature

Commit Changes:
git commit -m "Add your feature"

Push and PR:
git push origin feature/your-feature and open a pull request.

Issues: Report bugs or suggest features on GitHub Issues.
Code Style: Follow PEP 8; use comments for clarity.

### License
This project is licensed under the MIT License.

### Acknowledgments
Built with love by **Hugo Troche** using Python.