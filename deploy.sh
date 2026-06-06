#!/bin/bash

# 遠端伺服器部署腳本
# 使用方法: cp .env.example .env 填入參數後執行 ./deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ 找不到 .env，請先執行: cp .env.example .env"
    exit 1
fi

# shellcheck disable=SC1090
set -a
# 相容 Windows 編輯器產生的 CRLF .env
source <(sed 's/\r$//' "$ENV_FILE")
set +a

REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/TubeRelay}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_KEY="${SSH_KEY/#\~/$HOME}"

for var in REMOTE_USER REMOTE_HOST; do
    if [[ -z "${!var}" ]]; then
        echo "❌ .env 缺少必要變數: $var"
        exit 1
    fi
done

if [[ ! -f "$SSH_KEY" ]]; then
    echo "❌ SSH 金鑰不存在: $SSH_KEY"
    exit 1
fi

echo "🚀 開始部署 Telegram Bot 到遠端伺服器..."
echo "   目標: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT} → ${REMOTE_DIR}"

SSH_OPTS=(-p "$REMOTE_PORT" -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new)

echo "📦 正在同步檔案到遠端伺服器..."
rsync -avz --exclude '.git' \
           --exclude '__pycache__' \
           --exclude '.codegraph/' \
           --exclude 'downloads/' \
           --exclude 'bot-api-data/' \
           --exclude 'ffmpeg-8.0.1*' \
           --exclude '.env' \
           -e "ssh ${SSH_OPTS[*]}" \
           ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo "🔐 正在同步 .env 到遠端伺服器..."
REMOTE_ENV_FILE="$(mktemp)"
# 移除僅供本地 Windows 使用的 FFMPEG_PATH，Docker 映像已內建 ffmpeg
sed 's/\r$//' "$ENV_FILE" | grep -v '^FFMPEG_PATH=' > "$REMOTE_ENV_FILE"
rsync -avz -e "ssh ${SSH_OPTS[*]}" "$REMOTE_ENV_FILE" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/.env"
rm -f "$REMOTE_ENV_FILE"

echo "🔧 正在遠端伺服器上重新建置並啟動容器..."
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$REMOTE_HOST" << ENDSSH
cd "$REMOTE_DIR"

mkdir -p downloads
docker-compose down
docker-compose build
docker-compose up -d

echo "✅ 部署完成！以下是最新日誌："
docker-compose logs --tail=50
ENDSSH

echo "🎉 部署成功！"
echo "📊 查看即時日誌: ssh -p $REMOTE_PORT -i $SSH_KEY $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && docker-compose logs -f'"
