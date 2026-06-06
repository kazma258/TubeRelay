import logging
import os
import time

import config

logger = logging.getLogger(__name__)

_MEDIA_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".webm", ".mkv", ".opus", ".ogg"}


def _is_managed_media(path: str) -> bool:
    name = os.path.basename(path)
    if name.startswith("thumb_"):
        return False
    return os.path.splitext(name)[1].lower() in _MEDIA_EXTENSIONS


def _iter_media_files():
    if not os.path.isdir(config.DOWNLOAD_PATH):
        return
    for name in os.listdir(config.DOWNLOAD_PATH):
        path = os.path.join(config.DOWNLOAD_PATH, name)
        if os.path.isfile(path) and _is_managed_media(path):
            yield path


def get_storage_stats() -> dict:
    """計算 downloads 目錄內受管理媒體檔的用量。"""
    used_bytes = 0
    file_count = 0
    for path in _iter_media_files():
        used_bytes += os.path.getsize(path)
        file_count += 1
    limit_bytes = config.STORAGE_LIMIT_BYTES
    free_bytes = max(0, limit_bytes - used_bytes)
    return {
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "limit_bytes": limit_bytes,
        "file_count": file_count,
        "used_gb": used_bytes / 1024 / 1024 / 1024,
        "free_gb": free_bytes / 1024 / 1024 / 1024,
        "limit_gb": limit_bytes / 1024 / 1024 / 1024,
    }


def cleanup_expired_files() -> tuple[int, int]:
    """刪除超過保留期限的媒體檔。回傳 (刪除數量, 釋放位元組)。"""
    cutoff = time.time() - config.FILE_RETENTION_SECONDS
    removed = 0
    freed = 0
    for path in list(_iter_media_files()):
        try:
            if os.path.getmtime(path) < cutoff:
                size = os.path.getsize(path)
                os.remove(path)
                removed += 1
                freed += size
                logger.info(
                    "storage_expired_removed path=%s size_mb=%.2f",
                    os.path.basename(path),
                    size / 1024 / 1024,
                )
        except OSError as exc:
            logger.warning("storage_expired_remove_failed path=%s error=%s", path, exc)
    if removed:
        logger.info(
            "storage_cleanup_complete removed=%d freed_mb=%.2f",
            removed,
            freed / 1024 / 1024,
        )
    return removed, freed


def check_storage_available(estimated_bytes: int = 0) -> tuple[bool, str]:
    """
    檢查是否還能下載新檔案。
    estimated_bytes 為 0 時僅檢查是否已滿。
    """
    cleanup_expired_files()
    stats = get_storage_stats()
    limit_gb = stats["limit_gb"]
    used_gb = stats["used_gb"]

    if stats["used_bytes"] >= stats["limit_bytes"]:
        return False, (
            f"❌ 儲存空間已滿（上限 {limit_gb:.0f}GB，已使用 {used_gb:.2f}GB）。\n"
            f"檔案保留 {config.FILE_RETENTION_DAYS} 天後會自動清理，請稍後再試。"
        )

    if estimated_bytes > 0 and estimated_bytes > stats["free_bytes"]:
        need_gb = estimated_bytes / 1024 / 1024 / 1024
        free_gb = stats["free_gb"]
        return False, (
            f"❌ 儲存空間不足（上限 {limit_gb:.0f}GB，已使用 {used_gb:.2f}GB，"
            f"剩餘 {free_gb:.2f}GB，需要約 {need_gb:.2f}GB）。\n"
            f"請選擇較小檔案或等待過期檔案自動清理。"
        )

    return True, ""


def format_storage_status() -> str:
    stats = get_storage_stats()
    return (
        f"{stats['used_gb']:.2f}GB / {stats['limit_gb']:.0f}GB "
        f"（{stats['file_count']} 檔，保留 {config.FILE_RETENTION_DAYS} 天）"
    )
