#!/bin/bash

# 遠端伺服器部署腳本
# 使用方法: ./deploy.sh

set -e

echo "🚀 開始部署 Telegram Bot 到遠端伺服器..."

# 設定變數 (請根據您的伺服器修改)
REMOTE_USER="ubuntu"
REMOTE_HOST="your-server-ip"
REMOTE_PORT="22"
REMOTE_DIR="/home/$REMOTE_USER/TubeRelay"
# WSL 請用 Linux 路徑（/mnt/c/ 上的金鑰無法設定 chmod 600，SSH 會拒絕）
SSH_KEY="$HOME/.ssh/id_rsa"

SSH_OPTS=(-p "$REMOTE_PORT" -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new)

echo "📦 正在同步檔案到遠端伺服器..."
rsync -avz --exclude '.git' \
           --exclude '__pycache__' \
           --exclude 'downloads/' \
           --exclude 'bot-api-data/' \
           --exclude 'ffmpeg-8.0.1*' \
           --exclude '.env' \
           -e "ssh ${SSH_OPTS[*]}" \
           ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo "🔧 正在遠端伺服器上重新建置並啟動容器..."
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$REMOTE_HOST" << 'ENDSSH'
cd ~/TubeRelay

mkdir -p downloads
docker-compose down
docker-compose build
docker-compose up -d

echo "✅ 部署完成！以下是最新日誌："
docker-compose logs --tail=50
ENDSSH

echo "🎉 部署成功！"
echo "📊 查看即時日誌: ssh -p $REMOTE_PORT -i $SSH_KEY $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && docker-compose logs -f'"
