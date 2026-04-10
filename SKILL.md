---
name: TriSignal Trader V4.3 Lite
description: A lightweight 4-hour crypto perpetual trading skill for Claude Code. It evaluates BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP, and XRP-USDT-SWAP using structured scores from moving averages, MACD, price structure, OI, funding, ATR, and optional event signals, then selects one best candidate and outputs only open, watch, or skip. Default mode is paper trading. Use this skill whenever the user wants to run, simulate, debug, or iterate a 4h BTC/ETH/SOL/XRP strategy with position sizing, stop-loss, and structured trade logs.
compatibility:
  tools:
    - market_get_candles
    - market_get_funding_rate
    - market_get_open_interest
    - swap_place_order
    - swap_place_algo_order
---

# TriSignal Trader V4.2 Lite

## Goal
Run every `4 hours` and evaluate:

- `BTC-USDT-SWAP`
- `ETH-USDT-SWAP`
- `SOL-USDT-SWAP`
- `XRP-USDT-SWAP`

Select at most one best candidate per cycle and output only:

- `open`
- `watch`
- `skip`

Default mode is `paper`.

---

## Run Lock

Each cycle must acquire a run lock before executing. If the lock is held (previous run still active), skip this cycle entirely.

Use `run_lock.py`:
- Call `acquire_lock()` at the very start — if it returns `False`, exit immediately
- Call `release_lock()` in a `finally` block to ensure cleanup
- Stale locks older than 1 hour are auto-expired

---

## Hard Constraints
These rules are fixed and must not be changed by daily review or local optimization:

1. Execute every `4 hours`
2. Symbols are fixed:
   - `BTC-USDT-SWAP`
   - `ETH-USDT-SWAP`
   - `SOL-USDT-SWAP`
   - `XRP-USDT-SWAP`
3. Final status can only be:
   - `open`
   - `watch`
   - `skip`
4. If placing an order:
   - `ordType = "market"`
   - `tag = "agentTradeKit"`
5. Stop-loss must be set immediately after entry
6. Max risk per trade = account equity × `3%`
7. Stop opening new positions if daily drawdown exceeds `8%`
8. Max simultaneous open symbols = `2` (distinct symbols), with exceptions below
9. Hedged positions are not allowed (same symbol, opposite direction)

## Position Rules

These rules govern whether a new open is allowed. Use `account_risk_check.py` to evaluate.

| Scenario | Allowed? | Reason |
|---|---|---|
| Same symbol, same direction | Yes | Add-on / pyramid |
| Same symbol, opposite direction | No | HEDGE_CONFLICT |
| New symbol, already 2 distinct open | No | MAX_POSITIONS_REACHED |
| Existing symbol, already 2 distinct open | Yes | Add-on exception |
| Different symbols (e.g. ETH short + SOL long) | Yes | Cross-symbol allowed |

Input files: `position_list.json` + `candidate.json`
Output file: `account_risk_check.json`

---

## Execution Mode

### paper
Default mode.
- Run full analysis
- Calculate scores
- Calculate `sz`
- Produce `decision_snapshot`
- If decision is `open`, produce `trade_record`
- Do not rely on real execution outcome as the main objective

### shadow
- Run full analysis and simulated execution path
- Keep full structured logs
- Used before live mode

### live
- Use only after paper/shadow is stable
- Must obey all hard constraints

If mode is not explicitly set, use `paper`.

---

## Fast Execution Workflow

### Step 1: Get market data
For each symbol:
- fetch `4h` candles
- calculate:
  - `MA5`
  - `MA10`
  - `MA20`
  - `MA60`
  - `MACD`
  - `ATR(14)`

If one symbol fails, skip that symbol and continue.  
If all symbols fail, output `skip`.

---

### Step 2: Get sentiment data
For each available symbol:
- fetch funding rate
- fetch open interest

Event signal is optional.  
Do not block execution if event data is missing.

---

### Step 3: Apply selection principle

Selection priority:

1. Prefer the symbol with the clearest trend and highest structured score
2. Support both long and short opportunities
3. Prefer MA structure and MACD resonance first
4. Use OI, funding, ATR, event signals as adjustment layers
5. Soft problems should usually reduce score or reduce size, not immediately hard reject
6. Hard risk conditions must still block opening

Preferred flow:
1. Use `score_assets.py`
2. Read:
   - total score
   - score breakdown
   - soft flags
   - hard flags
   - best symbol
   - second symbol
   - score gap
   - entry tier

Only use model judgment for edge cases.

---

### Step 4: Candidate selection
Use the scored result to determine:

- `strong_entry`
- `conservative_entry`
- `no_trade`

Rules:
- If strongest candidate is clearly best and hard constraints pass, prefer `open`
- If best candidate has moderate quality but still tradable, prefer `open` with conservative sizing
- If structured score is weak or hard reject exists, use `watch` or `skip`

If score gap between first and second is small:
- prefer reduced size
- do not automatically reject
- only use `watch` if the structural advantage is unclear

---

### Step 5: Position sizing

## Long / Short Execution Rules

This skill supports both long and short trading.

### Direction Mapping

- If MA structure is bullish and MACD confirms, direction = `buy`
- If MA structure is bearish and MACD confirms, direction = `sell`
- If direction is unclear, final decision must be `watch` or `skip`, not `open`

### Entry Side Rules

- `buy` means opening a long position
- `sell` means opening a short position

The final decision output must always include:

- `symbol`
- `side`
- `entry_price`
- `stop_loss_price`

### Stop-Loss Rules

For long positions:

- `stop_loss_price = entry_price × (1 - stop_loss_pct_long)`

For short positions:

- `stop_loss_price = entry_price × (1 + stop_loss_pct_short)`

This means:

- long stop-loss must be below entry
- short stop-loss must be above entry

If the stop-loss direction is wrong, reject opening and record:

- `STOPLOSS_SETUP_RISK`

### Position Size Rules

Use the same sizing formula for both long and short:

- `risk_budget = account_equity × 0.03`
- `unit_risk = abs(entry_price - stop_loss_price)`
- `sz = risk_budget / unit_risk`

Because `unit_risk` uses absolute difference, the same formula works for both long and short.

Use `calc_position_size.py` instead of reasoning manually.

If candidate is `conservative_entry`, reduce effective risk budget using a risk multiplier.

If sizing fails:
- do not open
- output `skip`

### Order Placement Rules

When opening a long position:

- `side = "buy"`

When opening a short position:

- `side = "sell"`

All opening orders must still use:

- `ordType = "market"`
- `tag = "agentTradeKit"`

### Logging Rules

Every decision snapshot and trade record must include the actual side:

- `buy`
- `sell`

Do not leave side empty.

If a short setup is selected but execution fields are inconsistent, reject opening and record the relevant reason code.

---

### Step 6: Final decision
Final decision must be one of:

- `open`
- `watch`
- `skip`

#### open
Use only if:
- best symbol is clear enough
- hard constraints pass
- `sz` is valid
- stop-loss can be defined

#### watch
Use if:
- candidate exists but confidence is moderate
- score gap is too small
- soft penalties are too heavy
- best symbol is tradable but not attractive enough yet

#### skip
Use if:
- no usable symbols
- hard reject exists
- sizing fails
- account-level risk blocks new entries

---

### Step 7: Order rule
Only if final decision is `open`:

- `instId` = selected symbol
- `side` = `buy` or `sell`
- `ordType` = `"market"`
- `sz` = calculated size
- `tag` = `"agentTradeKit"`

If `tag` is missing, order is invalid.

---

### Step 8: Stop-loss rule
After successful open:
- immediately set stop-loss

Rules:
- long: entry × `0.98`
- short: entry × `1.02`

If stop-loss setup fails:
- record failure
- surface clearly in output
- do not ignore silently

---

## Soft Reject vs Hard Reject

### Soft reject
These should usually reduce score or reduce size, not automatically block trading:
- mild funding crowding
- mildly high ATR
- mildly low ATR
- weak OI confirmation
- missing event signal
- small score gap
- minor structure imperfection

### Hard reject
These must block opening:
- account equity unavailable
- size invalid
- daily drawdown limit hit
- max open positions hit
- hedge conflict
- all key data missing
- stop-loss cannot be defined
- extreme funding + extreme OI crowding + stretched structure
- extreme ATR abnormality
- completely unclear trend structure

---

## Logging Requirements

### decision_snapshot
Each cycle must generate a structured `decision_snapshot` with:
- timestamp
- mode
- timeframe
- scores for BTC / ETH / SOL
- best symbol
- second symbol
- score gap
- entry tier
- final decision
- reason codes
- hard reject / soft reject flags
- risk check result
- size result

### trade_record
If final decision is `open`, also generate `trade_record` with:
- symbol
- side
- entry tier
- score at entry
- score gap
- entry price
- stop-loss price
- `sz`
- `ordType`
- `tag`
- order status
- stop-loss status
- reason codes

---

## Daily Activity Target

This skill should be active enough for paper trading, while still respecting hard risk controls.

Operational target:

- under normal market conditions, aim for at least `1` valid trade per day
- allow up to `2` traded symbols per day
- do not force a trade if hard constraints are not satisfied

This is a target, not a force-trade rule.

---

## Daily Review Boundary
Daily review may:
- summarize trade frequency
- summarize reason codes
- identify whether thresholds are too strict
- suggest score or penalty adjustments

Daily review must not automatically change:
- 4-hour execution frequency
- required tag
- order type
- max risk per trade
- daily drawdown limit
- max open positions
- hedge prohibition
- mandatory stop-loss

---

## Execution Principle

Use scripts for deterministic work.
Use the model only for final structured judgment, exception handling, and logging.
Keep output short.
Support both long and short setups.
Do not break hard risk controls in order to increase trade frequency.

---

## Output Format
Use short output by default.

# Trade Run Summary
- Time:
- Mode:
- Timeframe: 4h

## Scores
- BTC-USDT-SWAP:
- ETH-USDT-SWAP:
- SOL-USDT-SWAP:

## Selection
- Best Symbol:
- Second Symbol:
- Score Gap:
- Entry Tier:

## Decision
- Final Decision: open / watch / skip
- Side:
- Size:
- Entry Price:
- Stop Loss:
- Reason Codes:

## Execution
- Order Type: market
- Tag: agentTradeKit
- Order Status:
- Stoploss Status:

Only expand into long-form reasoning when the user explicitly asks, or when an exception occurs.

---

## Execution Style
- Prefer fast structured execution
- Avoid long repeated explanations
- Use scripts for deterministic calculations
- Use model judgment only for edge cases
- Default to short output
- Do not re-explain the full strategy every cycle
