
import os
import logging
import requests

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AUDIUS_API_KEY = os.getenv("AUDIUS_API_KEY", "").strip()
AUDIUS_BEARER_TOKEN = os.getenv("AUDIUS_BEARER_TOKEN", "").strip()

BASE_URL = "https://api.audius.co/v1"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def search_music(query):
    headers = {}

    if AUDIUS_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {AUDIUS_BEARER_TOKEN}"

    response = requests.get(
        f"{BASE_URL}/tracks/search",
        params={
            "query": query,
            "app_name": "SherryMusicBot",
            "limit": 5,
        },
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("data", [])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Welcome to Sherry Music Bot!\n\n"
        "Song ka naam bhejo aur music search karo."
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)

    if not query:
        await update.message.reply_text(
            "Use: /song song name"
        )
        return

    await find_song(update, query)


async def find_song(update, query):
    msg = await update.message.reply_text("🔎 Searching music...")

    try:
        tracks = search_music(query)

        if not tracks:
            await msg.edit_text("❌ Koi track nahi mila.")
            return

        text = "🎵 Search Results:\n\n"

        for i, track in enumerate(tracks, 1):
            title = track.get("title", "Unknown")
            artist = track.get("user", {}).get("name", "Unknown")
            text += f"{i}. {title}\n👤 {artist}\n\n"

        await msg.edit_text(text)

    except Exception:
        log.exception("Audius search failed")
        await msg.edit_text(
            "❌ Music search failed. API settings check karo."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    await find_song(update, query)


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("song", search))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    print("Sherry Music Bot Started!")
    app.run_polling()


if __name__ == "__main__":
    main()
