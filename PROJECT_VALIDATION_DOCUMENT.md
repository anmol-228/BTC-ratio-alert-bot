# Project Validation Document — BTC Ratio Alert Bot

Last updated: 2026-06-26

## Purpose

Validate the implemented logic for the Delta Exchange BTC options Telegram alert bot.

The system is alert-only. It never places trades and never uses private Delta API credentials.

## Market Data

- Exchange: Delta Exchange
- Asset: BTC only
- Data source: public REST endpoints
- Expiries: all active BTC option expiries
- Pricing fields:
  - buy leg: `best_ask`
  - sell leg: `best_bid`
  - fallback: `mark_price` if bid/ask is missing and fallback is enabled

Raw Delta quote prices are used directly. `contract_value`, fees, slippage, margin, and liquidation checks are not applied.

## Active Strategy

Only call ratio spreads are enabled now.

```toml
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
```

## Candidate Direction

For calls:

```text
spot_price < buy_call_strike < sell_call_strike
```

Puts are disabled in config.

## Net Inflow

```text
net_inflow = (ratio * sell_price) - buy_price
```

Alert condition:

```text
20 <= net_inflow <= 100
```

## Sell Premium Cap Relative To Buy

The sell-leg premium must be no more than 60% of the buy-leg premium.

```text
sell_price <= buy_price * 0.60
```

If the sell premium is more than 60% of the buy premium, the opportunity is skipped.

## Strike Difference

The strike gap is configurable.

Current live config:

```toml
min_strike_difference = 0
max_strike_difference = 0
```

`max_strike_difference = 0` means no upper cap. This allows gaps below 2000 and above 20000.

## OTM Distance

The buy leg must be at least 2000 points away from BTC spot.

Because sell calls must be farther OTM than buy calls, the sell strike is naturally farther from spot.

Alert display uses:

```text
min(buy_distance, sell_distance)
```

## Negative ATM Same-Gap Rule

Every alert candidate must pass a same-gap, same-ratio ATM check.

Example:

```text
BTC ATM: 65000
Candidate: buy 69000 CE, sell 72000 CE
Gap: 3000
Ratio: 1:7
```

The bot checks:

```text
ATM buy: 65000 CE
ATM sell: 68000 CE
Same ratio: 1:7
```

The candidate alerts only if this ATM reference spread is negative.

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

## Deduplication

Dedupe key:

```text
underlying | strategy_type | expiry | ratio | buy_symbol | sell_symbol
```

Cooldown:

```toml
cooldown_seconds = 900
```

Same setup re-alerts during cooldown only if net inflow improves by at least `$20`.

## Tests

The test suite covers:

- dynamic ratios
- net inflow min/max range
- call direction
- put behavior as an internal capability
- raw premium calculation
- bid/ask and mark fallback pricing
- negative ATM same-gap confirmation
- sell premium cap relative to buy premium
- cooldown and re-alert behavior
- Telegram dry-run and missing credentials behavior
- health check behavior

Run:

```bash
python3 -m compileall delta_ratio_bot tests
python3 -m unittest discover -s tests
```
