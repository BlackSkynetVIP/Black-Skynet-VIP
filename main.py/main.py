# BLACK SKYNET VIP V4 - 1 Signal Filter
# Collects signals from all bots -> Compares -> Sends ONLY 1 signal
# If bots disagree, HTF Trend wins. If no clear winner -> NO TRADE

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import statistics

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
            print(f"[{symbol}] NO TRADE - RANGE + Bots Disagree")
            return None
    if len(scored) > 1:
        best_dir = best.direction
        second_dir = scored[1][1].direction
        if best_dir != second_dir and (best_score - second_score) < 20:
            print(f"[{symbol}] NO TRADE - Bots Conflict, No Clear Winner. Best {best_score} vs Second {second_score}")
            return None
    if best_score < 60:
        print(f"[{symbol}] NO TRADE - Best Score {best_score} < 60")
        return None
    agreeing = [s for _, s in scored if s.direction == best.direction]
    entry = statistics.median([s.entry for s in agreeing])
    sl = statistics.median([s.sl for s in agreeing])
    best_tps = max(agreeing, key=lambda s: len(s.tps)).tps
    sl_pct = abs(entry - sl) / entry * 100
    if sl_pct < 1.0:
        leverage = 3
    elif sl_pct < 2.0:
        leverage = 5
    else:
        leverage = 3
    rejected = [f"{s.source}:{s.direction}@{s.entry} Score:{s.score}" for _, s in scored if s.direction != best.direction]
    confidence = "HIGH" if best_score >= 90 else "MEDIUM"
    return FinalSignal(symbol=symbol, direction=best.direction, entry=round(entry, 6), sl=round(sl, 6), tps=best_tps, leverage=leverage, confidence=confidence, reason=f"HTF={htf_bias} | Winner={best.source} | Score={best_score} | Agreeing Bots={len(agreeing)}/{len(fresh)} | Rejected={len(rejected)}", rejected_signals=rejected)

def format_vip_post(signal: FinalSignal) -> str:
    emoji = "🟢" if signal.direction == "LONG" else "🔴"
    tp_lines = ""
    for i, tp in enumerate(signal.tps, 1):
        tp_lines += f"TP{i}: ${tp}\n"
    return f"""
{emoji} {signal.symbol} {signal.direction} - {signal.leverage}X
━━━━━━━━━━━━━━━
⭐ VERDICT: {signal.direction} ONLY - DO NOT TAKE OPPOSITE
━━━━━━━━━━━━━━━
Entry: ${signal.entry} (Limit)
SL: ${signal.sl}

{tp_lines}━━━━━━━━━━━━━━━
Leverage: {signal.leverage}x Isolated
Risk: 1-2% Only
Confidence: {signal.confidence}
━━━━━━━━━━━━━━━
Reason: {signal.reason}
Set and forget. SL Mandatory. NFA / DYOR
BLACK SKYNET VIP - 1 Signal, No Confusion
"""

if __name__ == "__main__":
    now = datetime.utcnow()
    signals = [
        BotSignal(source="OurBot_V3.3", symbol="NEAR/USDT", direction="LONG", entry=3.034246, sl=3.009292, tps=[3.059199, 3.075669, 3.092388, 3.109106], timeframe="1H", score=81, timestamp=now, reason="RSI 42 Pullback to EMA20"),
        BotSignal(source="BotA", symbol="NEAR/USDT", direction="SHORT", entry=3.05, sl=3.08, tps=[2.95, 2.92, 2.85], timeframe="15m", score=75, timestamp=now, reason="Resistance + Lower Highs"),
        BotSignal(source="BotB", symbol="NEAR/USDT", direction="SHORT", entry=3.04, sl=3.07, tps=[2.95, 2.90, 2.85], timeframe="1H", score=78, timestamp=now, reason="Breakdown below VWAP"),
    ]
    htf_bias = "DOWN"
    print(f"HTF Bias: {htf_bias}")
    final = filter_to_one_signal("NEAR/USDT", signals, htf_bias)
    if final:
        print("✅ FINAL 1 SIGNAL TO VIP:")
        print(format_vip_post(final))
        print(f"Rejected: {final.rejected_signals}")
    else:
        print("⏸️ NO TRADE - Do not send anything to VIP")
