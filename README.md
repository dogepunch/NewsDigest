# NewsDigest - 個人新聞推送系統

每日自動抓取新聞，經 AI 過濾與摘要後推送到指定管道。

## 功能

- 多來源 RSS 新聞抓取
- AI 驅動的品質控制（農場文偵測、立場標記）
- 自動分類與摘要
- 定時推送（Telegram / LINE / Email / Discord）

## 快速開始

1. 複製 `config.yaml` 並填入設定
2. 安裝依賴：`pip install -r requirements.txt`
3. 執行：`python main.py`

## 專案結構

```
NewsDigest/
├── config.yaml          # 設定檔
├── main.py              # 主程式入口
├── requirements.txt     # Python 依賴
├── src/
│   ├── fetcher.py       # 新聞抓取模組
│   ├── filter.py        # 品質過濾模組（AI）
│   ├── formatter.py     # 訊息格式化
│   └── notifier.py      # 推送模組
└── data/
    └── blocked_sources.txt  # 媒體黑名單
```
