import os
import time
import threading
import requests
import ccxt
import pandas as pd
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# If you use group chat, CHAT_ID is your group ID. If DM, your user ID.

app = Flask(__name__)

# 15 COINS ONLY - NO ETH, NO DOGE, NO PEPE
SYMBOLS = ['BTC/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT','LINK/USDT:USDT','AVAX/USDT:USDT','SUI/USDT:USDT','NEAR/USDT:USDT','APT/USDT:USDT','ARB/USDT:USDT','TON/USDT:USDT','OP/USDT:USDT','INJ/USDT:USDT','ZEC/USDT:USDT','TRX/USDT:USDT','BNB/USDT:USDT']

exchange = ccxt.mexc({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def check_symbol(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=250)
        df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
        df['rsi'] = get_rsi(df['close'])
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        coin = symbol.split('/')[0]

        # GOLDEN CROSS: EMA50 crosses above EMA200
        if prev['ema50'] < prev['ema200'] and last['ema50'] >= last['ema200']:
            send_telegram(f"🟢 *GOLDEN CROSS - {coin}*\nEMA50 crossed above EMA200\nPrice: {last['close']}\nRSI: {round(last['rsi'],1)}")
            return

        # DEATH CROSS: EMA50 crosses below EMA200
        if prev['ema50'] > prev['ema200'] and last['ema50'] <= last['ema200']:
            send_telegram(f"🔴 *DEATH CROSS - {coin}*\nEMA50 crossed below EMA200\nPrice: {last['close']}\nRSI: {round(last['rsi'],1)}")
            return

        # RSI OVERSOLD + Price above EMA50 = LONG
        if last['rsi'] <= 20 and last['close'] > last['ema50']:
            send_telegram(f"🟢 *LONG SIGNAL - {coin}*\nRSI Oversold: {round(last['rsi'],1)}\nPrice: {last['close']} above EMA50\nMEXC USDT Perp")
            return

        # RSI OVERBOUGHT + Price below EMA50 = SHORT
        if last['rsi'] >= 80 and last['close'] < last['ema50']:
            send_telegram(f"🔴 *SHORT SIGNAL - {coin}*\nRSI Overbought: {round(last['rsi'],1)}\nPrice: {last['close']} below EMA50\nMEXC USDT Perp")
            return

        print(f"{coin}: RSI {round(last['rsi'],1)} - No signal")

    except Exception as e:
        print(f"Error {symbol}: {e}")

def bot_loop():
    print("BLACK SKYNET BOT STARTED")
    send_telegram("✅ *BLACK SKYNET BOT ONLINE*\nMEXC USDT Perps | RSI 20/80 + EMA 50/200\n15 Coins: BTC, SOL, XRP, LINK, AVAX, SUI, NEAR, APT, ARB, TON, OP, INJ, ZEC, TRX, BNB\nNo ETH / DOGE / PEPE")
    while True:
        for sym in SYMBOLS:
            check_symbol(sym)
            time.sleep(2)
        print("Scan done, waiting 5 min...")
        time.sleep(300)

@app.route('/')
def home():
    return "BLACK SKYNET BOT IS RUNNING - 15 COINS"

@app.route('/health')
def health():
    return "OK"

if __name__ == '__main__':
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
