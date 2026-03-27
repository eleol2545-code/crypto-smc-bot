import pandas as pd
import numpy as np
import ccxt
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class SMCAnalyzer:
    """SMC/ICT анализ с индикаторами RSI, MACD, Bollinger, Stochastic, VWAP"""
    
    def __init__(self):
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
    
    def fetch_data(self, symbol, timeframe='1h', limit=150):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            return None
    
    def calculate_indicators(self, df):
        if df is None or len(df) < 50:
            return df
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_fast = df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_line'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal']
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # Stochastic
        low_min = df['low'].rolling(window=14).min()
        high_max = df['high'].rolling(window=14).max()
        df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
        
        # EMA
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # VWAP
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        # Объем
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        return df
    
    def find_order_blocks(self, df):
        if df is None or len(df) < 30:
            return df
        
        df['bullish_ob'] = 0
        df['bearish_ob'] = 0
        
        for i in range(5, len(df) - 1):
            if (df['close'].iloc[i] > df['close'].iloc[i-1] * 1.01 and
                df['volume'].iloc[i] > df['volume'].iloc[i-5:i].mean() * 1.5):
                for j in range(i, min(i + 20, len(df))):
                    if df['low'].iloc[j] <= df['high'].iloc[i-1]:
                        df.loc[df.index[j], 'bullish_ob'] = 1
            
            elif (df['close'].iloc[i] < df['close'].iloc[i-1] * 0.99 and
                  df['volume'].iloc[i] > df['volume'].iloc[i-5:i].mean() * 1.5):
                for j in range(i, min(i + 20, len(df))):
                    if df['high'].iloc[j] >= df['low'].iloc[i-1]:
                        df.loc[df.index[j], 'bearish_ob'] = 1
        
        return df
    
    def generate_signal(self, df, style='day', min_confidence=70):
        if df is None or len(df) < 50:
            return None
        
        current = df.iloc[-1]
        
        params = {
            'scalp': {'sl_pct': 0.008, 'tp_pct': 0.015, 'min_conf': 65},
            'day': {'sl_pct': 0.015, 'tp_pct': 0.03, 'min_conf': 70},
            'swing': {'sl_pct': 0.025, 'tp_pct': 0.06, 'min_conf': 75}
        }
        p = params.get(style, params['day'])
        
        score = 0
        signal_type = None
        signals_detail = []
        
        if current['bullish_ob'] == 1:
            score += 20
            signal_type = 'LONG'
            signals_detail.append('🔵 Бычий Order Block')
        if current['bearish_ob'] == 1:
            score += 20
            signal_type = 'SHORT'
            signals_detail.append('🔴 Медвежий Order Block')
        
        if current['rsi'] < 30:
            score += 15
            if not signal_type:
                signal_type = 'LONG'
            signals_detail.append(f'📊 RSI: {current["rsi"]:.1f} (перепроданность)')
        elif current['rsi'] > 70:
            score += 15
            if not signal_type:
                signal_type = 'SHORT'
            signals_detail.append(f'📊 RSI: {current["rsi"]:.1f} (перекупленность)')
        
        if current['macd_hist'] > 0:
            if signal_type == 'LONG':
                score += 15
                signals_detail.append(f'📈 MACD: +{current["macd_hist"]:.2f}')
        elif current['macd_hist'] < 0:
            if signal_type == 'SHORT':
                score += 15
                signals_detail.append(f'📉 MACD: {current["macd_hist"]:.2f}')
        
        if current['close'] <= current['bb_lower'] * 1.005:
            score += 15
            if not signal_type:
                signal_type = 'LONG'
            signals_detail.append(f'📊 Bollinger: у нижней полосы ${current["bb_lower"]:.2f}')
        elif current['close'] >= current['bb_upper'] * 0.995:
            score += 15
            if not signal_type:
                signal_type = 'SHORT'
            signals_detail.append(f'📊 Bollinger: у верхней полосы ${current["bb_upper"]:.2f}')
        
        if current['stoch_k'] < 20 and current['stoch_d'] < 20:
            score += 15
            if not signal_type:
                signal_type = 'LONG'
            signals_detail.append(f'📊 Stochastic: %K={current["stoch_k"]:.1f} (перепроданность)')
        elif current['stoch_k'] > 80 and current['stoch_d'] > 80:
            score += 15
            if not signal_type:
                signal_type = 'SHORT'
            signals_detail.append(f'📊 Stochastic: %K={current["stoch_k"]:.1f} (перекупленность)')
        
        if current['ema_9'] > current['ema_21'] and current['ema_21'] > current['ema_50']:
            score += 10
            if signal_type == 'LONG':
                score += 5
                signals_detail.append('📈 EMA: золотой крест')
        elif current['ema_9'] < current['ema_21'] and current['ema_21'] < current['ema_50']:
            score += 10
            if signal_type == 'SHORT':
                score += 5
                signals_detail.append('📉 EMA: мертвый крест')
        
        if current['volume_ratio'] > 1.5:
            score += 10
            signals_detail.append(f'⚡ Объем: {current["volume_ratio"]:.1f}x от среднего')
        
        if current['close'] < current['vwap'] and signal_type == 'LONG':
            score += 10
            signals_detail.append(f'🎯 VWAP: цена ниже ${current["vwap"]:.2f}')
        elif current['close'] > current['vwap'] and signal_type == 'SHORT':
            score += 10
            signals_detail.append(f'🎯 VWAP: цена выше ${current["vwap"]:.2f}')
        
        confidence = min(100, score)
        
        if signal_type and confidence >= min_confidence:
            entry = current['close']
            if signal_type == 'LONG':
                sl = entry * (1 - p['sl_pct'])
                tp = entry * (1 + p['tp_pct'])
            else:
                sl = entry * (1 + p['sl_pct'])
                tp = entry * (1 - p['tp_pct'])
            
            return {
                'type': signal_type,
                'entry': round(entry, 2),
                'stop_loss': round(sl, 2),
                'take_profit': round(tp, 2),
                'confidence': confidence,
                'score': score,
                'signals': signals_detail,
                'indicators': {
                    'rsi': round(current['rsi'], 1),
                    'macd_hist': round(current['macd_hist'], 2),
                    'vwap': round(current['vwap'], 2),
                    'volume_ratio': round(current['volume_ratio'], 2)
                }
            }
        
        return None
    
    def get_current_price(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except:
            return None
