import os, threading, time
from flask import Flask
import ccxt
import requests
import pandas as pd
from datetime import datetime, timezone

# ================= KEEP ALIVE =================
app = Flask(__name__)
@app.route('/')
def home():
    return "Black Skynet VIP V3 is running"
def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=keep_alive, daemon=True).start()

# ================= BLACK SKYNET V3 - ABSOLUTE BEST =================
# MTF: 1H Trend + 15m Entry | Wick-Tolerant EMA | BOX Edge | BOS | Soft OI/Funding | Session Filter

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "-1003502607416"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

exchange = ccxt.mexc({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
TF_ENTRY = '15m'
TF_TREND = '1h'

last_signal_time = {}
last_oi = {}

def send_signal(text):
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}, timeout=10)
        print("Sent to Telegram")
    except Exception as e:
        print("Telegram error:", e)

# ================= INDICATORS =================
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

# ================= SMART LEVERAGE 7x-27x =================
def calc_leverage_smart(score, volatility_pct, sl_pct, tier):
    base = 7 + ((score - 55) / 45) * 13  # 55->7x, 100->20x
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
        syms = [s for s, m in markets.items() if m.get('swap') and m.get('quote') == 'USDT' and m.get('active')]
        print(f"Found {len(syms)} MEXC USDT Perp coins")
        return sorted(syms)
    except Exception as e:
        print(f"Market load error: {e}")
        return ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT']

# ================= SESSION FILTER =================
def in_trading_session():
    # Only London + NY: 07:00 - 22:00 UTC. Skip Asia chop.
    hour = datetime.now(timezone.utc).hour
    return 7 <= hour < 22

# ================= SCANNER V3 =================
def scan_symbol(symbol):
    try:
        # --- SESSION CHECK (once per symbol is ok, cheap) ---
        if not in_trading_session():
            return

        # --- FETCH 1H TREND + 15m ENTRY ---
        ohlcv_1h = exchange.fetch_ohlcv(symbol, TF_TREND, limit=250)
        ohlcv_15 = exchange.fetch_ohlcv(symbol, TF_ENTRY, limit=250)
        df1h = pd.DataFrame(ohlcv_1h, columns=['ts','open','high','low','close','vol'])
        df = pd.DataFrame(ohlcv_15, columns=['ts','open','high','low','close','vol'])
        if len(df) < 210 or len(df1h) < 210:
            return

        # 1H Trend indicators
        df1h['ema50'] = get_ema(df1h['close'], 50)
        df1h['ema200'] = get_ema(df1h['close'], 200)
        trend_last = df1h.iloc[-2]  # closed 1H candle
        trend_prev = df1h.iloc[-3]
        htf_price = trend_last['close']
        htf_ema50, htf_ema200 = trend_last['ema50'], trend_last['ema200']
        # Golden / Death on 1H - REAL trend, not 15m noise
        golden_1h = (trend_prev['ema50'] <= trend_prev['ema200']) and (htf_ema50 > htf_ema200)
        death_1h = (trend_prev['ema50'] >= trend_prev['ema200']) and (htf_ema50 < htf_ema200)

        # 15m Entry indicators
        df['rsi'] = get_rsi_wilder(df['close'])
        df['ema20'] = get_ema(df['close'], 20)
        df['ema50'] = get_ema(df['close'], 50)
        df['ema200'] = get_ema(df['close'], 200)
        df['atr'] = get_atr(df)
        df['vwap'] = get_vwap(df)

        last = df.iloc[-2]  # CLOSED candle only - NO REPAINT
        prev = df.iloc[-3]
        prev2 = df.iloc[-4]

        price = last['close']  # CLOSE only, wicks ignored
        rsi = last['rsi']
        rsi_prev = prev['rsi']
        ema20, ema50, ema200 = last['ema20'], last['ema50'], last['ema200']
        vwap = last['vwap']
        atr = last['atr']
        atr_pct = (atr / price) * 100
        coin = symbol.split('/')[0]

        # --- VOLATILITY FILTER: Skip dead coins ---
        if atr_pct < 0.4:
            return

        # --- VOLUME ---
        avg_vol = df['vol'].tail(20).mean()
        vol_ratio = last['vol'] / avg_vol if avg_vol > 0 else 0
        vol_ok = vol_ratio >= 1.2

        # --- WICK-TOLERANT EMA: 0.15% buffer, CLOSE only ---
        BUFFER = 0.0015
        # 1H Trend Bias - This decides LONG vs SHORT, 15m cannot override it
        htf_long_bias = htf_price > htf_ema200 * (1 - BUFFER)
        htf_short_bias = htf_price < htf_ema200 * (1 + BUFFER)
        # 15m pullback to EMA20 / VWAP - with buffer, wick through is OK if close holds
        near_ema20_long = abs(price - ema20) / price < 0.008 or (price > ema20 * (1 - BUFFER) and price < ema20 * 1.01)
        near_vwap_long = abs(price - vwap) / price < 0.008
        near_ema20_short = abs(price - ema20) / price < 0.008 or (price < ema20 * (1 + BUFFER) and price > ema20 * 0.99)
        near_vwap_short = abs(price - vwap) / price < 0.008

        # --- BOS - Break of Structure ---
        # LONG BOS: Close > prev high AND prev high > prev2 high = Higher High
        bos_long = last['close'] > prev['high'] and prev['high'] > prev2['high']
        bos_short = last['close'] < prev['low'] and prev['low'] < prev2['low']

        # --- BOX EDGE LOGIC - Trade EDGES only, NO MIDDLE ---
        last20_high = df['high'].tail(20).max()
        last20_low = df['low'].tail(20).min()
        box_range = last20_high - last20_low
        box_pos = (price - last20_low) / box_range if box_range > 0 else 0.5
        # Edge zones: Bottom 20% = LONG edge, Top 20% = SHORT edge, Middle 60% = NO TRADE unless BOS strong
        at_box_low = box_pos <= 0.20
        at_box_high = box_pos >= 0.80
        in_box_middle = 0.20 < box_pos < 0.80

        # --- FUNDING + OI - SOFT OPINION ONLY, NEVER REQUIRED ---
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
                if abs(oi_change_pct) > 2:  # Soft: any notable OI move, not aggressive -3% flush hunt
                    oi_soft = True
            last_oi[symbol] = oi_now
        except:
            pass

        # ================= SCORING V3 - PULLBACK LOGIC =================
        score = 0
        direction = None
        reasons = []

        # --- LONG: HTF UP + 15m Pullback + RSI 38-55 turning up ---
        rsi_turning_up = rsi > rsi_prev
        if htf_long_bias and (38 <= rsi <= 55) and rsi_turning_up:
            # Must be near support (EMA20/VWAP) OR at BOX LOW OR BOS - not in middle for no reason
            if near_ema20_long or near_vwap_long or at_box_low or bos_long:
                # If in BOX middle with NO BOS, skip - this is the only middle filter
                if in_box_middle and not bos_long and not at_box_low:
                    pass  # will fall through to no signal
                else:
                    direction = "LONG"
                    # RSI pullback score - 45-52 is perfect pullback
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
                    # SOFT bonuses - max +5 each, never required
                    if funding <= -0.02:
                        score += 5; reasons.append(f"Funding {funding:.3f}% Soft Bearish")
                    if oi_soft and oi_change_pct < 0:
                        score += 5; reasons.append(f"OI Soft {oi_change_pct:.1f}%")

        # --- SHORT: HTF DOWN + 15m Pullback + RSI 45-62 turning down ---
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

        # --- FILTERS ---
        if not direction:
            return
        if score < 55:  # Lowered from 62 to 55 - pullback logic needs lower threshold
            print(f"No signal {coin} Score {score} low")
            return
        if not vol_ok:
            print(f"Skip {coin} Low Volume {vol_ratio:.2f}x")
            return

        # --- TIER ---
        if score >= 85:
            tier = "S-TIER"
            tier_emoji = "🔥"
        elif score >= 70:
            tier = "A-TIER"
            tier_emoji = "⭐"
        else:
            tier = "B-TIER"
            tier_emoji = "✅"
            # B-Tier needs volume spike to be worth posting
            if vol_ratio < 1.5:
                print(f"Skip {coin} B-Tier no volume spike")
                return

        # --- COOLDOWN 2H (was 4H) ---
        key = f"{coin}_{direction}"
        now = time.time()
        if key in last_signal_time and (now - last_signal_time[key]) < 2 * 3600:
            print(f"Skip {coin} Cooldown")
            return
        last_signal_time[key] = now

        # --- DYNAMIC TP 2/4/6 - BOT Decides ---
        if score >= 85 and atr_pct < 2.5 and vol_ratio >= 1.5 and (bos_long or bos_short or golden_1h or death_1h):
            tp_count = 6
            tp_label = "RUNNER - Trend Trade - Trail SL to TP6"
            tp_multipliers = [1.5, 2.5, 3.5, 4.5, 6.0, 8.0]
        elif score >= 70 and atr_pct < 4.0:
            tp_count = 4
            tp_label = "STANDARD - Day Trade"
            tp_multipliers = [1.5, 2.5, 3.5, 4.5]
        else:
            tp_count = 2
            tp_label = "QUICK SCALP - Take Profit Fast"
            tp_multipliers = [1.5, 2.5]

        # --- ATR SL / TP ---
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
            f"⚠️ Trade at your own risk. Use SL. | BLACK SKYNET VIP V3"
        )
        send_signal(msg)
        print(f"SIGNAL {coin} {direction} {leverage}x {tp_count}TP {tier} Score {score}")

    except Exception as e:
        print(f"Error {symbol}: {e}")

# ================= MAIN LOOP =================
print("BLACK SKYNET V3 BOT STARTED - ALL MEXC COINS")
send_signal("✅ <b>BLACK SKYNET V3 BOT ONLINE</b>\nSystem: 1H Trend + 15m Pullback + BOS + Wick-Tolerant EMA + BOX Edge + Soft OI/Funding\nSession: 07:00-22:00 UTC Only\nLeverage: Smart 7x-27x | TP: Dynamic 2 / 4 / 6 TP\nSignals ONLY - Trailing TP")

while True:
    try:
        # If outside session, sleep 10 min and check again - don't spam scans in Asia chop
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
