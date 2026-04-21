import logging
import time
from itertools import groupby

from google import genai

log = logging.getLogger(__name__)

# Gemini 2.5 Flash 免費 tier: 20 RPM，保守設定每次請求間隔 4 秒
REQUEST_INTERVAL = 4
MAX_RETRIES = 3


def _call_gemini(client: genai.Client, model: str, prompt: str) -> str | None:
    """呼叫 Gemini API，含 rate limit retry。"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text.strip()
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # 從錯誤訊息中嘗試取得建議等待時間，否則用預設值
                wait = 60
                log.warning("API rate limit，等待 %ds 後重試 (%d/%d)", wait, attempt, MAX_RETRIES)
                time.sleep(wait)
            else:
                log.warning("Gemini API 錯誤: %s", e)
                return None
    log.error("重試 %d 次仍失敗，跳過", MAX_RETRIES)
    return None


def _summarize_single(article: dict, client: genai.Client, model: str) -> str:
    """對單篇新聞產生摘要。"""
    prompt = f"""請用繁體中文為以下新聞撰寫 2-3 句精簡摘要，重點呈現關鍵事實。

標題: {article['title']}
來源: {article['source']}
內容片段: {article['summary'][:500]}

只回傳摘要文字，不要加標題或其他標記。"""

    result = _call_gemini(client, model, prompt)
    if result:
        return result
    return article["summary"][:200] if article["summary"] else ""


def _summarize_balanced_group(group: list[dict], client: genai.Client, model: str) -> str:
    """對同一事件的多篇不同立場報導產生對照摘要。"""
    articles_text = ""
    for a in group:
        bias_label = {"neutral": "中立", "lean_left": "偏左", "lean_right": "偏右",
                      "strong_left": "左", "strong_right": "右"}.get(a.get("bias", ""), "")
        articles_text += f"\n- [{a['source']}]（立場：{bias_label}）{a['title']}\n  {a['summary'][:200]}\n"

    prompt = f"""以下是同一事件的多家媒體報導，請用繁體中文撰寫 3-4 句對照摘要，呈現不同立場的觀點差異。

{articles_text}

只回傳摘要文字。"""

    return _call_gemini(client, model, prompt) or ""


def _find_similar_groups(articles: list[dict]) -> list[list[dict]]:
    """
    將標題相似的新聞歸組（簡易版：同分類內，標題有 3 個以上共同字詞）。
    回傳歸組結果，每組 >= 2 篇。
    """
    groups = []
    used = set()

    sorted_articles = sorted(articles, key=lambda a: a.get("ai_category", a["category"]))
    for _, cat_group in groupby(sorted_articles, key=lambda a: a.get("ai_category", a["category"])):
        cat_list = list(cat_group)
        for i, a in enumerate(cat_list):
            if id(a) in used:
                continue
            group = [a]
            a_words = set(a["title"])
            for j in range(i + 1, len(cat_list)):
                b = cat_list[j]
                if id(b) in used:
                    continue
                b_words = set(b["title"])
                if len(a_words & b_words) >= 3:
                    group.append(b)
                    used.add(id(b))
            if len(group) >= 2:
                used.add(id(a))
                groups.append(group)

    return groups


def ai_summarize(articles: list[dict], cfg: dict) -> list[dict]:
    """為每篇新聞產生 AI 摘要。balanced_view 時做立場對照。"""
    if not articles:
        return []

    client = genai.Client(api_key=cfg["ai"]["api_key"])
    model = cfg["ai"]["model"]
    balanced = cfg["quality_filter"].get("balanced_view", False)

    # balanced_view：找出同事件的不同立場報導
    balanced_articles = set()
    if balanced:
        groups = _find_similar_groups(articles)
        for group in groups:
            balanced_summary = _summarize_balanced_group(group, client, model)
            if balanced_summary:
                group[0]["ai_summary"] = balanced_summary
                group[0]["is_balanced_group"] = True
                group[0]["balanced_sources"] = [a["source"] for a in group]
                for a in group:
                    balanced_articles.add(id(a))
            time.sleep(REQUEST_INTERVAL)

    # 逐篇摘要（跳過已做對照摘要的）
    for i, article in enumerate(articles):
        if id(article) in balanced_articles:
            continue
        article["ai_summary"] = _summarize_single(article, client, model)
        # 請求間隔，避免觸發 rate limit
        if i < len(articles) - 1:
            time.sleep(REQUEST_INTERVAL)

    return articles
