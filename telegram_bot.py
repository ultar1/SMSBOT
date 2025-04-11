import asyncio
import requests
import time
import os
import sys
import random
import string
from quart import Quart, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ConversationHandler, CallbackContext, filters
)
import yt_dlp
import openai

# Set up OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Quart app
app = Quart(__name__)

# Store the current email globally
current_email = None

# Initialize the Telegram application
application = Application.builder().token("7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY").build()

@app.route("/webhook", methods=["POST"])
async def webhook():
    """Handle incoming webhook updates from Telegram."""
    if request.method == "POST":
        json_data = await request.get_json()
        try:
            await application.update_queue.put(Update.de_json(json_data, application.bot))
            return {"ok": True}
        except Exception as e:
            print(f"Error processing update: {str(e)}")
            return {"ok": True}  # Return success to prevent Telegram retries
    return {"ok": True}

async def start(update: Update, _) -> None:
    keyboard = [
        ["Generate Email", "Refresh Inbox"],
        ["Download Music", "GPT"],
        ["Refresh Bot"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        'Hello! I am your bot. Use the buttons or commands:\n'
        '/start - Show this menu\n'
        '/dl - Download music\n'
        '/gpt - Chat with GPT\n'
        '/generate_email - Generate temporary email\n'
        '/refresh_inbox - Check email inbox\n'
        '/refresh - Refresh bot',
        reply_markup=reply_markup
    )

async def generate_email_command(update: Update, _) -> None:
    global current_email
    current_email = generate_temp_email()
    if current_email:
        await update.message.reply_text(f"Generated Email: {current_email}")
    else:
        await update.message.reply_text("Failed to generate email.")

async def refresh_inbox_command(update: Update, _) -> None:
    if current_email:
        await update.message.reply_text("Checking inbox...")
        messages = check_inbox(current_email)
        if messages:
            for msg in messages:
                await update.message.reply_text(f"From: {msg['from']}\nSubject: {msg['subject']}\nBody: {msg.get('textBody', 'No content')}")
        else:
            await update.message.reply_text("No new messages.")
    else:
        await update.message.reply_text("No email generated yet. Please generate an email first.")

async def refresh(update: Update, _) -> None:
    await update.message.reply_text("Refreshing the bot...")
    os.execl(sys.executable, sys.executable, *sys.argv)

async def gpt_response(update: Update, context) -> None:
    """Ask for a query and respond using GPT."""
    await update.message.reply_text("Please provide your query for GPT.")

    # Dynamically add a handler for the user's response
    def gpt_query_handler(update: Update, context):
        context.dispatcher.remove_handler(gpt_query_handler)  # Remove the handler after use
        asyncio.create_task(process_gpt_query(update, update.message.text))

    context.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, gpt_query_handler))

async def process_gpt_query(update: Update, query: str):
    """Process the GPT query based on the user's input."""
    await update.message.reply_text(f"Processing your query: {query}")

    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=query,
            max_tokens=150
        )
        answer = response.choices[0].text.strip()
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Failed to get GPT response: {str(e)}")

def generate_fallback_email():
    """Generate a random fallback email."""
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    domain = "fallbackmail.com"
    return f"{username}@{domain}"

def generate_temp_email():
    """Generate a temporary email address using a public API."""
    try:
        response = requests.get(
            "https://www.1secmail.com/api/v1/",
            params={"action": "genRandomMailbox", "count": 1},
            timeout=10
        )
        print(f"API Response: {response.text}")  # Debug log
        response.raise_for_status()

        emails = response.json()
        if emails and isinstance(emails, list) and len(emails) > 0:
            email = emails[0]
            print(f"Successfully generated email: {email}")
            return email

        print("Invalid response format or empty email list.")
        return generate_fallback_email()
    except Exception as e:
        print(f"Error generating email: {str(e)}")
        return generate_fallback_email()

def check_inbox(email):
    """Check the inbox of the temporary email for new messages."""
    try:
        username, domain = email.split("@")
        print(f"Checking inbox for: {email}")  # Debug log

        response = requests.get(
            "https://www.1secmail.com/api/v1/",
            params={
                "action": "getMessages",
                "login": username,
                "domain": domain
            },
            timeout=10
        )
        print(f"Inbox API Response: {response.text}")  # Debug log
        response.raise_for_status()

        messages = response.json()
        if messages:
            for message in messages:
                try:
                    msg_id = message['id']
                    msg_response = requests.get(
                        "https://www.1secmail.com/api/v1/",
                        params={
                            "action": "readMessage",
                            "login": username,
                            "domain": domain,
                            "id": msg_id
                        },
                        timeout=10
                    )
                    print(f"Message {msg_id} Response: {msg_response.text}")  # Debug log
                    msg_response.raise_for_status()
                    message.update(msg_response.json())
                except (requests.RequestException, KeyError) as e:
                    print(f"Error fetching message {msg_id}: {str(e)}")
                    continue
            return messages
        print("No messages found in the inbox.")
        return []
    except requests.RequestException as e:
        print(f"Error checking inbox: {str(e)}")
        return []
    except Exception as e:
        print(f"Unexpected error checking inbox: {str(e)}")
        return []

async def handle_buttons(update: Update, context) -> None:
    text = update.message.text
    if text == "Generate Email":
        await generate_email_command(update, context)
    elif text == "Refresh Inbox":
        await refresh_inbox_command(update, context)
    elif text == "Refresh Bot":
        await refresh(update, context)
    elif text == "Download Music":
        await start_music_download(update, context)
    elif text == "GPT":
        await start_gpt_query(update, context)
    else:
        await update.message.reply_text("I didn't understand that. Please use the buttons.")

# Define conversation states
EXPECTING_MUSIC_NAME = 1
EXPECTING_GPT_QUERY = 2

# Store user states
user_states = {}

async def start_music_download(update: Update, context: CallbackContext) -> int:
    """Start the music download conversation."""
    await update.message.reply_text("Please provide the name of the music you want to download.")
    return EXPECTING_MUSIC_NAME

async def handle_music_name(update: Update, context: CallbackContext) -> int:
    """Handle the music name input."""
    music_name = update.message.text
    await update.message.reply_text(f"Searching for '{music_name}'...")
    
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f"{music_name}.mp3",
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch:{music_name}"])
        await update.message.reply_text(f"Music '{music_name}' downloaded successfully.")
    except Exception as e:
        await update.message.reply_text(f"Failed to download music: {str(e)}")
    
    return ConversationHandler.END

async def start_gpt_query(update: Update, context: CallbackContext) -> int:
    """Start the GPT query conversation."""
    await update.message.reply_text("Please provide your query for GPT.")
    return EXPECTING_GPT_QUERY

async def handle_gpt_query(update: Update, context: CallbackContext) -> int:
    """Handle the GPT query input."""
    query = update.message.text
    await update.message.reply_text(f"Processing your query: {query}")
    
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=query,
            max_tokens=150
        )
        answer = response.choices[0].text.strip()
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Failed to get GPT response: {str(e)}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def setup():
    """Set up the application and webhook."""
    # Create conversation handler for music download
    music_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('dl', start_music_download),
            MessageHandler(filters.TEXT & filters.Regex('^Download Music$'), start_music_download)
        ],
        states={
            EXPECTING_MUSIC_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_music_name)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Create conversation handler for GPT
    gpt_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('gpt', start_gpt_query),
            MessageHandler(filters.TEXT & filters.Regex('^GPT$'), start_gpt_query)
        ],
        states={
            EXPECTING_GPT_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gpt_query)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Add all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate_email", generate_email_command))
    application.add_handler(CommandHandler("refresh_inbox", refresh_inbox_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(music_conv_handler)
    application.add_handler(gpt_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    # Set webhook URL
    webhook_url = "https://smsbott-52febd4592e2.herokuapp.com/webhook"
    await application.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to {webhook_url}")

@app.before_serving
async def startup():
    """Initialize the bot before serving."""
    await setup()
    await application.initialize()
    await application.start()

@app.after_serving
async def shutdown():
    """Cleanup when shutting down."""
    await application.stop()
    await application.shutdown()

if __name__:
    # Run the Quart application
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        use_reloader=False
    )