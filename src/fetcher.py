import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

log = logging.getLogger(__name__)

# feedparser 預設沒有 timeout，透過全域設定避免卡住
feedparser.USER_AGENT = "NewsDigest/1.0"


def _parse_entry(entry, source_name: str, category: str) -> dict | None:
    """將單筆 RSS entry 轉為標準化新聞物件。"""
    url = entry.get("link")
    title = entry.get("title")
    if not url or not title:
        return None

    published = None
    if entry.get("published_parsed"):
        try:
            published = datetime.fromtimestamp(
                mktime(entry.published_parsed), tz=timezone.utc
            ).isoformat()
        except (ValueError, OverflowError):
            pass

    return {
        "title": title.strip(),
        "url": url.strip(),
        "source": source_name,
        "category": category,
        "published": published,
        "summary": entry.get("summary", "").strip(),
    }


def fetch_feed(feed_cfg: dict) -> list[dict]:
    """抓取單一 RSS feed，回傳新聞物件 list。"""
    name = feed_cfg["name"]
    url = feed_cfg["url"]
    category = feed_cfg.get("category", "其他")

    try:
        parsed = feedparser.parse(url, request_headers={"timeout": "10"})
    except Exception as e:
        log.warning("抓取 %s 失敗: %s", name, e)
        return []

    if parsed.bozo and not parsed.entries:
        log.warning("解析 %s 異常: %s", name, parsed.bozo_exception)
        return []

    articles = []
    for entry in parsed.entries:
        article = _parse_entry(entry, name, category)
        if article:
            articles.append(article)

    return articles


def fetch_all(feeds_cfg: list[dict]) -> list[dict]:
    """抓取所有 RSS feeds，回傳合併的新聞 list（按發布時間降序）。"""
    all_articles = []
    for feed in feeds_cfg:
        articles = fetch_feed(feed)
        log.info("  %s: %d 篇", feed["name"], len(articles))
        all_articles.extend(articles)

    # 按發布時間降序排列，無時間的放最後
    all_articles.sort(key=lambda a: a["published"] or "", reverse=True)
    return all_articles
