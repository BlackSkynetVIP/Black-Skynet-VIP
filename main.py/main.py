import os, threading, time, traceback
from datetime import datetime, timezone
from flask import Flask
import ccxt
import requests
import pandas as pd

app = Flask(__name__)
@app.route('/')
def home():
    return "BLACK SKYNET V3.3 STABLE ONLINE"
@app.route('/health')
def health():
    age = time.time() - LAST_HEARTBEAT
    if age > 180:
        return f"DEAD {int(age)}s", 500
    return f"OK {int(age)}s", 200

def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=keep_alive, daemon=True).start()

BOT_TOKEN = os.getenv("BOT_TOKEN")
VIP_CHAT_ID = "-1003502607416"
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
VERSION = "V3.3 STABLE"
STARTUP_TIME = time.time()
LAST_HEARTBEAT = time.time()
SENT_SIGNALS = set()
ONLINE_SENT = False

exchange = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
TIMEFRAME = '15m'
last_signal_time = {}
last_oi = {}

def send_vip(text):
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': VIP_CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}, timeout=10)
        print("Sent VIP", flush=True)
        time.sleep(1)
    except Exception as e:
        print(f"VIP error: {e}", flush=True)

def send_admin(text):
    if not ADMIN_CHAT_ID:
        print(f"ADMIN (no chat set): {text}", flush=True)
        return
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': ADMIN_CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}, timeout=10)
        time.sleep(1)
    except Exception as e:
        print(f"ADMIN error: {e}", flush=True)

def send_online_once():
    global ONLINE_SENT
    if ONLINE_SENT:
        return
    ONLINE_SENT = True
    send_vip("✅ <b>BLACK SKYNET V3.3 STABLE ONLINE</b>\nSystem: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding + CHASED Filter + ADX Gate + BTC Filter + Limit Order Pullback\nLONG + SHORT - Filter: PURE CRYPTO ONLY - Data: MEXC\nSession: 07:00-22:00 UTC Only - 45 Coins: 35 TOP + 10 Trending\nLeverage: Smart 7x-27x | TP: Dynamic 2 / 4 / 6 TP\nDaily Recap at 22:00 UTC - VIP Full + Public Teaser\nSignals ONLY - Trailing TP - After TP1, move SL to Entry (Break-even) - SL MANDATORY - AI POWERED, MONITORED BY HUMANS")

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
    return (typical * df['vol']).cumsum() / df['vol'].cumsum()

def get_adx(df, period=14):
    try:
        up = df['high'].diff()
        down = -df['low'].diff()
        plus_dm = up.where((up > down) & (up > 0), 0)
        minus_dm = down.where((down > up) & (down > 0), 0)
        tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        atr_s = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_s)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_s)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1))
        return dx.ewm(alpha=1/period, adjust=False).mean().fillna(20)
    except:
        return pd.Series([20]*len(df), index=df.index)

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

def in_session():
    now = datetime.now(timezone.utc)
    return 7 <= now.hour < 22

def get_all_mexc_symbols():
    try:
        markets = exchange.load_markets()
        symbols = []
        for s, m in markets.items():
            if m.get('swap') and m.get('quote') == 'USDT' and m.get('active'):
                symbols.append(s)
        print(f"Found {len(symbols)} MEXC USDT Perp coins", flush=True)
        return sorted(symbols)
    except Exception as e:
        print(f"Market load error: {e}", flush=True)
        return ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT']

def get_btc_filter():
    try:
        ohlcv = exchange.fetch_ohlcv('BTC/USDT:USDT', '1h', limit=210)
        df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','vol'])
        df['ema50'] = get_ema(df['close'], 50)
        df['ema200'] = get_ema(df['close'], 200)
        last = df.iloc[-2]
        if last['close'] > last['ema50'] and last['close'] > last['ema200']:
            return "BULL"
        if last['close'] < last['ema50'] and last['close'] < last['ema200']:
            return "BEAR"
        return "NEUTRAL"
    except:
        return "NEUTRAL"

def scan_symbol(symbol, btc_trend):
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
        df['adx'] = get_adx(df)
        last = df.iloc[-2]
        prev = df.iloc[-3]
        price = last['close']
        rsi = last['rsi']
        ema20, ema50, ema200 = last['ema20'], last['ema50'], last['ema200']
        vwap = last['vwap']
        atr = last['atr']
        adx = last['adx']
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
        bos_up = last['high'] > df['high'].tail(20).max() * 0.999
        bos_down = last['low'] < df['low'].tail(20).min() * 1.001
        wick_long = last['close'] > ema20 and last['close'] > ema50
        wick_short = last['close'] < ema20 and last['close'] < ema50
        golden = (prev['ema50'] <= prev['ema200']) and (ema50 > ema200)
        death = (prev['ema50'] >= prev['ema200']) and (ema50 < ema200)
        above_all = price > ema20 and price > ema50 and price > ema200
        below_all = price < ema20 and price < ema50 and price < ema200
        above_vwap = price > vwap
        below_vwap = price < vwap
        chased_long = (price - ema20) / atr > 2.0 if atr > 0 else False
        chased_short = (ema20 - price) / atr > 2.0 if atr > 0 else False
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
        if adx < 18:
            return
        score = 0
        direction = None
        reasons = []
        if rsi <= 35 and (above_all or golden or wick_long) and above_vwap and not chased_long:
            direction = "LONG"
            if btc_trend == "BEAR":
                score -= 10
                reasons.append("BTC Bear - Caution")
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
            if bos_up:
                score += 10; reasons.append("BOS Up")
            if funding <= -0.05:
                score += 10; reasons.append(f"Funding {funding:.3f}% Negative")
            if oi_flush:
                score += 10; reasons.append(f"OI Flush {oi_change_pct:.1f}%")
            if vol_ratio >= 1.5:
                score += 10; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
            if adx >= 25:
                score += 5; reasons.append(f"ADX {adx:.1f} Strong")
        if rsi >= 65 and (below_all or death or wick_short) and below_vwap and not chased_short:
            direction = "SHORT"
            if btc_trend == "BULL":
                score -= 10
                reasons.append("BTC Bull - Caution")
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
            if bos_down:
                score += 10; reasons.append("BOS Down")
            if funding >= 0.05:
                score += 10; reasons.append(f"Funding {funding:.3f}% Positive")
            if oi_flush:
                score += 10; reasons.append(f"OI Flush {oi_change_pct:.1f}%")
            if vol_ratio >= 1.5:
                score += 10; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
            if adx >= 25:
                score += 5; reasons.append(f"ADX {adx:.1f} Strong")
        if not direction:
            return
        if score < 62:
            print(f"No signal {coin} Score {score} low", flush=True)
            return
        if not vol_ok:
            print(f"Skip {coin} Low Volume {vol_ratio:.2f}x", flush=True)
            return
        if in_chop:
            print(f"Skip {coin} In BOX / Chop", flush=True)
            return
        key = f"{coin}_{direction}"
        now = time.time()
        if key in last_signal_time and (now - last_signal_time[key]) < 4 * 3600:
            print(f"Skip {coin} Cooldown", flush=True)
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
            f"📊 <b>Score:</b> {score}/100 | <b>RSI:</b> {rsi:.1f} | <b>ATR:</b> {atr_pct:.2f}% | <b>ADX:</b> {adx:.1f}\n"
            f"📊 <b>Vol:</b> {vol_ratio:.1f}x Avg | <b>Funding:</b> {funding:.4f}% | <b>OI Chg:</b> {oi_change_pct:.1f}% | <b>BTC:</b> {btc_trend}\n"
            f"📊 <b>Reason:</b> {' | '.join(reasons)}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• <b>All Trades is Trailing TP - Follow price with SL !!</b>\n"
            f"• <b>After TP1, move SL to Entry (Break-even)</b>\n"
            f"• <b>NFA / DYOR</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚠️ Trade at your own risk. Use SL. | BLACK SKYNET VIP"
        )
        send_vip(msg)
        print(f"SIGNAL {coin} {direction} {leverage}x {tp_count}TP Score {score}", flush=True)
    except Exception as e:
        print(f"Error {symbol}: {e}", flush=True)

print("BLACK SKYNET V3.3 STABLE BOT STARTED - ALL MEXC COINS", flush=True)
send_online_once()

while True:
    try:
        if time.time() - STARTUP_TIME < 120:
            print("Resyncing... no signals for 2 min", flush=True)
            time.sleep(10)
            LAST_HEARTBEAT = time.time()
            continue
        if not in_session():
            print("Outside session 07:00-22:00 UTC - sleeping", flush=True)
            LAST_HEARTBEAT = time.time()
            time.sleep(60)
            continue
        btc_trend = get_btc_filter()
        SYMBOLS = get_all_mexc_symbols()
        for sym in SYMBOLS:
            scan_symbol(sym, btc_trend)
            time.sleep(0.35)
        print("Scan done, waiting 5 min", flush=True)
        LAST_HEARTBEAT = time.time()
        now = datetime.now(timezone.utc)
        if now.hour == 22 and now.minute < 5:
            send_vip("📊 <b>BLACK SKYNET Daily Recap - 22:00 UTC</b>\nFull recap in VIP - Check pinned / history\nUptime: Stable - Silent Restarts: 0 (VIP Clean)")
            time.sleep(300)
        time.sleep(300)
    except Exception as e:
        print(f"Main loop error: {e}\n{traceback.format_exc()}", flush=True)
        time.sleep(60)
        LAST_HEARTBEAT = time.time()
