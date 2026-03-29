import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
import threading
from datetime import datetime

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)

# ==================== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ====================

GLOBAL_WATCHLIST_FILE = 'data/global_watchlist.json'
GLOBAL_TRADES_FILE = 'data/global_trades.json'

def get_global_watchlist():
    if os.path.exists(GLOBAL_WATCHLIST_FILE):
        with open(GLOBAL_WATCHLIST_FILE, 'r') as f:
            data = json.load(f)
            return data.get('watchlist', ['BTC', 'ETH', 'SOL'])
    return ['BTC', 'ETH', 'SOL']

def save_global_watchlist(watchlist):
    with open(GLOBAL_WATCHLIST_FILE, 'w') as f:
        json.dump({'watchlist': watchlist}, f, indent=2)

# ==================== БИРЖА ====================

exchange = ccxt.bybit({
    'enableRateLimit': True,
    'options': {'defaultType': 'linear'}
})

# ==================== УПРАВЛЕНИЕ СДЕЛКАМИ ====================

class TradeManager:
    def __init__(self):
        self.active_trades = {}
        self.trade_counter = 1
        self.load_trades()
    
    def load_trades(self):
        if os.path.exists(GLOBAL_TRADES_FILE):
            with open(GLOBAL_TRADES_FILE, 'r') as f:
                data = json.load(f)
                self.active_trades = data.get('active', {})
                self.trade_counter = data.get('counter', 1)
    
    def save_trades(self):
        with open(GLOBAL_TRADES_FILE, 'w') as f:
            json.dump({'active': self.active_trades, 'counter': self.trade_counter}, f, indent=2)
    
    def get_next_id(self):
        current = self.trade_counter
        self.trade_counter += 1
        self.save_trades()
        return current
    
    def add_trade(self, symbol, side, entry_price, size=1, leverage=1, tp=None, sl=None):
        trade_id = self.get_next_id()
        trade = {
            'id': trade_id, 'symbol': symbol, 'side': side, 'entry': entry_price,
            'size': size, 'leverage': leverage, 'tp': tp, 'sl': sl,
            'open_time': datetime.now().isoformat(), 'status': 'open'
        }
        self.active_trades[str(trade_id)] = trade
        self.save_trades()
        return trade_id
    
    def close_trade(self, trade_id, exit_price):
        trade_id = str(trade_id)
        if trade_id not in self.active_trades:
            return None
        trade = self.active_trades[trade_id]
        if trade['side'] == 'LONG':
            pnl_pct = (exit_price - trade['entry']) / trade['entry'] * 100 * trade['leverage']
            pnl_usdt = trade['size'] * (exit_price - trade['entry']) / trade['entry'] * trade['leverage']
        else:
            pnl_pct = (trade['entry'] - exit_price) / trade['entry'] * 100 * trade['leverage']
            pnl_usdt = trade['size'] * (trade['entry'] - exit_price) / trade['entry'] * trade['leverage']
        trade['exit'] = exit_price
        trade['exit_time'] = datetime.now().isoformat()
        trade['pnl_pct'] = round(pnl_pct, 2)
        trade['pnl_usdt'] = round(pnl_usdt, 2)
        trade['status'] = 'closed'
        history_file = 'data/trades_history.json'
        history = []
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
        history.append(trade)
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        del self.active_trades[trade_id]
        self.save_trades()
        return trade
    
    def reset_all_trades(self):
        self.active_trades = {}
        self.trade_counter = 1
        self.save_trades()
        if os.path.exists('data/trades_history.json'):
            os.remove('data/trades_history.json')
        return True
    
    def get_active_trades(self):
        return self.active_trades
    
    def get_history(self, limit=20):
        history_file = 'data/trades_history.json'
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
            return history[-limit:]
        return []
    
    def get_stats(self):
        history = self.get_history(1000)
        if not history:
            return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'total_pnl_pct': 0, 'total_pnl_usdt': 0, 'profit_factor': 0}
        wins = [t for t in history if t['pnl_pct'] > 0]
        losses = [t for t in history if t['pnl_pct'] <= 0]
        total_pnl_pct = sum(t['pnl_pct'] for t in history)
        total_pnl_usdt = sum(t['pnl_usdt'] for t in history)
        avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
        profit_factor = abs(sum(t['pnl_usdt'] for t in wins) / sum(t['pnl_usdt'] for t in losses)) if losses and sum(t['pnl_usdt'] for t in losses) != 0 else 0
        return {
            'total_trades': len(history), 'wins': len(wins), 'losses': len(losses),
            'win_rate': round(len(wins) / len(history) * 100, 2) if history else 0,
            'total_pnl_pct': round(total_pnl_pct, 2), 'total_pnl_usdt': round(total_pnl_usdt, 2),
            'avg_win': round(avg_win, 2), 'avg_loss': round(avg_loss, 2), 'profit_factor': round(profit_factor, 2)
        }

trade_manager = TradeManager()

# ==================== ФУНКЦИЯ ФОРМАТИРОВАНИЯ ЦЕНЫ ====================

def format_price(price):
    if price is None:
        return "0"
    if price < 0.00001:
        return f"{price:.8f}".rstrip('0').rstrip('.')
    elif price < 0.001:
        return f"{price:.6f}".rstrip('0').rstrip('.')
    elif price < 1:
        return f"{price:.4f}".rstrip('0').rstrip('.')
    elif price < 1000:
        return f"{price:.2f}"
    else:
        return f"{price:.0f}"

# ==================== ТЕСТОВЫЙ СИГНАЛ ====================

def get_simple_signal(symbol, style='day'):
    try:
        sym = f"{symbol}USDT"
        ticker = exchange.fetch_ticker(sym)
        price = ticker['last']
        
        # Простой сигнал для теста
        return {
            'price': price,
            'signal': 'LONG' if price < 65000 else 'SHORT',
            'entry': price,
            'sl': price * 0.985,
            'tp': price * 1.04,
            'confidence': 75,
            'reasons': ['Тестовый сигнал']
        }
    except Exception as e:
        return None

# ==================== TELEGRAM БОТ ====================

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    watchlist = get_global_watchlist()
    
    if text == "/start":
        send_message(chat_id, """🤖 *SMC CRYPTO BOT* — УПРОЩЕННАЯ ВЕРСИЯ

*Команды:*
/add BTC,ETH,SOL — добавить монеты
/remove DOGE — удалить
/list — список монет
/signals — сигналы
/all_signals — сигналы по всем стилям
/aggregate BTC — агрегированные данные
/take LONG BTC 65000 100 5 — открыть сделку
/close 123 — закрыть
/trades — активные сделки
/history — история
/stats — статистика
/pnl — P&L
/reset_trades — сброс
/help — помощь""")
    
    elif text.startswith("/add"):
        args = text.replace("/add", "").strip().upper().replace(",", " ").split()
        added = []
        for arg in args:
            if arg not in watchlist:
                watchlist.append(arg)
                added.append(arg)
        save_global_watchlist(watchlist)
        send_message(chat_id, f"✅ Добавлено: {', '.join(added)}\n\n📋 Всего монет: {len(watchlist)}")
    
    elif text.startswith("/remove"):
        args = text.replace("/remove", "").strip().upper()
        if args and args in watchlist:
            watchlist.remove(args)
            save_global_watchlist(watchlist)
            send_message(chat_id, f"❌ Удалено: {args}")
        else:
            send_message(chat_id, f"⚠️ {args} не найдена")
    
    elif text == "/list":
        if not watchlist:
            send_message(chat_id, "📭 Список пуст. Добавьте: `/add BTC`")
        else:
            msg = "📋 *МОИ МОНЕТЫ*\n\n"
            for s in watchlist: msg += f"• {s}\n"
            send_message(chat_id, msg)
    
    elif text == "/signals":
        if not watchlist:
            send_message(chat_id, "📭 Нет монет в списке")
            return
        msg = "🚨 *СИГНАЛЫ*\n\n"
        for sym in watchlist[:5]:
            signal = get_simple_signal(sym)
            if signal:
                emoji = "📈" if signal['signal'] == 'LONG' else "📉"
                msg += f"{emoji} *{sym}* | {signal['signal']}\n"
                msg += f"   💰 Цена: ${signal['price']:.2f}\n"
                msg += f"   🎯 Уверенность: {signal['confidence']}%\n"
                msg += f"   🚪 Вход: ${signal['entry']:.2f}\n"
                msg += f"   🛑 SL: ${signal['sl']:.2f}\n"
                msg += f"   🎯 TP: ${signal['tp']:.2f}\n\n"
            else:
                msg += f"❌ *{sym}* | ошибка\n\n"
        send_message(chat_id, msg[:4000])
    
    elif text == "/all_signals":
        send_message(chat_id, "🔍 *Поиск сигналов по всем стилям...*")
        await handle_message(chat_id, "/signals")
    
    elif text == "/aggregate":
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        send_message(chat_id, f"📊 *АГРЕГИРОВАННЫЕ ДАННЫЕ | {symbol}*\n\n🏦 *Биржи:* Bybit, KuCoin\n💰 *Средняя цена:* тестовые данные\n\n📡 Функция в разработке")
    
    # ==================== УПРАВЛЕНИЕ СДЕЛКАМИ ====================
    
    elif text.startswith("/take"):
        parts = text.split()
        if len(parts) < 4:
            send_message(chat_id, "📝 *Формат:* `/take LONG BTC 65000`")
            return
        side = parts[1].upper()
        symbol = parts[2].upper()
        try:
            entry = float(parts[3])
        except:
            send_message(chat_id, "❌ Цена должна быть числом")
            return
        size = float(parts[4]) if len(parts) > 4 else 1
        leverage = float(parts[5]) if len(parts) > 5 else 1
        tp = float(parts[6]) if len(parts) > 6 else None
        sl = float(parts[7]) if len(parts) > 7 else None
        
        trade_id = trade_manager.add_trade(symbol, side, entry, size, leverage, tp, sl)
        
        msg = f"✅ *СДЕЛКА ЗАФИКСИРОВАНА*\n\n📊 *{side} {symbol}*\n💰 Вход: ${entry:.2f}\n📦 Размер: {size} USDT\n⚡ Плечо: x{leverage}\n🆔 ID: {trade_id}"
        if tp: msg += f"\n🎯 TP: ${tp:.2f}"
        if sl: msg += f"\n🛑 SL: ${sl:.2f}"
        send_message(chat_id, msg)
    
    elif text.startswith("/close"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/close 123`")
            return
        try:
            trade_id = int(parts[1])
            exit_price = float(parts[2]) if len(parts) > 2 else None
            
            active = trade_manager.get_active_trades()
            if str(trade_id) not in active:
                send_message(chat_id, f"❌ Сделка с ID {trade_id} не найдена")
                return
            trade = active[str(trade_id)]
            
            if not exit_price:
                exit_price = trade['entry'] * (1.02 if trade['side'] == 'LONG' else 0.98)
            
            closed = trade_manager.close_trade(trade_id, exit_price)
            if closed:
                emoji = "✅" if closed['pnl_pct'] > 0 else "❌"
                msg = f"{emoji} *СДЕЛКА ЗАКРЫТА*\n\n📊 *{closed['side']} {closed['symbol']}*\n💰 Вход: ${closed['entry']:.2f}\n🚪 Выход: ${closed['exit']:.2f}\n📈 P&L: {closed['pnl_pct']:+.2f}% (${closed['pnl_usdt']:+.2f})"
                send_message(chat_id, msg)
        except ValueError:
            send_message(chat_id, "❌ ID должен быть числом")
    
    elif text == "/trades":
        active = trade_manager.get_active_trades()
        if not active:
            send_message(chat_id, "📭 *Нет активных сделок*")
            return
        msg = "📊 *АКТИВНЫЕ СДЕЛКИ*\n\n"
        for trade_id, trade in active.items():
            msg += f"🆔 *{trade_id}* | {trade['symbol']} | {trade['side']}\n"
            msg += f"   💰 Вход: ${trade['entry']:.2f}\n"
            msg += f"   ⚡ Плечо: x{trade['leverage']}\n"
            if trade.get('tp'): msg += f"   🎯 TP: ${trade['tp']:.2f}\n"
            if trade.get('sl'): msg += f"   🛑 SL: ${trade['sl']:.2f}\n"
            msg += "\n"
        send_message(chat_id, msg)
    
    elif text == "/history":
        history = trade_manager.get_history(10)
        if not history:
            send_message(chat_id, "📭 *Нет истории сделок*")
            return
        msg = "📜 *ПОСЛЕДНИЕ СДЕЛКИ*\n\n"
        for trade in reversed(history):
            emoji = "✅" if trade['pnl_pct'] > 0 else "❌"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}*\n"
            msg += f"   Вход: ${trade['entry']:.2f} → Выход: ${trade['exit']:.2f}\n"
            msg += f"   P&L: {trade['pnl_pct']:+.2f}%\n\n"
        send_message(chat_id, msg)
    
    elif text == "/stats":
        stats = trade_manager.get_stats()
        if stats['total_trades'] == 0:
            send_message(chat_id, "📭 *Нет данных для статистики*")
            return
        msg = f"""📊 *СТАТИСТИКА*

📈 *Всего сделок:* {stats['total_trades']}
✅ *Прибыльных:* {stats['wins']}
❌ *Убыточных:* {stats['losses']}
🎯 *Win Rate:* {stats['win_rate']}%

💰 *Общая прибыль:* {stats['total_pnl_pct']:+.2f}% (${stats['total_pnl_usdt']:+.2f})
📊 *Profit Factor:* {stats['profit_factor']}"""
        send_message(chat_id, msg)
    
    elif text == "/pnl":
        active = trade_manager.get_active_trades()
        if not active:
            send_message(chat_id, "📭 *Нет открытых сделок*")
            return
        total_pnl = 0
        msg = "📊 *ТЕКУЩИЙ P&L*\n\n"
        for trade_id, trade in active.items():
            current = trade['entry'] * (1.01 if trade['side'] == 'LONG' else 0.99)
            if trade['side'] == 'LONG':
                pnl_pct = (current - trade['entry']) / trade['entry'] * 100 * trade['leverage']
                pnl_usdt = trade['size'] * (current - trade['entry']) / trade['entry'] * trade['leverage']
            else:
                pnl_pct = (trade['entry'] - current) / trade['entry'] * 100 * trade['leverage']
                pnl_usdt = trade['size'] * (trade['entry'] - current) / trade['entry'] * trade['leverage']
            total_pnl += pnl_usdt
            emoji = "📈" if pnl_pct > 0 else "📉"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}* (ID: {trade_id})\n   P&L: {pnl_pct:+.2f}% (${pnl_usdt:+.2f})\n\n"
        msg += f"💰 *ИТОГО:* ${total_pnl:+.2f}"
        send_message(chat_id, msg)
    
    elif text == "/reset_trades":
        trade_manager.reset_all_trades()
        send_message(chat_id, "🗑️ *ВСЕ СДЕЛКИ СБРОШЕНЫ*")
    
    elif text == "/help":
        send_message(chat_id, """📋 *ВСЕ КОМАНДЫ*

/add BTC,ETH — добавить монеты
/remove DOGE — удалить
/list — список монет
/signals — сигналы
/all_signals — сигналы по всем стилям
/aggregate BTC — агрегированные данные
/take LONG BTC 65000 — открыть сделку
/close 123 — закрыть
/trades — активные сделки
/history — история
/stats — статистика
/pnl — P&L
/reset_trades — сброс
/help — помощь""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ЗАПУСК ====================

print("=" * 60)
print("🚀 SMC CRYPTO BOT — УПРОЩЕННАЯ ВЕРСИЯ")
print("=" * 60)
print("Ожидание сообщений...\n")

while True:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        response = requests.get(url, params={"offset": LAST_UPDATE_ID + 1, "timeout": 30})
        data = response.json()
        if data.get("ok"):
            for update in data.get("result", []):
                if update["update_id"] > LAST_UPDATE_ID:
                    LAST_UPDATE_ID = update["update_id"]
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")
                        handle_message(chat_id, text)
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(1)
