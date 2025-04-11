import requests
import time
import os
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Store the current email globally
current_email = None

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

# Define a start command handler
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Hello! I am your bot. How can I assist you?')

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

def main():
    email = generate_temp_email()
    if email:
        print("Waiting for messages...")
        while True:
            check_inbox(email)
            time.sleep(10)  # Check inbox every 10 seconds

    # Replace 'YOUR_TOKEN' with the actual bot token
    updater = Updater("7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY", use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("generate_email", generate_email_command))
    dp.add_handler(CommandHandler("refresh_inbox", refresh_inbox_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    # Update the Flask app to use the PORT environment variable for Heroku deployment
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)