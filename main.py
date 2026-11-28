# BLACK SKYNET VIP V4.4 - Full App + 1 Signal Filter + Startup + TP Tracker
# FULL FILE - Paste WHOLE file
# FIX: Reads Telegram Token from ANY name in Render - so it finds your old INFO
import os
import json
import urllib.request
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
import statistics

try:
    from flask import Flask, jsonify, send_file
    app = Flask(__name__)
except:
    app = None

# ============================================================
# 0. TELEGRAM - CHECK ALL POSSIBLE NAMES IN RENDER
# Render had the INFO, but code looked for wrong name. Now we check ALL.
# ============================================================
def get_env_any(names):
    for n in names:
        v = os.environ.get(n, "")
        if v:
            print(f"Found env: {n}")
            return v
    return ""

TELEGRAM_BOT_TOKEN = get_env_any(["TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN", "TELEGRAM_BOT", "BOT_API_TOKEN", "TELEGRAM_API_TOKEN"])
TELEGRAM_CHAT_ID = get_env_any(["TELEGRAM_CHAT_ID", "CHAT_ID", "TELEGRAM_SIGNALS_CHAT_ID", "SIGNAL_CHAT_ID", "SIGNALS_CHAT_ID", "VIP_CHAT_ID", "TELEGRAM_CHANNEL_ID", "CHANNEL_ID"])

print(f"Telegram configured: Token={bool(TELEGRAM_BOT_TOKEN)} Chat={bool(TELEGRAM_CHAT_ID)} Chat value starts with: {TELEGRAM_CHAT_ID[:4] if TELEGRAM_CHAT_ID else 'NONE'}")

def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"TELEGRAM NOT CONFIGURED - Token={bool(TELEGRAM_BOT_TOKEN)} Chat={bool(TELEGRAM_CHAT_ID)} - Would send: {text[:80]}")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Telegram send: {resp.status}")
            return resp.status == 200
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False

def announce_live():
    time.sleep(5)
    msg = (
        "🟢 <b>BLACK SKYNET VIP V4.4 IS LIVE</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "⭐ 1 Signal Filter - ON\n"
        "⭐ TP Hit Tracker - ON\n"
        "Bots compared. Only 1 signal sent.\n"
        "No more LONG + SHORT at same time.\n"
        "━━━━━━━━━━━━━━━\n"
        "BLACK SKYNET VIP"
    )
    ok = send_telegram_message(msg)
    print(f"Startup announce sent: {ok}")

# ============================================================
# 1. SIGNAL STRUCTURE
# ============================================================
@dataclass
class BotSignal:
    source: str
    symbol: str
    direction: str
    entry: float
    sl: float
    tps: List[float]
    timeframe: str
    score: int
    timestamp: datetime
    reason: str = ""

@dataclass
class FinalSignal:
    symbol: str
    direction: str
    entry: float
    sl: float
    tps: List[float]
    leverage: int
    confidence: str
    reason: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    hit_tps: List[int] = field(default_factory=list)
    rejected_signals: List[str] = field(default_factory=list)

ACTIVE_TRADES: Dict[str, FinalSignal] = {}

# ============================================================
# 2. HTF FILTER
# ============================================================
def get_htf_bias(symbol: str, close_1d: list, ema200_1d: float, close_4h: list) -> str:
    price_1d = close_1d[-1]
    price_1d_20_ago = close_1d[-20]
    above_ema = price_1d > ema200_1d
    trend_up = price_1d > price_1d_20_ago * 1.02
    trend_down = price_1d < price_1d_20_ago * 0.98
    high_4h = max(close_4h[-20:])
    low_4h = min(close_4h[-20:])
    current_4h = close_4h[-1]
    in_upper_half = current_4h > (low_4h + high_4h) / 2
    if trend_down and not above_ema:
        return "DOWN"
    if trend_up and above_ema:
        return "UP"
    if not trend_up and not trend_down:
        return "RANGE"
    return "UP" if above_ema and in_upper_half else "DOWN"

# ============================================================
# 3. COMPARE ALL BOTS, PICK 1 WINNER
# ============================================================
def filter_to_one_signal(symbol: str, signals: List[BotSignal], htf_bias: str, max_age_minutes: int = 30) -> Optional[FinalSignal]:
    if not signals:
        return None
    now = datetime.utcnow()
    fresh = [s for s in signals if (now - s.timestamp).total_seconds() < max_age_minutes * 60]
    if not fresh:
        return None
    scored = []
    for s in fresh:
        score = s.score
        if htf_bias == "UP" and s.direction == "LONG":
            score += 30
        elif htf_bias == "DOWN" and s.direction == "SHORT":
            score += 30
        elif htf_bias == "UP" and s.direction == "SHORT":
            score -= 40
        elif htf_bias == "DOWN" and s.direction == "LONG":
            score -= 40
        elif htf_bias == "RANGE":
            score -= 20
        if s.timeframe == "1H":
            score += 10
        elif s.timeframe == "15m":
            score -= 5
        elif s.timeframe == "5m":
            score -= 15
        sl_pct = abs(s.entry - s.sl) / s.entry * 100
        if sl_pct < 1.0:
            score -= 15
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0
    if htf_bias == "RANGE":
        directions = set(s.direction for _, s in scored)
        if len(directions) > 1:
            return None
    if len(scored) > 1:
        if best.direction != scored[1][1].direction and (best_score - second_score) < 20:
            return None
    if best_score < 60:
        return None
    agreeing = [s for _, s in scored if s.direction == best.direction]
    entry = statistics.median([s.entry for s in agreeing])
    sl = statistics.median([s.sl for s in agreeing])
    best_tps = max(agreeing, key=lambda s: len(s.tps)).tps
    sl_pct = abs(entry - sl) / entry * 100
    leverage = 3 if sl_pct < 1.0 else 5 if sl_pct < 2.0 else 3
    rejected = [f"{s.source}:{s.direction}@{s.entry}" for _, s in scored if s.direction != best.direction]
    confidence = "HIGH" if best_score >= 90 else "MEDIUM"
    return FinalSignal(symbol=symbol, direction=best.direction, entry=round(entry, 6), sl=round(sl, 6), tps=best_tps, leverage=leverage, confidence=confidence, reason=f"HTF={htf_bias} | Winner={best.source} | Score={best_score}", rejected_signals=rejected)

# ============================================================
# 4. TP HIT TRACKER - 【entity-Binance¦canonical_name=Binance】 Killers Style
# ============================================================
def get_price_binance(symbol: str) -> Optional[float]:
    try:
        pair = symbol.replace("/", "").replace("-", "")
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return float(data["price"])
    except Exception as e:
        print(f"Price fetch failed {symbol}: {e}")
        return None

def tp_tracker_loop():
    print("TP Tracker started")
    while True:
        try:
            time.sleep(60)
            if not ACTIVE_TRADES:
                continue
            for key in list(ACTIVE_TRADES.keys()):
                sig = ACTIVE_TRADES[key]
                price = get_price_binance(sig.symbol)
                if price is None:
                    continue
                for idx, tp in enumerate(sig.tps, 1):
                    if idx in sig.hit_tps:
                        continue
                    hit = False
                    if sig.direction == "LONG" and price >= tp:
                        hit = True
                    if sig.direction == "SHORT" and price <= tp:
                        hit = True
                    if hit:
                        sig.hit_tps.append(idx)
                        profit_pct = abs(tp - sig.entry) / sig.entry * 100 * sig.leverage
                        elapsed = datetime.utcnow() - sig.start_time
                        hours = int(elapsed.total_seconds() // 3600)
                        mins = int((elapsed.total_seconds() % 3600) // 60)
                        msg = f"#{sig.symbol.replace('/', '')}\nTarget Touch {idx} ✅\nProfit: {profit_pct:.2f}% 📈\nin: {hours} Hours {mins} Minutes ⏰\nEntry: ${sig.entry} -> TP{idx}: ${tp}\nBLACK SKYNET VIP"
                        send_telegram_message(msg)
                sl_hit = False
                if sig.direction == "LONG" and price <= sig.sl:
                    sl_hit = True
                if sig.direction == "SHORT" and price >= sig.sl:
                    sl_hit = True
                if sl_hit:
                    send_telegram_message(f"🔴 #{sig.symbol.replace('/', '')} STOP LOSS TRIGGERED\nEntry: ${sig.entry} SL: ${sig.sl}\nBLACK SKYNET VIP")
                    del ACTIVE_TRADES[key]
        except Exception as e:
            print(f"TP Tracker error: {e}")
            time.sleep(10)

# ============================================================
# 5. WEB SERVER
# ============================================================
if app is not None:
    @app.route("/")
    def home():
        if os.path.exists("index.html"):
            return send_file("index.html")
        return "Black Skynet VIP V4.4 - Live"

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": "V4.4", "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID), "active_trades": len(ACTIVE_TRADES)})

    @app.route("/test-telegram")
    def test_telegram():
        ok = send_telegram_message("🟢 TEST - Black Skynet V4.4 Telegram is working")
        return jsonify({"telegram_sent": ok, "token_set": bool(TELEGRAM_BOT_TOKEN), "chat_set": bool(TELEGRAM_CHAT_ID)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=announce_live, daemon=True).start()
    threading.Thread(target=tp_tracker_loop, daemon=True).start()
    if app is not None:
        print(f"Starting Black Skynet VIP V4.4 on port {port}")
        app.run(host="0.0.0.0", port=port)
