# Asibot

**Asibot** is an open-source Slack bot that integrates with Jira to provide project metrics and initiative summaries via direct messages (DMs). Built with **Flask**, **LiteLLM**, and the **Slack SDK**, it allows users to query Jira data in real-time by sending natural language messages directly to the bot. Whether you want sprint metrics for a project or a summary of issues with status changes for an initiative, Asibot responds in your DMs with a clean, formatted reply.

## Features

- **Direct Messages:** DM the bot with queries like `"metrics for XYZ last 3 sprints"` or `"summary of all issues in blocked status for initiative PROG-123 in the last 2 weeks"`.
- **Processing Indicators:** Multiple visual cues (reactions, typing indicator, and status messages) show when the bot is processing a request.
- **Jira Integration:** Fetches project metrics and initiative issues, including status changes within a date range.
- **Pagination:** Handles >100 issues/epics with Jira's API.
- **Slack Blocks:** Responses are formatted in a single Slack Block Kit section for clarity.
- **LLM-Agnostic:** Supports multiple LLM providers (OpenAI, Anthropic Claude, etc.) to interpret queries and format responses dynamically.
- **Production-Ready:** Configurable debug mode and threading to handle Slack's 3-second event timeout.

## Prerequisites

- **Python:** 3.9+ (tested with 3.9-slim in Docker).
- **Slack Workspace:** With admin access to create/install an app.
- **Jira Instance:** With API token access (e.g., Atlassian Cloud).
- **LLM Provider Account:** With an API key (OpenAI, Anthropic, etc.).
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

STORY_POINTS_FIELD=customfield_10025  # Your Jira story points field ID

JIRA_FIELDS=key,summary,status,updated,description,issuetype,customfield_10025  # Comma-separated list of Jira fields to fetch

SLACK_SIGNING_SECRET=your-slack-signing-secret

SLACK_BOT_TOKEN=xoxb-your-slack-bot-token

PYTHONUNBUFFERED=1  # For Cloud Run logging

### LLM Configuration
LLM_PROVIDER=openai  # or anthropic, etc.

OPENAI_API_KEY=your-openai-api-key

OPENAI_MODEL=o3-mini

ANTHROPIC_API_KEY=your-anthropic-key

ANTHROPIC_MODEL=claude-3-opus-20240229

LLM_FALLBACKS=anthropic/claude-3-haiku-20240307,openai/gpt-3.5-turbo

Jira API Token: Generate at id.atlassian.com.
LLM API Keys: From respective provider platforms (platform.openai.com, console.anthropic.com, etc.).
Slack Secrets: See Slack Setup below.

### 3. Install Dependencies

pip install -r requirements.txt
Contents of requirements.txt:


flask==2.3.2
requests==2.31.0
slack-sdk==3.27.1
openai==1.10.0
python-dotenv==1.0.0
litellm>=1.10.0

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
reactions:write (to add reaction emojis to messages)
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

### Dockerfile
```
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

### Build and Deploy

#### Option 1: Using the example deployment script
We provide an example deployment script that uses your `.env` file for environment variables:

1. Copy the example script to create your own deployment script:
   ```bash
   cp example.deploy_google.sh deploy_google.sh
   ```

2. Edit the script to replace placeholders with your actual values:
   - `YOUR_PROJECT_ID` - Your Google Cloud project ID
   - `YOUR_APP_NAME` - Your application name (e.g., asibot)
   - `YOUR_SERVICE_NAME` - Your Cloud Run service name (e.g., asibot-service)
   - `YOUR_REGION` - Your desired region (e.g., us-central1)

3. Make the script executable and run it:
   ```bash
   chmod +x deploy_google.sh
   ./deploy_google.sh
   ```

This script automatically converts your `.env` file to the YAML format required by Google Cloud Run, so you can manage all your environment variables in one place.

#### Option 2: Manual deployment
```bash
docker build --platform linux/amd64 -t asibot .
docker tag asibot gcr.io/your-project-id/asibot
docker push gcr.io/your-project-id/asibot
gcloud run deploy asibot \
  --image gcr.io/your-project-id/asibot \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "JIRA_BASE_URL=https://your-jira-instance.atlassian.net,JIRA_EMAIL=your-email@example.com,JIRA_API_TOKEN=your-api-token,LLM_PROVIDER=openai,OPENAI_API_KEY=your-openai-key,OPENAI_MODEL=o3-mini,STORY_POINTS_FIELD=customfield_10016,JIRA_FIELDS=key,summary,status,updated,description,issuetype,SERVICE_BASE_URL=https://your-app-url.com,PYTHONUNBUFFERED=1,SLACK_SIGNING_SECRET=your-signing-secret,SLACK_BOT_TOKEN=xoxb-your-bot-token"
```

Replace your-project-id and your-app-url.com with your GCP project ID and deployed URL.

### Usage
**Processing Indicators**
When a user sends a message to the bot, they will see multiple indicators that their request is being processed:
1. An hourglass emoji (⏳) reaction is added to their message
2. The bot shows a typing indicator
3. An initial "Processing your request..." message appears
4. Once processing is complete:
   - The initial message is updated with the response
   - The hourglass reaction is replaced with a checkmark (✅)
   - The typing indicator stops
5. If an error occurs:
   - The error message is displayed
   - The hourglass reaction is replaced with an X (❌)

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
├── llm_manager.py      # LLM abstraction layer for multiple providers
├── metrics_manager.py  # Jira metrics logic
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container definition
├── .env                # Environment variables (not tracked)
├── example.deploy_google.sh # Example deployment script for Google Cloud Run
└── README.md           # This file

### Configuration Details
Jira: Uses Parent Link and Epic Link for initiative-to-epic-to-issue hierarchy. 

- **STORY_POINTS_FIELD**: Customize if your Jira instance uses a different custom field for story points.
- **JIRA_FIELDS**: Configure which fields to fetch from Jira. This is a comma-separated list of field names (e.g., `key,summary,status,updated,description,issuetype`). The story points field will be automatically included if not already in the list.

LLM Providers: The application supports multiple LLM providers through LiteLLM:
- OpenAI (default): Set `LLM_PROVIDER=openai` and configure `OPENAI_API_KEY` and `OPENAI_MODEL`
- Anthropic Claude: Set `LLM_PROVIDER=anthropic` and configure `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`
- Fallbacks: Configure `LLM_FALLBACKS` with comma-separated list of models to try if the primary model fails

Slack: Handles DMs via the Events API, with threading to avoid timeouts.

Troubleshooting
"Sending messages to this app has been turned off":
Ensure the bot user is added, scopes are set (im:read, im:write, chat:write), and the app is reinstalled.

Infinite Loop in DMs:
Verify that the bot_user_id filter is working (logs should show "Ignoring message from bot").

Timeout Errors:
Check logs for slow LLM/Jira calls; threading should mitigate this (endpoint returns within 3 seconds).

Debug Mode:
Don't set FLASK_DEBUG in production (defaults to False).

### Contributing
Fork the Repo:
git fork https://github.com/htroche/Asibot.git

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
