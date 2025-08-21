// app.js

const {
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  makeWASocket
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const {
  Telegraf
} = require('telegraf');
const express = require('express');
const archiver = require('archiver');
const { parsePhoneNumber } = require("libphonenumber-js"); // NEW: Import phone number parser

// --- Configuration ---
const TELEGRAM_BOT_TOKEN = '7433555932:AAGF1T90OpzcEVZSJpUh8RkluxoF-w5Q8CY'; // Replace with your Telegram bot token
const SESSION_FOLDER = './session';
const PORT = process.env.PORT || 3000;

// --- Telegraf Bot Setup ---
const telegramBot = new Telegraf(TELEGRAM_BOT_TOKEN);

// --- Express Server Setup ---
const app = express();
app.get('/', (req, res) => {
  res.send('WhatsApp bot is running and listening for Telegram commands.');
});

// Start the Express server
app.listen(PORT, () => {
  console.log(`Web server listening on port ${PORT}`);
});

// --- WhatsApp Bot Logic ---
async function startWhatsAppBot(chatId, phoneNumber) {
  const logger = pino({
    level: 'info' // Set log level to info to see connection details
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

  sock.ev.on('connection.update', async (update) => {
    const {
      connection,
      lastDisconnect,
      isNewLogin
    } = update;
    if (isNewLogin) {
      try {
        // Baileys requires the phone number without a plus sign
        const code = await sock.requestPairingCode(phoneNumber); 
        telegramBot.telegram.sendMessage(chatId, `Your WhatsApp pairing code for number \`${phoneNumber}\` is: \`\`\`${code}\`\`\`\n\n*To link your account, go to WhatsApp > Linked Devices > Link with phone number and enter this code.*`, {
          parse_mode: 'Markdown'
        });
      } catch (e) {
        telegramBot.telegram.sendMessage(chatId, '*ERROR:* Failed to generate pairing code. Please check server logs for details.', {
          parse_mode: 'Markdown'
        });
        console.error('Failed to request pairing code:', e);
      }
    }
    if (connection === 'close') {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== 401;
      if (shouldReconnect) {
        startWhatsAppBot(chatId, phoneNumber);
      } else {
        telegramBot.telegram.sendMessage(chatId, '*ERROR:* Connection closed, possibly banned. You may need a new session.', {
          parse_mode: 'Markdown'
        });
      }
    } else if (connection === 'open') {
      telegramBot.telegram.sendMessage(chatId, '*SUCCESS:* WhatsApp session is now connected!', {
        parse_mode: 'Markdown'
      });
      const zipPath = `${SESSION_FOLDER}.zip`;
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
        telegramBot.telegram.sendDocument(chatId, {
          source: zipPath
        }, {
          caption: '*Your WhatsApp session files are ready. Keep this file safe.*',
          parse_mode: 'Markdown'
        }).then(() => {
          fs.unlinkSync(zipPath);
        });
      });
    }
  });

  sock.ev.on('creds.update', saveCreds);
}

// --- Telegram Commands ---
telegramBot.start((ctx) => {
  ctx.reply('Welcome! I am a bot designed to manage your WhatsApp connection. Use /connect to start.');
});

telegramBot.command('connect', async (ctx) => {
  const phoneNumber = ctx.message.text.split(' ')[1];
  if (!phoneNumber) {
    ctx.reply('Please provide a phone number. Usage: `/connect +<number>` (e.g., `/connect +12345678901`)', {
      parse_mode: 'Markdown'
    });
    return;
  }
  
  // Use a dedicated library to parse and validate the phone number
  let parsedNumber;
  try {
    parsedNumber = parsePhoneNumber(phoneNumber);
    if (!parsedNumber.isValid()) {
      throw new Error("Invalid phone number");
    }
  } catch (e) {
    ctx.reply('Invalid phone number format. Please use a valid number with a country code (e.g., `+12345678901`).', {
      parse_mode: 'Markdown'
    });
    return;
  }

  // Pass the phone number without the plus sign to the connection function
  const cleanNumber = parsedNumber.nationalNumber;
  
  await ctx.reply(`Attempting to connect to WhatsApp for number \`${cleanNumber}\`... Please wait for a pairing code.`, {
    parse_mode: 'Markdown'
  });
  startWhatsAppBot(ctx.chat.id, cleanNumber);
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

process.once('SIGINT', () => telegramBot.stop('SIGINT'));
process.once('SIGTERM', () => telegramBot.stop('SIGTERM'));
