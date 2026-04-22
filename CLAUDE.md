# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

NewsDigest 是個人新聞推送系統，自動抓取台灣新聞 RSS，經 Google Gemini AI 過濾（農場文偵測、立場標記、重要性判斷）與摘要後，推送至 Telegram 等管道。

## 開發語言與框架

- Python 專案
- AI 後端：Google Gemini (`gemini-2.5-flash`)
- 設定檔：`config.yaml`（已不含機敏資訊，可提交）
- 本機環境變數：`.env`（含 API key、bot token，已 gitignored）

## 建置與執行

```bash
pip install -r requirements.txt
cp .env.example .env       # 首次設定：複製範本後填入金鑰
python main.py
```

執行模式：
```bash
python main.py --mode morning    # 早報（預設）
python main.py --mode breaking   # 即時快訊（僅推送 importance=high）
python main.py --mode evening    # 晚報（需在 config.yaml 啟用）
```

## 架構

五階段 pipeline，入口點 `main.py`，各模組在 `src/` 下：

1. **fetcher.py** — RSS 新聞抓取，從 `config.yaml` 的 `sources.rss_feeds` 讀取來源
2. **dedup.py** — JSON 檔去重（`data/sent_articles.json`），URL 紀錄保留 7 天自動清理
3. **filter.py** — 黑名單預過濾 + 單次 Gemini API 呼叫完成分類、農場文偵測、立場標記、重要性判斷、摘要生成
4. **formatter.py** — 訊息格式化，按 `ai_category` 分組，自動分割超過 Telegram 4096 字元上限的訊息
5. **notifier.py** — 推送至 Telegram Bot API

⚠️ **summarizer.py 為遺留模組**，採逐篇呼叫 API 的舊架構，已被 `filter.py` 的批次合併方案取代。`main.py` 不引用此模組，修改 AI 相關邏輯應改 `filter.py`。

### 核心資料結構

各模組間傳遞的 article dict 隨 pipeline 逐步擴充：

```python
# fetcher 產出
{"title", "url", "source", "category", "published", "summary"}

# filter 擴充
{"is_clickbait", "ai_category", "bias", "importance", "ai_summary"}
```

## 部署：GitHub Actions

排程定義在 `.github/workflows/news-digest.yml`，透過 cron 觸發三種模式。

需設定的 GitHub Secrets：
- `GEMINI_API_KEY` — Google AI Studio API key
- `TELEGRAM_BOT_TOKEN` — Telegram BotFather token
- `TELEGRAM_CHAT_ID` — 目標聊天室 ID

去重快取透過 `actions/cache` 在 runs 間持久化 `data/sent_articles.json`。

## 排程設計

- 每日早報 08:00（最多 10 則）
- 每 30 分鐘檢查重大新聞（AI 判定 importance = high）
- 可選晚報 20:00（預設關閉）

## 關鍵設計決策

- AI 五項功能（摘要、分類、農場文偵測、立場偵測、重要性判斷）合併為單次 Gemini API 呼叫，以節省 API 配額
- `balanced_view: true`：同一事件會抓取不同立場報導對照呈現
- 媒體黑名單同時存在 `config.yaml` 和 `data/blocked_sources.txt`，兩處需保持同步
- Gemini API 使用 `google-genai` SDK（非舊版 `google-generativeai`），呼叫方式為 `client.models.generate_content()`
- AI 回傳 JSON 時需手動剝離 markdown code fence（```json ... ```），無結構化輸出

## 注意事項

- 所有使用者面向文字使用繁體中文
- 機敏資訊（API key、bot token）僅透過環境變數提供，不可寫入 `config.yaml` 或任何提交檔案
- 本機開發從 `.env` 載入（須先 `cp .env.example .env` 並填值）；GitHub Actions 從 repo Secrets 注入
