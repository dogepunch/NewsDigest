import json
import logging
import time
from pathlib import Path

from google import genai

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BLOCKED_FILE = DATA_DIR / "blocked_sources.txt"
MAX_RETRIES = 3


def _load_blocked_sources(config_blocked: list[str]) -> set[str]:
    """合併 config 和檔案中的黑名單。"""
    blocked = set(config_blocked)
    if BLOCKED_FILE.exists():
        with open(BLOCKED_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    blocked.add(line)
    return blocked


def _pre_filter(articles: list[dict], blocked: set[str]) -> list[dict]:
    """程式碼層級的快速過濾（黑名單來源）。"""
    result = []
    for a in articles:
        source = a.get("source", "")
        if any(b in source for b in blocked):
            log.info("  黑名單過濾: %s (%s)", a["title"][:30], source)
            continue
        result.append(a)
    return result


def _build_combined_prompt(
    articles: list[dict],
    categories: list[str],
    max_articles: int,
    importance_threshold: str | None,
    balanced_view: bool,
) -> str:
    """建構合併過濾+摘要的 AI prompt。"""
    articles_text = ""
    for i, a in enumerate(articles):
        articles_text += (
            f"\n[{i}] 標題: {a['title']}\n"
            f"    來源: {a['source']}\n"
            f"    分類（原始）: {a['category']}\n"
            f"    摘要片段: {a['summary'][:200]}\n"
        )

    importance_instruction = ""
    if importance_threshold:
        importance_instruction = f"\n⚠️ 本次為即時快訊模式，只選擇 importance 為 \"{importance_threshold}\" 的新聞。\n"

    balanced_instruction = ""
    if balanced_view:
        balanced_instruction = """
🔄 平衡呈現：若同一事件有不同立場的報導，請在摘要中對照呈現各方觀點差異。"""

    return f"""你是專業新聞編輯。請分析以下新聞列表，完成「過濾」與「摘要」兩項任務。

## 任務一：過濾與評估
對每篇新聞判斷：
1. **is_clickbait**（bool）：是否為農場文、釣魚標題、內容農場
2. **category**（string）：最適合的分類，從以下選擇：{', '.join(categories)}
3. **bias**（string）：立場傾向，選擇：neutral / lean_left / lean_right / strong_left / strong_right
4. **importance**（string）：重要性，選擇：high / medium / low
5. **keep**（bool）：綜合判斷是否值得推送（排除農場文、低品質、重複內容）
{importance_instruction}
## 任務二：摘要
對你判斷為 keep=true 的新聞，撰寫 2-3 句繁體中文精簡摘要，重點呈現關鍵事實。
{balanced_instruction}
## 新聞列表（共 {len(articles)} 篇）
{articles_text}

## 回傳格式
只回傳 JSON array，從中選出最多 {max_articles} 篇最值得推送的新聞，不要加任何說明文字：
[
  {{"index": 0, "is_clickbait": false, "category": "政治", "bias": "neutral", "importance": "high", "keep": true, "summary": "摘要文字..."}},
  ...
]

注意：
- 只回傳 keep=true 的新聞
- 最多回傳 {max_articles} 篇，優先選擇 importance 較高的
- summary 必須是繁體中文"""


def ai_filter_and_summarize(
    articles: list[dict],
    cfg: dict,
    max_articles: int = 10,
    importance_threshold: str | None = None,
) -> list[dict]:
    """
    一次 AI 呼叫完成：黑名單過濾 → Gemini 批次分析（過濾+分類+立場+重要性+摘要）。
    回傳已過濾且含摘要的新聞 list。
    """
    if not articles:
        return []

    # 程式碼層級快速過濾
    blocked = _load_blocked_sources(cfg["quality_filter"].get("blocked_sources", []))
    articles = _pre_filter(articles, blocked)

    if not articles or not cfg["quality_filter"].get("ai_filter_enabled", True):
        return articles[:max_articles]

    # 建構 prompt
    client = genai.Client(api_key=cfg["ai"]["api_key"])
    categories = cfg.get("categories", [])
    balanced_view = cfg["quality_filter"].get("balanced_view", False)
    prompt = _build_combined_prompt(
        articles, categories, max_articles, importance_threshold, balanced_view
    )

    # 呼叫 Gemini（含 retry）
    results = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=cfg["ai"]["model"],
                contents=prompt,
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0]
            results = json.loads(raw)
            break
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait = 60
                log.warning("API rate limit，等待 %ds 後重試 (%d/%d)", wait, attempt, MAX_RETRIES)
                time.sleep(wait)
            else:
                log.error("AI 回應解析失敗: %s", e)
                break

    if not results:
        log.warning("AI 呼叫失敗，回傳未過濾的前 %d 篇", max_articles)
        return articles[:max_articles]

    # 組裝結果
    filtered = []
    for result in results:
        idx = result.get("index")
        if idx is None or idx >= len(articles):
            continue

        article = articles[idx]
        article["is_clickbait"] = result.get("is_clickbait", False)
        article["ai_category"] = result.get("category", article["category"])
        article["bias"] = result.get("bias", "neutral")
        article["importance"] = result.get("importance", "medium")
        article["ai_summary"] = result.get("summary", "")

        if not result.get("keep", True):
            continue

        filtered.append(article)

    return filtered[:max_articles]
