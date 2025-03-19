import os
import threading
import requests
import json
import csv
import time
from io import StringIO
from datetime import datetime, timedelta
from dateutil import parser as date_parser 
from flask import Flask, jsonify, request, send_from_directory
from requests.auth import HTTPBasicAuth
from llm_manager import LLMManager
from slack_sdk.signature import SignatureVerifier
from slack_sdk import WebClient
from threading import Lock

signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
verifier = SignatureVerifier(signing_secret)
slack_token = os.environ.get("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

from dotenv import load_dotenv
load_dotenv()

# Message deduplication cache
processed_messages = {}
MESSAGE_CACHE_SIZE = 100
message_cache_lock = Lock()


DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "t") 

app = Flask(__name__, static_folder='static')

llm_manager = LLMManager()

@app.route("/", methods=["GET"])
def index():
    if not DEBUG:
        return 'Not found', 404
    """
    Serve the chat interface HTML page.
    """
    return send_from_directory(app.static_folder, 'index.html')

@app.route("/<path:filename>")
def static_files(filename):
    if not DEBUG:
        return 'Not found', 404
    """
    Serve static files (CSS, JS, etc.)
    """
    return send_from_directory(app.static_folder, filename)


@app.route("/assistant", methods=["POST"])
def assistant_endpoint():
    if not DEBUG:
        return 'Not found', 404
    data = request.get_json()
    user_message = data.get("message", "")
    conversation = data.get("conversation", [])
    
    # Use the agent-based architecture for all queries
    print(f"Processing query through agent-based architecture", flush=True)
    response_text = llm_manager.analyze_jira_data(user_message, conversation)
    
    # Update conversation history
    updated_conversation = conversation + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response_text}
    ]
    
    return jsonify({
        "response": response_text,
        "conversation": updated_conversation
    })

@app.route("/analytics", methods=["POST"])
def analytics_endpoint():
    """
    Endpoint for complex analytics queries that require the agent-based architecture.
    """
    if not DEBUG:
        return 'Not found', 404
    data = request.get_json()
    query = data.get("query", "")
    conversation = data.get("conversation", [])
    result = llm_manager.analyze_jira_data(query, conversation)
    
    # Update conversation history
    updated_conversation = conversation + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": result}
    ]
    
    return jsonify({
        "result": result,
        "conversation": updated_conversation
    })

def get_conversation_history(channel_id, limit=5):
    """
    Retrieve recent conversation history from Slack.
    
    Args:
        channel_id: The Slack channel ID
        limit: Maximum number of messages to retrieve
        
    Returns:
        List of messages in the conversation format expected by the LLM
    """
    try:
        # Call the Slack API to get conversation history
        result = client.conversations_history(
            channel=channel_id,
            limit=limit * 2  # Get more messages than needed to account for bot messages
        )
        
        # Messages are returned in reverse chronological order (newest first)
        # So we need to reverse them to get chronological order
        messages = list(reversed(result["messages"]))
        
        # Get our own bot ID
        bot_info = client.auth_test()
        our_bot_id = bot_info["bot_id"]
        
        # Convert to the format expected by our LLM
        conversation = []
        for msg in messages:
            # Skip bot messages from other bots
            if msg.get("bot_id") and msg.get("bot_id") != our_bot_id:
                continue
                
            # Determine the role (user or assistant)
            if msg.get("bot_id") == our_bot_id:
                role = "assistant"
            else:
                role = "user"
                
            # Extract the text content
            content = msg.get("text", "")
            
            # Add to conversation
            conversation.append({
                "role": role,
                "content": content
            })
            
        # Limit to the requested number of messages
        return conversation[-limit:] if len(conversation) > limit else conversation
    except Exception as e:
        print(f"Error retrieving conversation history: {str(e)}", flush=True)
        return []

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return jsonify({"text": "Invalid request - not from Slack"}), 403

    # Check for retry attempts from Slack
    retry_count = request.headers.get('X-Slack-Retry-Num')
    if retry_count:
        print(f"Received retry attempt #{retry_count}", flush=True)

    data = request.json
    if "challenge" in data:  # Slack URL verification
        return jsonify({"challenge": data["challenge"]})

    if "event" in data and data["event"]["type"] == "message" and data["event"]["channel_type"] == "im":
        event = data["event"]
        user_id = event.get("user")  # User ID (e.g., "U12345678")
        bot_id = event.get("bot_id")  # Bot ID (e.g., "B12345678") if sent by a bot
        text = event["text"]
        channel = event["channel"]  # DM channel ID
        
        # Get unique message identifier
        message_id = event.get("client_msg_id")  # Unique ID for each message
        event_ts = event.get("ts")  # Timestamp as fallback ID
        unique_id = message_id or event_ts
        
        print(f"Received message with ID: {unique_id}", flush=True)
        
        # Check if we've already processed this message
        with message_cache_lock:
            if unique_id in processed_messages:
                print(f"Ignoring duplicate message with ID: {unique_id}", flush=True)
                return jsonify({"status": "ignored_duplicate"}), 200
            
            # Mark this message as processed
            processed_messages[unique_id] = datetime.now()
            
            # Limit cache size by removing oldest entries
            if len(processed_messages) > MESSAGE_CACHE_SIZE:
                oldest_keys = sorted(processed_messages, key=processed_messages.get)[:len(processed_messages) - MESSAGE_CACHE_SIZE]
                for key in oldest_keys:
                    del processed_messages[key]

        # Ignore messages from bots (including ourselves)
        if bot_id or (user_id and user_id == bot_id):
            print(f"Ignoring message from bot (user_id: {user_id}, bot_id: {bot_id})", flush=True)
            return jsonify({"status": "ignored"}), 200

        # Process and respond in a separate thread
        def process_dm():
            processing = True
            initial_message_ts = None
            message_thread_id = f"{channel}:{unique_id}"
            
            print(f"[{message_thread_id}] Starting processing thread", flush=True)
            
            try:
                # 1. Add a reaction to the user's message
                try:
                    print(f"[{message_thread_id}] Adding hourglass reaction", flush=True)
                    client.reactions_add(
                        channel=channel,
                        timestamp=event['ts'],
                        name="hourglass_flowing_sand"  # ⏳ emoji
                    )
                except Exception as e:
                    print(f"[{message_thread_id}] Failed to add reaction: {str(e)}", flush=True)
                
                # 2. Start typing indicator in a separate thread
                def show_typing():
                    while processing:
                        try:
                            client.conversations_typing(channel=channel)
                            time.sleep(2)  # Typing indicator lasts ~3 seconds
                        except Exception as e:
                            print(f"[{message_thread_id}] Typing indicator error: {str(e)}", flush=True)
                            break
                
                typing_thread = threading.Thread(target=show_typing)
                typing_thread.daemon = True
                typing_thread.start()
                print(f"[{message_thread_id}] Started typing indicator thread", flush=True)
                
                # 3. Send initial "processing" message
                print(f"[{message_thread_id}] Sending initial processing message", flush=True)
                initial_response = client.chat_postMessage(
                    channel=channel,
                    blocks=[{
                        "type": "section", 
                        "text": {
                            "type": "mrkdwn", 
                            "text": "🔄 *Processing your request...*\n\nConnecting to Jira and preparing your answer. This may take a moment."
                        }
                    }]
                )
                initial_message_ts = initial_response['ts']
                print(f"[{message_thread_id}] Initial message sent with timestamp: {initial_message_ts}", flush=True)
                
                # 4. Process the actual message
                print(f"[{message_thread_id}] Calling LLM manager to process message", flush=True)
                
                # Retrieve conversation history from Slack
                print(f"[{message_thread_id}] Retrieving conversation history", flush=True)
                conversation = get_conversation_history(channel, limit=5)
                print(f"[{message_thread_id}] Retrieved {len(conversation)} messages from conversation history", flush=True)
                
                # Use the agent-based architecture for all queries
                print(f"[{message_thread_id}] Processing query through agent-based architecture", flush=True)
                response_text = llm_manager.analyze_jira_data(text, conversation)
                
                print(f"[{message_thread_id}] Received response from LLM manager (length: {len(response_text)})", flush=True)
                
                # 5. Stop the typing indicator
                processing = False
                print(f"[{message_thread_id}] Stopped typing indicator", flush=True)
                
                # 6. Update the initial message with the response
                print(f"[{message_thread_id}] Updating initial message with response", flush=True)
                update_response = client.chat_update(
                    channel=channel,
                    ts=initial_message_ts,
                    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": response_text}}]
                )
                print(f"[{message_thread_id}] Message update successful: {update_response['ok']}", flush=True)
                
                # 7. Remove the "processing" reaction and add a "complete" reaction
                try:
                    print(f"[{message_thread_id}] Updating reactions", flush=True)
                    client.reactions_remove(
                        channel=channel,
                        timestamp=event['ts'],
                        name="hourglass_flowing_sand"
                    )
                    client.reactions_add(
                        channel=channel,
                        timestamp=event['ts'],
                        name="white_check_mark"  # ✅ emoji
                    )
                except Exception as e:
                    print(f"[{message_thread_id}] Failed to update reactions: {str(e)}", flush=True)
                
                print(f"[{message_thread_id}] Processing complete, response sent to {channel}", flush=True)
            except Exception as e:
                # Stop the typing indicator
                processing = False
                
                print(f"[{message_thread_id}] Error occurred: {str(e)}", flush=True)
                
                # Handle errors
                error_text = f"*Error:* {str(e)}"
                
                # Update the initial message if it exists, otherwise send a new message
                if initial_message_ts:
                    print(f"[{message_thread_id}] Updating initial message with error", flush=True)
                    try:
                        error_update = client.chat_update(
                            channel=channel,
                            ts=initial_message_ts,
                            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": error_text}}]
                        )
                        print(f"[{message_thread_id}] Error update successful: {error_update['ok']}", flush=True)
                    except Exception as update_error:
                        print(f"[{message_thread_id}] Failed to update message with error: {str(update_error)}", flush=True)
                else:
                    print(f"[{message_thread_id}] Sending new message with error", flush=True)
                    try:
                        error_message = client.chat_postMessage(
                            channel=channel,
                            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": error_text}}]
                        )
                        print(f"[{message_thread_id}] Error message sent: {error_message['ts']}", flush=True)
                    except Exception as post_error:
                        print(f"[{message_thread_id}] Failed to send error message: {str(post_error)}", flush=True)
                
                # Change reaction to error
                try:
                    print(f"[{message_thread_id}] Updating reactions for error", flush=True)
                    client.reactions_remove(
                        channel=channel,
                        timestamp=event['ts'],
                        name="hourglass_flowing_sand"
                    )
                    client.reactions_add(
                        channel=channel,
                        timestamp=event['ts'],
                        name="x"  # ❌ emoji
                    )
                except Exception as reaction_error:
                    print(f"[{message_thread_id}] Failed to update reactions for error: {str(reaction_error)}", flush=True)
                
                print(f"[{message_thread_id}] Error handling complete", flush=True)

        threading.Thread(target=process_dm).start()
        return jsonify({"status": "processing"}), 200  # Return immediately

    return jsonify({"status": "ok"}), 200


# --------------------------
# Main Entry Point
# --------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))  # Default to 5000 locally, use PORT in Cloud Run
    app.run(debug=DEBUG, host='0.0.0.0', port=port)
