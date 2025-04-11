import asyncio
import requests
import time
import os
import sys
from quart import Quart, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters as Filters

# Initialize Flask app with Quart for async support
app = Quart(__name__)

# Store the current email globally
current_email = None

# Initialize the application
application = Application.builder().token("7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY").build()

@app.route("/", methods=["POST"])
async def webhook():
    if request.method == "POST":
        try:
            json_data = await request.get_json()
            # Print the received data for debugging
            print("Received update:", json_data)
            
            # Ensure update_id is present
            if 'update_id' not in json_data:
                print("Missing update_id in update")
                return "OK", 200
                
            update = Update.de_json(json_data, application.bot)
            await application.process_update(update)
            return "ok"
        except Exception as e:
            print(f"Error processing update: {str(e)}")
            # Return 200 OK even on error to prevent Telegram from retrying
            return "OK", 200
    return "OK"

async def start(update: Update, _) -> None:
    keyboard = [["Generate Email", "Refresh Inbox"], ["Refresh Bot"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        'Hello! I am your bot. Use the buttons below to interact with me.',
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

def generate_temp_email():
    """Generate a temporary email address using a public API."""
    response = requests.get("https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1")
    if response.status_code == 200:
        email = response.json()[0]
        return email
    return None

def check_inbox(email):
    """Check the inbox of the temporary email for new messages."""
    username, domain = email.split("@")
    response = requests.get(f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}")
    if response.status_code == 200:
        messages = response.json()
        if messages:
            for message in messages:
                msg_id = message['id']
                msg_response = requests.get(f"https://www.1secmail.com/api/v1/?action=readMessage&login={username}&domain={domain}&id={msg_id}")
                if msg_response.status_code == 200:
                    message.update(msg_response.json())
            return messages
    return []

async def handle_buttons(update: Update, context) -> None:
    text = update.message.text
    if text == "Generate Email":
        await generate_email_command(update, context)
    elif text == "Refresh Inbox":
        await refresh_inbox_command(update, context)
    elif text == "Refresh Bot":
        await refresh(update, context)
    else:
        await update.message.reply_text("I didn't understand that. Please use the buttons.")

async def main():
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate_email", generate_email_command))
    application.add_handler(CommandHandler("refresh_inbox", refresh_inbox_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(MessageHandler(Filters.TEXT & ~Filters.COMMAND, handle_buttons))

    # Set the webhook
    await application.bot.set_webhook(url="https://smsbott-52febd4592e2.herokuapp.com/")
    
    # Start the Quart application
    port = int(os.environ.get("PORT", 5000))
    await app.run_task(host="0.0.0.0", port=port)

if __name__ == "__main__":
    asyncio.run(main())