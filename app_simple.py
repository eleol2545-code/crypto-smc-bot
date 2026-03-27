from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os

app = FastAPI(title="SMC Crypto Bot")

@app.get("/")
async def root():
    return HTMLResponse("""
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
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🤖 SMC Crypto Bot</h1>
            <p>Статус: <span class="status">🟢 РАБОТАЕТ</span></p>
            <p>Версия: 1.0</p>
        </div>
        <div class="card">
            <h2>📊 Информация</h2>
            <p>Бот работает!</p>
            <p>Telegram: настройка в процессе</p>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Service is running"}

@app.get("/api/info")
async def info():
    return {
        "name": "SMC Crypto Bot",
        "version": "1.0",
        "status": "running"
    }
