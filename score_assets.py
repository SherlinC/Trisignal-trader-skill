#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from typing import Dict, Any, List


def safe_get(dct: Dict[str, Any], key: str, default=0):
    value = dct.get(key, default)
    return default if value is None else value


def load_params() -> Dict[str, Any]:
    try:
        with open("strategy_params.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def infer_direction(asset: Dict[str, Any]) -> str:
    ma5 = safe_get(asset, "ma5")
    ma10 = safe_get(asset, "ma10")
    ma20 = safe_get(asset, "ma20")
    ma60 = safe_get(asset, "ma60")

    if ma5 > ma10 > ma20 > ma60:
        return "buy"
    if ma5 < ma10 < ma20 < ma60:
        return "sell"
    if ma5 > ma10 > ma20:
        return "buy"
    if ma5 < ma10 < ma20:
        return "sell"
    return "neutral"


def score_ma_structure(asset: Dict[str, Any]) -> int:
    ma5 = safe_get(asset, "ma5")
    ma10 = safe_get(asset, "ma10")
    ma20 = safe_get(asset, "ma20")
    ma60 = safe_get(asset, "ma60")
    close = safe_get(asset, "close")

    if ma5 > ma10 > ma20 > ma60:
        base = 24
    elif ma5 < ma10 < ma20 < ma60:
        base = 24
    elif ma5 > ma10 > ma20:
        base = 16
    elif ma5 < ma10 < ma20:
        base = 16
    elif ma5 > ma20 and ma10 > ma20:
        base = 12
    elif ma5 < ma20 and ma10 < ma20:
        base = 12
    else:
        base = 6

    bonus = 0

    if close > ma20 or close < ma20:
        bonus += 2

    spread_1 = abs(ma5 - ma10)
    spread_2 = abs(ma10 - ma20)
    spread_3 = abs(ma20 - ma60)

    if spread_1 > 0:
        bonus += 1
    if spread_2 > 0:
        bonus += 1
    if spread_3 > 0:
        bonus += 1

    return min(base + bonus, 28)


def score_macd(asset: Dict[str, Any], direction: str) -> int:
    dif = safe_get(asset, "macd_dif")
    dea = safe_get(asset, "macd_dea")
    hist = safe_get(asset, "macd_hist")

    if direction == "buy":
        score = 0
        if dif > dea:
            score += 8
        if hist > 0:
            score += 6
        if dif > 0:
            score += 3
        if dea > 0:
            score += 3
        return min(score, 20)

    if direction == "sell":
        score = 0
        if dif < dea:
            score += 8
        if hist < 0:
            score += 6
        if dif < 0:
            score += 3
        if dea < 0:
            score += 3
        return min(score, 20)

    return 4


def calc_trend_strength(asset: Dict[str, Any]) -> int:
    """
    Deterministic trend_strength (0-10) from MA alignment and close position.
    Replaces subjective model input.
    """
    ma5 = safe_get(asset, "ma5")
    ma10 = safe_get(asset, "ma10")
    ma20 = safe_get(asset, "ma20")
    ma60 = safe_get(asset, "ma60")
    close = safe_get(asset, "close")

    score = 0
    direction = infer_direction(asset)

    if direction == "buy":
        if ma5 > ma10: score += 2
        if ma10 > ma20: score += 2
        if ma20 > ma60: score += 2
        if close > ma20: score += 2
        if close > ma5: score += 2
    elif direction == "sell":
        if ma5 < ma10: score += 2
        if ma10 < ma20: score += 2
        if ma20 < ma60: score += 2
        if close < ma20: score += 2
        if close < ma5: score += 2
    else:
        score = 3  # neutral baseline

    return min(score, 10)


def calc_structure_clarity(asset: Dict[str, Any]) -> int:
    """
    Deterministic structure_clarity (0-10) from MA spread and MACD alignment.
    Replaces subjective model input.
    """
    ma5 = safe_get(asset, "ma5")
    ma10 = safe_get(asset, "ma10")
    ma20 = safe_get(asset, "ma20")
    ma60 = safe_get(asset, "ma60")
    dif = safe_get(asset, "macd_dif")
    dea = safe_get(asset, "macd_dea")
    hist = safe_get(asset, "macd_hist")
    direction = infer_direction(asset)

    score = 0

    # MA spread — wider = clearer structure
    if ma20 > 0:
        spread_ratio = abs(ma5 - ma60) / ma20
        if spread_ratio > 0.03: score += 3
        elif spread_ratio > 0.015: score += 2
        elif spread_ratio > 0.005: score += 1

    # MACD alignment with direction
    if direction == "buy":
        if dif > dea: score += 3
        if hist > 0: score += 2
        if dif > 0: score += 2
    elif direction == "sell":
        if dif < dea: score += 3
        if hist < 0: score += 2
        if dif < 0: score += 2
    else:
        score = max(score - 2, 0)

    return min(score, 10)



    trend_strength = safe_get(asset, "trend_strength", 0)
    structure_clarity = safe_get(asset, "structure_clarity", 0)

    score = 0
    score += max(0, min(10, int(trend_strength)))
    score += max(0, min(10, int(structure_clarity)))

    if direction == "neutral":
        score = min(score, 6)

    return min(score, 20)


def score_oi(asset: Dict[str, Any], direction: str) -> int:
    oi_change = safe_get(asset, "oi_change_pct", 0)
    price_change = safe_get(asset, "price_change_pct", 0)

    if direction == "buy":
        if price_change > 0 and oi_change > 0:
            return 10
        if price_change > 0 and oi_change >= -1:
            return 6
        return 2

    if direction == "sell":
        if price_change < 0 and oi_change > 0:
            return 10
        if price_change < 0 and oi_change >= -1:
            return 6
        return 2

    return 3


def funding_penalty(asset: Dict[str, Any]) -> int:
    funding = abs(safe_get(asset, "funding_rate", 0))

    if funding > 0.003:
        return -12
    if funding > 0.002:
        return -8
    if funding > 0.001:
        return -4
    return 0


def atr_adjustment(asset: Dict[str, Any]) -> int:
    atr_ratio = safe_get(asset, "atr_ratio", 0)

    if atr_ratio <= 0:
        return -4
    if atr_ratio > 0.08:
        return -6
    if atr_ratio > 0.05:
        return -2
    if atr_ratio < 0.003:
        return -4
    if atr_ratio < 0.006:
        return -1
    return 4


def event_adjustment(asset: Dict[str, Any]) -> int:
    event_bias = safe_get(asset, "event_bias", "neutral")

    if event_bias == "aligned":
        return 4
    if event_bias == "conflict":
        return -4
    return 0


def build_flags(asset: Dict[str, Any], direction: str) -> (List[str], List[str]):
    soft_flags = []
    hard_flags = []

    funding = abs(safe_get(asset, "funding_rate", 0))
    atr_ratio = safe_get(asset, "atr_ratio", 0)
    data_ok = asset.get("data_ok", True)

    if not data_ok:
        hard_flags.append("DATA_MISSING")

    if direction == "neutral":
        soft_flags.append("TREND_NOT_CLEAR")

    if funding > 0.001:
        soft_flags.append("FUNDING_CROWDED")
    if funding > 0.003:
        hard_flags.append("FUNDING_EXTREME")

    if atr_ratio > 0.05:
        soft_flags.append("ATR_TOO_HIGH")
    if atr_ratio > 0.08:
        hard_flags.append("ATR_EXTREME_HIGH")

    if atr_ratio < 0.006:
        soft_flags.append("ATR_TOO_LOW")
    if 0 < atr_ratio < 0.003:
        hard_flags.append("ATR_EXTREME_LOW")

    if safe_get(asset, "oi_divergence", False):
        soft_flags.append("OI_PRICE_DIVERGENCE")

    if safe_get(asset, "event_bias", "neutral") == "conflict":
        soft_flags.append("EVENT_CONFLICT")

    return soft_flags, hard_flags


def score_one_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    symbol = asset["symbol"]
    direction = infer_direction(asset)

    # Use deterministic calculations; fall back to input values if provided
    if safe_get(asset, "trend_strength") == 0:
        asset = dict(asset, trend_strength=calc_trend_strength(asset))
    if safe_get(asset, "structure_clarity") == 0:
        asset = dict(asset, structure_clarity=calc_structure_clarity(asset))

    ma_score = score_ma_structure(asset)
    macd_score = score_macd(asset, direction)
    price_score = max(0, min(20, asset["trend_strength"] + asset["structure_clarity"]))
    oi_score = score_oi(asset, direction)
    funding_adj = funding_penalty(asset)
    atr_adj = atr_adjustment(asset)
    event_adj = event_adjustment(asset)
    soft_flags, hard_flags = build_flags(asset, direction)

    total = ma_score + macd_score + price_score + oi_score + funding_adj + atr_adj + event_adj

    return {
        "symbol": symbol,
        "direction": direction,
        "score_total": total,
        "score_breakdown": {
            "ma_structure": ma_score,
            "macd": macd_score,
            "price_structure": price_score,
            "oi": oi_score,
            "funding_penalty": funding_adj,
            "atr_adjustment": atr_adj,
            "event_adjustment": event_adj
        },
        "soft_flags": soft_flags,
        "hard_flags": hard_flags,
        "notes": ""
    }


def select_candidate(scored_assets: List[Dict[str, Any]], params: Dict[str, Any] = None) -> Dict[str, Any]:
    if params is None:
        params = {}
    score_rules = params.get("score_rules", {})
    strong_threshold = score_rules.get("strong_entry_score", 55)
    conservative_threshold = score_rules.get("conservative_entry_score", 42)
    watch_threshold = score_rules.get("watch_score", 38)
    min_gap_strong = score_rules.get("min_gap_strong", 4)
    min_gap_conservative = score_rules.get("min_gap_conservative", 1)

    ranked = sorted(scored_assets, key=lambda x: x["score_total"], reverse=True)
    best = ranked[0]
    second = ranked[1]
    gap = best["score_total"] - second["score_total"]

    # BTC anchor direction filter
    # If BTC is scored and its direction conflicts with the best candidate, penalize
    btc_anchor_penalty = 0
    btc_scored = next((a for a in scored_assets if a["symbol"] == "BTC-USDT-SWAP"), None)
    if btc_scored and btc_scored["direction"] != "neutral" and best["symbol"] != "BTC-USDT-SWAP":
        if btc_scored["direction"] != best["direction"]:
            btc_anchor_penalty = 6
            best = dict(best, score_total=best["score_total"] - btc_anchor_penalty,
                        notes=f"BTC anchor conflict penalty -{btc_anchor_penalty}")
            gap = best["score_total"] - second["score_total"]

    if best["score_total"] >= strong_threshold and gap >= min_gap_strong and not best["hard_flags"]:
        entry_tier = "strong_entry"
        candidate_decision = "open"
    elif best["score_total"] >= conservative_threshold and gap >= min_gap_conservative and not best["hard_flags"]:
        entry_tier = "conservative_entry"
        candidate_decision = "open"
    elif best["score_total"] >= watch_threshold and not best["hard_flags"]:
        entry_tier = "conservative_entry"
        candidate_decision = "watch"
    else:
        entry_tier = "no_trade"
        candidate_decision = "skip"

    return {
        "best_symbol": best["symbol"],
        "best_direction": best["direction"],
        "best_score": best["score_total"],
        "second_symbol": second["symbol"],
        "second_direction": second["direction"],
        "second_score": second["score_total"],
        "score_gap": gap,
        "entry_tier": entry_tier,
        "candidate_decision": candidate_decision
    }


def main():
    with open("market_input.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    params = load_params()
    assets = data["assets"]
    timestamp = data.get("timestamp", "")
    timeframe = data.get("timeframe", "4h")

    scored_assets = [score_one_asset(asset) for asset in assets]
    ranking = select_candidate(scored_assets, params)

    result = {
        "timestamp": timestamp,
        "timeframe": timeframe,
        "assets": scored_assets,
        "ranking": ranking
    }

    with open("score_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
