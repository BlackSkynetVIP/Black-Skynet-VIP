import os, threading, time
from flask import Flask
import ccxt
import requests
import pandas as pd

app = Flask(__name__)
@app.route('/')
def home():
    return "Black Skynet VIP V2.1 is running"
def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=keep_alive, daemon=True).start()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003502607416"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

exchange = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
TIMEFRAME = '15m'
last_signal_time = {}
last_oi = {}

def send_signal(text):
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}, timeout=10)
        print("Sent to Telegram")
    except Exception as e:
        print("Telegram error:", e)

def get_rsi_wilder(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def get_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()

def get_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def get_vwap(df):
    typical = (df['high'] + df['low'] + df['close']) / 3
    vwap = (typical * df['vol']).cumsum() / df['vol'].cumsum()
    return vwap

def calc_leverage_smart(score, volatility_pct, sl_pct):
    base = 7 + ((score - 60) / 40) * 13
    if volatility_pct > 8:
        base *= 0.55
    elif volatility_pct > 5:
        base *= 0.7
    elif volatility_pct > 3:
        base *= 0.85
    if sl_pct > 0:
        max_safe_lev = 65 / (sl_pct * 10)
        base = min(base, max_safe_lev)
    if score >= 92 and volatility_pct < 3 and sl_pct < 2.0:
        base = min(27, base + 7)
    lev = int(round(base))
    return max(7, min(27, lev))

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
        return ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT']

def scan_symbol(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=250)
        df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','vol'])
        if len(df) < 210:
            return
        df['rsi'] = get_rsi_wilder(df['close'])
        df['ema20'] = get_ema(df['close'], 20)
        df['ema50'] = get_ema(df['close'], 50)
        df['ema200'] = get_ema(df['close'], 200)
        df['atr'] = get_atr(df)
        df['vwap'] = get_vwap(df)
        last = df.iloc[-2]
        prev = df.iloc[-3]
        price = last['close']
        rsi = last['rsi']
        ema20, ema50, ema200 = last['ema20'], last['ema50'], last['ema200']
        vwap = last['vwap']
        atr = last['atr']
        atr_pct = (atr / price) * 100
        coin = symbol.split('/')[0]
        avg_vol = df['vol'].tail(20).mean()
        vol_ratio = last['vol'] / avg_vol if avg_vol > 0 else 0
        vol_ok = vol_ratio >= 1.15
        last20_high = df['high'].tail(20).max()
        last20_low = df['low'].tail(20).min()
        box_range = last20_high - last20_low
        box_pos = (price - last20_low) / box_range if box_range > 0 else 0.5
        in_chop = 0.35 < box_pos < 0.65 and atr_pct < 1.0
        golden = (prev['ema50'] <= prev['ema200']) and (ema50 > ema200)
        death = (prev['ema50'] >= prev['ema200']) and (ema50 < ema200)
        above_all = price > ema20 and price > ema50 and price > ema200
        below_all = price < ema20 and price < ema50 and price < ema200
        above_vwap = price > vwap
        below_vwap = price < vwap
        try:
            funding_data = exchange.fetch_funding_rate(symbol)
            funding = funding_data.get('fundingRate', 0) * 100
        except:
            funding = 0
        oi_change_pct = 0
        oi_flush = False
        try:
            oi_data = exchange.fetch_open_interest(symbol)
            oi_now = oi_data.get('openInterest', 0)
            if symbol in last_oi and last_oi[symbol] > 0:
                oi_change_pct = ((oi_now - last_oi[symbol]) / last_oi[symbol]) * 100
                if oi_change_pct < -3:
                    oi_flush = True
            last_oi[symbol] = oi_now
        except:
            oi_now = 0
        score = 0
        direction = None
        reasons = []
        if rsi <= 35 and (above_all or golden) and above_vwap:
            direction = "LONG"
            if rsi <= 20:
                score += 30; reasons.append(f"RSI {rsi:.1f} Extreme Oversold")
            elif rsi <= 25:
                score += 25; reasons.append(f"RSI {rsi:.1f} Oversold")
            else:
                score += 18; reasons.append(f"RSI {rsi:.1f} Oversold Alt")
            if golden:
                score += 25; reasons.append("Golden Cross EMA 50/200")
            if above_all:
                score += 15; reasons.append("Price > EMA 20/50/200")
            if above_vwap:
                score += 10; reasons.append("Price > VWAP")
            if funding <= -0.05:
                score += 10; reasons.append(f"Funding {funding:.3f}% Negative")
            if oi_flush:
                score += 10; reasons.append(f"OI Flush {oi_change_pct:.1f}%")
            if vol_ratio >= 1.5:
                score += 10; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
        if rsi >= 65 and (below_all or death) and below_vwap:
            direction = "SHORT"
            if rsi >= 80:
                score += 30; reasons.append(f"RSI {rsi:.1f} Extreme Overbought")
            elif rsi >= 75:
                score += 25; reasons.append(f"RSI {rsi:.1f} Overbought")
            else:
                score += 18; reasons.append(f"RSI {rsi:.1f} Overbought Alt")
            if death:
                score += 25; reasons.append("Death Cross EMA 50/200")
            if below_all:
                score += 15; reasons.append("Price < EMA 20/50/200")
            if below_vwap:
                score += 10; reasons.append("Price < VWAP")
            if funding >= 0.05:
                score += 10; reasons.append(f"Funding {funding:.3f}% Positive")
            if oi_flush:
                score += 10; reasons.append(f"OI Flush {oi_change_pct:.1f}%")
            if vol_ratio >= 1.5:
                score += 10; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
        if not direction:
            return
        if score < 62:
            print(f"No signal {coin} Score {score} low")
            return
        if not vol_ok:
            print(f"Skip {coin} Low Volume {vol_ratio:.2f}x")
            return
        if in_chop:
            print(f"Skip {coin} In BOX / Chop")
            return
        key = f"{coin}_{direction}"
        now = time.time()
        if key in last_signal_time and (now - last_signal_time[key]) < 4 * 3600:
            print(f"Skip {coin} Cooldown")
            return
        last_signal_time[key] = now
        if score >= 86 and atr_pct < 2.5 and vol_ratio >= 1.5 and (golden or death or oi_flush):
            tp_count = 6
            tp_label = "RUNNER - Trend Trade - Trail SL to TP6"
            tp_multipliers = [1.5, 2.5, 3.5, 4.5, 6.0, 8.0]
        elif score >= 73 and atr_pct < 4.0:
            tp_count = 4
            tp_label = "STANDARD - Day Trade"
            tp_multipliers = [1.5, 2.5, 3.5, 4.5]
        else:
            tp_count = 2
            tp_label = "QUICK SCALP - Take Profit Fast"
            tp_multipliers = [1.5, 2.5]
        if direction == "LONG":
            entry1 = price
            entry2 = price - (atr * 0.6)
            sl = price - (atr * 1.5)
            tps = [price + (atr * m) for m in tp_multipliers]
            emoji = "🟢"
        else:
            entry1 = price
            entry2 = price + (atr * 0.6)
            sl = price + (atr * 1.5)
            tps = [price - (atr * m) for m in tp_multipliers]
            emoji = "🔴"
        def pct(target):
            return ((target - entry1) / entry1) * 100
        sl_pct = abs(pct(sl))
        tp_pcts = [abs(pct(tp)) for tp in tps]
        volatility_pct = atr_pct * 2
        leverage = calc_leverage_smart(score, volatility_pct, sl_pct)
        if tp_count == 2:
            leverage = min(leverage, 12)
        def fmt(p):
            if p >= 100:
                return f"{p:,.2f}"
            elif p >= 1:
                return f"{p:,.4f}"
            else:
                return f"{p:,.6f}"
        tp_lines = ""
        for i, (tp_price, tp_pct) in enumerate(zip(tps, tp_pcts), start=1):
            tp_lines += f"• <b>TP{i}:</b> ${fmt(tp_price)} (+{tp_pct:.2f}%)\n"
        msg = (
            f"{emoji} <b>{coin} / USDT {direction} - {leverage}X</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎯 <b>{tp_label} - {tp_count} TPs</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• <b>Entry 1:</b> ${fmt(entry1)}\n"
            f"• <b>Entry 2 (Optional):</b> ${fmt(entry2)}\n"
            f"\n"
            f"• <b>SL:</b> ${fmt(sl)} (-{sl_pct:.2f}%)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{tp_lines}"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 <b>Score:</b> {score}/100 | <b>RSI:</b> {rsi:.1f} | <b>ATR:</b> {atr_pct:.2f}%\n"
            f"📊 <b>Vol:</b> {vol_ratio:.1f}x Avg | <b>Funding:</b> {funding:.4f}% | <b>OI Chg:</b> {oi_change_pct:.1f}%\n"
            f"📊 <b>Reason:</b> {' | '.join(reasons)}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• <b>All Trades is Trailing TP - Follow price with SL !!</b>\n"
            f"• <b>NFA / DYOR</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚠️ Trade at your own risk. Use SL. | BLACK SKYNET VIP"
        )
        send_signal(msg)
        print(f"SIGNAL {coin} {direction} {leverage}x {tp_count}TP Score {score}")
    except Exception as e:
        print(f"Error {symbol}: {e}")

print("BLACK SKYNET V2.1 BOT STARTED - ALL MEXC COINS")
send_signal("✅ <b>BLACK SKYNET V2.1 BOT ONLINE</b>\nScanner: MEXC ALL USDT Perps\nSystem: RSI Wilder + EMA 20/50/200 + VWAP + ATR + Volume + OI + Funding + BOX Filter\nLeverage: Smart 7x-27x Risk Managed\nTP System: Dynamic 2 / 4 / 6 TP - BOT Decides Best\nSignals ONLY - Trailing TP")

while True:
    try:
        SYMBOLS = get_all_mexc_symbols()
        for sym in SYMBOLS:
            scan_symbol(sym)
            time.sleep(0.35)
        print("Scan done, waiting 5 min")
        time.sleep(300)
    except Exception as e:
        print(f"Main loop error: {e}")
        time.sleep(60)
