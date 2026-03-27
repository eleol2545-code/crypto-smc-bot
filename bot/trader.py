import ccxt
import json
import os
from datetime import datetime

class Trader:
    def __init__(self, config):
        self.config = config
        self.exchange = None
        self.positions = {}
        self.trades_history = []
        self.daily_pnl = 0
        self.daily_loss = 0
        self.init_exchange()
        self.load_history()
    
    def init_exchange(self):
        exchange_config = self.config.get('exchanges', {}).get('binance', {})
        testnet = exchange_config.get('testnet', True)
        
        if testnet:
            self.exchange = ccxt.binance({
                'apiKey': exchange_config.get('api_key', ''),
                'secret': exchange_config.get('api_secret', ''),
                'enableRateLimit': True,
                'options': {'defaultType': 'future', 'testnet': True}
            })
        else:
            self.exchange = ccxt.binance({
                'apiKey': exchange_config.get('api_key', ''),
                'secret': exchange_config.get('api_secret', ''),
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
    
    def get_balance(self):
        try:
            balance = self.exchange.fetch_balance()
            return {
                'total': balance['USDT']['total'] if 'USDT' in balance else 0,
                'free': balance['USDT']['free'] if 'USDT' in balance else 0,
                'used': balance['USDT']['used'] if 'USDT' in balance else 0
            }
        except:
            return None
    
    def open_position(self, signal):
        if not self.config['trading']['enabled']:
            return False, "Торговля отключена"
        
        symbol = signal['symbol']
        active = len([p for p in self.positions.values() if p])
        if active >= self.config['trading']['max_positions']:
            return False, f"Лимит позиций {self.config['trading']['max_positions']}"
        
        balance = self.get_balance()
        if not balance:
            return False, "Не удалось получить баланс"
        
        risk_amount = balance['total'] * (self.config['trading']['risk_per_trade'] / 100)
        risk_per_unit = abs(signal['entry'] - signal['stop_loss'])
        quantity = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.001
        
        try:
            if signal['type'] == 'LONG':
                self.exchange.create_order(symbol=symbol, type='market', side='buy', amount=quantity)
            else:
                self.exchange.create_order(symbol=symbol, type='market', side='sell', amount=quantity)
            
            self.positions[symbol] = {
                'symbol': symbol,
                'type': signal['type'],
                'entry': signal['entry'],
                'stop_loss': signal['stop_loss'],
                'take_profit': signal['take_profit'],
                'quantity': quantity,
                'open_time': datetime.now().isoformat()
            }
            return True, f"Открыта {symbol} {signal['type']}"
        except Exception as e:
            return False, str(e)
    
    def close_position(self, symbol, reason):
        if symbol not in self.positions:
            return False, "Позиция не найдена"
        
        pos = self.positions[symbol]
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            exit_price = ticker['last']
            
            if pos['type'] == 'LONG':
                pnl_pct = (exit_price - pos['entry']) / pos['entry'] * 100
            else:
                pnl_pct = (pos['entry'] - exit_price) / pos['entry'] * 100
            
            self.trades_history.append({
                'symbol': symbol,
                'type': pos['type'],
                'entry': pos['entry'],
                'exit': exit_price,
                'pnl_pct': pnl_pct,
                'reason': reason
            })
            self.daily_pnl += pnl_pct
            del self.positions[symbol]
            self.save_history()
            return True, f"Закрыта {symbol}: {pnl_pct:+.2f}%"
        except Exception as e:
            return False, str(e)
    
    def save_history(self):
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/trades_history.json', 'w') as f:
                json.dump(self.trades_history, f, indent=2)
        except:
            pass
    
    def load_history(self):
        try:
            if os.path.exists('data/trades_history.json'):
                with open('data/trades_history.json', 'r') as f:
                    self.trades_history = json.load(f)
        except:
            pass
