from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import requests
import ccxt
import pandas as pd
import numpy as np

app = FastAPI()

# ==================== КОНФИГУРАЦИЯ ====================

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"

# Инициализируем биржу
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# ==================== ФУНКЦИИ ====================

def send_message(chat_id, text):
    """Отправляет сообщение"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        print(f"Sent to {chat_id}")
    except Exception as e:
        print(f"Send error: {e}")

def get_signal(symbol='BTC/USDT'):
    """Получает SMC сигнал"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        price = df['c'].iloc[-1]
        
        # RSI
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # Уровни
        high = df['h'].iloc[-20:].max()
        low = df['l'].iloc[-20:].min()
        
        if price <= low * 1.005 and rsi < 40:
            return {
                'signal': 'LONG',
                'entry': round(price, 2),
                'sl': round(price * 0.985, 2),
                'tp': round(price * 1.04, 2),
                'confidence': 75,
                'price': price,
                'rsi': round(rsi, 1),
                'support': round(low, 2),
                'resistance': round(high, 2)
            }
        elif price >= high * 0.995 and rsi > 60:
            return {
                'signal': 'SHORT',
                'entry': round(price, 2),
                'sl': round(price * 1.015, 2),
                'tp': round(price * 0.96, 2),
                'confidence': 75,
                'price': price,
                'rsi': round(rsi, 1),
                'support': round(low, 2),
                'resistance': round(high, 2)
            }
        else:
            return {
                'signal': None,
                'price': price,
                'rsi': round(rsi, 1),
                'support': round(low, 2),
                'resistance': round(high, 2)
            }
    except Exception as e:
        print(f"Signal error: {e}")
        return None

# ==================== ОБРАБОТКА СООБЩЕНИЙ ====================

def handle_message(chat_id, text):
    """Обрабатывает команды"""
    print(f"Handling: {text} from {chat_id}")
    
    if text == "/start":
        send_message(chat_id, """
🤖 *SMC Crypto Bot*

✅ Бот работает!

*Команды:*
/signals - сигналы BTC, ETH, SOL
/status - статус BTC
/help - помощь
""")
    
    elif text == "/signals":
        msg = "🚨 *АКТИВНЫЕ СИГНАЛЫ*\n\n"
        
        for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']:
            s = get_signal(sym)
            if s and s.get('signal'):
                emoji = "📈" if s['signal'] == 'LONG' else "📉"
                msg += f"{emoji} *{sym}* | {s['signal']}\n"
                msg += f"   🎯 Уверенность: {s['confidence']}%\n"
                msg += f"   💰 Вход: ${s['entry']}\n"
                msg += f"   🛑 SL: ${s['sl']}\n"
                msg += f"   🎯 TP: ${s['tp']}\n\n"
            else:
                msg += f"⏳ *{sym}* | {s['price']:.0f} | нет сигнала\n\n" if s else f"⏳ *{sym}* | ошибка\n\n"
        
        send_message(chat_id, msg)
    
    elif text == "/status":
        s = get_signal('BTC/USDT')
        if s:
            send_message(chat_id, f"""
✅ *Статус BTC*

💰 Цена: ${s['price']:.2f}
📊 RSI: {s['rsi']}
🟢 Поддержка: ${s['support']}
🔴 Сопротивление: ${s['resistance']}
""")
        else:
            send_message(chat_id, "❌ Ошибка получения данных")
    
    elif text == "/help":
        send_message(chat_id, """
📋 *Команды:*
/start - запуск
/signals - сигналы
/status - статус BTC
/help - помощь
""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестная команда: {text}\nИспользуйте /help")

# ==================== WEBHOOK ====================

@app.post("/webhook")
async def webhook(request: Request):
    """Принимает обновления"""
    try:
        data = await request.json()
        print(f"Webhook received: {data}")
        
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            handle_message(chat_id, text)
        
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"Webhook error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

# ==================== WEB ====================

@app.get("/")
async def root():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SMC Crypto Bot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { background: #0a0a0a; color: #00ff88; font-family: monospace; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .container { text-align: center; padding: 40px; border: 2px solid #00ff88; border-radius: 20px; }
            h1 { font-size: 48px; }
            .status { color: #fff; font-size: 24px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 SMC CRYPTO BOT</h1>
            <div class="status">✅ РАБОТАЕТ</div>
            <p>Telegram: @SMCryptoBot</p>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/test")
async def test():
    """Тестовый эндпоинт"""
    return {"message": "Bot is running"}
