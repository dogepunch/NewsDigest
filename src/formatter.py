import logging
from itertools import groupby

log = logging.getLogger(__name__)

# Telegram 單則訊息上限
MAX_MESSAGE_LENGTH = 4096

MODE_TITLES = {
    "morning": "📰 早安新聞",
    "breaking": "🔴 即時快訊",
    "evening": "🌙 晚間新聞",
}

CATEGORY_EMOJI = {
    "政治": "🏛",
    "國際": "🌍",
    "財經": "💰",
    "科技": "🔬",
    "娛樂": "🎬",
    "體育": "⚽",
    "社會": "👥",
    "生活": "🏠",
}


def _format_article(article: dict) -> str:
    """格式化單篇新聞。"""
    title = article["title"]
    url = article["url"]
    summary = article.get("ai_summary", "")
    bias = article.get("bias", "neutral")

    bias_tag = ""
    if bias and bias != "neutral":
        bias_labels = {
            "lean_left": "偏左", "lean_right": "偏右",
            "strong_left": "左", "strong_right": "右",
        }
        bias_tag = f" [{bias_labels.get(bias, '')}]"

    lines = [f"• [{title}]({url}){bias_tag}"]
    if summary:
        lines.append(f"  {summary}")

    # balanced_view 標記
    if article.get("is_balanced_group"):
        sources = article.get("balanced_sources", [])
        lines.append(f"  📊 綜合報導：{'、'.join(sources)}")

    return "\n".join(lines)


def format_digest(articles: list[dict], mode: str) -> list[str]:
    """
    將新聞列表格式化為 Telegram 訊息。
    回傳 list[str]，因為可能需要分割成多則訊息。
    """
    if not articles:
        return []

    title = MODE_TITLES.get(mode, "📰 新聞摘要")
    header = f"*{title}*\n"

    # 按分類分組
    sorted_articles = sorted(articles, key=lambda a: a.get("ai_category", a["category"]))
    sections = []
    for category, group in groupby(sorted_articles, key=lambda a: a.get("ai_category", a["category"])):
        emoji = CATEGORY_EMOJI.get(category, "📌")
        section = f"\n*{emoji} {category}*\n"
        for article in group:
            # 跳過 balanced_group 中非首篇的新聞
            if "ai_summary" not in article and not article.get("is_balanced_group"):
                continue
            section += _format_article(article) + "\n"
        sections.append(section)

    # 組裝並分割訊息
    messages = []
    current = header
    for section in sections:
        if len(current) + len(section) > MAX_MESSAGE_LENGTH:
            messages.append(current.strip())
            current = f"*{title}（續）*\n"
        current += section

    if current.strip():
        messages.append(current.strip())

    return messages
