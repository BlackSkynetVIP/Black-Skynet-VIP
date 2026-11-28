# BLACK SKYNET VIP V4.2 - Full App + 1 Signal Filter + Startup Announce
# FULL FILE - Do NOT paste only part
import os
import requests
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import statistics

try:
    from flask import Flask, jsonify, send_file
    app = Flask(__name__)
except:
    app = None

# ============================================================
# 0. TELEGRAM - STARTUP MESSAGE - THIS WAS MISSING IN V4.1
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# If you use TELEGRAM_SIGNALS_CHAT_ID in Render, it will use that too
if not TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_SIGNALS_CHAT_ID", "")

def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"Telegram not configured - would send: {text}")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        print(f"Telegram send: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False

def announce_live():
    # Wait 5 sec for Render to be fully up, then announce
    time.sleep(5)
    msg = (
        "🟢 <b>BLACK SKYNET VIP V4.2 IS LIVE</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "⭐ NEW: 1 Signal Filter - ON\n"
        "Bots are now compared. Only 1 signal sent.\n"
        "No more LONG + SHORT at same time.\n"
        "━━━━━━━━━━━━━━━\n"
        "HTF Wins. If bots fight, HTF decides.\n"
        "If no clear winner = NO TRADE\n"
        "━━━━━━━━━━━━━━━\n"
        "Set and forget. SL Mandatory.\n"
        "BLACK SKYNET VIP"
    )
    send_telegram_message(msg)

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
    rejected_signals: List[str] = field(default_factory=list)

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
# 4. WEB SERVER - RENDER NEEDS THIS
# ============================================================
if app is not None:
    @app.route("/")
    def home():
        if os.path.exists("index.html"):
            return send_file("index.html")
        return "Black Skynet VIP V4.2 - Live - 1 Signal Filter"

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": "V4.2", "filter": "1-Signal-Only"})

    @app.route("/test-filter")
    def test_filter():
        now = datetime.utcnow()
        signals = [
            BotSignal(source="OurBot_V3.3", symbol="NEAR/USDT", direction="LONG", entry=3.034246, sl=3.009292, tps=[3.059199, 3.075669], timeframe="1H", score=81, timestamp=now),
            BotSignal(source="BotA", symbol="NEAR/USDT", direction="SHORT", entry=3.05, sl=3.08, tps=[2.95, 2.92], timeframe="15m", score=75, timestamp=now),
            BotSignal(source="BotB", symbol="NEAR/USDT", direction="SHORT", entry=3.04, sl=3.07, tps=[2.95, 2.90], timeframe="1H", score=78, timestamp=now),
        ]
        final = filter_to_one_signal("NEAR/USDT", signals, "DOWN")
        if final:
            return jsonify({"final": final.direction, "entry": final.entry, "sl": final.sl, "tps": final.tps})
        return jsonify({"final": "NO TRADE"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Start announce in background so it does not block web server
    threading.Thread(target=announce_live, daemon=True).start()
    if app is not None:
        print(f"Starting Black Skynet VIP V4.2 on port {port}")
        app.run(host="0.0.0.0", port=port)
