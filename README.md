# Whisky Universal Downloader

Standalone Telegram bot for publicly accessible media links from Facebook, TikTok, YouTube, Google Drive, Snapchat, Instagram, X/Twitter, Pinterest and Reddit. Audio-only mode can extract MP3 when FFmpeg is available. Support depends on upstream site behavior and does not imply every URL is downloadable. It uses `yt-dlp`; support depends on upstream site behavior and does not imply every URL is downloadable.

## Run locally

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` locally. Never commit tokens or paste them into chat.
3. Run `python bot.py`.
4. Run tests with `pytest`.

## Container

Build from the repository root with `docker build -f whisky-universal-downloader/Dockerfile -t whisky-bot whisky-universal-downloader` and provide `TELEGRAM_BOT_TOKEN` through the runtime environment/secret store. The health check verifies configuration only; it does not prove Telegram connectivity.

## Security notes

Only supported public platform domains are accepted. DNS answers are checked against non-public IP ranges and rejected on lookup failure. This reduces SSRF risk but cannot completely guarantee safety against DNS rebinding or redirects inside third-party extractors; use network-level egress restrictions in production. Files are stored in isolated temporary directories, capped at 48 MiB, and cleaned after sending. Rate limits are process-local and reset on restart. Do not use this bot to bypass access controls or download content without permission.

## Deployment status

This repository contains deployment artifacts, not a hosted service. Continuous operation requires a running host and a configured token. No hosting provider is configured by this code alone.
