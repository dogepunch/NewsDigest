import argparse
import logging
import os
import sys

import yaml
from dotenv import load_dotenv

from src.fetcher import fetch_all
from src.dedup import load_sent, filter_new, save_sent
from src.filter import ai_filter_and_summarize
from src.formatter import format_digest
from src.notifier import send_telegram

# 本機開發：從 .env 載入；GitHub Actions：環境變數已由 secrets 注入，load_dotenv 無作用
load_dotenv()

REQUIRED_ENV_VARS = ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 機敏欄位只能來自環境變數，config.yaml 不再保存
    cfg["ai"]["api_key"] = os.environ["GEMINI_API_KEY"]
    cfg["channel"]["telegram"]["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    cfg["channel"]["telegram"]["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]
    return cfg


def validate_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        log.error("缺少環境變數: %s", ", ".join(missing))
        log.error("請複製 .env.example 為 .env 並填入金鑰")
        sys.exit(1)


def run(mode: str, cfg: dict):
    schedule_cfg = cfg["schedule"]

    # 晚報預設關閉
    if mode == "evening" and not schedule_cfg.get("evening_digest", {}).get("enabled", False):
        log.info("晚報未啟用，跳過")
        return

    max_articles = {
        "morning": schedule_cfg["morning_digest"]["max_articles"],
        "breaking": 5,
        "evening": schedule_cfg.get("evening_digest", {}).get("max_articles", 10),
    }.get(mode, 10)

    # 1. 抓取新聞
    log.info("開始抓取新聞...")
    articles = fetch_all(cfg["sources"]["rss_feeds"])
    log.info("抓取到 %d 篇新聞", len(articles))

    if not articles:
        log.info("沒有新聞，結束")
        return

    # 2. 去重
    sent = load_sent()
    articles = filter_new(articles, sent)
    log.info("去重後剩餘 %d 篇", len(articles))

    if not articles:
        log.info("沒有新的新聞，結束")
        return

    # 3. AI 過濾 + 摘要（單次 API 呼叫）
    log.info("AI 過濾與摘要中...（1 次 API 呼叫）")
    importance_threshold = None
    if mode == "breaking":
        importance_threshold = schedule_cfg["breaking_news"]["ai_importance_threshold"]

    articles = ai_filter_and_summarize(
        articles, cfg,
        max_articles=max_articles,
        importance_threshold=importance_threshold,
    )
    log.info("AI 處理完成，取得 %d 篇新聞", len(articles))

    if not articles:
        log.info("沒有符合條件的新聞，結束")
        return

    # 6. 格式化
    messages = format_digest(articles, mode)

    if not messages:
        log.info("格式化後無訊息，結束")
        return

    # 7. 推送
    log.info("推送至 Telegram...（共 %d 則訊息）", len(messages))
    send_telegram(messages, cfg["channel"]["telegram"])

    # 8. 記錄已推送
    for a in articles:
        sent.add(a["url"])
    save_sent(sent)

    log.info("完成！推送了 %d 篇新聞", len(articles))


def main():
    parser = argparse.ArgumentParser(description="NewsDigest 新聞推送系統")
    parser.add_argument(
        "--mode",
        choices=["morning", "breaking", "evening"],
        default="morning",
        help="執行模式：morning（早報）、breaking（即時）、evening（晚報）",
    )
    parser.add_argument("--config", default="config.yaml", help="設定檔路徑")
    args = parser.parse_args()

    # 先驗證環境變數，避免 load_config 拋出 KeyError
    validate_env()

    cfg = load_config(args.config)
    run(args.mode, cfg)


if __name__ == "__main__":
    main()
