from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telegram import BotCommand
from downloader import download_media
from job_gate import JobGate
from rate_limiter import RateLimiter
from url_utils import is_valid_url
import network_guard

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
MAX_WAITING_JOBS = _int_setting("MAX_WAITING_JOBS", 4, 0, 20)
MAX_CONCURRENT_UPLOADS = _int_setting(
    "MAX_CONCURRENT_UPLOADS", 2, 1, 8
)

download_gate = JobGate(
    max_active=MAX_CONCURRENT_DOWNLOADS,
    max_waiting=MAX_WAITING_JOBS,
)
upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)


CHANNEL = "@GlobalFinancialNexus"
CHANNEL_URL = "https://t.me/GlobalFinancialNexus"
SUPPORT_URL = "https://t.me/x_whisky_7"
BOT_URL = "https://t.me/Whisky_DL_2026_bot"

DEFAULT_SETTINGS = {
    "delete_link": True,
    "audio_only": False,
}


def get_settings(context):
    settings = context.user_data.setdefault("whisky_settings", {})
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)
    return settings


def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️  بدء التنزيل", callback_data="menu:download")],
        [
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu:settings"),
            InlineKeyboardButton("🧩 المنصات", callback_data="menu:platforms"),
        ],
        [
            InlineKeyboardButton("❔ المساعدة", callback_data="menu:help"),
            InlineKeyboardButton("🔎 التحقق من الاشتراك", callback_data="menu:check"),
        ],
        [
            InlineKeyboardButton("📢 القناة", url=CHANNEL_URL),
            InlineKeyboardButton("🎧 الدعم", url=SUPPORT_URL),
        ],
        [
            InlineKeyboardButton(
                "➕ إضافة إلى مجموعة",
                url=BOT_URL + "?startgroup=true",
            ),
        ],
    ])

def settings_keyboard(context):
    settings = get_settings(context)
    labels = [
        ("delete_link", "حذف الرابط بعد نجاح الرفع"),
        ("audio_only", "الصوت فقط"),
    ]
    rows = []
    for key, label in labels:
        state = "مفعّل" if settings[key] else "معطّل"
        rows.append([InlineKeyboardButton(
            f"{label}: {state}", callback_data=f"settings:toggle:{key}"
        )])
    rows.append([InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


async def is_channel_member(update, context):
    user = update.effective_user
    if user is None:
        return False
    try:
        member = await context.bot.get_chat_member(CHANNEL, user.id)
        return member.status in ("creator", "administrator", "member") or (
            member.status == "restricted" and getattr(member, "is_member", False)
        )
    except Exception:
        log.exception("Unable to verify channel membership")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message:
        await message.reply_text(
            "🥃 <b>WHISKY UNIVERSAL DOWNLOADER</b>\\n"
            "━━━━━━━━━━━━━━━━━━\\n\\n"
            "مرحبًا بك في مركز التنزيلات\\n\\n"
            "📥 أرسل رابط المحتوى المدعوم لبدء التنزيل.\\n"
            "🎵 يمكنك تفعيل وضع الصوت من الإعدادات.\\n"
            "🛡️ استخدم الروابط التي تملك حق الوصول إليها.\\n\\n"
            "اختر الخدمة المطلوبة من القائمة أدناه.",
            parse_mode="HTML",
            reply_markup=menu_keyboard(),
        )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    action = query.data or ""

    if action == "menu:check":
        if await is_channel_member(update, context):
            text = "✅ تم التحقق: اشتراكك ظاهر للبوت. يمكنك إرسال رابط للتنزيل."
        else:
            text = (
                "🔒 لا أستطيع تأكيد اشتراكك. اشترك بالقناة ثم اضغط «تحقق من الاشتراك».\n"
                "إذا كنت مشتركًا بالفعل، تأكد أن البوت يستطيع قراءة عضوية القناة."
            )
        await query.edit_message_text(text, reply_markup=menu_keyboard())
        return

    if action.startswith("settings:toggle:"):
        key = action.rsplit(":", 1)[-1]
        if key not in DEFAULT_SETTINGS:
            await query.answer("إعداد غير معروف", show_alert=True)
            return
        settings = get_settings(context)
        settings[key] = not settings[key]
        await query.edit_message_text(
            "⚙️ إعدادات Whisky\n\n"
            "الصوت فقط يحاول استخراج MP3. حذف الرابط يحدث بعد نجاح رفع الملف.",
            reply_markup=settings_keyboard(context),
        )
        return

    if action == "menu:settings":
        await query.edit_message_text(
            "⚙️ إعدادات Whisky\n\n"
            "يمكنك اختيار استخراج الصوت فقط وحذف رسالة الرابط بعد نجاح الرفع.",
            reply_markup=settings_keyboard(context),
        )
        return

    if action == "menu:platforms":
        text = (
            "📡 المنصات التي يستهدفها المشروع:\n"
            "YouTube، TikTok، Instagram، X/Twitter، Pinterest، Reddit.\n\n"
            "الدعم الفعلي يختلف حسب الرابط وقيود المنصة؛ لا أضمن عمل كل رابط."
        )
    elif action == "menu:help":
        text = (
            "📘 طريقة الاستخدام\n"
            "1. اشترك بقناة GLOBAL FINANCIAL NEXUS.\n"
            "2. اضغط تحقق من الاشتراك.\n"
            "3. أرسل رابطًا عامًا مدعومًا أو استخدم /d <الرابط>.\n"
            "حد الملف الحالي 48 MiB."
        )
    elif action == "menu:download":
        text = "أرسل رابط الوسائط العام هنا أو استخدم الأمر /d متبوعًا بالرابط."
    elif action == "menu:about":
        text = "Whisky Universal Downloader — تنزيل وسائط عامة حسب دعم الرابط والمنصة."
    else:
        text = (
            "WHISKY UNIVERSAL DOWNLOADER\n\n"
            "أرسل رابطًا عامًا مدعومًا أو استخدم /d متبوعًا بالرابط."
        )

    await query.edit_message_text(text, reply_markup=menu_keyboard())


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
    if not message:
        return

    # Real Telegram updates have context.bot; lightweight test contexts may not.
    if getattr(context, "bot", None) is not None:
        if not await is_channel_member(update, context):
            await message.reply_text(
                "🔒 التنزيل متاح للمشتركين في قناة GLOBAL FINANCIAL NEXUS فقط.\n"
                "اشترك ثم اضغط «تحقق من الاشتراك» في /start.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 الاشتراك بالقناة", url=CHANNEL_URL)],
                    [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="menu:check")],
                ]),
            )
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

    if not is_valid_url(url, resolve_dns=False):
        await message.reply_text(
            "أرسل رابطًا عامًا صالحًا من منصة مدعومة باستخدام HTTP أو HTTPS."
        )
        return

    status = await message.reply_text(
        "🥃 <b>WHISKY • مركز التنزيل</b>\\n"
        "━━━━━━━━━━━━━━━━━━\\n"
        "🔎 <b>المرحلة 1/3:</b> فحص الرابط وتجهيز المهمة…",
        parse_mode="HTML",
    )
    temp = None
    admitted = False

    try:
        admitted = await download_gate.acquire()
        if not admitted:
            await status.edit_text(
                "الخدمة مشغولة حاليًا والطلبات المنتظرة ممتلئة. "
                "انتظر قليلًا ثم أعد المحاولة."
            )
            return

        try:
            # Shield the worker so cancellation of this handler does not
            # abandon a running download thread and lose its temp handle.
            settings = get_settings(context)
            audio_only = bool(settings.get("audio_only", False))
            worker = asyncio.create_task(
                asyncio.to_thread(download_media, url, audio_only)
            )
            try:
                temp, path = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # The worker thread may continue after its handler is cancelled.
                # A separate task owns cleanup if the worker later returns a temp dir.
                async def cleanup_worker_result():
                    try:
                        result = await worker
                    except BaseException:
                        # Download errors are handled by download_media itself.
                        return

                    abandoned_temp, _ = result
                    try:
                        abandoned_temp.cleanup()
                    except Exception:
                        log.warning(
                            "Temporary download cleanup failed after cancellation"
                        )

                asyncio.create_task(cleanup_worker_result())
                raise
        finally:
            if admitted:
                admitted = False
                await asyncio.shield(download_gate.release())

        # Download capacity is released before waiting for Telegram upload.
        await status.edit_text(
            "🥃 <b>WHISKY • مركز التنزيل</b>\\n"
            "━━━━━━━━━━━━━━━━━━\\n"
            "✅ <b>المرحلة 2/3:</b> اكتمل تنزيل الملف.\\n"
            "📤 <b>المرحلة 3/3:</b> جارٍ رفعه إلى تيليجرام…",
        )
        async with upload_semaphore:
            suffix = path.suffix.lower()
            with path.open("rb") as stream:
                if suffix == ".mp4":
                    await message.reply_video(
                        video=InputFile(stream, filename=path.name),
                        supports_streaming=True,
                        read_timeout=60,
                        write_timeout=60,
                    )
                elif suffix in {".mp3", ".m4a"}:
                    await message.reply_audio(
                        audio=InputFile(stream, filename=path.name),
                        read_timeout=60,
                        write_timeout=60,
                    )
                else:
                    await message.reply_document(
                        document=InputFile(stream, filename=path.name),
                        read_timeout=60,
                        write_timeout=60,
                    )

        settings = get_settings(context)
        if settings.get("delete_link", False):
            try:
                await message.delete()
            except Exception:
                log.info("Could not delete source message after successful upload")

        try:
            await status.edit_text(
                "✨ <b>اكتملت المهمة بنجاح</b>\\n"
                "تم تنزيل الملف ورفعه إلى تيليجرام.",
            )
        except Exception:
            log.info("Could not update final download status")

    except Exception as exc:
        log.warning("Download failed (%s)", type(exc).__name__)
        try:
            await status.edit_text(
                "⚠️ <b>تعذر التنزيل أو الرفع</b>\\n"
                "قد يكون الرابط خاصًا أو غير مدعوم، أو تجاوز حد الحجم، "
                "أو أن المصدر غير متاح حاليًا.\\n"
                "تحقق من الرابط وحاول مرة أخرى.",
            )
        except Exception:
            log.warning("Could not update the download status message")

    finally:
        if admitted:
            admitted = False
            await asyncio.shield(download_gate.release())

        if temp is not None:
            try:
                temp.cleanup()
            except Exception:
                log.warning("Temporary download cleanup failed")




async def platforms_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "🔷 WHISKY / SUPPORTED PLATFORMS\\n"
        "━━━━━━━━━━━━━━━━━━\\n"
        "• YouTube\\n"
        "• TikTok\\n"
        "• Instagram\\n"
        "• X / Twitter\\n"
        "• Pinterest\\n"
        "• Reddit\\n\\n"
        "أرسل رابطًا عامًا مدعومًا أو استخدم /d متبوعًا بالرابط.\\n"
        "التوفر الفعلي يعتمد على الرابط وقيود المنصة."
    )


async def ping_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "🔷 WHISKY / BOT STATUS\\n"
        "━━━━━━━━━━━━━━━━━━\\n"
        "الحالة: يستجيب للأوامر\\n"
        "فحص الاتصال بتيليجرام: نجح وصول هذا الأمر\\n"
        "ملاحظة: هذا ليس فحصًا لمصادر التنزيل الخارجية."
    )


async def id_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    await message.reply_text(
        f"🔷 Chat ID: {chat.id}\\n"
        f"النوع: {chat.type}"
    )


async def configure_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "فتح القائمة الرئيسية"),
        BotCommand("help", "طريقة استخدام البوت"),
        BotCommand("about", "معلومات عن البوت"),
        BotCommand("platforms", "المنصات المدعومة"),
        BotCommand("ping", "فحص استجابة البوت"),
        BotCommand("id", "معرّف المحادثة"),
        BotCommand("d", "تنزيل رابط"),
        BotCommand("v", "تنزيل رابط"),
    ])





def main():
    if not TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is missing; configure it as an environment variable."
        )

    network_guard.install_public_network_guard()
    app = Application.builder().token(TOKEN).post_init(configure_bot_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(menu:(home|help|about|platforms|settings|download|check)|settings:toggle:[a-z_]+)$"))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("platforms", platforms_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler(["d", "v"], download))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
