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
        
        # Create cookies file with proper format
        cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	TRUE	1743897600	VISITOR_PRIVACY_METADATA	CgJORxIEGgAgDQ%3D%3D
.youtube.com	TRUE	/	TRUE	1743897600	__Secure-3PSID	g.a000vAgzaXaoUv1lfqGXwF6Zq-EMUaAPgcfoBRGKFy7_sqpIEql8St292ulyECZ1G5EFisnYowACgYKAbUSARUSFQHGX2MirrEkqfKXDX-WmRa8gqfE2xoVAUF8yKrDwG0-WvGRFv2sF_DYTp9t0076
.youtube.com	TRUE	/	TRUE	1743897600	SIDCC	AKEyXzWUOdGxFHAPyzpF9y719BZEjM9A00S1rGZ75qjfYI1j_YqTSo2TRWT5E_K_kV9ooqsp3ig
.youtube.com	TRUE	/	TRUE	1743897600	SID	g.a000vAgzaXaoUv1lfqGXwF6Zq-EMUaAPgcfoBRGKFy7_sqpIEql8D17hw7luxjnDnZHIou-TuQACgYKASQSARUSFQHGX2MihZqVL4JB68O_Ubzt6wTXvRoVAUF8yKrbltMdV7lzK37KzG2ZJTys0076
.youtube.com	TRUE	/	TRUE	1743897600	LOGIN_INFO	AFmmF2swRgIhAJaX938y0qaO7SRZ9J-4nFNuE_VsvV_d1YV15oU4JYxKAiEAwkMOXRbQhv9g57qZrfzA0NGYbXYBRaR4sJUJ2RukvlU:QUQ3MjNmd2QxeXE4eXFtSi1ZQ0txZFA3SjJ6bFBYNUNhX3R5ZVB5TFBhV2NBbVpZeTkwcG0wa2thTmpVY3JRT2M1TkNXamg2YUpFUmRXSG8wV2o2Z3dTS1RiaExiS0xZdndnSG1NWTl3Ui0zd3hRMnc3Qk1SWHM5eUh5eVlxWFlBd2s0Y3NqZVRHNkd6eWs1YWdHXy1OSTRaVGdHazN4cDB3
.youtube.com	TRUE	/	TRUE	1743897600	VISITOR_INFO1_LIVE	ky1HG6C5ZZA"""

        cookies_file = os.path.join(output_dir, "youtube_cookies.txt")
        with open(cookies_file, "w", encoding='utf-8') as f:
            f.write(cookies)

        # Common options for both search and download
        common_opts = {
            'cookiefile': cookies_file,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'no_warnings': True,
            'quiet': True,
            'no_color': True,
            'extract_flat': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
        }

        # First phase: Search for the video
        with yt_dlp.YoutubeDL(common_opts) as ydl:
            try:
                # Search for the video
                result = ydl.extract_info(f"ytsearch1:{music_name}", download=False)
                
                if not result or 'entries' not in result or not result['entries']:
                    await update.message.reply_text("❌ Could not find the music. Please try a more specific search term.")
                    return ConversationHandler.END

                # Get the first result
                video = result['entries'][0]
                video_url = video.get('url', video.get('webpage_url'))
                video_id = video.get('id', '')
                title = video.get('title', 'Unknown Title')
                
                if not video_url:
                    await update.message.reply_text("❌ Could not extract video URL. Please try another song.")
                    return ConversationHandler.END

                await update.message.reply_text(f"📥 Found: {title}\nDownloading...")

                # Second phase: Download the video
                download_opts = {
                    **common_opts,
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '128',
                    }],
                    'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                    'quiet': False,
                    'verbose': True,
                }

                # Add direct video URL options
                if video_id:
                    download_opts.update({
                        'referer': f'https://www.youtube.com/watch?v={video_id}',
                        'add_header': [
                            'Cookie:' + cookies,
                            'Origin:https://www.youtube.com',
                        ],
                    })

                # Attempt download
                with yt_dlp.YoutubeDL(download_opts) as dl:
                    dl.download([video_url])

                # Look for the downloaded file
                downloaded_file = None
                for file in os.listdir(output_dir):
                    if file.endswith('.mp3'):
                        downloaded_file = os.path.join(output_dir, file)
                        break

                if downloaded_file and os.path.exists(downloaded_file):
                    try:
                        # Send the audio file
                        with open(downloaded_file, 'rb') as audio:
                            await update.message.reply_audio(
                                audio=audio,
                                title=title,
                                performer=video.get('uploader', 'Unknown Artist'),
                                duration=video.get('duration')
                            )
                        await update.message.reply_text(f"✅ Successfully sent: {title}")
                    except Exception as e:
                        print(f"Error sending file: {str(e)}")
                        if "File is too big" in str(e):
                            await update.message.reply_text("❌ Sorry, this audio file is too large to send. Please try a shorter song.")
                        else:
                            await update.message.reply_text("❌ Error sending the audio file. Please try a different song.")
                else:
                    await update.message.reply_text("❌ Failed to process the audio. Please try another song.")

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
        # Clean up
        try:
            if os.path.exists(cookies_file):
                os.remove(cookies_file)
            if os.path.exists(output_dir):
                for file in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
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
        # Create Gemini response in an async way
        response = model.generate_content(query)
        
        if hasattr(response, 'text'):
            # Split long responses into chunks if needed
            chunks = [response.text[i:i+4096] for i in range(0, len(response.text), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("I couldn't generate a response. Please try asking something else.")
            
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