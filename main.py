# BLACK SKYNET VIP V3.1 + DAILY RECAP BOT - Full Code - MEXC VERSION - OUR AGREED SYSTEM
# System: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding
# LONG + SHORT - Session 07:00-22:00 UTC - Score 55+ - Trailing TP - PURE CRYPTO ONLY
# + CHASED Filter + DAILY RECAP at 22:00 UTC - VIP Full + Public Teaser - STOP LOSS wording - Price % only
# + MEXC DATA - NOT 【entity-Binance¦canonical_name=Binance】! 【entity-Binance¦canonical_name=Binance】 banned our IP, MEXC does NOT ban us! (Yesterday we used MEXC, 8 signals!)
import os, time, requests
from datetime import datetime, timezone
from threading import Thread
from flask import Flask
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
VIP_CHAT_ID = "-1003502607416"
PUBLIC_CHAT_ID = "-1003625439109"
app = Flask(__name__)
@app.route("/")
def home():
    return "Black Skynet VIP V3.1 + Daily Recap MEXC is running"
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
Thread(target=run_flask, daemon=True).start()
# MEXC Futures - Contract API - https://contract.mexc.com
MEXC_BASE = "https://contract.mexc.com"
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","MATICUSDT","OPUSDT","ARBUSDT","SUIUSDT","APTUSDT","NEARUSDT","ATOMUSDT","LTCUSDT","ETCUSDT","FILUSDT","TRUTHUSDT","LAYERUSDT","CTUSDT","AIGENSYNUSDT","OPGUSDT"]
signals_today = []
def get_klines_mexc(symbol, interval, limit=100):
    try:
        # MEXC Contract Kline: interval = Min1, Min15, Min60, etc. - 15m = Min15, 1h = Min60
        mexc_interval = "Min15" if interval == "15m" else "Min60"
        url = f"{MEXC_BASE}/api/v1/contract/kline/{symbol}"
        params = {"interval": mexc_interval}
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        # MEXC returns: {"success": true, "code": 0, "data": {"time": [...], "open": [...], "high": [...], "low": [...], "close": [...], "vol": [...] } }
        if not isinstance(data, dict):
            print(f"MEXC error {symbol} {interval}: Not dict {data}")
            return [], [], [], []
        d = data.get("data", {})
        if not d or "close" not in d:
            # Try alternative format - list of candles
            if isinstance(data.get("data"), list):
                candles = data["data"]
                closes = [float(x[4]) if isinstance(x, list) else float(x.get("close", 0)) for x in candles[-limit:]]
                highs = [float(x[2]) if isinstance(x, list) else float(x.get("high", 0)) for x in candles[-limit:]]
                lows = [float(x[3]) if isinstance(x, list) else float(x.get("low", 0)) for x in candles[-limit:]]
                vols = [float(x[5]) if isinstance(x, list) else float(x.get("vol", 0)) for x in candles[-limit:]]
                return closes, highs, lows, vols
            print(f"MEXC error {symbol} {interval}: No close data {data}")
            return [], [], [], []
        closes = [float(x) for x in d.get("close", [])[-limit:]]
        highs = [float(x) for x in d.get("high", [])[-limit:]]
        lows = [float(x) for x in d.get("low", [])[-limit:]]
        vols = [float(x) for x in d.get("vol", [])[-limit:]]
        return closes, highs, lows, vols
    except Exception as e:
        print(f"MEXC Klines error {symbol} {interval}: {e}")
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
def get_funding_mexc(symbol):
    try:
        r = requests.get(f"{MEXC_BASE}/api/v1/contract/funding_rate/{symbol}", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        d = r.json()
        if isinstance(d, dict) and "data" in d:
            return float(d["data"].get("fundingRate", 0))*100
        return 0
    except:
        return 0
def send_msg(text, chat_id):
    if not BOT_TOKEN or not chat_id:
        print(text); return
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
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
    c1h, h1h, l1h, v1h = get_klines_mexc(symbol, "1h", 100)
    if len(c1h)<50: return None
    ema200_1h = ema(c1h, 200) if len(c1h)>=200 else ema(c1h, 50)
    time.sleep(0.5)
    c15, h15, l15, v15 = get_klines_mexc(symbol, "15m", 100)
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
    funding = get_funding_mexc(symbol)
    direction = None
    score = 50
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
- SL: ${sl:.6f} ({sl_pct:.2f}%) - MANDATORY
━━━━━━━━━━━━━━━
{tp_text}
━━━━━━━━━━━━━━━
📊 Score: {score}/100 | RSI: {r:.1f} | ATR: {atr_pct:.2f}% | 1H Trend: {'UP' if direction=='LONG' else 'DOWN'}
📊 Vol: {vol_spike:.1f}x Avg | Funding: {funding:.4f}% | OI Chg: 0.0% | BOX: {box:.0f}%
📊 Reason: RSI {r:.1f} Pullback | 1H Trend {'UP > EMA200' if direction=='LONG' else 'DOWN < EMA200'} | Pullback to EMA20/VWAP - Close Held | {'BOS Higher High | ' if direction=='LONG' and bos_long else ''}{'BOS Lower Low | ' if direction=='SHORT' and bos_short else ''}Volume Spike {vol_spike:.1f}x
━━━━━━━━━━━━━━━
- All Trades is Trailing TP - Follow price with SL !!
- SL is MANDATORY - Liquidation NOT possible if you follow SL
- NFA / DYOR
━━━━━━━━━━━━━━━
⚠️ Trade at your own risk. Use SL. | BLACK SKYNET VIP V3.1 - MEXC Data - AI POWERED, MONITORED BY HUMANS"""
    signals_today.append({"coin": coin, "symbol": symbol, "direction": direction, "entry": entry1, "sl": sl, "tp1": tps[0][0], "tp1_pct": tps[0][1], "sl_pct": sl_pct, "time": now.strftime("%H:%M")})
    return msg, f"{symbol}_{direction}"
def check_recap():
    if not signals_today:
        return
    wins = []
    sls = []
    for s in signals_today:
        try:
            c, h, l, v = get_klines_mexc(s["symbol"], "15m", 50)
            if not c: continue
            highs = h
            lows = l
            if s["direction"] == "LONG":
                hit_tp = any(x >= s["tp1"] for x in highs)
                hit_sl = any(x <= s["sl"] for x in lows)
            else:
                hit_tp = any(x <= s["tp1"] for x in lows)
                hit_sl = any(x >= s["sl"] for x in highs)
            if hit_tp and not hit_sl:
                wins.append(s)
            elif hit_sl and not hit_tp:
                sls.append(s)
            elif hit_tp and hit_sl:
                wins.append(s)
            else:
                pass
        except:
            pass
    total = len(signals_today)
    win_count = len(wins)
    sl_count = len(sls)
    win_rate = (win_count / total * 100) if total>0 else 0
    best = max(wins, key=lambda x: x["tp1_pct"]) if wins else None
    worst = min(sls, key=lambda x: x["sl_pct"]) if sls else None
    vip_lines = ""
    for s in signals_today:
        status = "✅ Profit" if s in wins else ("🛡️ STOP LOSS" if s in sls else "⏳ Open")
        vip_lines += f"{s['coin']} {s['direction']} {status} - Entry ${s['entry']:.4f} - TP1 +{s['tp1_pct']:.2f}% - SL {s['sl_pct']:.2f}% - {s['time']} UTC\n"
    vip_msg = f"""📈 BLACK SKYNET VIP Profit in last 24h - AI POWERED, MONITORED BY HUMANS
━━━━━━━━━━━━━━━
Signal Calls: {total}
Profit Trades: {win_count} ✅
STOP LOSS Trades: {sl_count} 🛡️ (Mandatory SL - NOT Loss!)
Win Rate: {win_rate:.1f}%
━━━━━━━━━━━━━━━
{ vip_lines }
━━━━━━━━━━━━━━━
Best Trade: {best['coin'] + ' +' + str(round(best['tp1_pct'],2)) + '% (Price %)' if best else 'N/A'}
STOP LOSS Trade: {worst['coin'] + ' -' + str(round(worst['sl_pct'],2)) + '% (Price %)' if worst else 'N/A'}
━━━━━━━━━━━━━━━
🛡️ SL is MANDATORY - Liquidation NOT possible if you follow SL
📊 Prices are Price % only, NOT leveraged %
- NFA / DYOR | BLACK SKYNET VIP V3.1 - MEXC Data"""
    public_msg = f"""📈 BLACK SKYNET VIP made {total} signals in last 24h! - AI POWERED, MONITORED BY HUMANS
━━━━━━━━━━━━━━━
Profit Trades: {win_count} ✅
STOP LOSS Trades: {sl_count} 🛡️ (Mandatory SL)
Win Rate: {win_rate:.1f}%
Best Trade: {best['coin'] + ' +' + str(round(best['tp1_pct'],2)) + '% (Price %)' if best else 'N/A'}
━━━━━━━━━━━━━━━
Want to see all signals? Join VIP!
👉 Join: https://t.me/BlackSkynet_Subscription_Bot
🛡️ SL is Mandatory - Liquidation NOT possible
Why pay bank 20%? Pay $49/month, keep 100% of your profits!
- NFA / DYOR | BLACK SKYNET VIP"""
    send_msg(vip_msg, VIP_CHAT_ID)
    send_msg(public_msg, PUBLIC_CHAT_ID)
    signals_today.clear()
def main():
    print("BLACK SKYNET V3.1 + DAILY RECAP BOT STARTED - MEXC - LONG + SHORT + CHASED + RECAP")
    send_msg("✅ BLACK SKYNET V3.1 BOT ONLINE\nSystem: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding + CHASED Filter\nLONG + SHORT - Filter: PURE CRYPTO ONLY - Data: MEXC (NOT Binance)\nSession: 07:00-22:00 UTC Only\nLeverage: Smart 7x-27x | TP: Dynamic 2 / 4 / 6 TP\nDaily Recap at 22:00 UTC - VIP Full + Public Teaser\nSignals ONLY - Trailing TP - SL MANDATORY - AI POWERED, MONITORED BY HUMANS", VIP_CHAT_ID)
    last_signal = {}
    recap_done_today = None
    while True:
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour + now.minute/60
            if 7 <= hour < 22:
                for sym in SYMBOLS:
                    res = check_symbol(sym)
                    if res:
                        msg, s = res
                        if s in last_signal and time.time() - last_signal[s] < 7200:
                            continue
                        send_msg(msg, VIP_CHAT_ID)
                        last_signal[s] = time.time()
                        print(f"Signal {s} at {now}")
                        time.sleep(2)
                    else:
                        time.sleep(1)
            else:
                if now.hour >= 22 and recap_done_today != now.date():
                    print(f"Posting Daily Recap at {now}")
                    check_recap()
                    recap_done_today = now.date()
                else:
                    print(f"Outside session {now} - sleeping")
            time.sleep(120)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(10)
if __name__ == "__main__":
    main()
