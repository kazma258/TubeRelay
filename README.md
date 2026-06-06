# TubeRelay

一個以 Python 撰寫的 Telegram Bot，透過 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 下載 YouTube 影片，並轉換為 MP3 或 MP4 後回傳給使用者。

## 功能

- 接收 YouTube 連結，解析標題、時長與縮圖
- Inline Keyboard 選擇 **MP3 音訊** 或 **MP4 影片**
- 依檔案大小分流上傳：≤50MB 官方 API、50–500MB Local Bot API
- 自動篩選可用品質（音質 / 解析度），大檔選項標示 `[大檔]`
- 下載前顯示預估檔案大小
- 異步架構，下載任務不阻塞其他使用者
- MP4 上傳前套用 faststart，Telegram 內可邊緩衝邊播放
- 上傳完成後自動清理暫存檔
- Docker 容器化，支援遠端一鍵部署

## 限制

| 項目 | 說明 |
|------|------|
| 檔案大小 | ≤50MB 走官方 API；50–500MB 需 Local Bot API；>500MB 拒絕 |
| 平台 | 主要針對 YouTube，其他 yt-dlp 支援的網站理論上可用 |
| 出站連線 | Bot 僅需對外連線，**無需**開放入站端口 |

## 快速開始

### 1. 取得原始碼

```bash
git clone https://github.com/kazma258/TubeRelay.git
cd TubeRelay
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 設定環境變數

複製範例設定並填入實際值：

```bash
cp .env.example .env
```

`.env` 至少需設定 `BOT_TOKEN`。Docker 大檔上傳還需至 [my.telegram.org](https://my.telegram.org) 申請 `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`（詳見 `.env.example`）。

本地開發若未啟動 Local Bot API，僅能上傳 ≤50MB 的檔案。

Windows 本地開發若 FFmpeg 不在 PATH，可額外設定：

```ini
FFMPEG_PATH=C:\path\to\ffmpeg\bin
```

Linux / macOS 安裝 FFmpeg：

```bash
# Debian / Ubuntu
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### 4. 啟動

```bash
python main.py
```

看到 `機器人正在運行中...` 後，在 Telegram 傳送 YouTube 連結即可使用。

## 使用方式

1. 在 Telegram 找到你的 Bot，傳送 `/start`
2. 貼上 YouTube 影片連結
3. 選擇 **MP3** 或 **MP4**
4. 選擇品質（≤50MB 標準；50–500MB 標示 `[大檔]`）
5. 等待下載與上傳完成

## 專案結構

```text
TubeRelay/
├── main.py              # 程式入口，註冊 Handler 並啟動 polling
├── config.py            # 環境變數、下載路徑、檔案大小上限
├── handlers.py          # Telegram 訊息與按鈕回調
├── services/
│   └── downloader.py    # yt-dlp 下載、格式分析、FFmpeg 轉檔
├── Dockerfile           # 容器映像（含 FFmpeg）
├── docker-compose.yml   # 雙容器編排（bot + telegram-bot-api）
├── deploy.sh            # rsync + 遠端重建部署腳本
├── .env.example         # 環境變數範本
└── requirements.txt     # Python 依賴
```

### 模組職責

| 模組 | 職責 |
|------|------|
| `main.py` | 初始化 `ApplicationBuilder`，註冊 `/start`、URL 訊息、`CallbackQuery` |
| `config.py` | 讀取 `BOT_TOKEN`、雙檔案上限、`LOCAL_BOT_API_URL`、`to_local_api_file_uri()` |
| `handlers.py` | URL 驗證 → 格式選擇 → 品質選擇 → 下載上傳 → 清理 |
| `services/downloader.py` | `get_video_info`、`get_available_formats`、`download_media` |

### 請求流程

```text
使用者傳送 URL
    → handle_url()          解析影片資訊，顯示 MP3 / MP4 按鈕
    → handle_format_selection()  分析可用格式，顯示品質選項
    → handle_quality_download()  run_in_executor(download_media)
    → send_audio / send_video   依大小分流（官方 API 或 Local API file:///）並刪除暫存
```

同步的 yt-dlp 操作皆透過 `asyncio.run_in_executor` 執行，避免阻塞 Telegram 事件迴圈。

## Docker 部署

採用雙容器架構：`telegram-bot` 處理 polling 與小檔上傳；`telegram-bot-api` 提供 Local Bot API 供大檔以 `file:///` 路徑上傳。

```text
使用者 → telegram-bot (官方 API polling)
              ↓ 下載至共享 ./downloads
         檔案 ≤ 50MB  → context.bot（官方 API）
         檔案 50–500MB → local_bot（Local API, file:///downloads/...）
```

| 容器 | 掛載 | 說明 |
|------|------|------|
| `telegram-bot` | `./downloads` → `/app/downloads` | Bot 主程式 |
| `telegram-bot-api` | `./downloads` → `/downloads` | Local API，8081 僅 Docker 內網 expose |

```bash
# 建立 .env（含 BOT_TOKEN、TELEGRAM_API_ID、TELEGRAM_API_HASH）後啟動
docker compose up -d

# 確認兩個服務皆健康
docker compose ps
docker compose logs telegram-bot-api --tail=20
docker compose logs telegram-bot --tail=20

# 停止
docker compose down
```

### 上傳分流規則

| 檔案大小 | API | 上傳方式 |
|----------|-----|----------|
| ≤ 50 MB | 官方 `api.telegram.org` | `open(filepath, 'rb')` |
| 50–500 MB | Local Bot API | `file:///downloads/{檔名}` |
| > 500 MB | 不上傳 | 錯誤提示 |

### 部署後測試

| 案例 | 預期 |
|------|------|
| ~30MB 音檔 | 官方 API 上傳成功 |
| ~80MB 影片 | Local API `file:///` 上傳成功 |
| >500MB | 拒絕，不嘗試上傳 |
| `telegram-bot-api` 未啟動 | >50MB 檔案提示「大檔服務未就緒」 |

## 遠端伺服器部署

以下說明如何部署到支援 SSH 的 Linux 伺服器（以 Ubuntu 為例）。

### 伺服器環境準備

```bash
ssh -i ~/.ssh/id_rsa ubuntu@your-server-ip

sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt install docker-compose -y
sudo usermod -aG docker $USER
exit
```

重新連線後：

```bash
mkdir -p ~/TubeRelay
cd ~/TubeRelay
nano .env   # 填入 BOT_TOKEN、TELEGRAM_API_ID、TELEGRAM_API_HASH
```

### 方法 1：使用 deploy.sh（推薦）

編輯 `deploy.sh`：

```bash
REMOTE_USER="ubuntu"
REMOTE_HOST="your-server-ip"
REMOTE_PORT="22"
SSH_KEY="$HOME/.ssh/id_rsa"
```

執行部署：

```bash
chmod +x deploy.sh
./deploy.sh
```

腳本會透過 rsync 同步檔案，並在遠端執行 `docker-compose down` → `build` → `up -d`。

### 方法 2：手動部署

```bash
rsync -avz --exclude '.git' \
           --exclude '__pycache__' \
           --exclude 'downloads/' \
           --exclude 'bot-api-data/' \
           --exclude 'ffmpeg-8.0.1*' \
           --exclude '.env' \
           ./ ubuntu@your-server-ip:~/TubeRelay/

ssh ubuntu@your-server-ip
cd ~/TubeRelay
docker-compose up -d
```

### 日常維護

```bash
# 即時日誌
ssh ubuntu@your-server-ip 'cd ~/TubeRelay && docker-compose logs -f'

# 重啟
ssh ubuntu@your-server-ip 'cd ~/TubeRelay && docker-compose restart'

# 更新程式碼（本地修改後）
./deploy.sh
```

### 故障排除

```bash
docker-compose ps
docker-compose logs
```

- **容器無法啟動**：檢查 `.env` 是否包含有效的 `BOT_TOKEN`
- **記憶體不足**：可於 `docker-compose.yml` 調整資源限制
- **網路問題**：確認伺服器可對外連線

## 功能一覽

| 功能 | 實作位置 |
|------|----------|
| 接收 URL 並解析影片資訊 | `handlers.handle_url` → `downloader.get_video_info` |
| MP3 / MP4 Inline 按鈕與二階段品質選擇 | `handlers.handle_url`、`get_available_formats` |
| 檔案大小分流上傳（50MB / 500MB） | `config`、`handlers.handle_quality_download` |
| Local Bot API 大檔上傳 | `main.post_init`、`config.to_local_api_file_uri` |
| MP4 faststart 漸進式播放 | `downloader._optimize_mp4_for_streaming`、`supports_streaming` |
| 異步下載（不阻塞 polling） | `asyncio.run_in_executor` |
| 上傳 metadata 與暫存清理 | `handlers._send_media`、`finally` 區塊 |
| 長 URL callback 快取 | `handlers._store_url` |

## 技術棧

- Python 3.11+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v20+（Async）
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- FFmpeg
- Docker / Docker Compose

## 授權

MIT License

## 貢獻

歡迎提交 Issue 與 Pull Request。
