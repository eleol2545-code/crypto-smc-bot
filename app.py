from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import requests
import json

app = FastAPI()

# ==================== КОНФИГУРАЦИЯ ====================

# ВСТАВЬТЕ ВАШ ТОКЕН СЮДА!
TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"  # ← Ваш токен

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
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

def set_webhook():
    """Устанавливает webhook для бота"""
    try:
        # Получаем URL из Railway
        railway_url = "https://crypto-smc-bot.railway.app"
        webhook_url = f"{railway_url}/webhook"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        response = requests.post(url, json={"url": webhook_url})
        result = response.json()
        
        if result.get("ok"):
            print(f"✅ Webhook установлен: {webhook_url}")
        else:
            print(f"❌ Ошибка: {result}")
        
        return result
    except Exception as e:
        print(f"Error: {e}")
        return None

# ==================== ОБРАБОТЧИКИ TELEGRAM ====================

def handle_message(chat_id, text):
    """Обрабатывает сообщения"""
    print(f"Сообщение от {chat_id}: {text}")
    
    if text == "/start":
        send_telegram_message(chat_id, """
🤖 *SMC Crypto Bot*

✅ Бот работает!

*Команды:*
/signals - активные сигналы
/status - статус
/help - помощь
""")
    elif text == "/help":
        send_telegram_message(chat_id, """
📋 *Помощь*
/start - запуск
/status - статус
/signals - сигналы
""")
    elif text == "/status":
        send_telegram_message(chat_id, "✅ *Статус:* Активен\nВерсия: 1.0")
    elif text == "/signals":
        send_telegram_message(chat_id, """
🚨 *ТЕСТОВЫЙ СИГНАЛ*

📈 *BTC/USDT* | LONG
🎯 Уверенность: 75%
💰 Вход: $65,432
🛑 SL: $64,450
🎯 TP: $68,049
""")
    else:
        send_telegram_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== WEBHOOK ЭНДПОИНТ ====================

@app.post("/webhook")
async def webhook(request: Request):
    """Принимает обновления от Telegram"""
    try:
        update = await request.json()
        print(f"Webhook: {update}")
        
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            handle_message(chat_id, text)
        
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"Error: {e}")
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
                font-family: monospace;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .container {
                text-align: center;
                padding: 40px;
                border: 2px solid #00ff88;
                border-radius: 20px;
            }
            h1 { font-size: 48px; margin-bottom: 20px; }
            .status { color: #fff; font-size: 24px; margin: 20px 0; }
            .commands { text-align: left; background: #0f0f1a; padding: 15px; border-radius: 10px; margin-top: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 SMC CRYPTO BOT</h1>
            <div class="status">✅ БОТ РАБОТАЕТ</div>
            <div class="commands">
                📋 <strong>Команды Telegram:</strong><br>
                <code>/start</code> - запуск<br>
                <code>/signals</code> - сигналы<br>
                <code>/status</code> - статус<br>
                <code>/help</code> - помощь
            </div>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {"status": "ok", "telegram": bool(TELEGRAM_TOKEN)}

@app.get("/setwebhook")
async def set_webhook_endpoint():
    """Устанавливает webhook"""
    result = set_webhook()
    return result

# ==================== ПРИ СТАРТЕ ====================

if TELEGRAM_TOKEN:
    set_webhook()
