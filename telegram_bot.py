import asyncio
import requests
import time
import os
import sys
import random
import string
from quart import Quart, request  # Make sure request is imported
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ConversationHandler, CallbackContext, filters
)
import yt_dlp
from openai import AsyncOpenAI

# Initialize Quart app
app = Quart(__name__)

# Store the current email globally
current_email = None

# Initialize OpenAI client
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    print("Warning: OPENAI_API_KEY environment variable is not set")
    client = None
else:
    try:
        client = AsyncOpenAI(api_key=openai_api_key)
        print("OpenAI client initialized successfully")
    except Exception as e:
        print(f"Error initializing OpenAI client: {str(e)}")
        client = None

# Initialize the Telegram application
application = Application.builder().token("7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY").build()

@app.route("/", methods=["POST"])
async def webhook():
    """Handle incoming webhook updates."""
    try:
        json_data = await request.get_json()
        print(f"Received update: {json_data}")  # Debug log
        
        # Check if this is a Heroku webhook update
        if 'webhook_metadata' in json_data:
            print("Received Heroku webhook update - ignoring")
            return {"ok": True}
            
        # This is a Telegram update
        if 'update_id' not in json_data:
            print("Invalid Telegram update format")
            return {"ok": True}
            
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        print(f"Error processing update: {str(e)}")
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
    """Start the GPT conversation."""
    await start_gpt_query(update, context)

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
    """Handle button presses."""
    text = update.message.text
    if text == "Generate Email":
        await generate_email_command(update, context)
    elif text == "Refresh Inbox":
        await refresh_inbox_command(update, context)
    elif text == "Refresh Bot":
        await refresh(update, context)
    elif text == "Download Music":
        return await start_music_download(update, context)
    elif text == "GPT":
        return await start_gpt_query(update, context)
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
    await update.message.reply_text(f"🔍 Searching for '{music_name}'...")
    
    try:
        # Configure yt-dlp options
        output_dir = "/tmp/downloads"  # Use /tmp directory on Heroku
        os.makedirs(output_dir, exist_ok=True)
        
        ydl_opts = {
            'format': 'bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'default_search': 'ytsearch1:',
            'quiet': True,
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'extract_audio': True,
            'audio_format': 'mp3',
            'force_generic_extractor': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Search for the video
                result = ydl.extract_info(f"ytsearch:{music_name}", download=False)
                
                if not result or 'entries' not in result or not result['entries']:
                    await update.message.reply_text("❌ Could not find the requested music. Please try a different search term.")
                    return ConversationHandler.END

                # Get the first result
                video = result['entries'][0]
                title = video.get('title', 'Unknown Title')
                await update.message.reply_text(f"📥 Found: {title}\nDownloading...")

                # Download the video
                ydl.download([video['webpage_url']])
                
                # Find and send the downloaded file
                output_file = os.path.join(output_dir, f"{title}.mp3")
                if not os.path.exists(output_file):
                    # Try alternative filename pattern
                    files = os.listdir(output_dir)
                    mp3_files = [f for f in files if f.endswith('.mp3')]
                    if mp3_files:
                        output_file = os.path.join(output_dir, mp3_files[0])

                if os.path.exists(output_file):
                    # Send the audio file
                    await update.message.reply_audio(
                        audio=open(output_file, 'rb'),
                        title=title,
                        performer=video.get('uploader', 'Unknown Artist'),
                        duration=video.get('duration')
                    )
                    await update.message.reply_text(f"✅ Successfully sent: {title}")
                else:
                    await update.message.reply_text("❌ Sorry, there was an error processing the audio file.")

            except Exception as e:
                print(f"Download error: {str(e)}")
                await update.message.reply_text(
                    "❌ Sorry, I couldn't download that music. Please try:\n"
                    "1. A different song name\n"
                    "2. Including the artist name\n"
                    "3. Using a shorter title"
                )

    except Exception as e:
        print(f"Outer error: {str(e)}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")
    
    finally:
        # Clean up downloads directory
        try:
            if os.path.exists(output_dir):
                for file in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up downloads: {str(e)}")
    
    return ConversationHandler.END

async def start_gpt_query(update: Update, context: CallbackContext) -> int:
    """Start the GPT query conversation."""
    await update.message.reply_text("Please provide your query for GPT.")
    return EXPECTING_GPT_QUERY

async def handle_gpt_query(update: Update, context: CallbackContext) -> int:
    """Handle the GPT query input."""
    query = update.message.text
    await update.message.reply_text("🤔 Processing your query...")

    if not openai_api_key:
        await update.message.reply_text(
            "❌ GPT functionality is not available. Please ask the bot owner to set up the OPENAI_API_KEY."
        )
        return ConversationHandler.END

    try:
        client = AsyncOpenAI(api_key=openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": query}
            ],
            max_tokens=1000,
            temperature=0.7,
        )
        
        answer = response.choices[0].message.content.strip()
        if answer:
            await update.message.reply_text(answer)
        else:
            await update.message.reply_text("I couldn't generate a response. Please try asking something else.")
            
    except Exception as e:
        print(f"GPT error: {str(e)}")
        await update.message.reply_text(
            "❌ Sorry, I encountered an error while processing your query. Please try again later."
        )
    
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
            MessageHandler(filters.Regex('^Download Music$'), start_music_download)
        ],
        states={
            EXPECTING_MUSIC_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(Generate Email|Refresh Inbox|Download Music|GPT|Refresh Bot)$'), handle_music_name)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="music_conversation",
        persistent=False
    )

    # Create conversation handler for GPT
    gpt_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('gpt', start_gpt_query),
            MessageHandler(filters.Regex('^GPT$'), start_gpt_query)
        ],
        states={
            EXPECTING_GPT_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(Generate Email|Refresh Inbox|Download Music|GPT|Refresh Bot)$'), handle_gpt_query)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="gpt_conversation",
        persistent=False
    )

    # Remove all handlers and add them in the correct order
    application.handlers.clear()
    
    # Add handlers in the correct order
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate_email", generate_email_command))
    application.add_handler(CommandHandler("refresh_inbox", refresh_inbox_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(music_conv_handler)
    application.add_handler(gpt_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    # Set webhook URL
    webhook_url = "https://smsbott-52febd4592e2.herokuapp.com/"
    await application.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to {webhook_url}")

@app.before_serving
async def startup():
    """Initialize the bot before serving."""
    await setup()
    await application.initialize()
    await application.start()
    print("Bot started successfully!")

@app.after_serving
async def shutdown():
    """Cleanup when shutting down."""
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    # Initialize application before running
    asyncio.run(setup())
    
    # Run the Quart application
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        use_reloader=False
    )