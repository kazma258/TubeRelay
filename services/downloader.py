import os
import uuid
import asyncio
import subprocess
import yt_dlp
from config import (
    DOWNLOAD_PATH,
    OFFICIAL_MAX_FILE_SIZE,
    LOCAL_MAX_FILE_SIZE,
    FFMPEG_LOCATION,
)

def get_video_info(url):
    """
    不下載影片,僅獲取影片資訊。
    回傳一個包含標題、時長、縮圖、網頁連結的字典。
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    
    # yt-dlp 的 python 嵌入通常使用 parameters 中的 'ffmpeg_location'
    ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', '未知標題'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', None),
                'webpage_url': info.get('webpage_url', url),
                'id': info.get('id', '')
            }
        except Exception as e:
            print(f"提取資訊時發生錯誤: {e}")
            raise e

def get_available_formats(url, format_type):
    """
    獲取可用的格式列表,並篩選出符合 LOCAL_MAX_FILE_SIZE 限制的選項。
    format_type: 'mp3' 或 'mp4'
    回傳格式列表,每個格式包含: format_id, quality_label, filesize_approx, description
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    
    ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            duration = info.get('duration', 0)  # 影片時長（秒）
            
            available_formats = []
            
            if format_type == 'mp3':
                # 音訊格式:篩選純音訊串流
                audio_formats = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
                
                # 按音質排序 (abr = audio bitrate)
                audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                
                seen_quality = set()
                for fmt in audio_formats:
                    abr = fmt.get('abr', 0) or 0
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                    
                    # 如果沒有檔案大小資訊,使用位元率和時長估算
                    if filesize == 0 and abr > 0 and duration > 0:
                        # 公式: (位元率 kbps * 時長秒) / 8 = KB, 再轉 bytes
                        filesize = int((abr * duration * 1024) / 8)
                    
                    # 估算 MP3 轉檔後的大小 (通常會略小於原始音訊)
                    estimated_size = filesize * 0.8 if filesize else 0
                    
                    quality_label = f"{int(abr)}kbps" if abr else "未知音質"
                    
                    # 避免重複的音質
                    if quality_label in seen_quality:
                        continue
                    seen_quality.add(quality_label)
                    
                    if estimated_size > 0 and estimated_size > LOCAL_MAX_FILE_SIZE:
                        continue
                    
                    available_formats.append({
                        'format_id': fmt['format_id'],
                        'quality_label': quality_label,
                        'filesize_approx': estimated_size,
                        'description': f"🎵 {quality_label} ({_format_size(estimated_size)}{_size_tier_suffix(estimated_size)})"
                    })
                
                # 如果沒有找到合適的,提供一個預設選項
                if not available_formats:
                    available_formats.append({
                        'format_id': 'bestaudio',
                        'quality_label': '最佳音質',
                        'filesize_approx': 0,
                        'description': '🎵 最佳音質 (自動選擇)'
                    })
                    
            elif format_type == 'mp4':
                # 影片格式:篩選有影像的格式
                video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('ext') == 'mp4']
                
                # 按解析度排序
                video_formats.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
                
                seen_resolution = set()
                for fmt in video_formats:
                    height = fmt.get('height', 0)
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                    
                    if height == 0:
                        continue
                    
                    # 如果沒有檔案大小,使用位元率估算
                    if filesize == 0 and duration > 0:
                        vbr = fmt.get('vbr', 0) or fmt.get('tbr', 0) or 0
                        if vbr > 0:
                            # 公式: (總位元率 kbps * 時長秒) / 8 = KB, 再轉 bytes
                            filesize = int((vbr * duration * 1024) / 8)
                    
                    resolution_label = f"{height}p"
                    
                    # 避免重複的解析度
                    if resolution_label in seen_resolution:
                        continue
                    seen_resolution.add(resolution_label)
                    
                    if filesize > 0 and filesize > LOCAL_MAX_FILE_SIZE:
                        continue
                    
                    available_formats.append({
                        'format_id': fmt['format_id'],
                        'quality_label': resolution_label,
                        'filesize_approx': filesize,
                        'description': f"🎬 {resolution_label} ({_format_size(filesize)}{_size_tier_suffix(filesize)})"
                    })
                
                # 如果沒有找到合適的,嘗試提供較低畫質
                if not available_formats:
                    # 嘗試找最小的影片格式
                    for fmt in reversed(video_formats):
                        filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                        height = fmt.get('height', 0)
                        
                        # 再次嘗試估算
                        if filesize == 0 and duration > 0:
                            vbr = fmt.get('vbr', 0) or fmt.get('tbr', 0) or 0
                            if vbr > 0:
                                filesize = int((vbr * duration * 1024) / 8)
                        
                        if filesize > 0 and filesize <= LOCAL_MAX_FILE_SIZE and height > 0:
                            available_formats.append({
                                'format_id': fmt['format_id'],
                                'quality_label': f"{height}p",
                                'filesize_approx': filesize,
                                'description': f"🎬 {height}p ({_format_size(filesize)}{_size_tier_suffix(filesize)})"
                            })
                            break
            
            return available_formats[:5]  # 最多顯示 5 個選項
            
        except Exception as e:
            print(f"獲取格式列表時發生錯誤: {e}")
            raise e

def _format_size(size_bytes):
    """格式化檔案大小顯示"""
    if size_bytes == 0:
        return "大小未知"
    mb = size_bytes / (1024 * 1024)
    if mb < 1:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{mb:.1f}MB"


def _size_tier_suffix(size_bytes):
    """標示超過官方 API 上限的格式（需走 Local Bot API）。"""
    if size_bytes <= 0 or size_bytes <= OFFICIAL_MAX_FILE_SIZE:
        return ""
    return " [大檔]"


def _optimize_mp4_for_streaming(filepath):
    """將 moov atom 移到檔頭（faststart），讓 Telegram 可邊緩衝邊播放。"""
    if not filepath.lower().endswith(".mp4"):
        return filepath

    tmp_path = f"{filepath}.streaming.mp4"
    try:
        subprocess.run(
            [
                FFMPEG_LOCATION,
                "-y",
                "-i",
                filepath,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                tmp_path,
            ],
            check=True,
            capture_output=True,
        )
        os.replace(tmp_path, filepath)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"faststart 優化失敗，使用原始檔案: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return filepath


def download_media(url, format_id, format_type):
    """
    從 URL 下載媒體。
    url: 影片網址
    format_id: yt-dlp 格式 ID (例如 '140', '22', 'bestaudio')
    format_type: 'mp3' 或 'mp4'
    回傳下載檔案的絕對路徑。
    """
    file_id = str(uuid.uuid4())
    # 輸出範本: downloads/<uuid>.<ext>
    # 注意: yt-dlp 會自動補上副檔名,所以我們只需要提供主檔名
    out_tmpl = os.path.join(DOWNLOAD_PATH, f"{file_id}.%(ext)s")
    
    ydl_opts = {
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'max_filesize': LOCAL_MAX_FILE_SIZE,
        'socket_timeout': 60,
        'retries': 10,  # 重試次數
        'fragment_retries': 10,  # 分段重試次數
        'file_access_retries': 3,  # 檔案存取重試
    }

    ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

    if format_type == 'mp3':
        # 如果 format_id 是 'bestaudio',使用預設選擇
        if format_id == 'bestaudio':
            ydl_opts['format'] = 'bestaudio/best'
        else:
            ydl_opts['format'] = format_id
            
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    elif format_type == 'mp4':
        # 對於 MP4,需要合併影像和音訊
        # format_id 可能只有影像,需要加上音訊
        ydl_opts['format'] = f"{format_id}+bestaudio[ext=m4a]/best[ext=mp4]"
    else:
        raise ValueError("無效的 format_type。必須是 'mp3' 或 'mp4'。")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            
            # 嘗試取得下載檔案的路徑
            filepath = None
            
            # 方法 1: 從 requested_downloads 取得 (最準確,包含後處理後的路徑)
            if 'requested_downloads' in info:
                for d in info['requested_downloads']:
                    if 'filepath' in d:
                        filepath = d['filepath']
                        break
            
            # 方法 2: 使用 prepare_filename (備案)
            if not filepath:
                filepath = ydl.prepare_filename(info)
                # MP3 後處理會改變副檔名,需手動修正
                if format_type == 'mp3':
                    base, _ = os.path.splitext(filepath)
                    filepath = f"{base}.mp3"

            if not filepath:
                raise ValueError("無法取得下載檔案路徑")
            
            # 檢查檔案是否確實存在
            if not os.path.exists(filepath):
                # 再次檢查是否是因為檔案過大 (如果 yt-dlp 沒拋出異常但沒下載)
                raise ValueError("下載失敗：找不到檔案 (可能是檔案過大被略過或下載不完整)")

            if format_type == "mp4":
                filepath = _optimize_mp4_for_streaming(filepath)

            return filepath

        except yt_dlp.utils.DownloadError as de:
            # 檢查是否因為檔案過大而失敗
            if "File is larger than max-filesize" in str(de):
                local_mb = LOCAL_MAX_FILE_SIZE // 1024 // 1024
                raise ValueError(f"檔案超過 {local_mb}MB 限制,取消下載。")
            print(f"yt-dlp 下載錯誤: {de}")
            raise de
        except Exception as e:
            print(f"下載時發生未預期錯誤: {e}")
            raise e
