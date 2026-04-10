#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json


def calc_position_size(account_equity, entry_price, stop_loss_price, risk_pct,
                       min_order_size, max_order_size, risk_multiplier=1.0):
    if account_equity is None or account_equity <= 0:
        return {
            "status": "error",
            "reason_code": "NET_VALUE_UNAVAILABLE",
            "risk_budget": 0,
            "unit_risk": 0,
            "raw_sz": 0,
            "final_sz": 0
        }

    unit_risk = abs(entry_price - stop_loss_price)
    if unit_risk <= 0:
        return {
            "status": "error",
            "reason_code": "UNIT_RISK_INVALID",
            "risk_budget": 0,
            "unit_risk": unit_risk,
            "raw_sz": 0,
            "final_sz": 0
        }

    risk_budget = account_equity * risk_pct * risk_multiplier
    raw_sz = risk_budget / unit_risk

    if raw_sz <= 0:
        return {
            "status": "error",
            "reason_code": "SZ_INVALID",
            "risk_budget": risk_budget,
            "unit_risk": unit_risk,
            "raw_sz": raw_sz,
            "final_sz": 0
        }

    if raw_sz < min_order_size:
        return {
            "status": "error",
            "reason_code": "SZ_TOO_SMALL",
            "risk_budget": risk_budget,
            "unit_risk": unit_risk,
            "raw_sz": raw_sz,
            "final_sz": 0
        }

    final_sz = int(raw_sz)  # SWAP contracts require integer lot size
    reason_code = None
    status = "ok"

    if final_sz < min_order_size:
        return {
            "status": "error",
            "reason_code": "SZ_TOO_SMALL",
            "risk_budget": risk_budget,
            "unit_risk": unit_risk,
            "raw_sz": raw_sz,
            "final_sz": 0
        }

    if raw_sz > max_order_size:
        final_sz = int(max_order_size)
        reason_code = "SZ_TOO_LARGE_CAPPED"
        status = "ok"

    return {
        "status": status,
        "reason_code": reason_code,
        "risk_budget": risk_budget,
        "unit_risk": unit_risk,
        "raw_sz": raw_sz,
        "final_sz": final_sz
    }


def main():
    with open("position_input.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    result = calc_position_size(
        account_equity=data["account_equity"],
        entry_price=data["entry_price"],
        stop_loss_price=data["stop_loss_price"],
        risk_pct=data.get("risk_pct", 0.03),
        min_order_size=data.get("min_order_size", 0.001),
        max_order_size=data.get("max_order_size", 1000000),
        risk_multiplier=data.get("risk_multiplier", 1.0)
    )

    with open("position_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
