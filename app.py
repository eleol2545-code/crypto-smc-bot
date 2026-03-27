from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
import os
import asyncio
import threading

app = FastAPI()

# ==================== TELEGRAM БОТ ====================

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"  # ВСТАВЬТЕ СЮДА

# Простой Telegram бот
class SimpleTelegramBot:
    def __init__(self, token):
        self.token = token
        self.running = False
    
    async def send_message(self, chat_id, text):
        import aiohttp
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    
    async def handle_update(self, update):
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")
            
            if text == "/start":
                await self.send_message(chat_id, "🤖 *SMC Crypto Bot*\n\nБот работает! Команды:\n/signals - сигналы\n/help - помощь")
            elif text == "/help":
                await self.send_message(chat_id, "📋 *Команды:*\n/start - запуск\n/signals - сигналы\n/status - статус")
            elif text == "/status":
                await self.send_message(chat_id, "✅ Бот активен\nВерсия: 1.0")
            else:
                await self.send_message(chat_id, f"⚠️ Неизвестная команда: {text}\nИспользуйте /help")
    
    async def run(self):
        import aiohttp
        self.running = True
        offset = 0
        
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params={"offset": offset, "timeout": 30}) as resp:
                        data = await resp.json()
                        
                        if data.get("ok"):
                            for update in data.get("result", []):
                                await self.handle_update(update)
                                offset = update["update_id"] + 1
            except Exception as e:
                print(f"Telegram error: {e}")
            
            await asyncio.sleep(1)
    
    def start(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.run())

# Запускаем Telegram бота, если есть токен
if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU":
    telegram_bot = SimpleTelegramBot(TELEGRAM_TOKEN)
    thread = threading.Thread(target=telegram_bot.start, daemon=True)
    thread.start()
    print("✅ Telegram бот запущен")
else:
    print("⚠️ Telegram токен не настроен")

# ==================== ВЕБ-ИНТЕРФЕЙС ====================

@app.get("/")
async def root():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SMC Crypto Bot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
                color: #00ff88;
                font-family: 'Courier New', monospace;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0;
                padding: 20px;
            }
            .container {
                text-align: center;
                padding: 40px;
                border: 2px solid #00ff88;
                border-radius: 20px;
                background: rgba(0,0,0,0.5);
                max-width: 500px;
            }
            h1 {
                font-size: 48px;
                margin-bottom: 20px;
                text-shadow: 0 0 10px #00ff88;
            }
            .status {
                color: #fff;
                font-size: 24px;
                margin: 20px 0;
            }
            .commands {
                text-align: left;
                background: #0f0f1a;
                padding: 15px;
                border-radius: 10px;
                margin-top: 20px;
                font-size: 12px;
            }
            .commands code {
                color: #00ff88;
            }
            .telegram-link {
                display: inline-block;
                background: #00ff88;
                color: #000;
                padding: 10px 20px;
                border-radius: 10px;
                text-decoration: none;
                margin-top: 20px;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 SMC CRYPTO BOT</h1>
            <div class="status">✅ БОТ РАБОТАЕТ</div>
            <div class="commands">
                📋 <strong>Команды Telegram:</strong><br>
                <code>/start</code> - запуск бота<br>
                <code>/signals</code> - активные сигналы<br>
                <code>/chart BTC</code> - график<br>
                <code>/status</code> - статус<br>
                <code>/help</code> - помощь
            </div>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {"status": "ok", "telegram": bool(TELEGRAM_TOKEN and TELEGRAM_TOKEN != "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU")}
