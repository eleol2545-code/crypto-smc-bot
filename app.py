from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import json
import os
import threading

from bot import SMCAnalyzer, Trader
from telegram.bot import TelegramBot

with open('config/config.json', 'r') as f:
    config = json.load(f)

os.makedirs('data', exist_ok=True)
os.makedirs('data/charts', exist_ok=True)

analyzer = SMCAnalyzer()
trader = Trader(config)

telegram_token = config.get('telegram', {}).get('bot_token', '')
telegram_chat_id = config.get('telegram', {}).get('chat_id', '')

if telegram_token and telegram_chat_id:
    telegram_bot = TelegramBot(
        token=telegram_token,
        chat_id=telegram_chat_id,
        analyzer=analyzer,
        trader=trader,
        config=config
    )
    telegram_thread = threading.Thread(target=telegram_bot.run, daemon=True)
    telegram_thread.start()

app = FastAPI(title="SMC Crypto Bot")

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SMC Crypto Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background: #0a0a0a; color: #e0e0e0; font-family: -apple-system, sans-serif; padding: 20px; }
        .card { background: #1a1a2e; border-radius: 20px; padding: 20px; margin-bottom: 20px; }
        h1 { color: #00ff88; }
        .status { color: #00ff88; }
        pre { background: #0f0f1a; padding: 15px; border-radius: 10px; overflow-x: auto; }
        button { background: #00ff88; color: #000; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🤖 SMC Crypto Bot</h1>
        <p>Статус: <span class="status">🟢 Активен</span></p>
        <p>Стиль: <strong>DAY</strong></p>
        <p>Режим: <strong>Только сигналы</strong></p>
    </div>
    <div class="card">
        <h2>📱 Telegram Бот</h2>
        <p>Добавьте бота и используйте команды:</p>
        <pre>/signals - активные сигналы
/status - статус бота
/positions - открытые позиции
/chart BTC - график с уровнями
/dashboard - мобильный дашборд</pre>
    </div>
</body>
</html>
"""

@app.get("/")
async def root():
    return HTMLResponse(HTML)

@app.get("/health")
async def health():
    return {"status": "ok", "trading_enabled": config['trading']['enabled']}
