// app.js

const {
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  makeWASocket
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const chalk = require('chalk');
const {
  Telegraf
} = require('telegraf');

// --- Configuration ---
const TELEGRAM_BOT_TOKEN = '7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY'; // Replace with your Telegram bot token
const ADMIN_TELEGRAM_ID = '7302005705'; // Replace with your Telegram user ID
const SESSION_FOLDER = './session';

// --- Telegraf Bot Setup ---
const telegramBot = new Telegraf(TELEGRAM_BOT_TOKEN);

// Function to send messages to the Telegram admin
const sendTelegramMessage = (message) => {
  telegramBot.telegram.sendMessage(ADMIN_TELEGRAM_ID, message, {
    parse_mode: 'Markdown'
  });
};

// --- WhatsApp Bot Logic ---
async function startWhatsAppBot() {
  const logger = pino({
    level: 'silent'
  });
  const {
    state,
    saveCreds
  } = await useMultiFileAuthState(SESSION_FOLDER);

  const sock = makeWASocket({
    logger,
    printQRInTerminal: false,
    browser: ["Ubuntu", "Chrome", "20.0.04"],
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
  });

  // Handle connection events
  sock.ev.on('connection.update', async (update) => {
    const {
      connection,
      lastDisconnect,
      isNewLogin
    } = update;
    if (isNewLogin) {
      try {
        const code = await sock.requestPairingCode('YOUR_PHONE_NUMBER'); // Replace with the WhatsApp number to link, e.g., '2349163916316'
        sendTelegramMessage(`Your WhatsApp pairing code is: \`\`\`${code}\`\`\`\n\n*To link your account, go to WhatsApp > Linked Devices > Link with phone number and enter this code.*`);
      } catch (e) {
        sendTelegramMessage(`*ERROR:* Failed to generate pairing code. Please check server logs for details.`);
        console.error('Failed to request pairing code:', e);
      }
    }
    if (connection === 'close') {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== 401;
      if (shouldReconnect) {
        startWhatsAppBot();
      } else {
        sendTelegramMessage('*ERROR:* Connection closed, possibly banned. You may need a new session.');
      }
    } else if (connection === 'open') {
      sendTelegramMessage('*SUCCESS:* WhatsApp session is now connected!');
      // After connection, send the session files to the admin
      const zipPath = `${SESSION_FOLDER}.zip`;
      const archiver = require('archiver');
      const output = fs.createWriteStream(zipPath);
      const archive = archiver('zip', {
        zlib: {
          level: 9
        }
      });
      archive.pipe(output);
      archive.directory(SESSION_FOLDER, false);
      archive.finalize();

      output.on('close', () => {
        telegramBot.telegram.sendDocument(ADMIN_TELEGRAM_ID, {
          source: zipPath
        }, {
          caption: '*Your WhatsApp session files are ready. Keep this file safe.*'
        }).then(() => {
          fs.unlinkSync(zipPath); // Clean up the zip file
        });
      });
    }
  });

  // Handle incoming messages on WhatsApp (optional)
  sock.ev.on('messages.upsert', async ({
    messages
  }) => {
    for (const msg of messages) {
      if (msg.key.fromMe) continue;
      const jid = msg.key.remoteJid;
      const text = msg.message?.extendedTextMessage?.text || msg.message?.conversation;
      if (text) {
        sendTelegramMessage(`*New WhatsApp message from ${jid}:*\n\`\`\`${text}\`\`\``);
      }
    }
  });

  sock.ev.on('creds.update', saveCreds);
}

// --- Telegram Commands ---
telegramBot.start((ctx) => {
  ctx.reply('Welcome! I am a bot designed to manage your WhatsApp connection. Use /connect to start.');
});

telegramBot.command('connect', async (ctx) => {
  await ctx.reply('Attempting to connect to WhatsApp... Please wait for a pairing code.');
  startWhatsAppBot();
});

telegramBot.command('disconnect', async (ctx) => {
  if (fs.existsSync(SESSION_FOLDER)) {
    try {
      fs.rmSync(SESSION_FOLDER, {
        recursive: true,
        force: true
      });
      ctx.reply('WhatsApp session files have been deleted.');
    } catch (e) {
      console.error('Failed to delete session files:', e);
      ctx.reply('Failed to delete session files. Please check server permissions.');
    }
  } else {
    ctx.reply('No active WhatsApp session found.');
  }
});

// Start the Telegram bot
telegramBot.launch();
console.log('Telegram bot is running.');

// Graceful shutdown
process.once('SIGINT', () => telegramBot.stop('SIGINT'));
process.once('SIGTERM', () => telegramBot.stop('SIGTERM'));

