# Live Settings

This bot is an alert-only Delta Exchange BTC options scanner. It sends Telegram alerts only; it does not place trades or use private Delta API keys.

## Current Scope

- Asset: BTC only
- Market data: REST polling only
- Strategy side: CALL ratio spreads only
- Put ratio spreads: disabled for now
- Ratios: `1:3` through `1:8`
- Expiries: all active BTC option expiries
- Telegram: sends to configured group/chat when credentials are present

## Active Strategy Filters

```toml
[strategy]
enable_calls = true
enable_puts = false
ratio_min = 3
ratio_max = 8
min_net_inflow_usd = 20
max_net_inflow_usd = 100
min_strike_difference = 0
max_strike_difference = 0
min_otm_distance = 2000
max_sell_premium_percent_of_buy = 60
require_negative_atm_spread = true
premium_mode = "bid_ask"
fallback_to_mark_price = true
require_bid_ask = false
premium_multiplier_mode = "raw"
```

## Alert Conditions

An alert is sent only when all conditions pass:

1. Candidate is a call ratio spread.
2. `spot_price < buy_call_strike < sell_call_strike`.
3. Buy leg is at least `2000` points above BTC spot.
4. Sell-leg premium is no more than `60%` of the buy-leg premium.
5. Net inflow is from `$20` to `$100`.
6. Strike difference has no fixed minimum or maximum by default.
7. The same-gap, same-ratio ATM reference spread is negative.

Formula:

```text
net_inflow = (ratio * sell_price) - buy_price
```

Premium ratio rule:

```text
sell_price <= buy_price * 0.60
```

Pricing:

- Buy leg uses best ask.
- Sell leg uses best bid.
- If bid/ask is missing and fallback is enabled, mark price is used.
- Raw Delta quote prices are used directly.
- No contract multiplier, fees, slippage, margin, or risk checks are applied.

## Negative ATM Same-Gap Rule

If a candidate uses a 3000-point gap and ratio `1:7`, the bot checks the ATM spread with the same 3000-point gap and same `1:7` ratio.

Example:

```text
Candidate: buy 69000 CE, sell 72000 CE, ratio 1:7
ATM check: buy 65000 CE, sell 68000 CE, ratio 1:7
```

The candidate alerts only if the ATM check has negative net inflow.

## Alert Format

```text
Trade Opportunity Detected

Strategy Type:
CALL 🟩

Expiry: 03 July 2026
Ratio: 1:7

Net Credit/Inflow:
+$50

Buy:
1x BTC 60,000 CE @ $90
Sell:
7x BTC 73,000 CE @ $20

Strike Difference: 3000

Distance From Spot:
2,774.50 points OTM

BTC Spot Price:
$62,774.5
```

## Alerts And Cooldown

```toml
cooldown_seconds = 900
realert_if_inflow_improves = true
realert_if_inflow_improves_by = 20
max_alerts_per_scan = 0
```

- Duplicate cooldown is 15 minutes.
- Same setup can re-alert during cooldown only if net inflow improves by at least `$20`.
- `max_alerts_per_scan = 0` means no per-scan limit.

## Run Commands

```bash
python3 -m delta_ratio_bot --config config.toml --health-check
python3 -m delta_ratio_bot --config config.toml --test-telegram
python3 -m delta_ratio_bot --config config.toml --once
python3 -m delta_ratio_bot --config config.toml
```

Local dry-run demo:

```bash
python3 -m delta_ratio_bot --config config.local-demo.toml --once
```

## Limitations

1. REST API availability and rate limits can affect scan cycles.
2. No liquidity filters are enforced.
3. No trading, margin, fee, slippage, or liquidation checks are included.
4. Ratio spreads carry tail risk; this bot only sends alerts.
