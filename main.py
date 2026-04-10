#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — TriSignal Trader V4.3 Lite orchestrator

Ties together: lock → data → score → risk check → sizing → order → stoploss → log

Run:
    cd /Users/bytedance/Documents/claude/okx/.claude/skills/trisignal-trader
    python3 main.py [--mode paper|shadow|live] [--profile okx-demo|okx-live]
"""

import json
import os
import sys
import subprocess
import math
from datetime import datetime, timezone

from run_lock import acquire_lock, release_lock
from score_assets import score_one_asset, select_candidate, load_params
from calc_position_size import calc_position_size
from account_risk_check import check as risk_check

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def okx(args: list, profile: str) -> dict:
    """Run an okx CLI command and return parsed JSON output."""
    cmd = ["okx", "--profile", profile] + args + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"okx command failed: {' '.join(cmd)}\n{result.stderr}")
    return json.loads(result.stdout)


def fetch_candles(symbol: str, profile: str) -> list:
    result = subprocess.run(
        ["okx", "--profile", profile, "market", "candles", symbol, "--bar", "4H", "--limit", "80", "--json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    data = json.loads(result.stdout)
    # CLI returns either a list directly or {"data": [...]}
    return data if isinstance(data, list) else data.get("data", [])


def calc_indicators(candles: list) -> dict:
    """Calculate MA5/10/20/60, MACD, ATR from raw candle data."""
    closes = [float(c[4]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]

    def sma(n):
        return sum(closes[-n:]) / n if len(closes) >= n else 0

    def ema(values, period):
        k = 2 / (period + 1)
        e = values[0]
        for v in values[1:]:
            e = v * k + e * (1 - k)
        return e

    ma5 = sma(5)
    ma10 = sma(10)
    ma20 = sma(20)
    ma60 = sma(60)

    ema12 = ema(closes[-33:], 12) if len(closes) >= 33 else 0
    ema26 = ema(closes[-33:], 26) if len(closes) >= 33 else 0
    dif = ema12 - ema26

    # Approximate DEA from last 9 DIF values (simplified)
    dea = dif * 0.8  # fallback; full calculation needs historical DIFs
    hist = (dif - dea) * 2

    # ATR(14)
    trs = []
    for i in range(1, min(15, len(candles))):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    atr_ratio = atr / closes[-1] if closes[-1] > 0 else 0

    return {
        "close": closes[-1],
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "macd_dif": dif, "macd_dea": dea, "macd_hist": hist,
        "atr_ratio": atr_ratio,
    }


def fetch_sentiment(symbol: str, profile: str) -> dict:
    funding_rate = 0.0
    oi_change_pct = 0.0
    try:
        result = subprocess.run(
            ["okx", "--profile", profile, "market", "funding-rate", symbol, "--json"],
            capture_output=True, text=True
        )
        fr = json.loads(result.stdout)
        fr_list = fr if isinstance(fr, list) else fr.get("data", [])
        funding_rate = float(fr_list[0].get("fundingRate", 0)) if fr_list else 0.0
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["okx", "--profile", profile, "market", "open-interest", "--instType", "SWAP", "--instId", symbol, "--json"],
            capture_output=True, text=True
        )
        oi = json.loads(result.stdout)
        oi_list = oi if isinstance(oi, list) else oi.get("data", [])
        if len(oi_list) >= 2:
            oi_now = float(oi_list[0].get("oi", 0))
            oi_prev = float(oi_list[1].get("oi", 1))
            oi_change_pct = (oi_now - oi_prev) / oi_prev * 100 if oi_prev else 0
    except Exception:
        pass
    return {"funding_rate": funding_rate, "oi_change_pct": oi_change_pct}


def get_account(profile: str) -> tuple:
    """Returns (equity, positions, daily_drawdown)."""
    equity = 0
    try:
        result = subprocess.run(
            ["okx", "--profile", profile, "account", "balance", "USDT", "--json"],
            capture_output=True, text=True
        )
        bal = json.loads(result.stdout)
        bal_list = bal if isinstance(bal, list) else bal.get("data", [])
        if bal_list:
            details = bal_list[0].get("details", [])
            equity = float(details[0].get("eq", 0)) if details else 0
    except Exception:
        pass

    positions = []
    try:
        result = subprocess.run(
            ["okx", "--profile", profile, "account", "positions", "--instType", "SWAP", "--json"],
            capture_output=True, text=True
        )
        pos_raw = json.loads(result.stdout)
        positions = pos_raw if isinstance(pos_raw, list) else pos_raw.get("data", [])
    except Exception:
        pass

    daily_drawdown = 0.0
    return equity, positions, daily_drawdown


def place_order(symbol: str, side: str, sz: int, profile: str) -> dict:
    pos_side = "long" if side == "buy" else "short"
    try:
        result = subprocess.run(
            ["okx", "--profile", profile, "swap", "place",
             "--instId", symbol,
             "--tdMode", "isolated",
             "--side", side,
             "--posSide", pos_side,
             "--ordType", "market",
             "--sz", str(sz),
             "--tag", "agentTradeKit"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return {"status": "failed", "error": result.stderr.strip()}
        out = result.stdout.strip()
        return {"status": "success", "data": json.loads(out) if out and out.startswith("{") else out}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def place_stoploss(symbol: str, side: str, sz: int, sl_price: float, profile: str) -> dict:
    close_side = "sell" if side == "buy" else "buy"
    pos_side = "long" if side == "buy" else "short"
    try:
        result = subprocess.run(
            ["okx", "--profile", profile, "swap", "algo", "place",
             "--instId", symbol,
             "--tdMode", "isolated",
             "--side", close_side,
             "--posSide", pos_side,
             "--sz", str(sz),
             "--slTriggerPx", str(round(sl_price, 4)),
             "--slOrdPx=-1"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return {"status": "failed", "error": result.stderr}
        out = result.stdout.strip()
        if not out:
            return {"status": "success", "data": {}}
        return {"status": "success", "data": json.loads(out) if out.startswith(("{", "[")) else out}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=None)
    parser.add_argument("--profile", default="okx-demo")
    args = parser.parse_args()

    os.chdir(SKILL_DIR)

    # --- Run lock ---
    if not acquire_lock():
        sys.exit(0)

    try:
        params = load_params()
        mode = args.mode or params.get("mode", "paper")
        profile = args.profile
        symbols = params.get("symbols", SYMBOLS)
        now = datetime.now(timezone.utc)
        ts = now.isoformat()

        print(f"[{ts}] TriSignal Trader V4.3 Lite | mode={mode} | profile={profile}")

        # --- Step 1: Fetch market data ---
        assets = []
        for symbol in symbols:
            try:
                candles = fetch_candles(symbol, profile)
                if len(candles) < 20:
                    print(f"  {symbol}: insufficient candles ({len(candles)}), skipping")
                    continue
                indicators = calc_indicators(candles)
                sentiment = fetch_sentiment(symbol, profile)
                asset = {
                    "symbol": symbol,
                    "data_ok": True,
                    "price_change_pct": (indicators["close"] - float(candles[1][4])) / float(candles[1][4]) if len(candles) > 1 else 0,
                    "oi_divergence": False,
                    "event_bias": "neutral",
                    **indicators,
                    **sentiment,
                }
                assets.append(asset)
                print(f"  {symbol}: close={indicators['close']:.4f} ma5={indicators['ma5']:.4f} atr_ratio={indicators['atr_ratio']:.4f}")
            except Exception as e:
                print(f"  {symbol}: data fetch failed — {e}")

        if not assets:
            print("All symbols failed. Outputting skip.")
            _write_snapshot(ts, mode, [], {}, "skip", ["DATA_MISSING"], None, None)
            return

        # Save market_input.json for audit
        save_json("market_input.json", {"timestamp": ts, "timeframe": "4h", "assets": assets})

        # --- Step 2: Score ---
        scored = [score_one_asset(a) for a in assets]
        ranking = select_candidate(scored, params)
        print(f"  Best: {ranking['best_symbol']} {ranking['best_score']} ({ranking['best_direction']}) | Gap: {ranking['score_gap']} | Tier: {ranking['entry_tier']}")

        # --- Step 3: Account risk check ---
        equity, positions, daily_drawdown = get_account(profile)
        candidate_symbol = ranking["best_symbol"]
        candidate_side = ranking["best_direction"]  # "buy" or "sell"
        symbol_rules = params.get("symbol_rules", {})

        # BTC (or any score_only symbol): skip trading, output watch
        if symbol_rules.get(candidate_symbol, {}).get("score_only", False):
            print(f"  {candidate_symbol} is score-only (trade_enabled=false), outputting watch")
            _write_snapshot(ts, mode, scored, ranking, "watch", ["SCORE_ONLY"], None, None)
            return

        arc = risk_check(
            positions=positions,
            candidate_symbol=candidate_symbol,
            candidate_side=candidate_side,
            account_equity=equity,
            daily_drawdown=daily_drawdown,
        )
        save_json("account_risk_check.json", arc)

        if not arc["risk_check_passed"]:
            print(f"  Risk check failed: {arc['block_reason']}")
            _write_snapshot(ts, mode, scored, ranking, "skip", [arc["block_reason"]], arc, None)
            return

        candidate_decision = ranking["candidate_decision"]
        if candidate_decision != "open":
            print(f"  Decision: {candidate_decision} (score insufficient)")
            _write_snapshot(ts, mode, scored, ranking, candidate_decision, [], arc, None)
            return

        # --- Check 1: Skip if already holding same symbol + same direction ---
        pos_side_map = {"buy": "long", "sell": "short"}
        existing_same = any(
            p.get("instId") == candidate_symbol
            and p.get("posSide") == pos_side_map[candidate_side]
            and float(p.get("pos", 0)) != 0
            for p in positions
        )
        if existing_same:
            print(f"  Already holding {candidate_symbol} {candidate_side}, skipping (no pyramid this cycle)")
            _write_snapshot(ts, mode, scored, ranking, "watch", ["EXISTING_POSITION_SAME_SIDE"], arc, None)
            return

        # --- Step 4: Position sizing ---
        hard = params.get("hard_constraints", {})
        pos_rules = params.get("position_rules", {})
        risk_pct = hard.get("risk_per_trade", 0.03)
        sl_pct = hard.get("stop_loss_pct_long", 0.02) if candidate_side == "buy" else hard.get("stop_loss_pct_short", 0.02)
        risk_multiplier = pos_rules.get("strong_entry_risk_multiplier", 1.0) if ranking["entry_tier"] == "strong_entry" else pos_rules.get("conservative_entry_risk_multiplier", 1.0)

        # Soft rule: DOGE conservative_entry capped at 0.5x
        sym_rule = symbol_rules.get(candidate_symbol, {})
        if ranking["entry_tier"] == "conservative_entry":
            max_multiplier = sym_rule.get("conservative_entry_risk_multiplier_max", risk_multiplier)
            risk_multiplier = min(risk_multiplier, max_multiplier)

        entry_price = assets[[a["symbol"] for a in assets].index(candidate_symbol)]["close"]
        sl_price = entry_price * (1 - sl_pct) if candidate_side == "buy" else entry_price * (1 + sl_pct)

        sizing = calc_position_size(
            account_equity=equity,
            entry_price=entry_price,
            stop_loss_price=sl_price,
            risk_pct=risk_pct,
            min_order_size=pos_rules.get("min_order_size", 1),
            max_order_size=pos_rules.get("max_order_size", 1000000),
            risk_multiplier=risk_multiplier,
        )
        save_json("position_output.json", sizing)

        if sizing["status"] != "ok":
            print(f"  Sizing failed: {sizing['reason_code']}")
            _write_snapshot(ts, mode, scored, ranking, "skip", [sizing["reason_code"]], arc, sizing)
            return

        sz = int(sizing["final_sz"])
        print(f"  Sizing: equity={equity} entry={entry_price} sl={sl_price:.4f} sz={sz}")

        # --- Step 5: Order + stoploss ---
        order_result = {"status": "skipped"}
        sl_result = {"status": "skipped"}

        if mode in ("paper", "live"):
            # Cap sz to account's actual max available size
            try:
                max_result = subprocess.run(
                    ["okx", "--profile", profile, "account", "max-size",
                     "--instId", candidate_symbol, "--tdMode", "isolated", "--json"],
                    capture_output=True, text=True
                )
                max_data = json.loads(max_result.stdout)
                max_list = max_data if isinstance(max_data, list) else max_data.get("data", [])
                if max_list:
                    max_key = "maxBuy" if candidate_side == "buy" else "maxSell"
                    max_avail = int(float(max_list[0].get(max_key, sz)))
                    if sz > max_avail:
                        print(f"  sz capped from {sz} to {max_avail} (account max-size)")
                        sz = max_avail
            except Exception:
                pass

            if sz <= 0:
                print(f"  sz=0 after cap, skipping")
                _write_snapshot(ts, mode, scored, ranking, "skip", ["SZ_TOO_SMALL"], arc, sizing)
                return

            order_result = place_order(candidate_symbol, candidate_side, sz, profile)
            print(f"  Order: {order_result['status']}")

            if order_result["status"] == "success":
                # Compute stop-loss price from current market price
                current_price = assets[[a["symbol"] for a in assets].index(candidate_symbol)]["close"]
                actual_sl = current_price * (1 - sl_pct) if candidate_side == "buy" else current_price * (1 + sl_pct)

                # Retry stop-loss up to 2 times
                sl_result = {"status": "failed"}
                for attempt in range(3):
                    sl_result = place_stoploss(candidate_symbol, candidate_side, sz, actual_sl, profile)
                    if sl_result["status"] == "success":
                        break
                    print(f"  Stoploss attempt {attempt+1} failed: {sl_result.get('error')}")
                    import time; time.sleep(1)

                print(f"  Stoploss: {sl_result['status']} (trigger={actual_sl:.4f})")

                # If stoploss still failed after retries — close position immediately
                if sl_result["status"] == "failed":
                    print(f"  CRITICAL: Stoploss failed after 3 attempts — closing position to protect capital")
                    close_side = "sell" if candidate_side == "buy" else "buy"
                    close_pos_side = "long" if candidate_side == "buy" else "short"
                    subprocess.run(
                        ["okx", "--profile", profile, "swap", "close",
                         "--instId", candidate_symbol, "--mgnMode", "isolated",
                         "--posSide", close_pos_side],
                        capture_output=True, text=True
                    )
                    order_result["status"] = "closed_no_stoploss"

        # --- Step 6: Log ---
        _write_snapshot(ts, mode, scored, ranking, "open", [], arc, sizing)
        _write_trade_record(ts, mode, candidate_symbol, candidate_side, ranking, entry_price, sl_price, sz, order_result, sl_result)

        print(f"\nDone. Decision: open | {candidate_symbol} {candidate_side} sz={sz}")

    finally:
        release_lock()


def _write_snapshot(ts, mode, scored, ranking, decision, reason_codes, arc, sizing):
    snap_dir = "decision_snapshots"
    os.makedirs(snap_dir, exist_ok=True)
    fname = f"{snap_dir}/snapshot_{ts[:19].replace(':', '').replace('-', '').replace('T', '_')}.json"
    save_json(fname, {
        "timestamp": ts,
        "mode": mode,
        "timeframe": "4h",
        "symbols": scored,
        "ranking": ranking,
        "final_decision": {
            "decision": decision,
            "symbol": ranking.get("best_symbol", "") if ranking else "",
            "side": ranking.get("best_direction", "") if ranking else "",
            "reason_codes": reason_codes,
        },
        "account_risk_check": arc,
        "position_sizing": sizing,
    })


def _write_trade_record(ts, mode, symbol, side, ranking, entry_price, sl_price, sz, order_result, sl_result):
    rec_dir = "trade_records"
    os.makedirs(rec_dir, exist_ok=True)
    fname = f"{rec_dir}/trade_{ts[:19].replace(':', '').replace('-', '').replace('T', '_')}.json"
    save_json(fname, {
        "timestamp": ts,
        "mode": mode,
        "symbol": symbol,
        "side": side,
        "entry_tier": ranking.get("entry_tier"),
        "score_at_entry": ranking.get("best_score"),
        "score_gap": ranking.get("score_gap"),
        "entry_price": entry_price,
        "stop_loss_price": sl_price,
        "sz": sz,
        "ord_type": "market",
        "tag": "agentTradeKit",
        "order_status": order_result.get("status"),
        "stoploss_status": sl_result.get("status"),
        "reason_codes": [],
    })


if __name__ == "__main__":
    main()
