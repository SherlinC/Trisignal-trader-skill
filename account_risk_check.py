#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
account_risk_check.py — TriSignal Trader V4.3 Lite

Position and account-level risk check.

Rules:
- Max 2 simultaneous symbols (distinct instIds), UNLESS the new order is
  adding to an existing symbol — in that case allow regardless of count.
- Hedge conflict: same symbol cannot hold both long and short.
- Daily drawdown >= 8%: block all new opens.
- Same symbol + same direction: allowed (add-on / pyramid).
- Same symbol + opposite direction: blocked (hedge conflict).
- Different symbol, already 2 distinct symbols open: blocked (MAX_POSITIONS_REACHED),
  UNLESS the candidate symbol is already one of the open symbols.

Input:  position_list.json  (list of open positions from okx account positions)
        candidate.json       (symbol + side being considered)
Output: account_risk_check.json
"""

import json
from datetime import datetime, timezone


SYMBOLS = [
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP",
    "XRP-USDT-SWAP",
]

MAX_OPEN_SYMBOLS = 2
DAILY_DRAWDOWN_LIMIT = 0.08


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_per_symbol(positions: list) -> dict:
    """Build per-symbol long/short presence map from position list."""
    per_symbol = {
        s: {"has_long": False, "has_short": False, "can_add_long": True, "can_add_short": True, "block_reason": ""}
        for s in SYMBOLS
    }
    for pos in positions:
        symbol = pos.get("instId", "")
        side = pos.get("posSide", "")  # "long" or "short"
        sz = float(pos.get("pos", 0))
        if symbol not in per_symbol or sz == 0:
            continue
        if side == "long":
            per_symbol[symbol]["has_long"] = True
        elif side == "short":
            per_symbol[symbol]["has_short"] = True

    # Apply hedge conflict rule
    for symbol, info in per_symbol.items():
        if info["has_long"] and info["has_short"]:
            info["can_add_long"] = False
            info["can_add_short"] = False
            info["block_reason"] = "HEDGE_CONFLICT"
        elif info["has_long"]:
            # Can add more long (pyramid), cannot open short (would hedge)
            info["can_add_short"] = False
            info["block_reason"] = ""  # long add-on is fine
        elif info["has_short"]:
            # Can add more short (pyramid), cannot open long (would hedge)
            info["can_add_long"] = False
            info["block_reason"] = ""

    return per_symbol


def count_open_symbols(positions: list) -> list:
    """Return list of distinct symbols with non-zero positions."""
    symbols = set()
    for pos in positions:
        if float(pos.get("pos", 0)) != 0:
            symbols.add(pos.get("instId", ""))
    return list(symbols)


def check(positions: list, candidate_symbol: str, candidate_side: str,
          account_equity: float, daily_drawdown: float) -> dict:
    """
    Run full risk check.

    candidate_side: "buy" (long) or "sell" (short)
    Returns account_risk_check dict.
    """
    per_symbol = build_per_symbol(positions)
    open_symbols = count_open_symbols(positions)
    open_count = len(open_symbols)

    risk_check_passed = True
    block_reason = ""
    hedge_conflict = False

    # 1. Daily drawdown
    if daily_drawdown >= DAILY_DRAWDOWN_LIMIT:
        risk_check_passed = False
        block_reason = "DAILY_DRAWDOWN_LIMIT"

    # 2. Hedge conflict for candidate
    if risk_check_passed:
        sym_info = per_symbol.get(candidate_symbol, {})
        if candidate_side == "buy" and not sym_info.get("can_add_long", True):
            risk_check_passed = False
            block_reason = sym_info.get("block_reason", "HEDGE_CONFLICT")
            hedge_conflict = True
        elif candidate_side == "sell" and not sym_info.get("can_add_short", True):
            risk_check_passed = False
            block_reason = sym_info.get("block_reason", "HEDGE_CONFLICT")
            hedge_conflict = True

    # 3. Max open symbols check
    # Allow if: candidate symbol is already open (add-on), OR open_count < MAX
    if risk_check_passed:
        candidate_already_open = candidate_symbol in open_symbols
        if not candidate_already_open and open_count >= MAX_OPEN_SYMBOLS:
            risk_check_passed = False
            block_reason = "MAX_POSITIONS_REACHED"

    return {
        "account_equity": account_equity,
        "open_positions": open_symbols,
        "open_position_count": open_count,
        "daily_drawdown": daily_drawdown,
        "hedge_conflict": hedge_conflict,
        "risk_check_passed": risk_check_passed,
        "position_rules": {
            "max_open_positions": MAX_OPEN_SYMBOLS,
            "allow_add_on_existing": True,
            "allow_cross_symbol": True
        },
        "per_symbol_check": per_symbol,
        "block_reason": block_reason,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def main():
    positions_data = load_json("position_list.json")
    candidate_data = load_json("candidate.json")

    positions = positions_data.get("positions", [])
    account_equity = positions_data.get("account_equity", 0)
    daily_drawdown = positions_data.get("daily_drawdown", 0)

    candidate_symbol = candidate_data["symbol"]
    candidate_side = candidate_data["side"]  # "buy" or "sell"

    result = check(
        positions=positions,
        candidate_symbol=candidate_symbol,
        candidate_side=candidate_side,
        account_equity=account_equity,
        daily_drawdown=daily_drawdown,
    )

    with open("account_risk_check.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("risk_check_passed:", result["risk_check_passed"])
    if not result["risk_check_passed"]:
        print("block_reason:", result["block_reason"])


if __name__ == "__main__":
    main()
