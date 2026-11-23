
import os
import logging
import tempfile
import requests

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AUDIUS_API_KEY = os.getenv("AUDIUS_API_KEY", "").strip()
AUDIUS_BEARER_TOKEN = os.getenv("AUDIUS_BEARER_TOKEN", "").strip()

BASE_URL = "https://api.audius.co/v1"
APP_NAME = "SherryMusicBot"
MAX_FILE_SIZE = 49 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def get_headers():
    headers = {}

    if AUDIUS_API_KEY:
        headers["x-api-key"] = AUDIUS_API_KEY

    if AUDIUS_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {AUDIUS_BEARER_TOKEN}"

    return headers


def search_music(query):
    response = requests.get(
        f"{BASE_URL}/tracks/search",
        params={
            "query": query,
            "app_name": APP_NAME,
            "limit": 5,
        },
        headers=get_headers(),
        timeout=25,
    )

    response.raise_for_status()
    return response.json().get("data", [])


def download_track(track_id):
    url = f"{BASE_URL}/tracks/{track_id}/download"

    response = requests.get(
        url,
        params={"app_name": APP_NAME},
        headers=get_headers(),
        stream=True,
        timeout=60,
    )

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()

    if "text/html" in content_type or "application/json" in content_type:
        response.close()
        raise ValueError("Audius did not return an audio file.")

    temp = tempfile.NamedTemporaryFile(
        suffix=".mp3",
        delete=False
    )

    file_path = temp.name
    total_size = 0

    try:
        with temp:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise ValueError("Audio file is too large for Telegram.")

                temp.write(chunk)

    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    finally:
        response.close()

    if total_size == 0:
        os.remove(file_path)
        raise ValueError("Empty audio file received.")

    return file_path


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Welcome to Sherry Music Bot!\n\n"
        "Send any song name to search music.\n"
        "Or use /song song name\n\n"
        "Select a downloadable result to receive its audio."
    )


async def find_song(update, query, context):
    msg = await update.message.reply_text("🔎 Searching music...")

    try:
        tracks = search_music(query)

        if not tracks:
            await msg.edit_text("❌ No songs found.")
            return

        context.user_data["tracks"] = tracks

        keyboard = []

        for i, track in enumerate(tracks):
            title = track.get("title", "Unknown")
            artist = track.get("user", {}).get("name", "Unknown")

            keyboard.append([
                InlineKeyboardButton(
                    f"🎵 {title[:35]} - {artist[:20]}",
                    callback_data=f"play:{i}"
                )
            ])

        await msg.edit_text(
            "🎵 Search Results:\n\n"
            "Select a song to get its audio:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception:
        log.exception("Audius search failed")
        await msg.edit_text(
            "❌ Search failed. Check Audius API settings."
        )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()

    if not query:
        await update.message.reply_text(
            "Use: /song song name"
        )
        return

    await find_song(update, query, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()

    if query:
        await find_song(update, query, context)


async def play_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        index = int(query.data.split(":")[1])
        tracks = context.user_data.get("tracks", [])

        if index < 0 or index >= len(tracks):
            await query.message.reply_text(
                "❌ Search again. This result has expired."
            )
            return

        track = tracks[index]
        track_id = track.get("id")

        if not track_id:
            await query.message.reply_text("❌ Track ID missing.")
            return

        title = track.get("title", "Unknown")
        artist = track.get("user", {}).get("name", "Unknown")

        # Only download tracks explicitly marked downloadable.
        if track.get("is_downloadable") is not True:
            await query.message.reply_text(
                "⚠️ This song is not marked as downloadable by Audius.\n"
                "Please select another song."
            )
            return

        status = await query.message.reply_text(
            f"⏳ Preparing audio:\n{title}"
        )

        file_path = None

        try:
            import asyncio

            file_path = await asyncio.to_thread(
                download_track, track_id
            )

            with open(file_path, "rb") as audio:
                await query.message.reply_audio(
                    audio=audio,
                    title=title[:64],
                    performer=artist[:64],
                    caption=f"🎵 {title}\n👤 {artist}"
                )

            await status.delete()

        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    except Exception:
        log.exception("Audio sending failed")
        await query.message.reply_text(
            "❌ Could not send this audio.\n"
            "Try another downloadable track."
        )


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("song", search))

    app.add_handler(
        CallbackQueryHandler(play_song, pattern=r"^play:\d+$")
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("Sherry Music Bot Started!")

    app.run_polling()


if __name__ == "__main__":
    main()
