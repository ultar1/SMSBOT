import requests
import time
import os
import sys
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters as Filters, CallbackContext
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Store the current email globally
current_email = None

# Replace the updater with the Application class
application = Application.builder().token("7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY").build()

@app.route("/generate_email", methods=["GET"])
def generate_email():
    global current_email
    current_email = generate_temp_email()
    if current_email:
        return jsonify({"email": current_email})
    else:
        return jsonify({"error": "Failed to generate email."}), 500

@app.route("/get_inbox", methods=["GET"])
def get_inbox():
    if current_email:
        check_inbox(current_email)
        return jsonify({"message": "Inbox checked. See console for details."})
    else:
        return jsonify({"error": "No email generated yet."}), 400

@app.route("/")
def index():
    return render_template("index.html")

# Update the start command to include buttons
def start(update: Update, context: CallbackContext) -> None:
    keyboard = [["Generate Email", "Refresh Inbox"], ["Refresh Bot"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text(
        'Hello! I am your bot. Use the buttons below to interact with me.',
        reply_markup=reply_markup
    )

# Define a message handler
def echo(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(update.message.text)

# Add commands to the Telegram bot for generating a new email and refreshing the inbox
def generate_email_command(update: Update, context: CallbackContext) -> None:
    global current_email
    current_email = generate_temp_email()
    if current_email:
        update.message.reply_text(f"Generated Email: {current_email}")
    else:
        update.message.reply_text("Failed to generate email.")

def refresh_inbox_command(update: Update, context: CallbackContext) -> None:
    if current_email:
        update.message.reply_text("Checking inbox... Check the console for details.")
        check_inbox(current_email)
    else:
        update.message.reply_text("No email generated yet. Please generate an email first.")

# Add a refresh command to restart the bot
def refresh(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Refreshing the bot...")
    os.execl(sys.executable, sys.executable, *sys.argv)

def generate_temp_email():
    """Generate a temporary email address using a public API."""
    response = requests.get("https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1")
    if response.status_code == 200:
        email = response.json()[0]
        print(f"Generated Email: {email}")
        return email
    else:
        print("Failed to generate email.")
        return None

def check_inbox(email):
    """Check the inbox of the temporary email for new messages."""
    username, domain = email.split("@")
    response = requests.get(f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}")
    if response.status_code == 200:
        messages = response.json()
        if messages:
            print(f"You have {len(messages)} new message(s):")
            for message in messages:
                print(f"From: {message['from']}, Subject: {message['subject']}")
                # Fetch the full message
                msg_id = message['id']
                msg_response = requests.get(f"https://www.1secmail.com/api/v1/?action=readMessage&login={username}&domain={domain}&id={msg_id}")
                if msg_response.status_code == 200:
                    print("Message Body:")
                    print(msg_response.json().get("textBody", "No content"))
        else:
            print("No new messages.")
    else:
        print("Failed to check inbox.")

# Update the message handler to handle button presses
def handle_buttons(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    if text == "Generate Email":
        generate_email_command(update, context)
    elif text == "Refresh Inbox":
        refresh_inbox_command(update, context)
    elif text == "Refresh Bot":
        refresh(update, context)
    else:
        update.message.reply_text("I didn't understand that. Please use the buttons.")

# Update the main function to use the Application class
def main():
    email = generate_temp_email()
    if email:
        print("Waiting for messages...")
        while True:
            check_inbox(email)
            time.sleep(10)  # Check inbox every 10 seconds

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate_email", generate_email_command))
    application.add_handler(CommandHandler("refresh_inbox", refresh_inbox_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(MessageHandler(Filters.Text & ~Filters.Command, handle_buttons))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        url_path="",
        webhook_url="https://smsbott-52febd4592e2.herokuapp.com/"
    )

if __name__ == "__main__":
    main()