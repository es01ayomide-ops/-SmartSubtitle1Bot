"""
Helper utilities for SmartSubtitle bot:
- Whisper transcription (faster-whisper)
- SRT file generation
- YouTube audio download (yt-dlp)
"""

import os
import re
import logging
from datetime import timedelta

from faster_whisper import WhisperModel
import yt_dlp

logger = logging.getLogger(__name__)

YOUTUBE_REGEX = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+"
)

_model = None  # lazy-loaded singleton


def get_model():
    """Load the faster-whisper model once and reuse it for every request."""
    global _model
    if _model is None:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        logger.info(
            "Loading faster-whisper model '%s' (device=%s, compute_type=%s)...",
            model_size, device, compute_type,
        )
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Model loaded.")
    return _model


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_REGEX.search(text or ""))


def format_timestamp(seconds: float) -> str:
    """Convert seconds (float) to SRT timestamp: HH:MM:SS,mmm"""
    td = timedelta(seconds=max(seconds, 0))
    total_ms = int(td.total_seconds() * 1000)
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def transcribe_audio(file_path: str, task: str = "transcribe"):
    """
    Run faster-whisper on an audio/video file.
    task: 'transcribe' (keep original language) or 'translate' (to English)
    Returns (srt_text, detected_language)
    """
    model = get_model()
    segments, info = model.transcribe(
        file_path,
        task=task,
        vad_filter=True,  # skip silence, speeds things up & improves accuracy
        beam_size=5,
    )

    srt_lines = []
    for i, seg in enumerate(segments, start=1):
        start = format_timestamp(seg.start)
        end = format_timestamp(seg.end)
        text = seg.text.strip()
        srt_lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    srt_text = "\n".join(srt_lines) if srt_lines else ""
    return srt_text, info.language


def download_youtube_audio(url: str, output_dir: str) -> tuple[str, str]:
    """
    Download best audio from a YouTube URL and convert to wav.
    Returns (file_path, video_title)
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info["id"]
        title = info.get("title", video_id)

    file_path = os.path.join(output_dir, f"{video_id}.wav")
    return file_path, title
