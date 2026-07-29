# VALORANT Lineup Discord Bot

## 1. 建立 Discord Bot

1. 前往 Discord Developer Portal。
2. 建立 Application，進入 Bot 頁面後建立 Bot。
3. 複製 Bot Token，請勿公開或上傳到 GitHub。
4. 此程式不讀聊天室內容，因此不需要開啟 Message Content Intent。

## 2. 邀請機器人

在 OAuth2 → URL Generator 勾選：

- `bot`

Bot Permissions 建議勾選：

- View Channels
- Send Messages
- Embed Links
- Read Message History

產生邀請網址後，把 Bot 加入伺服器。

## 3. 取得頻道 ID

Discord 使用者設定 → 進階 → 開啟「開發者模式」。

對上傳頻道及查詢頻道按右鍵，選擇「複製頻道 ID」。

## 4. 設定環境變數

最安全的方式是由主機平台設定環境變數。

Windows PowerShell 暫時設定範例：

```powershell
$env:DISCORD_BOT_TOKEN="你的Token"
$env:UPLOAD_CHANNEL_ID="上傳頻道ID"
$env:WATCH_CHANNEL_ID="查詢頻道ID"
python bot.py
```

若希望使用 `.env`，請自行在 `bot.py` 最上方加入：

```python
from dotenv import load_dotenv
load_dotenv()
```

然後把 `.env.example` 複製為 `.env`。

## 5. 安裝與啟動

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

也可直接雙擊 Windows 的 `start_bot.bat`。

## 6. 常駐面板機制

第一次啟動時，Bot 會在指定的兩個頻道各建立一則面板訊息，並把訊息 ID 存入 SQLite。

之後重新啟動，Bot 會更新原本的面板，而不是一直重複發送新訊息。

## 7. 重要限制

Discord 一個 String Select 最多 25 個選項，但本專案特務清單有 26 位，因此採用：

1. 選擇特務定位
2. 選擇該定位下的特務

Modal 則負責接收影片網址和標題。這樣能完整保留 26 位特務，且全程不需輸入任何 Discord 指令。
