import os
import threading
import requests
import json
import csv
from io import StringIO
from datetime import datetime, timedelta
from dateutil import parser as date_parser 
from flask import Flask, jsonify, request
from requests.auth import HTTPBasicAuth
from openai_manager import *
from slack_sdk.signature import SignatureVerifier
from slack_sdk import WebClient
signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
verifier = SignatureVerifier(signing_secret)
slack_token = os.environ.get("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

from dotenv import load_dotenv
load_dotenv()


DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "t") 

app = Flask(__name__)

openai_manager = OpenAIManager()


@app.route("/assistant", methods=["POST"])
def assistant_endpoint():
    if not DEBUG:
        return 'Not found', 404
    data = request.get_json()
    user_message = data.get("message", "")
    conversation = data.get("conversation", [])
    response_text = openai_manager.process_message(user_message, conversation)
    return jsonify({"response": response_text})

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return jsonify({"text": "Invalid request - not from Slack"}), 403

    data = request.json
    if "challenge" in data:  # Slack URL verification
        return jsonify({"challenge": data["challenge"]})

    if "event" in data and data["event"]["type"] == "message" and data["event"]["channel_type"] == "im":
        event = data["event"]
        user_id = event.get("user")  # User ID (e.g., "U12345678")
        bot_id = event.get("bot_id")  # Bot ID (e.g., "B12345678") if sent by a bot
        text = event["text"]
        channel = event["channel"]  # DM channel ID

        #print(f"Received event: {json.dumps(event)}", flush=True)

        # Ignore messages from bots (including ourselves)
        # Note: Assuming bot_user_id is set globally as in previous examples
        if bot_id or (user_id and user_id == bot_id):
            print(f"Ignoring message from bot (user_id: {user_id}, bot_id: {bot_id})", flush=True)
            return jsonify({"status": "ignored"}), 200

        # Process and respond in a separate thread
        def process_dm():
            try:
                response_text = openai_manager.process_message(text)
                client.chat_postMessage(
                    channel=channel,
                    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": response_text}}]
                )
                print(f"Sent response to {channel}: {response_text}", flush=True)
            except Exception as e:
                error_text = f"*Error:* {str(e)}"
                client.chat_postMessage(
                    channel=channel,
                    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": error_text}}]
                )
                print(f"Error processing DM: {str(e)}", flush=True)

        threading.Thread(target=process_dm).start()
        immediate_response = {
            "response_type": "ephemeral",
            "text": "Fetching data from Jira... Please wait."
        }
        return jsonify(immediate_response), 200  # Return immediately

    return jsonify({"status": "ok"}), 200


# --------------------------
# Main Entry Point
# --------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))  # Default to 5000 locally, use PORT in Cloud Run
    app.run(debug=DEBUG, host='0.0.0.0', port=port)
