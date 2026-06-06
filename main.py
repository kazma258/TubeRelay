import logging
import config
from telegram import Bot, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from handlers import start, handle_url, button_callback


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "查看 Bot 功能說明"),
    ])

    if config.LOCAL_BOT_API_URL and config.BOT_TOKEN:
        base_file_url = config.LOCAL_BOT_API_URL.replace("/bot", "/file/bot")
        local_bot = Bot(
            token=config.BOT_TOKEN,
            base_url=config.LOCAL_BOT_API_URL,
            base_file_url=base_file_url,
            local_mode=True,
        )
        await local_bot.initialize()
        application.bot_data["local_bot"] = local_bot
        official_mb = config.OFFICIAL_MAX_FILE_SIZE // 1024 // 1024
        local_mb = config.LOCAL_MAX_FILE_SIZE // 1024 // 1024
        print(f"Info: Local Bot API 已啟用 ({config.LOCAL_BOT_API_URL})")
        print(f"Info: 上傳分流 <= {official_mb}MB 官方 API / {official_mb}–{local_mb}MB Local API")
    else:
        application.bot_data["local_bot"] = None
        print("Info: Local Bot API 未設定，僅支援官方 API 上傳上限")

# 啟用日誌紀錄
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    if not config.BOT_TOKEN:
        print("錯誤：未在 .env 檔案中找到 BOT_TOKEN。")
        return

    application = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # 註冊處理器 (Handlers)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    # 處理非指令的文字訊息
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))

    print("機器人正在運行中...")
    application.run_polling()

if __name__ == '__main__':
    main()
