from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import requests

app = FastAPI()

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    except:
        pass

@app.post("/webhook")
async def webhook(request: Request):
    """Главный эндпоинт для Telegram"""
    try:
        data = await request.json()
        print(f"Webhook: {data}")
        
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            
            if text == "/start":
                send_message(chat_id, "🤖 *SMC Crypto Bot*\n✅ Работает!\n/signals - сигналы")
            elif text == "/signals":
                send_message(chat_id, "📈 *BTC* | LONG\n💰 Вход: $65432\n🎯 TP: $68049\n🛑 SL: $64450")
            elif text == "/status":
                send_message(chat_id, "✅ Бот активен\nВерсия: 1.0")
            else:
                send_message(chat_id, "Используйте /start или /signals")
        
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

@app.get("/")
async def root():
    return HTMLResponse("<h1>SMC Crypto Bot</h1><p>✅ Работает</p>")

@app.get("/health")
async def health():
    return {"status": "ok"}
