import os, threading, time
from flask import Flask
import ccxt
import requests
import pandas as pd
from datetime import datetime, timezone

app = Flask(__name__)
@app.route('/')
def home():
    return "Black Skynet VIP V3.1 Pure Crypto is running"
def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=keep_alive, daemon=True).start()

# ================= BLACK SKYNET V3.1 - PURE CRYPTO ONLY =================
# MTF: 1H Trend + 15m Entry | Wick-Tolerant EMA | BOX Edge | BOS | Soft OI/Funding | Session Filter | Pure Crypto Filter

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003502607416"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

exchange = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
TF_ENTRY = '15m'
TF_TREND = '1h'
last_signal_time = {}
last_oi = {}

# ================= PURE CRYPTO FILTER =================
# You + VIPs only deal in Crypto - NO stocks, ETFs, forex, commodities, stablecoins
EXCLUDE_KEYWORDS = ['STOCK', 'ETF', 'INDEX', 'FOREX', 'GOLD', 'SILVER', 'OIL', 'SPX', 'NASDAQ', 'DJI', 'EUR', 'JPY', 'GBP']
EXCLUDE_COINS = ['KRSTOCK', 'APPLSTOCK', 'TSLASTOCK', 'NVDASTOCK', 'USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USD1']
EXCLUDE_SUFFIXES = ['UP', 'DOWN', 'BULL', 'BEAR']  # Leveraged tokens like BTCUP, ETHDOWN

def is_pure_crypto(symbol):
    coin = symbol.split('/')[0].upper()
    if coin in EXCLUDE_COINS:
        return False
    for kw in EXCLUDE_KEYWORDS:
        if kw in coin:
            return False
    # Leveraged tokens: ends with UP/DOWN/BULL/BEAR and length > 4 (to avoid blocking real coins like UP)
    for suf in EXCLUDE_SUFFIXES:
        if coin.endswith(suf) and len(coin) > 5:
            return False
    return True

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
    return (100 - (100 / (1 + rs))).fillna(50)

def get_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()

def get_atr(df, period=14):
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def get_vwap(df):
    typ = (df['high'] + df['low'] + df['close']) / 3
    return (typ * df['vol']).cumsum() / df['vol'].cumsum()

def calc_leverage_smart(score, volatility_pct, sl_pct, tier):
    base = 7 + ((score - 55) / 45) * 13
    if volatility_pct > 8:
        base *= 0.55
    elif volatility_pct > 5:
        base *= 0.7
    elif volatility_pct > 3:
        base *= 0.85
    if sl_pct > 0:
        max_safe = 65 / (sl_pct * 10)
        base = min(base, max_safe)
    if tier == "S-TIER" and volatility_pct < 3 and sl_pct < 2.0:
        base = min(27, base + 7)
    if tier == "B-TIER":
        base = min(base, 12)
    return max(7, min(27, int(round(base))))

def get_all_mexc_symbols():
    try:
        markets = exchange.load_markets()
        syms = [s for s, m in markets.items() if m.get('swap') and m.get('quote') == 'USDT' and m.get('active') and is_pure_crypto(s)]
        print(f"Found {len(syms)} MEXC PURE CRYPTO Perp coins (filtered)")
        return sorted(syms)
    except Exception as e:
        print(f"Market load error: {e}")
        return ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT']

def in_trading_session():
    hour = datetime.now(timezone.utc).hour
    return 7 <= hour < 22

def scan_symbol(symbol):
    try:
        if not in_trading_session():
            return
        ohlcv_1h = exchange.fetch_ohlcv(symbol, TF_TREND, limit=250)
        ohlcv_15 = exchange.fetch_ohlcv(symbol, TF_ENTRY, limit=250)
        df1h = pd.DataFrame(ohlcv_1h, columns=['ts','open','high','low','close','vol'])
        df = pd.DataFrame(ohlcv_15, columns=['ts','open','high','low','close','vol'])
        if len(df) < 210 or len(df1h) < 210:
            return
        df1h['ema50'] = get_ema(df1h['close'], 50)
        df1h['ema200'] = get_ema(df1h['close'], 200)
        trend_last = df1h.iloc[-2]
        trend_prev = df1h.iloc[-3]
        htf_price = trend_last['close']
        htf_ema50, htf_ema200 = trend_last['ema50'], trend_last['ema200']
        golden_1h = (trend_prev['ema50'] <= trend_prev['ema200']) and (htf_ema50 > htf_ema200)
        death_1h = (trend_prev['ema50'] >= trend_prev['ema200']) and (htf_ema50 < htf_ema200)
        df['rsi'] = get_rsi_wilder(df['close'])
        df['ema20'] = get_ema(df['close'], 20)
        df['ema50'] = get_ema(df['close'], 50)
        df['ema200'] = get_ema(df['close'], 200)
        df['atr'] = get_atr(df)
        df['vwap'] = get_vwap(df)
        last = df.iloc[-2]
        prev = df.iloc[-3]
        prev2 = df.iloc[-4]
        price = last['close']
        rsi = last['rsi']
        rsi_prev = prev['rsi']
        ema20, ema50, ema200 = last['ema20'], last['ema50'], last['ema200']
        vwap = last['vwap']
        atr = last['atr']
        atr_pct = (atr / price) * 100
        coin = symbol.split('/')[0]
        if atr_pct < 0.4:
            return
        avg_vol = df['vol'].tail(20).mean()
        vol_ratio = last['vol'] / avg_vol if avg_vol > 0 else 0
        vol_ok = vol_ratio >= 1.2
        BUFFER = 0.0015
        htf_long_bias = htf_price > htf_ema200 * (1 - BUFFER)
        htf_short_bias = htf_price < htf_ema200 * (1 + BUFFER)
        near_ema20_long = abs(price - ema20) / price < 0.008 or (price > ema20 * (1 - BUFFER) and price < ema20 * 1.01)
        near_vwap_long = abs(price - vwap) / price < 0.008
        near_ema20_short = abs(price - ema20) / price < 0.008 or (price < ema20 * (1 + BUFFER) and price > ema20 * 0.99)
        near_vwap_short = abs(price - vwap) / price < 0.008
        bos_long = last['close'] > prev['high'] and prev['high'] > prev2['high']
        bos_short = last['close'] < prev['low'] and prev['low'] < prev2['low']
        last20_high = df['high'].tail(20).max()
        last20_low = df['low'].tail(20).min()
        box_range = last20_high - last20_low
        box_pos = (price - last20_low) / box_range if box_range > 0 else 0.5
        at_box_low = box_pos <= 0.20
        at_box_high = box_pos >= 0.80
        in_box_middle = 0.20 < box_pos < 0.80
        try:
            funding_data = exchange.fetch_funding_rate(symbol)
            funding = funding_data.get('fundingRate', 0) * 100
        except:
            funding = 0
        oi_change_pct = 0
        oi_soft = False
        try:
            oi_data = exchange.fetch_open_interest(symbol)
            oi_now = oi_data.get('openInterest', 0)
            if symbol in last_oi and last_oi[symbol] > 0:
                oi_change_pct = ((oi_now - last_oi[symbol]) / last_oi[symbol]) * 100
                if abs(oi_change_pct) > 2:
                    oi_soft = True
            last_oi[symbol] = oi_now
        except:
            pass
        score = 0
        direction = None
        reasons = []
        rsi_turning_up = rsi > rsi_prev
        if htf_long_bias and (38 <= rsi <= 55) and rsi_turning_up:
            if near_ema20_long or near_vwap_long or at_box_low or bos_long:
                if in_box_middle and not bos_long and not at_box_low:
                    pass
                else:
                    direction = "LONG"
                    if 43 <= rsi <= 52:
                        score += 28; reasons.append(f"RSI {rsi:.1f} Perfect Pullback")
                    else:
                        score += 20; reasons.append(f"RSI {rsi:.1f} Pullback")
                    if htf_price > htf_ema200:
                        score += 20; reasons.append("1H Trend UP > EMA200")
                    if golden_1h:
                        score += 15; reasons.append("Golden Cross 1H")
                    if near_ema20_long or near_vwap_long:
                        score += 12; reasons.append("Pullback to EMA20/VWAP - Close Held")
                    if bos_long:
                        score += 12; reasons.append("BOS Higher High")
                    if at_box_low:
                        score += 12; reasons.append(f"BOX LOW Edge ({box_pos*100:.0f}%)")
                    if vol_ratio >= 1.5:
                        score += 10; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
                    if funding <= -0.02:
                        score += 5; reasons.append(f"Funding {funding:.3f}% Soft Bearish")
                    if oi_soft and oi_change_pct < 0:
                        score += 5; reasons.append(f"OI Soft {oi_change_pct:.1f}%")
        rsi_turning_down = rsi < rsi_prev
        if htf_short_bias and (45 <= rsi <= 62) and rsi_turning_down:
            if near_ema20_short or near_vwap_short or at_box_high or bos_short:
                if in_box_middle and not bos_short and not at_box_high:
                    pass
                else:
                    direction = "SHORT"
                    if 48 <= rsi <= 57:
                        score += 28; reasons.append(f"RSI {rsi:.1f} Perfect Pullback")
                    else:
                        score += 20; reasons.append(f"RSI {rsi:.1f} Pullback")
                    if htf_price < htf_ema200:
                        score += 20; reasons.append("1H Trend DOWN < EMA200")
                    if death_1h:
                        score += 15; reasons.append("Death Cross 1H")
                    if near_ema20_short or near_vwap_short:
                        score += 12; reasons.append("Pullback to EMA20/VWAP - Close Held")
                    if bos_short:
                        score += 12; reasons.append("BOS Lower Low")
                    if at_box_high:
                        score += 12; reasons.append(f"BOX HIGH Edge ({box_pos*100:.0f}%)")
                    if vol_ratio >= 1.5:
                        score += 10; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
                    if funding >= 0.02:
                        score += 5; reasons.append(f"Funding {funding:.3f}% Soft Bullish")
                    if oi_soft and oi_change_pct < 0:
                        score += 5; reasons.append(f"OI Soft {oi_change_pct:.1f}%")
        if not direction:
            return
        if score < 55:
            print(f"No signal {coin} Score {score} low")
            return
        if not vol_ok:
            print(f"Skip {coin} Low Volume {vol_ratio:.2f}x")
            return
        if score >= 85:
            tier = "S-TIER"; tier_emoji = "🔥"
        elif score >= 70:
            tier = "A-TIER"; tier_emoji = "⭐"
        else:
            tier = "B-TIER"; tier_emoji = "✅"
            if vol_ratio < 1.5:
                print(f"Skip {coin} B-Tier no volume spike")
                return
        key = f"{coin}_{direction}"
        now = time.time()
        if key in last_signal_time and (now - last_signal_time[key]) < 2 * 3600:
            print(f"Skip {coin} Cooldown")
            return
        last_signal_time[key] = now
        if score >= 85 and atr_pct < 2.5 and vol_ratio >= 1.5 and (bos_long or bos_short or golden_1h or death_1h):
            tp_count = 6; tp_label = "RUNNER - Trend Trade - Trail SL to TP6"; tp_multipliers = [1.5, 2.5, 3.5, 4.5, 6.0, 8.0]
        elif score >= 70 and atr_pct < 4.0:
            tp_count = 4; tp_label = "STANDARD - Day Trade"; tp_multipliers = [1.5, 2.5, 3.5, 4.5]
        else:
            tp_count = 2; tp_label = "QUICK SCALP - Take Profit Fast"; tp_multipliers = [1.5, 2.5]
        if direction == "LONG":
            entry1 = price; entry2 = price - (atr * 0.6); sl = price - (atr * 1.5); tps = [price + (atr * m) for m in tp_multipliers]; emoji = "🟢"
        else:
            entry1 = price; entry2 = price + (atr * 0.6); sl = price + (atr * 1.5); tps = [price - (atr * m) for m in tp_multipliers]; emoji = "🔴"
        def pct(target):
            return ((target - entry1) / entry1) * 100
        sl_pct = abs(pct(sl))
        tp_pcts = [abs(pct(tp)) for tp in tps]
        volatility_pct = atr_pct * 2
        leverage = calc_leverage_smart(score, volatility_pct, sl_pct, tier)
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
            f"{tier_emoji} <b>{tier} | {tp_label} - {tp_count} TPs</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• <b>Entry 1:</b> ${fmt(entry1)}\n"
            f"• <b>Entry 2 (Optional):</b> ${fmt(entry2)}\n"
            f"\n"
            f"• <b>SL:</b> ${fmt(sl)} (-{sl_pct:.2f}%)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{tp_lines}"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 <b>Score:</b> {score}/100 | <b>RSI:</b> {rsi:.1f} | <b>ATR:</b> {atr_pct:.2f}% | <b>1H Trend:</b> {'UP' if direction=='LONG' else 'DOWN'}\n"
            f"📊 <b>Vol:</b> {vol_ratio:.1f}x Avg | <b>Funding:</b> {funding:.4f}% | <b>OI Chg:</b> {oi_change_pct:.1f}% | <b>BOX:</b> {box_pos*100:.0f}%\n"
            f"📊 <b>Reason:</b> {' | '.join(reasons)}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"• <b>All Trades is Trailing TP - Follow price with SL !!</b>\n"
            f"• <b>NFA / DYOR</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚠️ Trade at your own risk. Use SL. | BLACK SKYNET VIP V3.1"
        )
        send_signal(msg)
        print(f"SIGNAL {coin} {direction} {leverage}x {tp_count}TP {tier} Score {score}")
    except Exception as e:
        print(f"Error {symbol}: {e}")

print("BLACK SKYNET V3.1 BOT STARTED - PURE CRYPTO ONLY")
send_signal("✅ <b>BLACK SKYNET V3.1 BOT ONLINE</b>\nSystem: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding\nFilter: PURE CRYPTO ONLY - No Stocks / ETFs / Forex / Stablecoins\nSession: 07:00-22:00 UTC Only\nLeverage: Smart 7x-27x | TP: Dynamic 2 / 4 / 6 TP\nSignals ONLY - Trailing TP")

while True:
    try:
        if not in_trading_session():
            print("Outside session (Asia) - sleeping 10 min")
            time.sleep(600)
            continue
        SYMBOLS = get_all_mexc_symbols()
        for sym in SYMBOLS:
            scan_symbol(sym)
            time.sleep(0.35)
        print("Scan done, waiting 5 min")
        time.sleep(300)
    except Exception as e:
        print(f"Main loop error: {e}")
        time.sleep(60)
