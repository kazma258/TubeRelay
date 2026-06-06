import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("警告：未在 .env 檔案中設定 BOT_TOKEN")

# 設定
DOWNLOAD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
OFFICIAL_MAX_FILE_SIZE = int(os.getenv("OFFICIAL_MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
LOCAL_MAX_FILE_SIZE = int(os.getenv("LOCAL_MAX_FILE_SIZE_MB", "500")) * 1024 * 1024
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "")
LOCAL_API_FILE_PREFIX = os.getenv("LOCAL_API_FILE_PREFIX", "/downloads")
FILE_RETENTION_DAYS = int(os.getenv("FILE_RETENTION_DAYS", "30"))
FILE_RETENTION_SECONDS = FILE_RETENTION_DAYS * 24 * 60 * 60
STORAGE_LIMIT_BYTES = int(os.getenv("STORAGE_LIMIT_GB", "20")) * 1024 * 1024 * 1024


def to_local_api_file_uri(filepath: str) -> str:
    """將 bot 容器內的下載路徑轉為 Local API 容器可讀的 file:// URI。"""
    return f"file://{LOCAL_API_FILE_PREFIX}/{os.path.basename(filepath)}"

# 確保下載目錄存在
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

import shutil

# FFMPEG 路徑配置
# 優先使用環境變數設定的路徑，若未設定則嘗試從系統 PATH 中尋找
env_ffmpeg_path = os.getenv("FFMPEG_PATH")
FFMPEG_LOCATION = None

if env_ffmpeg_path:
    if os.path.isdir(env_ffmpeg_path):
        # 如果給的是目錄，嘗試在裡面找 ffmpeg.exe
        potential_ffmpeg = os.path.join(env_ffmpeg_path, 'ffmpeg.exe')
        if os.path.exists(potential_ffmpeg):
            FFMPEG_LOCATION = potential_ffmpeg
        else:
            # 嘗試找 bin 子目錄
            potential_bin_ffmpeg = os.path.join(env_ffmpeg_path, 'bin', 'ffmpeg.exe')
            if os.path.exists(potential_bin_ffmpeg):
                FFMPEG_LOCATION = potential_bin_ffmpeg
            else:
                raise FileNotFoundError(f"錯誤：在目錄 {env_ffmpeg_path} 中找不到 ffmpeg.exe。請確保您下載的是 Windows 'Build/Binary' 而非 'Source Code'。")
    elif os.path.isfile(env_ffmpeg_path):
        if os.path.basename(env_ffmpeg_path).lower().startswith('ffmpeg'):
            FFMPEG_LOCATION = env_ffmpeg_path
        else:
            print(f"警告：設定的 FFMPEG_PATH ({env_ffmpeg_path}) 似乎不是 ffmpeg 執行檔，這可能會導致問題。")
            FFMPEG_LOCATION = env_ffmpeg_path
    else:
         raise FileNotFoundError(f"錯誤：在 .env 設定的 FFMPEG 路徑不存在：{env_ffmpeg_path}")
else:
    # 嘗試從系統 PATH 尋找
    system_ffmpeg = shutil.which('ffmpeg')
    if system_ffmpeg:
        FFMPEG_LOCATION = system_ffmpeg

if not FFMPEG_LOCATION:
    raise FileNotFoundError("錯誤：未安裝 FFMPEG 或未將其加入系統 PATH，且未在 .env 設定有效的 FFMPEG_PATH。\n請下載 Windows Binary 版本並設定路徑。")

# 檢查 ffprobe (yt-dlp 後處理和資訊解析通常也需要它)
ffmpeg_dir = os.path.dirname(FFMPEG_LOCATION)
ffprobe_path = os.path.join(ffmpeg_dir, 'ffprobe.exe')
if not os.path.exists(ffprobe_path):
    # 嘗試在 PATH 找
    if not shutil.which('ffprobe'):
        print("警告：找不到 ffprobe.exe。雖然 ffmpeg 存在，但缺少 ffprobe 可能導致部分功能失敗。請確保兩者在同一目錄。")

print(f"Info: 使用 FFMPEG 路徑: {FFMPEG_LOCATION}")
