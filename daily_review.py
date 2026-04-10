#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import glob
import os
from collections import defaultdict


REASON_CODES = [
    "LOW_SCORE",
    "SCORE_GAP_TOO_SMALL",
    "TREND_NOT_CLEAR",
    "PRICE_STRUCTURE_WEAK",
    "FUNDING_CROWDED",
    "OI_PRICE_DIVERGENCE",
    "ATR_TOO_HIGH",
    "ATR_TOO_LOW",
    "EVENT_CONFLICT",
    "EVENT_MISSING",
    "SZ_INVALID",
    "NET_VALUE_UNAVAILABLE",
    "ACCOUNT_RISK_LIMIT",
    "DAILY_DRAWDOWN_LIMIT",
    "MAX_POSITIONS_REACHED",
    "HEDGE_CONFLICT",
    "STOPLOSS_SETUP_RISK",
    "DATA_MISSING"
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_mean(values):
    if not values:
        return 0
    return sum(values) / len(values)


def main():
    snapshot_files = sorted(glob.glob("decision_snapshots/*.json"))
    trade_files = sorted(glob.glob("trade_records/*.json"))

    summary = {
        "total_runs": 0,
        "open_count": 0,
        "watch_count": 0,
        "skip_count": 0,
        "opened_symbols_count": 0
    }

    symbol_stats = {
        "BTC-USDT-SWAP": {
            "selected_count": 0,
            "opened_count": 0,
            "scores": [],
            "strong_entry_count": 0,
            "conservative_entry_count": 0
        },
        "ETH-USDT-SWAP": {
            "selected_count": 0,
            "opened_count": 0,
            "scores": [],
            "strong_entry_count": 0,
            "conservative_entry_count": 0
        },
        "SOL-USDT-SWAP": {
            "selected_count": 0,
            "opened_count": 0,
            "scores": [],
            "strong_entry_count": 0,
            "conservative_entry_count": 0
        },
        "XRP-USDT-SWAP": {
            "selected_count": 0,
            "opened_count": 0,
            "scores": [],
            "strong_entry_count": 0,
            "conservative_entry_count": 0
        }
    }

    reason_code_stats = {code: 0 for code in REASON_CODES}

    execution_stats = {
        "strong_entry_open_count": 0,
        "conservative_entry_open_count": 0,
        "order_success_count": 0,
        "order_failed_count": 0,
        "stoploss_success_count": 0,
        "stoploss_failed_count": 0,
        "size_calc_failed_count": 0
    }

    opened_symbols_set = set()
    mode = "paper"
    timeframe = "4h"
    date_value = ""

    for path in snapshot_files:
        data = load_json(path)

        summary["total_runs"] += 1
        mode = data.get("mode", mode)
        timeframe = data.get("timeframe", timeframe)
        timestamp = data.get("timestamp", "")
        if timestamp and not date_value:
            date_value = timestamp[:10]

        final_decision = data.get("final_decision", {})
        decision = final_decision.get("decision", "skip")
        best_symbol = final_decision.get("symbol", "")
        reason_codes = final_decision.get("reason_codes", [])

        if decision == "open":
            summary["open_count"] += 1
        elif decision == "watch":
            summary["watch_count"] += 1
        else:
            summary["skip_count"] += 1

        ranking = data.get("ranking", {})
        ranked_best = ranking.get("best_symbol", "")
        entry_tier = ranking.get("entry_tier", "")

        if ranked_best in symbol_stats:
            symbol_stats[ranked_best]["selected_count"] += 1

        for asset in data.get("symbols", []):
            symbol = asset.get("symbol", "")
            score_total = asset.get("score_total", 0)
            if symbol in symbol_stats:
                symbol_stats[symbol]["scores"].append(score_total)

        for code in reason_codes:
            if code in reason_code_stats:
                reason_code_stats[code] += 1

        size_reason = data.get("position_sizing", {}).get("size_reason_code", "")
        if size_reason in reason_code_stats:
            reason_code_stats[size_reason] += 1
            execution_stats["size_calc_failed_count"] += 1

        if decision == "open" and best_symbol in symbol_stats:
            symbol_stats[best_symbol]["opened_count"] += 1
            opened_symbols_set.add(best_symbol)

            if entry_tier == "strong_entry":
                symbol_stats[best_symbol]["strong_entry_count"] += 1
                execution_stats["strong_entry_open_count"] += 1
            elif entry_tier == "conservative_entry":
                symbol_stats[best_symbol]["conservative_entry_count"] += 1
                execution_stats["conservative_entry_open_count"] += 1

    for path in trade_files:
        trade = load_json(path)
        order_status = trade.get("order_status", "")
        stoploss_status = trade.get("stoploss_status", "")

        if order_status == "success":
            execution_stats["order_success_count"] += 1
        else:
            execution_stats["order_failed_count"] += 1

        if stoploss_status == "success":
            execution_stats["stoploss_success_count"] += 1
        else:
            execution_stats["stoploss_failed_count"] += 1

        for code in trade.get("reason_codes", []):
            if code in reason_code_stats:
                reason_code_stats[code] += 1

    summary["opened_symbols_count"] = len(opened_symbols_set)

    symbols_output = {}
    for symbol, stats in symbol_stats.items():
        symbols_output[symbol] = {
            "selected_count": stats["selected_count"],
            "opened_count": stats["opened_count"],
            "avg_score": round(safe_mean(stats["scores"]), 2),
            "strong_entry_count": stats["strong_entry_count"],
            "conservative_entry_count": stats["conservative_entry_count"]
        }

    target_met = summary["open_count"] >= 1 and summary["opened_symbols_count"] <= 2

    sorted_reasons = sorted(reason_code_stats.items(), key=lambda x: x[1], reverse=True)
    main_problem = sorted_reasons[0][0] if sorted_reasons and sorted_reasons[0][1] > 0 else ""
    secondary_problem = sorted_reasons[1][0] if len(sorted_reasons) > 1 and sorted_reasons[1][1] > 0 else ""

    suggestions = []

    if summary["open_count"] < 1:
        suggestions.append("Consider lowering the conservative entry threshold slightly.")
    if reason_code_stats["SCORE_GAP_TOO_SMALL"] > 0:
        suggestions.append("Consider relaxing the minimum score gap for conservative entry.")
    if reason_code_stats["FUNDING_CROWDED"] > 0:
        suggestions.append("Consider turning mild funding crowding into a size reduction instead of frequent rejection.")
    if reason_code_stats["ATR_TOO_HIGH"] > 0 or reason_code_stats["ATR_TOO_LOW"] > 0:
        suggestions.append("Consider using ATR more as a sizing factor and less as a blocking filter.")
    if execution_stats["size_calc_failed_count"] > 0:
        suggestions.append("Review size calculation failures and minimum order size constraints.")
    if execution_stats["stoploss_failed_count"] > 0:
        suggestions.append("Fix stop-loss setup reliability before moving beyond paper mode.")

    result = {
        "date": date_value,
        "mode": mode,
        "timeframe": timeframe,
        "summary": summary,
        "symbols": symbols_output,
        "reason_code_stats": reason_code_stats,
        "execution_stats": execution_stats,
        "daily_goal_check": {
            "target_min_trades_per_day": 1,
            "target_max_symbols_per_day": 2,
            "target_met": target_met
        },
        "review_notes": {
            "main_problem": main_problem,
            "secondary_problem": secondary_problem,
            "suggestions": suggestions
        }
    }

    with open("daily_review_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
