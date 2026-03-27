from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import asyncio
import threading
import requests
import json

app = FastAPI()

# ==================== КОНФИГУРАЦИЯ ====================

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"  # ВСТАВЬТЕ СЮДА!

# ==================== ФУНКЦИИ TELEGRAM ====================

def send_telegram_message(chat_id, text):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def set_webhook():
    """Устанавливает webhook для бота"""
    try:
        # Получаем URL из Railway
        railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
        if not railway_url:
            # Пробуем получить из переменных
            railway_url = "https://crypto-smc-bot.railway.app"
        
        webhook_url = f"{railway_url}/webhook"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        response = requests.post(url, json={"url": webhook_url})
        result = response.json()
        
        if result.get("ok"):
            print(f"✅ Webhook установлен: {webhook_url}")
        else:
            print(f"❌ Ошибка webhook: {result}")
        
        return result
    except Exception as e:
        print(f"Error setting webhook: {e}")
        return None

# ==================== ОБРАБОТЧИКИ TELEGRAM ====================

def handle_message(chat_id, text):
    """Обрабатывает сообщения от пользователя"""
    print(f"Получено сообщение от {chat_id}: {text}")
    
    if text == "/start":
        send_telegram_message(chat_id, """
🤖 *SMC Crypto Bot*

✅ Бот работает!

*Команды:*
/signals - активные сигналы
/status - статус бота
/help - помощь
""")
    
    elif text == "/help":
        send_telegram_message(chat_id, """
📋 *Помощь*

/start - запуск бота
/status - статус
/signals - сигналы
/help - эта справка
""")
    
    elif text == "/status":
        send_telegram_message(chat_id, """
✅ *Статус*
Бот: активен
Версия: 1.0
Мониторинг: BTC, ETH, SOL
""")
    
    elif text == "/signals":
        # Простой сигнал для теста
        send_telegram_message(chat_id, """
🚨 *ТЕСТОВЫЙ СИГНАЛ*

📈 *BTC/USDT* | LONG
🎯 Уверенность: 75%
💰 Вход: $65,432
🛑 SL: $64,450
🎯 TP: $68,049
""")
    
    else:
        send_telegram_message(chat_id, f"⚠️ Неизвестная команда: {text}\nИспользуйте /help")

# ==================== WEBHOOK ЭНДПОИНТ ====================

@app.post("/webhook")
async def webhook(request: Request):
    """Принимает обновления от Telegram"""
    try:
        update = await request.json()
        print(f"Webhook received: {update}")
        
        # Обрабатываем сообщение
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            
            # Обрабатываем в отдельном потоке, чтобы не блокировать
            threading.Thread(target=handle_message, args=(chat_id, text)).start()
        
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"Webhook error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

# ==================== WEB-ИНТЕРФЕЙС ====================

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
            .commands {
                text-align: left;
                background: #0f0f1a;
                padding: 15px;
                border-radius: 10px;
                margin-top: 20px;
                font-size: 12px;
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
                <code>/status</code> - статус<br>
                <code>/help</code> - помощь
            </div>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {"status": "ok", "telegram_token": bool(TELEGRAM_TOKEN and TELEGRAM_TOKEN != "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU")}

@app.get("/setwebhook")
async def set_webhook_endpoint():
    """Ручная установка webhook"""
    result = set_webhook()
    return result

# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# При старте устанавливаем webhook
if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU":
    set_webhook()
