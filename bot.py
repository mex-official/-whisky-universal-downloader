import os
import tempfile
import logging
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from url_utils import is_valid_url

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "أهلًا! أرسل رابطًا مباشرًا من منصة مدعومة.\n"
        "الأوامر: /d رابط — /help — /about"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "أرسل الرابط في رسالة أو استخدم /d رابط.\n"
        "قد لا تدعم بعض المواقع التنزيل، وقد تفرض قيودًا على المحتوى."
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Whisky Universal Downloader — نسخة أولية. دعم المواقع الفعلي غير مُتحقق منه."
    )

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    url = " ".join(context.args).strip()
    if not url and message:
        url = (message.text or "").strip()
    if not is_valid_url(url):
        await message.reply_text("أرسل رابط HTTP أو HTTPS صالحًا.")
        return
    await message.reply_text("جارٍ فحص الرابط ومحاولة التنزيل…")
    try:
        import yt_dlp
        with tempfile.TemporaryDirectory(prefix="whisky_") as tmp:
            opts = {
                "outtmpl": str(Path(tmp) / "%(title).100s.%(ext)s"),
                "noplaylist": True,
                "max_filesize": 48 * 1024 * 1024,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
            if not path.exists():
                candidates = list(Path(tmp).glob("*"))
                if not candidates:
                    raise RuntimeError("لم يُنتج الموقع ملفًا قابلًا للإرسال.")
                path = candidates[0]
            if path.stat().st_size > 48 * 1024 * 1024:
                await message.reply_text("الملف أكبر من حد الإرسال البالغ 48 MiB.")
                return
            with path.open("rb") as f:
                await message.reply_document(document=f, filename=path.name)
    except Exception as exc:
        log.warning("Download failed: %s", type(exc).__name__)
        await message.reply_text(
            "تعذر التنزيل. قد يكون الموقع غير مدعوم أو يتطلب تسجيل دخول."
        )

def main():
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN غير مضبوط. أنشئ ملف .env محليًا أولًا.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler(["d", "v"], download))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))
    app.run_polling()

if __name__ == "__main__":
    main()
