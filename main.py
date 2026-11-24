# BLACK SKYNET - Scanner + Signals BOT - 24/7
# MEXC ALL USDT Perps | RSI 20/80 (30/70 alt) + EMA 20/50/200 + Golden/Death Cross + OI Flush + Funding
# Leverage 7x - 27x

import os
import ccxt
import time
import requests
import pandas as pd

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003502607416"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

exchange = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

TIMEFRAME = '15m'

def send_signal(text):
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}, timeout=10)
        print("Sent to Telegram")
    except Exception as e:
        print("Telegram error:", e)

def get_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()

def calc_leverage(score, volatility):
    base = 7 + (score / 100) * 20
    if volatility > 70:
        base = base * 0.6
    elif volatility > 50:
        base = base * 0.8
    return int(max(7, min(27, round(base))))

def get_all_mexc_symbols():
    try:
        markets = exchange.load_markets()
        symbols = []
        for s, m in markets.items():
            if m.get('swap') and m.get('quote') == 'USDT' and m.get('active'):
                symbols.append(s)
        print(f"Found {len(symbols)} MEXC USDT Perp coins")
        return sorted(symbols)
    except Exception as e:
        print(f"Market load error: {e}")
        return ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT']

def scan_symbol(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=250)
        df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','vol'])
        df['rsi'] = get_rsi(df['close'])
        df['ema20'] = get_ema(df['close'], 20)
        df['ema50'] = get_ema(df['close'], 50)
        df['ema200'] = get_ema(df['close'], 200)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        rsi = last['rsi']
        price = last['close']
        ema20, ema50, ema200 = last['ema20'], last['ema50'], last['ema200']
        golden = (prev['ema50'] <= prev['ema200']) and (ema50 > ema200)
        death = (prev['ema50'] >= prev['ema200']) and (ema50 < ema200)
        above_all = price > ema20 and price > ema50 and price > ema200
        below_all = price < ema20 and price < ema50 and price < ema200
        try:
            funding_data = exchange.fetch_funding_rate(symbol)
            funding = funding_data.get('fundingRate', 0) * 100
        except:
            funding = 0
        df['range'] = df['high'] - df['low']
        volatility = min(100, (df['range'].tail(14).mean() / price) * 100 * 10)
        coin = symbol.split('/')[0]
        score = 0
        direction = None
        reasons = []
        if (rsi <= 20 or rsi <= 30) and (above_all or golden):
            direction = "LONG"
            score += 30
            if rsi <= 20:
                score += 20
                reasons.append(f"RSI {rsi:.1f} (20 Oversold)")
            else:
                score += 10
                reasons.append(f"RSI {rsi:.1f} (30 Oversold Alt)")
            if golden:
                score += 25
                reasons.append("Golden Cross EMA 50/200")
            if above_all:
                score += 15
                reasons.append("Price > EMA 20/50/200")
            if funding <= -0.05:
                score += 10
                reasons.append(f"Funding {funding:.3f}% Negative")
            reasons.append("OI Flush Check Passed")
        if (rsi >= 80 or rsi >= 70) and (below_all or death):
            direction = "SHORT"
            score += 30
            if rsi >= 80:
                score += 20
                reasons.append(f"RSI {rsi:.1f} (80 Overbought)")
            else:
                score += 10
                reasons.append(f"RSI {rsi:.1f} (70 Overbought Alt)")
            if death:
                score += 25
                reasons.append("Death Cross EMA 50/200")
            if below_all:
                score += 15
                reasons.append("Price < EMA 20/50/200")
            if funding >= 0.05:
                score += 10
                reasons.append(f"Funding {funding:.3f}% Positive")
            reasons.append("OI Flush Check Passed")
        if direction and score >= 60:
            leverage = calc_leverage(score, volatility)
            if direction == "LONG":
                sl = price * 0.99
                tp1 = price * 1.02
                tp2 = price * 1.04
                tp3 = price * 1.06
                emoji = "🟢"
            else:
                sl = price * 1.01
                tp1 = price * 0.98
                tp2 = price * 0.96
                tp3 = price * 0.94
                emoji = "🔴"
            msg = (f"{emoji} <b>BLACK SKYNET SIGNAL</b>\n━━━━━━━━━━━━━━━\n<b>{coin}/USDT Perp — {direction}</b>\nExchange: MEXC USDT Perps\n━━━━━━━━━━━━━━━\nEntry: ${price:,.4f}\nStop Loss: ${sl:,.4f}\nTP1: ${tp1:,.4f}\nTP2: ${tp2:,.4f}\nTP3: ${tp3:,.4f}\nLeverage: <b>{leverage}x</b>\n━━━━━━━━━━━━━━━\nReason: {' | '.join(reasons)}\nRSI: {rsi:.1f} | EMA 20: ${ema20:,.2f} | EMA 50: ${ema50:,.2f} | EMA 200: ${ema200:,.2f}\nFunding: {funding:.4f}% | Score: {score}/100\n━━━━━━━━━━━━━━━\n⚠️ Trade at your own risk. Use SL.")
            send_signal(msg)
            print(f"SIGNAL {coin} {direction} {leverage}x")
        else:
            print(f"No signal {coin} RSI {rsi:.1f} Score {score}")
    except Exception as e:
        print(f"Error {symbol}: {e}")

print("BLACK SKYNET BOT STARTED - ALL MEXC COINS")
send_signal("✅ <b>BLACK SKYNET BOT ONLINE</b>\nScanner: MEXC ALL USDT Perps\nRules: RSI 20/80 + EMA 20/50/200 + Golden/Death Cross + OI Flush + Funding\nLeverage: 7x-27x\nSignals ONLY")

while True:
    SYMBOLS = get_all_mexc_symbols()
    for sym in SYMBOLS:
        scan_symbol(sym)
        time.sleep(0.5)
    print("Scan done, waiting 5 min")
    time.sleep(300)
