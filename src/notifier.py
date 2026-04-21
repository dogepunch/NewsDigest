import logging
import time

import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def send_telegram(messages: list[str], telegram_cfg: dict):
    """透過 Telegram Bot API 發送訊息（支援多則分割訊息）。"""
    token = telegram_cfg["bot_token"]
    chat_id = telegram_cfg["chat_id"]
    url = TELEGRAM_API.format(token=token)

    for i, text in enumerate(messages):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    log.info("訊息 %d/%d 發送成功", i + 1, len(messages))
                    break
                elif resp.status_code == 429:
                    # Rate limit，等待後重試
                    retry_after = resp.json().get("parameters", {}).get("retry_after", RETRY_DELAY)
                    log.warning("Telegram rate limit，等待 %ds", retry_after)
                    time.sleep(retry_after)
                else:
                    log.error("Telegram 發送失敗 (%d): %s", resp.status_code, resp.text)
                    break
            except requests.RequestException as e:
                log.error("Telegram 發送錯誤 (attempt %d/%d): %s", attempt, MAX_RETRIES, e)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        # 多則訊息之間間隔，避免觸發 rate limit
        if i < len(messages) - 1:
            time.sleep(1)
