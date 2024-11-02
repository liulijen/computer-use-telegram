"""
Entrypoint for Telegram bot interaction.
"""

import asyncio
import base64
import logging
import os
from datetime import datetime
from functools import partial
from typing import cast

import httpx
from anthropic import RateLimitError
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
)
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from computer_use_demo.loop import (
    PROVIDER_TO_DEFAULT_MODEL_NAME,
    APIProvider,
    sampling_loop,
)
from computer_use_demo.tools import ToolResult

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
API_PROVIDER = os.getenv("API_PROVIDER", "anthropic") or APIProvider.ANTHROPIC
# Strip whitespace from TELEGRAM_USER_ID
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "").strip() or None

# Set up default model based on provider
MODEL = PROVIDER_TO_DEFAULT_MODEL_NAME[APIProvider(API_PROVIDER)]

# Initialize conversation state
user_states = {}

# Track active tasks per user
active_tasks = {}

WARNING_TEXT = "⚠️ Security Alert: Never provide access to sensitive accounts or data, as malicious web content can hijack Claude's behavior"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Log all incoming messages with user ID and username
    username = update.effective_user.username or "No username"
    logging.info(f"Received message from user {user_id} (@{username}): {message_text}")
    
    # Silently ignore messages if TELEGRAM_USER_ID is not set or user is not authorized
    if not TELEGRAM_USER_ID or str(user_id) != TELEGRAM_USER_ID:
        logging.warning(f"Ignoring message from unauthorized user ID: {user_id}")
        return

    # Initialize user state if needed - this needs to be thread-safe
    if user_id not in user_states:
        user_states[user_id] = {
            "messages": [],
            "tools": {},
            "responses": {},
            "only_n_most_recent_images": 10,
            "custom_system_prompt": "",
        }

    # Get user state reference
    state = user_states[user_id]
    
    # Create status message first
    status_message = await update.message.reply_text("Processing your request...")

    try:
        # Run message processing in a separate task
        task = context.application.create_task(
            process_message(update, context, state, status_message, message_text),
            update=update
        )
        # Store the task reference
        active_tasks[user_id] = task
        await task
    except Exception as e:
        await status_message.edit_text(f"❌ An error occurred: ```\n{str(e)}\n```", parse_mode="Markdown")
    finally:
        # Clean up task reference
        if user_id in active_tasks:
            del active_tasks[user_id]

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, status_message, message_text: str):
    """Process a single message in a separate task"""
    try:
        # Append message to state
        state["messages"].append(
            {
                "role": "user", 
                "content": [BetaTextBlockParam(type="text", text=message_text)]
            }
        )

        try:
            # Run sampling loop
            state["messages"] = await sampling_loop(
                system_prompt_suffix=state["custom_system_prompt"],
                model=MODEL,
                provider=APIProvider(API_PROVIDER),
                messages=state["messages"],
                output_callback=partial(output_callback, update, status_message),
                tool_output_callback=partial(tool_output_callback, update, status_message, state),
                api_response_callback=partial(api_response_callback, update, state),
                api_key=ANTHROPIC_API_KEY,
                only_n_most_recent_images=state["only_n_most_recent_images"],
            )
            await status_message.delete()
        except asyncio.CancelledError:
            # Handle cancellation gracefully
            logging.info(f"Task cancelled for user {update.effective_user.id}")
            # Remove the last message since it was interrupted
            if state["messages"]:
                state["messages"].pop()
            await status_message.edit_text("Processing cancelled.")
            # Clear the messages to start fresh after cancellation
            state["messages"] = []
            raise  # Re-raise to ensure proper task cleanup
    except RateLimitError as e:
        error_msg = (
            "⚠️ *Rate limit exceeded*\n\n"
            f"```\n{str(e)}\n```\n\n"
            "Please wait a minute before trying again."
        )
        await status_message.edit_text(error_msg, parse_mode="Markdown")
    except Exception as e:
        await status_message.edit_text(f"❌ An error occurred: ```\n{str(e)}\n```", parse_mode="Markdown")

async def output_callback(update: Update, status_message, content: BetaContentBlockParam):
    if content["type"] == "text":
        formatted_text = f"📝 *Assistant's response:*\n{content['text']}"
        await update.message.reply_text(formatted_text, parse_mode="Markdown")
    elif content["type"] == "tool_use":
        tool_use_id = content["id"]
        tool_name = content["name"]
        tool_input = content["input"]
        formatted_message = (
            f"🔧 *Using tool `{tool_name}` with input:*\n"
            f"```\n{tool_input}\n```"
        )
        await update.message.reply_text(formatted_message, parse_mode="Markdown")

async def tool_output_callback(
    update: Update, 
    status_message,
    state, 
    tool_output: ToolResult, 
    tool_use_id: str
):
    state["tools"][tool_use_id] = tool_output
    
    if tool_output.output:
        formatted_output = f"📄 *Tool output:*\n```\n{tool_output.output}\n```"
        await update.message.reply_text(formatted_output, parse_mode="Markdown")
    if tool_output.base64_image:
        image_bytes = base64.b64decode(tool_output.base64_image)
        await update.message.reply_photo(photo=image_bytes)
        await update.message.reply_text("📷 *Screenshot captured by the tool*", parse_mode="Markdown")
    if tool_output.error:
        formatted_error = f"❗️ *Tool error:*\n```\n{tool_output.error}\n```"
        await update.message.reply_text(formatted_error, parse_mode="Markdown")

def api_response_callback(
    update: Update,
    state,
    request: httpx.Request,
    response: httpx.Response | object | None,
    error: Exception | None,
):
    # Store API responses in state if needed
    response_id = datetime.now().isoformat()
    state["responses"][response_id] = (request, response)
    
    # Add detailed logging
    if error:
        logging.error(f"API Error: {str(error)}")
        if isinstance(error, httpx.HTTPError):
            try:
                error_json = error.response.json()
                logging.error(f"Anthropic API Error Response: {error_json}")
            except Exception as e:
                logging.error(f"Failed to parse error response: {str(e)}")
                if hasattr(error, 'response'):
                    logging.error(f"Raw error response text: {error.response.text}")
    
    if response and isinstance(response, httpx.Response):
        try:
            response_json = response.json()
            logging.info(f"Anthropic API Response: {response_json}")
        except Exception as e:
            logging.error(f"Failed to parse API response: {str(e)}")
            logging.info(f"Raw response text: {response.text}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    
    # Silently ignore if TELEGRAM_USER_ID is not set or user is not authorized
    if not TELEGRAM_USER_ID or str(user_id) != TELEGRAM_USER_ID:
        logging.warning(f"Ignoring /start from unauthorized user ID: {user_id}")
        return
    
    await update.message.reply_text(
        f"Hello! I'm your Computer Use assistant.\n\n{WARNING_TEXT}\n\nSend me a message to start interacting."
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the conversation state when /reset is issued."""
    user_id = update.effective_user.id
    
    # Silently ignore if TELEGRAM_USER_ID is not set or user is not authorized
    if not TELEGRAM_USER_ID or str(user_id) != TELEGRAM_USER_ID:
        logging.warning(f"Ignoring /reset from unauthorized user ID: {user_id}")
        return
    
    if user_id in user_states:
        del user_states[user_id]
    await update.message.reply_text("Conversation reset. Send a new message to start fresh.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop the ongoing sampling loop when /stop is issued."""
    user_id = update.effective_user.id
    
    # Silently ignore if TELEGRAM_USER_ID is not set or user is not authorized
    if not TELEGRAM_USER_ID or str(user_id) != TELEGRAM_USER_ID:
        logging.warning(f"Ignoring /stop from unauthorized user ID: {user_id}")
        return
    
    if user_id in active_tasks:
        task = active_tasks[user_id]
        task.cancel()
        await update.message.reply_text("🛑 Processing stopped.")
    else:
        await update.message.reply_text("No active processing to stop.")

def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
        
    if not TELEGRAM_USER_ID:
        logging.warning("TELEGRAM_USER_ID not set - bot will ignore all messages")

    # Build application with concurrent updates enabled
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)  # Enable concurrent updates
        .build()
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 