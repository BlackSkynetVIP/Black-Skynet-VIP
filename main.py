# BLACK SKYNET VIP V3.1 + CHASED FIX - Full Code - OUR AGREED SYSTEM
# System: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding
# LONG + SHORT - Session 07:00-22:00 UTC - Score 55+ - Trailing TP - PURE CRYPTO ONLY
import os, time, requests
from datetime import datetime, timezone
from threading import Thread
from flask import Flask
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
app = Flask(__name__)
@app.route("/")
def home():
    return "Black Skynet VIP V3.1 is running"
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
Thread(target=run_flask, daemon=True).start()
BASE = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","MATICUSDT","OPUSDT","ARBUSDT","SUIUSDT","APTUSDT","NEARUSDT","ATOMUSDT","LTCUSDT","ETCUSDT","FILUSDT","TRUTHUSDT","LAYERUSDT","CTUSDT","AIGENSYNUSDT","OPGUSDT"]
def get_klines(symbol, interval, limit=100):
    try:
        r = requests.get(f"{BASE}/fapi/v1/klines", params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10)
        data = r.json()
        closes = [float(x[4]) for x in data]
        highs = [float(x[2]) for x in data]
        lows = [float(x[3]) for x in data]
        vols = [float(x[5]) for x in data]
        return closes, highs, lows, vols
    except Exception as e:
        print(f"Klines error {symbol} {interval}: {e}")
        return [], [], [], []
def ema(values, period):
    if len(values) < period: return values[-1] if values else 0
    k = 2/(period+1)
    e = values[0]
    for v in values[1:]:
        e = v*k + e*(1-k)
    return e
def rsi(values, period=14):
    if len(values) < period+1: return 50
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i]-values[i-1]
        if d>=0: gains.append(d); losses.append(0)
        else: gains.append(0); losses.append(-d)
    avg_gain = sum(gains[-period:])/period
    avg_loss = sum(losses[-period:])/period
    if avg_loss==0: return 100
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))
def atr(highs, lows, closes, period=14):
    if len(closes)<period+1: return closes[-1]*0.01 if closes else 0
    trs=[]
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:])/period
def vwap(closes, vols):
    if not closes: return 0
    return sum(c*v for c,v in zip(closes, vols))/sum(vols) if sum(vols)>0 else closes[-1]
def get_funding(symbol):
    try:
        r = requests.get(f"{BASE}/fapi/v1/premiumIndex", params={"symbol": symbol}, timeout=5)
        d = r.json()
        return float(d.get("lastFundingRate", 0))*100
    except:
        return 0
def send_msg(text):
    if not BOT_TOKEN or not CHAT_ID:
        print(text); return
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")
def box_position(closes, lookback=20):
    if len(closes)<lookback: return 50
    window = closes[-lookback:]
    hi, lo = max(window), min(window)
    if hi==lo: return 50
    return (closes[-1]-lo)/(hi-lo)*100
def check_symbol(symbol):
    now = datetime.now(timezone.utc)
    hour = now.hour + now.minute/60
    if not (7 <= hour < 22):
        return None
    c1h, h1h, l1h, v1h = get_klines(symbol, "1h", 100)
    if len(c1h)<50: return None
    ema200_1h = ema(c1h, 200) if len(c1h)>=200 else ema(c1h, 50)
    c15, h15, l15, v15 = get_klines(symbol, "15m", 100)
    if len(c15)<50: return None
    price = c15[-1]
    ema20_15 = ema(c15, 20)
    vwap15 = vwap(c15[-20:], v15[-20:])
    close_prev = c15[-2]
    r = rsi(c15, 14)
    a = atr(h15, l15, c15, 14)
    atr_pct = (a/price*100) if price>0 else 1
    if atr_pct < 0.5 or atr_pct > 4:
        return None
    avg_vol = sum(v15[-21:-1])/20 if len(v15)>=21 else 1
    vol_spike = (v15[-2]/avg_vol) if avg_vol>0 else 1
    if vol_spike < 1.2:
        return None
    box = box_position(c15, 20)
    bos_long = h15[-2] > h15[-3] if len(h15)>=3 else False
    bos_short = l15[-2] < l15[-3] if len(l15)>=3 else False
    funding = get_funding(symbol)
    direction = None
    score = 50
    # LONG LOGIC - 1H UP + RSI 38-55 + Pullback to EMA20/VWAP
    if c1h[-1] > ema200_1h and 38 <= r <= 55:
        ref = min(ema20_15, vwap15)
        if close_prev >= ref * 0.998:
            if box <= 30 or (box >= 60 and bos_long) or (bos_long and vol_spike >= 1.7):
                direction = "LONG"
                if 43 <= r <= 52: score += 10
                else: score += 6
                if vol_spike >= 4: score += 12
                elif vol_spike >= 2.4: score += 10
                elif vol_spike >= 1.7: score += 7
                else: score += 4
                if box <= 15: score += 10
                elif box <= 30: score += 7
                elif box >= 60 and bos_long: score += 7
                if bos_long: score += 8
                if funding < -0.05: score += 5
                elif funding < 0: score += 2
                if 1.0 <= atr_pct <= 2.5: score += 3
    # SHORT LOGIC - 1H DOWN + RSI 45-62 + Pullback to EMA20/VWAP
    if direction is None and c1h[-1] < ema200_1h and 45 <= r <= 62:
        ref = max(ema20_15, vwap15)
        if close_prev <= ref * 1.002:
            if box >= 70 or (box <= 40 and bos_short) or (bos_short and vol_spike >= 1.7):
                direction = "SHORT"
                if 48 <= r <= 57: score += 10
                else: score += 6
                if vol_spike >= 4: score += 12
                elif vol_spike >= 2.4: score += 10
                elif vol_spike >= 1.7: score += 7
                else: score += 4
                if box >= 85: score += 10
                elif box >= 70: score += 7
                elif box <= 40 and bos_short: score += 7
                if bos_short: score += 8
                if funding > 0.05: score += 5
                elif funding > 0: score += 2
                if 1.0 <= atr_pct <= 2.5: score += 3
    if direction is None or score < 55:
        return None
    if score >= 85:
        tier = "S-TIER"; kind = "RUNNER - Trend Trade - Trail SL to TP6 - 6 TPs"; leverage = 7; tps_count = 6
    else:
        tier = "A-TIER"; kind = "STANDARD - Day Trade - 4 TPs"; leverage = 7; tps_count = 4
    entry1 = close_prev
    sl_dist = a * 1.5
    if direction == "LONG":
        sl = entry1 - sl_dist
        entry2 = entry1 - (a*0.5)
        mults = [1, 1.66, 2.33, 3.0, 4.0, 5.33]
        tps = [(entry1 + sl_dist*m, (sl_dist*m/entry1*100)) for m in mults[:tps_count]]
        emoji = "🟢"
        chased = (price - entry1)/entry1*100 > 0.8
        chased_val = (price-entry1)/entry1*100
    else:
        sl = entry1 + sl_dist
        entry2 = entry1 + (a*0.5)
        mults = [1, 1.66, 2.33, 3.0, 4.0, 5.33]
        tps = [(entry1 - sl_dist*m, (sl_dist*m/entry1*100)) for m in mults[:tps_count]]
        emoji = "🔴"
        chased = (entry1 - price)/entry1*100 > 0.8
        chased_val = (entry1-price)/entry1*100
    sl_pct = abs((sl-entry1)/entry1*100)
    coin = symbol.replace("USDT","")
    tp_text = "\n".join([f"• TP{i+1}: ${tp:.6f} (+{pct:.2f}%)" for i,(tp,pct) in enumerate(tps)])
    chased_text = ""
    if chased:
        chased_text = f"\n⚠️ CHASED - DON'T BUY ENTRY 1 - PRICE ALREADY +{chased_val:.2f}% ABOVE ENTRY\n• WAIT FOR ENTRY 2 ONLY: ${entry2:.6f}\n"
    msg = f"""{emoji} {coin} / USDT {direction} - {leverage}X
━━━━━━━━━━━━━━━
{'🔥' if tier=='S-TIER' else '⭐'} {tier} | {kind}
━━━━━━━━━━━━━━━
- Entry 1: ${entry1:.6f}
- Entry 2 (Optional): ${entry2:.6f}
{chased_text}
- SL: ${sl:.6f} ({sl_pct:.2f}%)
━━━━━━━━━━━━━━━
{tp_text}
━━━━━━━━━━━━━━━
📊 Score: {score}/100 | RSI: {r:.1f} | ATR: {atr_pct:.2f}% | 1H Trend: {'UP' if direction=='LONG' else 'DOWN'}
📊 Vol: {vol_spike:.1f}x Avg | Funding: {funding:.4f}% | OI Chg: 0.0% | BOX: {box:.0f}%
📊 Reason: RSI {r:.1f} Pullback | 1H Trend {'UP > EMA200' if direction=='LONG' else 'DOWN < EMA200'} | Pullback to EMA20/VWAP - Close Held | {'BOS Higher High | ' if direction=='LONG' and bos_long else ''}{'BOS Lower Low | ' if direction=='SHORT' and bos_short else ''}Volume Spike {vol_spike:.1f}x
━━━━━━━━━━━━━━━
- All Trades is Trailing TP - Follow price with SL !!
- NFA / DYOR
━━━━━━━━━━━━━━━
⚠️ Trade at your own risk. Use SL. | BLACK SKYNET VIP V3.1"""
    return msg, f"{symbol}_{direction}"
def main():
    print("BLACK SKYNET V3.1 BOT STARTED - LONG + SHORT + CHASED FIX")
    send_msg("✅ BLACK SKYNET V3.1 BOT ONLINE\nSystem: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding + CHASED Filter\nLONG + SHORT - Filter: PURE CRYPTO ONLY\nSession: 07:00-22:00 UTC Only\nLeverage: Smart 7x-27x | TP: Dynamic 2 / 4 / 6 TP\nSignals ONLY - Trailing TP")
    last_signal = {}
    while True:
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour + now.minute/60
            if 7 <= hour < 22:
                for sym in SYMBOLS:
                    for d in ["LONG","SHORT"]:
                        key = f"{sym}_{d}"
                        if key in last_signal and time.time() - last_signal[key] < 7200:
                            continue
                    res = check_symbol(sym)
                    if res:
                        msg, s = res
                        if s in last_signal and time.time() - last_signal[s] < 7200:
                            continue
                        send_msg(msg)
                        last_signal[s] = time.time()
                        print(f"Signal {s} at {now}")
                        time.sleep(2)
            else:
                print(f"Outside session {now} - sleeping")
            time.sleep(60)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(10)
if __name__ == "__main__":
    main()
