"""Telegram Bot with command handlers and inline keyboards.

Set TELEGRAM_BOT_TOKEN env var to your bot token from @BotFather.
Runs in long-polling mode by default.
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
    print("Get a token from @BotFather on Telegram")
    exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-bot")


async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Status", callback_data="status")],
        [InlineKeyboardButton("Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to the Berth Bot! Choose an option:", reply_markup=reply_markup
    )


async def help_command(update: Update, context):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Show main menu\n"
        "/help - Show this help message\n"
        "/status - Check bot status\n"
        "/echo <text> - Echo your message"
    )


async def status(update: Update, context):
    await update.message.reply_text("Bot is running and healthy!")


async def echo(update: Update, context):
    text = " ".join(context.args) if context.args else "Nothing to echo"
    await update.message.reply_text(f"Echo: {text}")


async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "status":
        await query.edit_message_text("Bot is running and healthy!")
    elif query.data == "help":
        await query.edit_message_text(
            "Commands: /start, /help, /status, /echo <text>"
        )


async def unknown(update: Update, context):
    await update.message.reply_text("Unknown command. Try /help for available commands.")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("echo", echo))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Starting Telegram bot in polling mode...")
    app.run_polling()


if __name__ == "__main__":
    main()
