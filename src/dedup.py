import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SENT_FILE = DATA_DIR / "sent_articles.json"
RETENTION_DAYS = 7


def load_sent() -> set[str]:
    """載入已推送的文章 URL set。"""
    if not SENT_FILE.exists():
        return set()

    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("讀取 %s 失敗: %s，重新開始", SENT_FILE, e)
        return set()

    # 清理過期紀錄（超過 RETENTION_DAYS 天）
    now = datetime.now(timezone.utc)
    valid = {}
    for url, timestamp in data.items():
        try:
            saved_at = datetime.fromisoformat(timestamp)
            if (now - saved_at).days <= RETENTION_DAYS:
                valid[url] = timestamp
        except (ValueError, TypeError):
            continue

    return set(valid.keys())


def filter_new(articles: list[dict], sent: set[str]) -> list[dict]:
    """過濾掉已推送過的新聞。"""
    return [a for a in articles if a["url"] not in sent]


def save_sent(sent: set[str]):
    """儲存已推送的文章 URL（附帶時間戳記）。"""
    # 讀取既有資料以保留時間戳記
    existing = {}
    if SENT_FILE.exists():
        try:
            with open(SENT_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    now = datetime.now(timezone.utc).isoformat()
    for url in sent:
        if url not in existing:
            existing[url] = now

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    log.info("已儲存 %d 筆推送紀錄", len(existing))
