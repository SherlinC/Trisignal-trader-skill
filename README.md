# TriSignal Trader V4.3 Lite

> **投资有风险，谨慎前行。本项目仅供学习与研究，不构成任何投资建议。使用本策略造成的任何损失，作者概不负责。**

A lightweight 4-hour crypto perpetual trading skill for [Claude Code](https://claude.ai/code). It evaluates BTC, ETH, SOL, and XRP USDT perpetual swaps using structured multi-signal scoring, then outputs only `open`, `watch`, or `skip` each cycle.

---

## Features

- 4H cycle execution on BTC/ETH/SOL/XRP-USDT-SWAP
- 7-dimension scoring: MA structure, MACD, price structure, OI, funding, ATR, event signal
- Long and short support
- Risk-based position sizing (3% equity per trade)
- Automatic stop-loss placement after entry
- Account-level risk checks: max 2 open symbols, hedge conflict detection, daily drawdown limit
- Add-on / pyramid support for existing positions
- Run lock to prevent cron re-entry
- Paper / shadow / live execution modes
- Structured decision snapshots and trade records for daily review

---

## File Structure

```
main.py                  # Orchestrator — runs the full cycle
score_assets.py          # Scoring engine (reads market_input.json)
calc_position_size.py    # Position sizing
account_risk_check.py    # Account-level risk validation
daily_review.py          # Daily summary aggregator
run_lock.py              # Run lock (Python)
lock.sh                  # Run lock (bash)
strategy_params.json     # All tunable parameters
SKILL.md                 # Full strategy specification
```

---

## Quickstart

### Requirements

- [Claude Code](https://claude.ai/code) with OKX MCP tools configured
- OKX account with API credentials (`okx config init`)

### Run manually

```bash
cd trisignal-trader
python3 main.py --mode paper --profile okx-demo
```

### Schedule (every 4 hours via Claude Code cron)

In a Claude Code session:
```
Run TriSignal Trader every 4 hours starting at 11:00 Beijing time
```

---

## Execution Modes

| Mode | Behavior |
|---|---|
| `paper` | Full analysis + real orders on demo account |
| `shadow` | Full analysis, no orders |
| `live` | Full analysis + real orders on live account |

Default is `paper`. Switch to `live` only after validating paper performance.

---

## Hard Constraints (not adjustable)

- Max risk per trade: 3% of account equity
- Daily drawdown limit: 8%
- Max simultaneous open symbols: 2
- No hedge positions
- Stop-loss required immediately after every entry
- Order type: market, tag: `agentTradeKit`

---

## Disclaimer

This is an experimental algorithmic trading strategy. Crypto markets are highly volatile. Past paper performance does not guarantee future live results. Always start with small capital and monitor closely.
