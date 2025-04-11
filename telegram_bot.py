import asyncio
import requests
import time
import os
import sys
import random
import string
import google.generativeai as genai
from quart import Quart, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ConversationHandler, CallbackContext, filters
)
import yt_dlp

# Initialize Quart app
app = Quart(__name__)
app.config['PROVIDE_AUTOMATIC_OPTIONS'] = True

# Initialize Gemini
genai.configure(api_key="AIzaSyDsvDWz-lOhuGyQV5rL-uumbtlNamXqfWM")
model = genai.GenerativeModel('gemini-pro')

# Store the current email globally
current_email = None

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
        ["Download Music", "Gemini"],
        ["Refresh Bot"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        'Hello! I am your bot. Use the buttons or commands:\n'
        '/start - Show this menu\n'
        '/dl - Download music\n'
        '/gemini - Chat with Gemini AI\n'
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
    elif text == "Gemini":
        return await start_gemini_query(update, context)
    else:
        await update.message.reply_text("I didn't understand that. Please use the buttons.")

# Define conversation states
EXPECTING_MUSIC_NAME = 1
EXPECTING_GEMINI_QUERY = 2  # Changed from EXPECTING_GPT_QUERY

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
        output_dir = "/app/downloads"  # Use /app directory on Heroku
        os.makedirs(output_dir, exist_ok=True)

        # Basic options for initial search
        search_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'no_color': True,
            'noprogress': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            }
        }

        try:
            # First search for the video
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                print(f"Searching for: {music_name}")
                result = ydl.extract_info(f"ytsearch:{music_name}", download=False)
                
                if not result or 'entries' not in result or not result['entries']:
                    print("No results found")
                    await update.message.reply_text("❌ Could not find the music. Please try a more specific search term.")
                    return ConversationHandler.END

                # Get the first result
                video = result['entries'][0]
                video_url = video.get('webpage_url', video.get('url'))
                title = video.get('title', 'Unknown Title')
                duration = video.get('duration', 0)
                
                # Check duration (if available) - limit to ~10 minutes
                if duration and duration > 600:
                    await update.message.reply_text("❌ This video is too long. Please choose a shorter song (under 10 minutes).")
                    return ConversationHandler.END
                
                if not video_url:
                    print("Could not extract video URL")
                    await update.message.reply_text("❌ Could not extract video URL. Please try another song.")
                    return ConversationHandler.END

                await update.message.reply_text(f"📥 Found: {title}\nDownloading...")

                # Configure download options with ffmpeg settings
                ffmpeg_location = os.environ.get('FFMPEG_PATH', 'ffmpeg')
                download_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '128',
                        'nopostoverwrites': False,
                        'FFmpegExtractAudioPP': {
                            'preferredcodec': 'mp3',
                            'preferredquality': '128',
                        }
                    }],
                    'ffmpeg_location': ffmpeg_location,
                    'prefer_ffmpeg': True,
                    'keepvideo': False,
                    'writethumbnail': False,
                    'quiet': False,
                    'verbose': True,
                    'no_warnings': True,
                    'ignoreerrors': True,
                    'no_color': True,
                    'noprogress': False,
                    'progress_hooks': [lambda d: print(f"Download progress: {d['_percent_str'] if '_percent_str' in d else 'N/A'}")],
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                        'Accept-Language': 'en-us,en;q=0.5',
                    },
                    'socket_timeout': 30,
                    'retries': 3,
                    'fragment_retries': 3,
                    'hls_prefer_native': True,
                    'external_downloader_args': ['-timeout', '30'],
                    'ffmpeg_args': ['-nostdin', '-y']
                }

                print(f"Attempting to download: {video_url}")
                
                # Try downloading with retries
                max_retries = 3
                downloaded_file = None
                
                for attempt in range(max_retries):
                    try:
                        print(f"Download attempt {attempt + 1}/{max_retries}")
                        with yt_dlp.YoutubeDL(download_opts) as ydl:
                            info = ydl.extract_info(video_url, download=True)
                            if info:
                                # Look for the downloaded file
                                print("Looking for downloaded file...")
                                for file in os.listdir(output_dir):
                                    if file.endswith('.mp3'):
                                        downloaded_file = os.path.join(output_dir, file)
                                        break
                                if downloaded_file:
                                    break
                    except Exception as e:
                        print(f"Download attempt {attempt + 1} failed: {str(e)}")
                        if attempt == max_retries - 1:  # Last attempt failed
                            raise
                        await asyncio.sleep(2)  # Wait before retrying
                        continue

                if downloaded_file and os.path.exists(downloaded_file):
                    try:
                        print(f"Sending file: {downloaded_file}")
                        file_size = os.path.getsize(downloaded_file)
                        print(f"File size: {file_size} bytes")
                        
                        if file_size > 0:
                            # Try to send with retries
                            max_send_retries = 3
                            for send_attempt in range(max_send_retries):
                                try:
                                    with open(downloaded_file, 'rb') as audio:
                                        await update.message.reply_audio(
                                            audio=audio,
                                            title=title,
                                            performer=video.get('uploader', 'Unknown Artist'),
                                            duration=duration
                                        )
                                    await update.message.reply_text(f"✅ Successfully sent: {title}")
                                    break
                                except Exception as e:
                                    print(f"Send attempt {send_attempt + 1} failed: {str(e)}")
                                    if "File is too big" in str(e):
                                        await update.message.reply_text("❌ Sorry, this audio file is too large to send. Please try a shorter song.")
                                        break
                                    elif send_attempt == max_send_retries - 1:
                                        await update.message.reply_text("❌ Error sending the audio file. Please try a different song.")
                                    await asyncio.sleep(2)
                        else:
                            print("File exists but is empty")
                            await update.message.reply_text("❌ Downloaded file is empty. Please try another song.")
                    except Exception as e:
                        print(f"Error handling file: {str(e)}")
                        await update.message.reply_text("❌ Error processing the audio file. Please try a different song.")
                else:
                    print("No MP3 file found after download")
                    await update.message.reply_text("❌ Failed to process the audio. Please try another song.")

        except Exception as e:
            print(f"Download error: {str(e)}")
            error_message = str(e).lower()
            if "copyright" in error_message:
                await update.message.reply_text("❌ This song is not available due to copyright restrictions. Please try another song.")
            elif "not available in your country" in error_message:
                await update.message.reply_text("❌ This song is not available in the current region. Please try another song.")
            elif "private video" in error_message:
                await update.message.reply_text("❌ This video is private. Please try another song.")
            elif "unable to extract" in error_message or "cipher" in error_message:
                await update.message.reply_text("❌ Unable to process this video. Please try another song.")
            else:
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
        # Clean up downloaded files
        try:
            if os.path.exists(output_dir):
                for file in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, file)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print(f"Error removing file {file_path}: {str(e)}")
        except Exception as e:
            print(f"Error cleaning up: {str(e)}")
    
    return ConversationHandler.END

async def start_gpt_query(update: Update, context: CallbackContext) -> int:
    """Start the GPT query conversation."""
    await update.message.reply_text("Please provide your query for GPT.")
    return EXPECTING_GEMINI_QUERY

async def start_gemini_query(update: Update, context: CallbackContext) -> int:
    """Start the Gemini query conversation."""
    await update.message.reply_text("Please provide your query for Gemini AI.")
    return EXPECTING_GEMINI_QUERY  # We'll keep using the same state name

async def handle_gpt_query(update: Update, context: CallbackContext) -> int:
    """Handle the query input using Gemini."""
    query = update.message.text
    await update.message.reply_text("🤔 Processing your query...")

    try:
        # Create Gemini response with safety settings
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]

        try:
            response = model.generate_content(query)
            
            if response and hasattr(response, 'text') and response.text:
                # Process and clean the response text
                response_text = response.text.strip()
                
                if response_text:
                    # Split long responses into chunks of 4000 characters (leaving buffer for formatting)
                    chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
                    
                    # Send each chunk
                    for chunk in chunks:
                        await update.message.reply_text(chunk)
                else:
                    await update.message.reply_text("I understood your question but couldn't generate a meaningful response. Please try rephrasing your query.")
            else:
                await update.message.reply_text("I couldn't process your query. Please try asking something else.")
                
        except Exception as generation_error:
            print(f"Generation error: {str(generation_error)}")
            if "blocked" in str(generation_error).lower():
                await update.message.reply_text("I apologize, but I cannot provide a response to that query as it may contain inappropriate content.")
            else:
                await update.message.reply_text(
                    "❌ I encountered an error while generating the response. Please try:\n"
                    "1. Rephrasing your question\n"
                    "2. Making your query more specific\n"
                    "3. Breaking it into smaller parts"
                )
            
    except Exception as e:
        print(f"Gemini error: {str(e)}")
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
    try:
        # Create conversation handler for music download
        music_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('dl', start_music_download),
                MessageHandler(filters.Regex('^Download Music$'), start_music_download)
            ],
            states={
                EXPECTING_MUSIC_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(Generate Email|Refresh Inbox|Download Music|Gemini|Refresh Bot)$'), handle_music_name)
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            name="music_conversation",
            persistent=False
        )

        # Create conversation handler for Gemini
        gemini_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('gemini', start_gemini_query),
                MessageHandler(filters.Regex('^Gemini$'), start_gemini_query)
            ],
            states={
                EXPECTING_GEMINI_QUERY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(Generate Email|Refresh Inbox|Download Music|Gemini|Refresh Bot)$'), handle_gpt_query)
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            name="gemini_conversation",
            persistent=False
        )

        # Initialize application
        await application.initialize()
        
        # Remove all handlers and add them in the correct order
        application.handlers.clear()
        
        # Add handlers in the correct order
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("generate_email", generate_email_command))
        application.add_handler(CommandHandler("refresh_inbox", refresh_inbox_command))
        application.add_handler(CommandHandler("refresh", refresh))
        application.add_handler(music_conv_handler)
        application.add_handler(gemini_conv_handler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

        # Set webhook URL with explicit HTTPS
        webhook_url = "https://smsbott-52febd4592e2.herokuapp.com/"
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True
        )
        print(f"Webhook set to {webhook_url}")
        
        # Start the application
        await application.start()
        print("Bot initialized and webhook set successfully!")
        
    except Exception as e:
        print(f"Error in setup: {str(e)}")
        raise

@app.before_serving
async def startup():
    """Initialize the bot before serving."""
    try:
        await setup()  # This function already handles initialization and startup
        print("Bot started successfully!")
    except Exception as e:
        print(f"Error during startup: {e}")
        sys.exit(1)

@app.after_serving
async def shutdown():
    """Cleanup when shutting down."""
    try:
        await application.stop()
        await application.shutdown()
        print("Bot shutdown successfully!")
    except Exception as e:
        print(f"Error during shutdown: {e}")

if __name__ == "__main__":
    # Initialize application before running
    asyncio.run(setup())
    
    # Run the Quart application with proper worker configuration
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )

# Enable graceful shutdown
import signal

def handle_sigterm(signum, frame):
    print("Received SIGTERM. Performing cleanup...")
    asyncio.run(shutdown())
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)