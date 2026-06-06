import os
import asyncio
import hashlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.downloader import get_video_info, get_available_formats, download_media
import config


def _store_url(context: ContextTypes.DEFAULT_TYPE, url: str) -> str:
    """將 URL 存入快取並回傳 8 字元 id（符合 Telegram callback_data 64 bytes 限制）。"""
    if "url_cache" not in context.bot_data:
        context.bot_data["url_cache"] = {}
    url_id = hashlib.sha256(url.encode()).hexdigest()[:8]
    context.bot_data["url_cache"][url_id] = url
    return url_id


def _resolve_url(context: ContextTypes.DEFAULT_TYPE, url_id: str) -> str | None:
    if url_id.startswith("http://") or url_id.startswith("https://"):
        return url_id
    return context.bot_data.get("url_cache", {}).get(url_id)


def _format_choice_keyboard(url_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🎵 音檔 (MP3)", callback_data=f"select_mp3|{url_id}"),
            InlineKeyboardButton("🎬 影片 (MP4)", callback_data=f"select_mp4|{url_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def _edit_menu_message(query, text: str, reply_markup=None):
    """依訊息類型更新文字或圖片說明（避免純文字訊息無法 edit_message_caption）。"""
    if query.message.photo:
        await query.edit_message_caption(
            caption=text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            text=text, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """當收到 /start 指令時發送歡迎訊息與功能說明。"""
    official_mb = config.OFFICIAL_MAX_FILE_SIZE // 1024 // 1024
    local_mb = config.LOCAL_MAX_FILE_SIZE // 1024 // 1024
    await update.message.reply_text(
        "👋 您好！我是 YouTube 下載機器人。\n\n"
        "📌 功能說明\n"
        "• 傳送 YouTube 連結，自動解析標題、時長與縮圖\n"
        "• 選擇下載 🎵 音檔 (MP3) 或 🎬 影片 (MP4)\n"
        f"• ≤{official_mb}MB 標準傳送；{official_mb}–{local_mb}MB 大檔模式\n\n"
        "📖 使用方式\n"
        "1. 貼上 YouTube 影片網址\n"
        "2. 點選音檔或影片\n"
        "3. 選擇品質並等待下載完成\n\n"
        f"⚠️ 單檔上限 {local_mb}MB（>{official_mb}MB 需啟用 Local Bot API）"
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理看起來像 URL 的傳入文字訊息。"""
    url = update.message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("請傳送有效的網址。")
        return

    status_msg = await update.message.reply_text("🔍 正在解析影片資訊...")

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_video_info, url)

        title = info["title"]
        thumbnail = info["thumbnail"]
        duration = info["duration"]

        m, s = divmod(duration, 60)
        h, m = divmod(m, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        caption = (
            f"🎬 **{title}**\n"
            f"⏱️ 時長: {duration_str}\n\n"
            f"請選擇要下載 **音檔** 或 **影片**："
        )

        url_id = _store_url(context, url)
        reply_markup = _format_choice_keyboard(url_id)

        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=status_msg.message_id
        )

        if thumbnail:
            await update.message.reply_photo(
                photo=thumbnail,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                text=caption, reply_markup=reply_markup, parse_mode="Markdown"
            )

    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id,
            text=f"❌ 解析失敗: {str(e)}",
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理按鈕點擊事件。"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("select_"):
        await handle_format_selection(update, context, data)
    elif data.startswith("download_"):
        await handle_quality_download(update, context, data)
    elif data.startswith("back|"):
        await handle_back_to_format(update, context, data)


async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    """處理格式選擇 (MP3/MP4)，顯示可用的品質選項。"""
    query = update.callback_query

    parts = data.split("|", 1)
    format_type = parts[0].replace("select_", "")
    url_id = parts[1]
    url = _resolve_url(context, url_id)

    if not url:
        await _edit_menu_message(query, "❌ 連結已過期，請重新傳送影片網址。")
        return

    format_label = "音檔" if format_type == "mp3" else "影片"
    await _edit_menu_message(query, f"🔍 正在分析可用的 {format_label} 格式...")

    try:
        loop = asyncio.get_event_loop()
        formats = await loop.run_in_executor(None, get_available_formats, url, format_type)

        if not formats:
            local_mb = config.LOCAL_MAX_FILE_SIZE // 1024 // 1024
            await _edit_menu_message(
                query,
                f"❌ 找不到符合 {local_mb}MB 限制的 {format_label} 格式。\n請嘗試較短的影片或較低畫質。",
            )
            return

        keyboard = []
        for fmt in formats:
            callback_data = f"download_{format_type}|{fmt['format_id']}|{url_id}"
            keyboard.append(
                [InlineKeyboardButton(fmt["description"], callback_data=callback_data)]
            )

        keyboard.append([InlineKeyboardButton("« 返回", callback_data=f"back|{url_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        official_mb = config.OFFICIAL_MAX_FILE_SIZE // 1024 // 1024
        local_mb = config.LOCAL_MAX_FILE_SIZE // 1024 // 1024
        await _edit_menu_message(
            query,
            f"請選擇 {format_label} 品質：\n"
            f"(≤{official_mb}MB 標準；{official_mb}–{local_mb}MB 標示 [大檔])",
            reply_markup=reply_markup,
        )

    except Exception as e:
        await _edit_menu_message(query, f"❌ 分析格式失敗: {str(e)}")


async def _send_media(bot, chat_id, format_type, media, title, duration, thumbnail_file, timeouts):
    """透過指定 Bot 實例上傳音訊或影片。"""
    if format_type == "mp3":
        await bot.send_audio(
            chat_id=chat_id,
            audio=media,
            title=title,
            performer="YouTube",
            duration=duration if duration > 0 else None,
            thumbnail=thumbnail_file,
            **timeouts,
        )
    else:
        await bot.send_video(
            chat_id=chat_id,
            video=media,
            duration=duration if duration > 0 else None,
            caption=title,
            thumbnail=thumbnail_file,
            supports_streaming=True,
            **timeouts,
        )


async def handle_quality_download(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    """處理品質選擇並開始下載。"""
    query = update.callback_query

    parts = data.split("|")
    format_type = parts[0].replace("download_", "")
    format_id = parts[1]
    url_id = parts[2]
    url = _resolve_url(context, url_id)

    if not url:
        await _edit_menu_message(query, "❌ 連結已過期，請重新傳送影片網址。")
        return

    format_label = "音檔" if format_type == "mp3" else "影片"
    await _edit_menu_message(
        query, f"⏳ 正在下載 {format_label}，請稍候...\n這可能需要一些時間。"
    )

    try:
        loop = asyncio.get_event_loop()
        filepath = await loop.run_in_executor(
            None, download_media, url, format_id, format_type
        )

        file_size = os.path.getsize(filepath)
        use_local = file_size > config.OFFICIAL_MAX_FILE_SIZE
        if use_local and not context.bot_data.get("local_bot"):
            await _edit_menu_message(
                query,
                "❌ 大檔服務未就緒（Local Bot API 未啟用）。請選擇較低品質或聯絡管理員。",
            )
            os.remove(filepath)
            return

        upload_bot = context.bot_data["local_bot"] if use_local else context.bot
        media = (
            config.to_local_api_file_uri(filepath)
            if use_local
            else open(filepath, "rb")
        )
        file_handle = media if not use_local else None

        upload_hint = ""
        if use_local:
            upload_hint = (
                "（超大檔模式）"
                if file_size > config.LOCAL_MAX_FILE_SIZE
                else "（大檔模式）"
            )
        await _edit_menu_message(query, f"📤 正在上傳檔案...{upload_hint}")

        video_info = await loop.run_in_executor(None, get_video_info, url)

        title = video_info.get("title", "Unknown")
        thumbnail_url = video_info.get("thumbnail")
        duration = video_info.get("duration", 0)

        thumbnail_file = None
        thumbnail_path = None
        if thumbnail_url:
            try:
                import urllib.request

                thumbnail_path = os.path.join(
                    config.DOWNLOAD_PATH, f"thumb_{os.path.basename(filepath)}.jpg"
                )
                urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
                thumbnail_file = open(thumbnail_path, "rb")
            except OSError:
                thumbnail_file = None

        chat_id = query.message.chat_id
        if use_local:
            timeout_secs = (
                1800 if file_size > config.LOCAL_MAX_FILE_SIZE else 900
            )
            timeouts = {
                "read_timeout": timeout_secs,
                "write_timeout": timeout_secs,
                "connect_timeout": 60,
            }
        else:
            timeouts = {
                "read_timeout": 300,
                "write_timeout": 300,
                "connect_timeout": 60,
            }
        try:
            await _send_media(
                upload_bot, chat_id, format_type, media, title, duration, thumbnail_file, timeouts
            )
        finally:
            if file_handle:
                file_handle.close()
            if thumbnail_file:
                thumbnail_file.close()
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except OSError:
                    pass

        await query.delete_message()
        await context.bot.send_message(chat_id=chat_id, text="✅ 下載完成！")

    except ValueError as ve:
        await context.bot.send_message(
            chat_id=query.message.chat_id, text=f"⚠️ {str(ve)}"
        )
    except Exception as e:
        if "Timed out" in str(e):
            print(f"Warning: 上傳時發生 Timeout ({e}),但檔案可能已發送成功。")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⚠️ 上傳耗時較久，若您已收到檔案請忽略此訊息；若未收到請稍後重試。",
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=f"❌ 下載或傳送失敗: {str(e)}"
            )
    finally:
        if "filepath" in locals() and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


async def handle_back_to_format(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    """處理返回按鈕，回到音檔/影片選擇畫面。"""
    query = update.callback_query
    url_id = data.split("|", 1)[1]

    await _edit_menu_message(
        query,
        "請選擇要下載 **音檔** 或 **影片**：",
        reply_markup=_format_choice_keyboard(url_id),
    )
