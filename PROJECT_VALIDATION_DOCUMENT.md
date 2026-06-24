# Delta Exchange Options Ratio Alert Bot - Technical and Market Validation Document

Last updated: 2026-06-19

This document explains the current project exactly as implemented. Use it to validate whether the bot logic, market assumptions, risk assumptions, Delta Exchange data handling, and Telegram alert behavior match your intended trading workflow.

This is not financial advice. The bot is an alerting/scanning tool only. It does not place trades, size positions, verify margin, or guarantee executable fills.

> **AUTHORITATIVE CORRECTION (2026-06-23).** Some sections below were written against an
> earlier draft and reference `min_net_inflow_usd = 20`, an upper cap of `100`,
> `min_strike_difference = 0`, and a required negative ATM same-gap spread. The current
> **confirmed** live configuration is: `min_net_inflow_usd = 35` with a **strict** `>`
> threshold (35.00 does not alert, 35.01 does), **no** upper cap (`max_net_inflow_usd = 0`,
> send all matching), `min_strike_difference = 3000`, and `require_negative_atm_spread = false`.
> Where this document and **FINAL_HANDOVER.md** disagree, FINAL_HANDOVER.md is authoritative.
> The max-cap and ATM filters remain in the code as optional, disabled capabilities.

## 1. Project Purpose

The bot scans Delta Exchange crypto options and detects ratio spread opportunities.

Current supported underlying:

- BTC

Current configured underlying is in [config.toml](/Users/mypc/Documents/PUTAN/config.toml):

```toml
[delta]
underlying_assets = ["BTC"]
```

The main goal is to detect structures where:

- 1 option leg is bought.
- N option legs are sold.
- N is configurable.
- Net premium inflow is strictly greater than the configured threshold (default 35), with no upper cap.
- Buy and sell strikes are at least 3000 points apart.
- Strikes are out-of-the-money relative to the current spot/index price.
- Both selected strikes are at least 2000 BTC points away from spot.
- All available expiries are scanned.

## 2. Current Project Files

Main files:

- [delta_ratio_bot/app.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/app.py): runtime loop, BTC scanning, expiry scanning, alert dispatch.
- [delta_ratio_bot/config.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/config.py): TOML config loading and validation.
- [delta_ratio_bot/delta_client.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/delta_client.py): Delta Exchange REST client and market data parsing.
- [delta_ratio_bot/scanner.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/scanner.py): ratio spread filtering logic.
- [delta_ratio_bot/models.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/models.py): internal data models.
- [delta_ratio_bot/alerts.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/alerts.py): Telegram/dry-run alert formatting and cooldown dedupe.
- [config.toml](/Users/mypc/Documents/PUTAN/config.toml): live editable settings.
- [tests/test_scanner.py](/Users/mypc/Documents/PUTAN/tests/test_scanner.py): regression tests for ratio logic and Delta symbol expiry parsing.

## 3. Runtime Flow

The bot runs as:

```bash
python3 -m delta_ratio_bot --config config.toml
```

For a one-time dry scan:

```bash
python3 -m delta_ratio_bot --config config.toml --once
```

Runtime sequence:

1. Load config from TOML.
2. Create one async Delta REST client.
3. Create the alert dedupe cache.
4. For each configured coin, scan concurrently.
5. Fetch spot/index price.
6. Fetch active option expiries.
7. Fetch option tickers for each expiry.
8. Normalize Delta ticker rows into `OptionQuote` objects.
9. Scan calls and/or puts.
10. Evaluate all configured ratios.
11. Filter opportunities by net credit range, OTM rules, strike distance, and the negative ATM same-gap confirmation.
12. Sort matching opportunities by highest net inflow.
13. Send Telegram messages or print dry-run alerts.
14. Sleep for `scan_frequency_seconds`.
15. Repeat until stopped.

## 4. Delta Exchange Market Data Used

Base URL currently configured:

```toml
base_url = "https://api.delta.exchange"
```

The India endpoint can be used by changing:

```toml
base_url = "https://api.india.delta.exchange"
```

REST endpoints currently used:

- `/v2/indices`
- `/v2/products`
- `/v2/tickers`
- `/v2/tickers/{symbol}`

The bot uses REST only right now. WebSocket support is not implemented yet, but the code has a placeholder module:

- [delta_ratio_bot/websocket_source.py](/Users/mypc/Documents/PUTAN/delta_ratio_bot/websocket_source.py)

Data fields used from Delta ticker payloads:

- `symbol`
- `product_id`
- `contract_type`
- `strike_price`
- `mark_price`
- `spot_price`
- `quotes.best_bid`
- `quotes.best_ask`
- `underlying_asset_symbol`

Data fields observed but not yet used:

- `contract_value`
- `greeks`
- `mark_iv`, `bid_iv`, `ask_iv`
- `oi`, `oi_contracts`, `volume`
- `product_trading_status`
- `price_band`
- bid/ask size

## 5. Spot Price Logic

The bot tries to resolve spot/index price as follows:

1. Calls `/v2/indices`.
2. Finds an index symbol containing BTC.
3. Attempts `/v2/tickers/{index_symbol}`.
4. Uses the first available positive value among:
   - `mark_price`
   - `spot_price`
   - `close`
5. If that fails, fetches option tickers for the underlying and uses `spot_price` from the first ticker containing a positive value.

Important validation question:

- Confirm whether you want Delta index price, spot price from option tickers, mark index, or another specific Delta reference price.

Current behavior is pragmatic and works for scanning, but the exact reference price should be confirmed before production use.

## 6. Expiry Discovery Logic

The bot fetches expiries from `/v2/products` using:

```text
contract_types = call_options,put_options
states = live
page_size = 500
```

It filters products by underlying asset, then parses:

- `settlement_time`
- fallback `expiry`

If product expiry discovery fails, it falls back to parsing expiries from option ticker symbols.

Delta symbol expiry parsing supports:

- ISO-like dates such as `2026-05-29`
- Delta compact dates such as `270526`, interpreted as `27 May 2026`

Observed live symbol example:

```text
P-BTC-77200-270526
```

This parses as:

- Put option
- BTC underlying
- 77200 strike
- 27 May 2026 expiry

## 7. BTC-Only Underlying Logic

The active project configuration is BTC only:

```toml
[delta]
underlying_assets = ["BTC"]
```

The code can technically accept a list, but this project should be considered BTC-only unless you explicitly decide otherwise later.

For BTC:

1. Fetch spot.
2. Fetch expiries.
3. Fetch option chain per expiry.
4. Apply the BTC strategy config.
5. Generate alerts.

Deduplication keys include the underlying symbol, so BTC alerts are uniquely keyed by BTC, expiry, ratio, buy symbol, and sell symbol.

Backward compatibility:

```toml
underlying_asset = "BTC"
```

still works if `underlying_assets` is not present, but the recommended explicit BTC-only config is `underlying_assets = ["BTC"]`.

## 8. Strategy Structure

The bot scans:

```text
Buy 1 option
Sell N options
```

Default ratio range:

```toml
ratio_min = 3
ratio_max = 8
```

This means the bot evaluates:

- 1:3
- 1:4
- 1:5
- 1:6
- 1:7
- 1:8

The bot does not assume a fixed 1:5 ratio.

## 9. Call Ratio Spread Logic

For calls, the current logic requires:

```text
spot_price < buy_call_strike < sell_call_strike
```

Meaning:

- Buy a call that is OTM.
- Sell calls farther OTM.
- Sell strike must be greater than buy strike.

Example:

```text
Spot: 101200
Buy: 105000 CE
Sell: 108000 CE
```

This is valid if all thresholds pass.

Market interpretation:

- This is a call ratio spread.
- It receives credit if sold calls collect enough premium.
- It has upside tail risk because more calls are sold than bought.

## 10. Put Ratio Spread Logic

For puts, the current logic requires:

```text
spot_price > buy_put_strike > sell_put_strike
```

Meaning:

- Buy a put that is OTM.
- Sell puts farther OTM.
- Sell strike must be lower than buy strike.

Example:

```text
Spot: 77000
Buy: 76000 PE
Sell: 73000 PE
```

Market interpretation:

- This is a put ratio spread.
- It receives credit if sold puts collect enough premium.
- It has downside tail risk because more puts are sold than bought.

## 11. Net Premium / Inflow Formula

Current formula:

```text
Net Inflow = (N * sell_price) - buy_price
```

Where:

- `N` is the sell ratio.
- `sell_price` is usually the sold option bid.
- `buy_price` is usually the bought option ask.

Alert condition (strict greater-than, no upper cap):

```text
Net Inflow > min_net_inflow_usd
```

Confirmed default:

```toml
min_net_inflow_usd = 35
max_net_inflow_usd = 0   # 0 = no upper cap (send all matching)
```

So:

```text
Net Inflow = 35.00
```

does not alert (strict greater-than).

```text
Net Inflow = 35.01
```

does alert.

There is no upper cap in the confirmed configuration; every opportunity above the
threshold is sent (subject to cooldown / re-alert rules).

## 12. Premium Mode

Current default:

```toml
premium_mode = "bid_ask"
```

In `bid_ask` mode:

- Buy leg uses `best_ask`.
- Sell leg uses `best_bid`.
- If bid/ask is missing or non-positive and `fallback_to_mark_price = true`, the bot falls back to `mark_price`.
- If `fallback_to_mark_price = false` or `require_bid_ask = true`, missing bid/ask causes that opportunity to be skipped.

Alternative:

```toml
premium_mode = "mark"
```

In `mark` mode:

- Buy leg uses `mark_price`.
- Sell leg uses `mark_price`.

Market interpretation:

- `bid_ask` is more conservative than mark for executable alerts because it assumes buying at ask and selling at bid.
- The fallback to mark is less conservative. You may want to disable mark fallback if you only want executable bid/ask opportunities.

## 13. Premium Multiplier / Contract Value Handling

The final confirmed live requirement is to use raw Delta quote prices directly.

Active config:

```toml
premium_multiplier_mode = "raw"
```

The bot may parse `contract_value` from Delta for future use, but it does not apply it in the current live calculation.

Current calculation:

```text
Buy price = 100
Sell price = 20
Ratio = 8
Net inflow = (8 * 20) - 100 = 60
```

No `contract_value`, fees, or slippage adjustments are applied.

## 14. Strike Difference Requirement

Confirmed default:

```toml
min_strike_difference = 3000
max_strike_difference = 0
```

Formula:

```text
strike_difference = abs(sell_strike - buy_strike)
```

Condition:

```text
strike_difference >= min_strike_difference   # i.e. >= 3000
```

If `max_strike_difference` is greater than zero, the bot also enforces:

```text
strike_difference <= max_strike_difference
```

The confirmed BTC live config requires buy and sell strikes to be at least 3000 points
apart and does not enforce a maximum gap (`max_strike_difference = 0`).

## 15. OTM Distance Requirement

Current global default:

```toml
min_otm_distance = 2000
```

For a call:

```text
distance = strike - spot
```

For a put:

```text
distance = spot - strike
```

The bot requires the buy leg to be at least `min_otm_distance` away from spot. Because the sell leg must be farther OTM than the buy leg, the sell leg will also be at least as far away under the current call/put direction rules.

Alert displays:

```text
Distance From Spot = min(buy_distance, sell_distance)
```

This means the displayed distance is the nearest selected strike's distance from spot.

For BTC, both selected strikes must be at least 2000 points OTM.

## 16. Negative ATM Same-Gap Confirmation

This is an optional capability that is **disabled** in the confirmed MVP configuration
(`require_negative_atm_spread = false`), so it does not block alerts. The behavior below
applies only if it is explicitly re-enabled.

When enabled, for each candidate the bot:

1. Finds the same option side nearest ATM.
2. Uses the same strike gap as the candidate.
3. Uses the same ratio as the candidate.
4. Calculates the ATM reference spread with the same buy/sell premium rules.
5. Allows the alert only if the ATM reference spread has negative net inflow.

Example:

```text
BTC spot / ATM: 65000
Candidate buy: 69000
Candidate sell: 72000
Candidate gap: 3000
Candidate ratio: 1:6
Candidate inflow: +40
```

The bot then checks the same-gap ATM spread:

```text
ATM buy: 65000
ATM sell: 68000
Same ratio: 1:6
```

The alert is valid only if that ATM same-gap, same-ratio spread is negative.

## 17. Strategy Configuration

Active BTC strategy:

```toml
[strategy]
enable_calls = true
enable_puts = true
ratio_min = 3
ratio_max = 8
min_net_inflow_usd = 35
max_net_inflow_usd = 0
min_strike_difference = 3000
max_strike_difference = 0
min_otm_distance = 2000
require_negative_atm_spread = false
premium_mode = "bid_ask"
fallback_to_mark_price = true
require_bid_ask = false
premium_multiplier_mode = "raw"
```

The code also supports per-underlying overrides, but the current project is BTC-only and does not use them. Supported override keys if this is ever needed later:

- `enable_calls`
- `enable_puts`
- `ratio_min`
- `ratio_max`
- `min_net_inflow_usd`
- `max_net_inflow_usd`
- `min_strike_difference`
- `max_strike_difference`
- `require_negative_atm_spread`
- `min_otm_distance`
- `premium_mode`
- `expiry_include`
- `expiry_exclude`

## 17. Expiry Include / Exclude

Global config:

```toml
expiry_include = []
expiry_exclude = []
```

If `expiry_include` is empty:

- all discovered expiries are scanned.

If `expiry_include` contains dates:

- only those dates are scanned.

Format:

```toml
expiry_include = ["2026-05-29", "2026-06-05"]
```

If `expiry_exclude` contains dates:

- those dates are skipped.

Per-underlying overrides can technically use their own expiry filters, but this BTC-only config uses the global filters.

## 18. Alert Deduplication and Cooldown

Config:

```toml
cooldown_seconds = 900
```

Deduplication key includes:

- option type
- underlying asset
- expiry
- ratio
- buy symbol
- sell symbol

This prevents repeated alerts for the same setup within the cooldown window.

Re-alert behavior:

```toml
realert_if_inflow_improves = true
realert_if_inflow_improves_by = 20
```

If the same setup appears during cooldown, it is suppressed unless the new net inflow is at least `$20` better than the previously alerted net inflow.

## 19. Telegram Alert Format

Current dry-run or Telegram alert format:

```text
BTC Ratio Trade Opportunity Detected

Strategy Type:
PUT RATIO SPREAD

Expiry:
05 June 2026

Ratio:
1:8

Buy:
1x BTC 77,000 PE @ $1,551

Sell:
8x BTC 74,000 PE @ $526

Net Credit/Inflow:
+$2,657

Strike Difference:
$3,000

Distance From Spot:
52.80 points OTM

BTC Spot Price:
$77,052.8
```

Live config uses Telegram mode by default:

```toml
dry_run = false
```

Telegram credentials should be supplied in `config.toml` or environment variables:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
export TELEGRAM_CHAT_ID="-1001234567890"
```

## 20. Current Tests

Tests are in:

- [tests/test_scanner.py](/Users/mypc/Documents/PUTAN/tests/test_scanner.py)

Current test coverage:

1. Dynamic ratio scanning.
   - Confirms 1:3 through 1:8 are evaluated.
   - Confirms only ratios clearing the inflow threshold are returned.

2. Put ratio strike direction.
   - Confirms put sell strike must be farther OTM than buy strike.

3. Delta symbol expiry parsing.
   - Confirms `P-BTC-77200-270526` parses to `2026-05-27`.
   - Confirms underlying can be inferred from symbol.

Verification commands:

```bash
python3 -m unittest discover -s tests
python3 -m compileall delta_ratio_bot tests
python3 -m delta_ratio_bot --config config.toml --once
```

## 21. What the Bot Does Not Do Yet

The current bot does not:

- Place trades.
- Check account balance.
- Check margin requirement.
- Check order book depth beyond best bid/ask.
- Verify that full ratio quantity can execute at displayed prices.
- Use WebSocket streaming.
- Use Greeks filters.
- Use IV filters.
- Use open interest filters.
- Use volume filters.
- Log all historical opportunities to CSV/database.
- Backtest.
- Calculate max profit/loss.
- Calculate breakeven.
- Calculate probability of profit.
- Account for fees.
- Account for slippage.
- Account for contract multiplier unless the raw quote already reflects it.

## 22. Market Risk Notes

Ratio spreads are not simple low-risk credit trades.

Call ratio spread risk:

- You buy 1 call and sell N calls farther OTM.
- Because N is greater than 1, you are net short calls.
- If price rises far beyond the sell strike, losses can become large.

Put ratio spread risk:

- You buy 1 put and sell N puts farther OTM.
- Because N is greater than 1, you are net short puts.
- If price crashes far below the sell strike, losses can become large.

The bot only checks the configured premium range, distance filters, and the negative ATM same-gap confirmation.

It does not check:

- liquidation risk
- exchange margin
- portfolio hedges
- implied volatility skew
- event risk
- gap risk
- settlement behavior
- early assignment, if applicable to the product
- contract expiry settlement mechanics

## 23. Important Trading Validity Questions

Before using live alerts, review these:

1. Should alerts require executable bid/ask only, with no mark fallback?
2. Is 2000 points the correct minimum BTC OTM distance?
3. Is the current `$20` to `$100` raw-premium inflow range correct?
4. Should calls and puts both be enabled?
5. Should near-expiry options be excluded?
6. Should low open-interest options be excluded?
7. Should minimum bid size / ask size be checked?
8. Should only monthly/weekly/quarterly expiries be included?
9. Should alerts be limited to top N opportunities per scan?
10. Should the bot avoid multiple alerts sharing the same buy leg?
11. Should the bot avoid multiple alerts sharing the same sell leg?
12. Should opportunities be grouped by expiry before alerting?
13. Should the scanner calculate risk metrics before alerting?

## 24. Suggested Production Improvements

Highest priority:

1. Review dry-run/live alert quality after the 2000-point OTM filter.
2. Consider `require_bid_ask = true` if mark fallback produces noisy alerts.
3. Add optional min bid size / ask size filters if liquidity becomes a concern.
4. Tune the BTC net inflow range and distance thresholds after dry-run review.

Medium priority:

1. Add CSV logging.
2. Add Greeks filters.
3. Add IV filters.
4. Add open interest and volume filters.
5. Add WebSocket market data.
6. Add a dashboard.

Future:

1. Backtesting.
2. Risk/reward analytics.
3. Position sizing.
4. Margin estimation.
5. Auto-trading integration.

## 25. Current Recommended Config Before Real Telegram Alerts

Confirmed starting point:

```toml
[strategy]
enable_calls = true
enable_puts = true
ratio_min = 3
ratio_max = 8
min_net_inflow_usd = 35
max_net_inflow_usd = 0
min_strike_difference = 3000
max_strike_difference = 0
min_otm_distance = 2000
require_negative_atm_spread = false
premium_mode = "bid_ask"
fallback_to_mark_price = true
require_bid_ask = false
premium_multiplier_mode = "raw"
```

Then tune based on observed dry-run alert quality.

## 26. Summary

The bot currently satisfies the core scanner requirements:

- BTC scanning.
- Multi-expiry scanning.
- Dynamic 1:N ratio evaluation.
- Calls and puts.
- OTM filters.
- Strike-distance filters.
- Net-credit filters.
- Telegram/dry-run alerts.
- Deduplication and cooldown.
- Async processing.

The confirmed live calculation uses raw Delta quote prices directly. `contract_value` may be parsed for future analytics but is not applied to alert inflow calculations.
