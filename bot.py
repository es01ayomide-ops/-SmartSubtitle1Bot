"""
SmartSubtitle Bot (@SmartSubtitle1Bot)

Send a video/audio file or a YouTube link -> get back an .srt subtitle file.

Run locally:
    export TELEGRAM_BOT_TOKEN=xxxx
    python bot.py
"""

import os
import logging
import tempfile
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from utils import transcribe_audio, download_youtube_audio, is_youtube_url

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Telegram's default Bot API server caps file downloads at 20MB for bots.
MAX_TELEGRAM_FILE_SIZE = 20 * 1024 * 1024


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I'm SmartSubtitle Bot.\n\n"
        "Send me:\n"
        "🎬 a video or audio file, or\n"
        "🔗 a YouTube link\n\n"
        "...and I'll send back a subtitle (.srt) file.\n\n"
        "Commands:\n"
        "/start - show this message\n"
        "/help - usage tips"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 How to use:\n"
        "1. Send a video/audio file (mp4, mp3, wav, m4a, ogg, voice notes...) "
        "up to 20MB, OR paste a YouTube link.\n"
        "2. Wait while I transcribe it — this can take a while depending on length.\n"
        "3. I'll reply with a .srt file you can drop straight into your editor.\n\n"
        "Note: Telegram bots can only download files up to 20MB. For longer videos, "
        "trim the audio first or send a YouTube link instead."
    )


async def _run_transcription_and_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE, audio_path: str, base_name: str
):
    """Shared logic: transcribe audio_path, send back .srt, clean up."""
    status_msg = await update.message.reply_text("🎧 Transcribing... this may take a bit.")
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        loop = asyncio.get_running_loop()
        srt_text, language = await loop.run_in_executor(
            None, transcribe_audio, audio_path
        )

        if not srt_text.strip():
            await status_msg.edit_text("⚠️ I couldn't detect any speech in that file.")
            return

        srt_path = os.path.join(tempfile.gettempdir(), f"{base_name}.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_text)

        await status_msg.edit_text(f"✅ Done! Detected language: {language}")
        with open(srt_path, "rb") as f:
            await update.message.reply_document(
                document=f, filename=f"{base_name}.srt"
            )

        os.remove(srt_path)
    except Exception:
        logger.exception("Transcription failed")
        await status_msg.edit_text(
            "❌ Something went wrong while transcribing that file. Please try again."
        )
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles video, audio, voice, and document (media) uploads."""
    message = update.message
    tg_file_obj = (
        message.video or message.audio or message.voice or message.document
    )
    if tg_file_obj is None:
        return

    if tg_file_obj.file_size and tg_file_obj.file_size > MAX_TELEGRAM_FILE_SIZE:
        await message.reply_text(
            "⚠️ That file is larger than Telegram's 20MB bot download limit. "
            "Try trimming it, compressing it, or sending a YouTube link instead."
        )
        return

    await message.reply_text("⬇️ Downloading your file...")
    tg_file = await tg_file_obj.get_file()

    suffix = Path(tg_file.file_path).suffix or ".bin"
    tmp_dir = tempfile.mkdtemp(prefix="ssbot_")
    local_path = os.path.join(tmp_dir, f"input{suffix}")
    await tg_file.download_to_drive(local_path)

    base_name = Path(local_path).stem
    await _run_transcription_and_reply(update, context, local_path, base_name)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles plain text messages — checks for a YouTube link."""
    text = update.message.text or ""

    if not is_youtube_url(text):
        await update.message.reply_text(
            "Send me a video/audio file or a YouTube link to get started. "
            "Use /help for more info."
        )
        return

    await update.message.reply_text("⬇️ Downloading audio from YouTube...")
    tmp_dir = tempfile.mkdtemp(prefix="ssbot_yt_")

    try:
        loop = asyncio.get_running_loop()
        audio_path, title = await loop.run_in_executor(
            None, download_youtube_audio, text.strip(), tmp_dir
        )
    except Exception:
        logger.exception("YouTube download failed")
        await update.message.reply_text(
            "❌ Couldn't download that YouTube video. It may be private, age-restricted, "
            "or otherwise unavailable."
        )
        return

    base_name = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:60] or "subtitle"
    await _run_transcription_and_reply(update, context, audio_path, base_name)


def build_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL,
            handle_media,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


def main():
    app = build_app()
    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
