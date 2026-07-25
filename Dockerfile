FROM python:3.11-slim

# ffmpeg is required by yt-dlp (audio extraction) and by faster-whisper's
# underlying decoder for many audio/video formats.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Whisper model size (tiny/base/small/medium/large-v3). "base" is a good
# default balance of speed, accuracy, and RAM use for small Railway plans.
ENV WHISPER_MODEL_SIZE=base
ENV WHISPER_DEVICE=cpu
ENV WHISPER_COMPUTE_TYPE=int8

CMD ["python", "bot.py"]
