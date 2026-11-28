# BLACK SKYNET VIP V4.1 - Full App + 1 Signal Filter
# This is the WHOLE main.py - Web Server + Filter - Do NOT paste only filter part
import os
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import statistics

# --- Try Flask, if not installed use simple fallback ---
try:
    from flask import Flask, jsonify, send_file
    app = Flask(__name__)
except:
    app = None

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

def format_vip_post(signal: FinalSignal) -> str:
    emoji = "🟢" if signal.direction == "LONG" else "🔴"
    tp_lines = "".join([f"TP{i}: ${tp}\n" for i, tp in enumerate(signal.tps, 1)])
    return f"{emoji} {signal.symbol} {signal.direction} - {signal.leverage}X\nEntry: ${signal.entry} SL: ${signal.sl}\n{tp_lines}BLACK SKYNET VIP"

# ============================================================
# 4. WEB SERVER - THIS IS WHAT RENDER NEEDS TO STAY LIVE
# ============================================================
if app is not None:
    @app.route("/")
    def home():
        # Serve index.html if exists, else simple text
        if os.path.exists("index.html"):
            return send_file("index.html")
        return "Black Skynet VIP V4.1 - Live - 1 Signal Filter"

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": "V4.1", "filter": "1-Signal-Only"})

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
            return jsonify({"final": final.direction, "entry": final.entry, "sl": final.sl, "tps": final.tps, "leverage": final.leverage})
        return jsonify({"final": "NO TRADE"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    if app is not None:
        print(f"Starting Black Skynet VIP V4.1 on port {port}")
        app.run(host="0.0.0.0", port=port)
    else:
        print("Flask not found, filter only mode")
