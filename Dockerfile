# 使用 Python 3.11 作為基礎映像
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴 (FFmpeg)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt 並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 建立 downloads 目錄
RUN mkdir -p downloads

# 設定環境變數
ENV PYTHONUNBUFFERED=1

# 執行應用程式
CMD ["python", "main.py"]
