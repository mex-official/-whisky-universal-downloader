from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from downloader import download_media
from rate_limiter import RateLimiter
from url_utils import is_valid_url

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
log = logging.getLogger("whisky")


def _int_setting(
    name: str, default: int, minimum: int, maximum: int
) -> int:
    raw = os.getenv(name, str(default)).strip()

    try:
        value = int(raw)
    except (TypeError, ValueError):
        log.warning("%s is invalid; using default %s", name, default)
        return default

    if not minimum <= value <= maximum:
        log.warning(
            "%s must be between %s and %s; using default %s",
            name, minimum, maximum, default,
        )
        return default

    return value


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
limiter = RateLimiter(
    limit=_int_setting("USER_RATE_LIMIT", 3, 1, 20),
    period_seconds=60,
)
MAX_CONCURRENT_DOWNLOADS = _int_setting(
    "MAX_CONCURRENT_DOWNLOADS", 2, 1, 8
)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message:
        await message.reply_text(
            "أهلًا بك في Whisky Universal Downloader.\n"
            "أرسل رابطًا عامًا مدعومًا أو استخدم /d <الرابط>.\n"
            "/help للمساعدة — /about حول البوت"
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message:
        await message.reply_text(
            "المنصات المستهدفة: YouTube، Instagram، TikTok، X/Twitter، "
            "Pinterest، Reddit.\n"
            "أرسل /d ثم الرابط أو أرسل الرابط مباشرة. "
            "التنزيل يخضع لقيود المنصة وحد الملف (48 MiB). "
            "لا ترسل روابط خاصة أو تتطلب تسجيل دخول."
        )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message:
        await message.reply_text(
            "Whisky Universal Downloader — يحاول تنزيل الوسائط العامة "
            "المتاحة. لا يوجد ضمان لدعم كل رابط أو منشور."
        )


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message is None:
        return

    args = getattr(context, "args", None) or []
    url = " ".join(args).strip()

    if not url and message.text:
        parts = message.text.strip().split(maxsplit=1)
        if parts and parts[0].startswith("/"):
            url = parts[1].strip() if len(parts) > 1 else ""
        else:
            url = message.text.strip()

    user = update.effective_user
    if user and not limiter.allow(user.id):
        await message.reply_text(
            "وصلت إلى حد الطلبات المؤقت. انتظر قليلًا ثم حاول مجددًا."
        )
        return

    # Perform basic URL validation here. Full validation, including DNS
    # checks, remains in download_media and runs in a worker thread.
    if not is_valid_url(url, resolve_dns=False):
        await message.reply_text(
            "أرسل رابطًا عامًا صالحًا من منصة مدعومة باستخدام HTTP أو HTTPS."
        )
        return

    status = await message.reply_text("جارٍ فحص الرابط وتجهيز التنزيل…")
    temp = None

    try:
        if semaphore.locked():
            try:
                await status.edit_text(
                    "هناك تنزيلات أخرى قيد التنفيذ. "
                    "سيبدأ طلبك عند توفر مكان."
                )
            except Exception:
                pass

        async with semaphore:
            temp, path = await asyncio.to_thread(download_media, url)

            with path.open("rb") as stream:
                await message.reply_document(
                    document=stream,
                    filename=path.name,
                    read_timeout=60,
                    write_timeout=60,
                )

        try:
            await status.delete()
        except Exception:
            pass

    except Exception as exc:
        log.warning("Download failed (%s)", type(exc).__name__)
        try:
            await status.edit_text(
                "تعذر التنزيل. قد يكون الرابط غير مدعوم أو خاصًا "
                "أو تجاوز حد الحجم، أو قد تكون الخدمة المصدر غير متاحة."
            )
        except Exception:
            log.warning("Could not update the download status message")

    finally:
        if temp is not None:
            try:
                temp.cleanup()
            except Exception:
                log.warning("Temporary download cleanup failed")


def main():
    if not TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is missing; configure it as an environment variable."
        )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler(["d", "v"], download))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
