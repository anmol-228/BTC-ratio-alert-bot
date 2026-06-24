# Live Settings

This bot is an alert-only Delta Exchange BTC options ratio spread scanner. It does not place trades, does not request trading API keys, and does not check balances, margin, positions, or order execution.

## Scope

- Asset: BTC only
- Market data: REST polling only
- Trading: no auto-trading, alerts only
- Telegram: sends to the configured chat or group ID when credentials are present

## Market Data

The first live version uses REST polling because it is simpler and cheaper to operate than a WebSocket stream.

```toml
[market_data]
mode = "rest"
use_websocket = false
scan_frequency_seconds = 5
max_consecutive_failures_before_backoff = 3
backoff_seconds = 30
```

WebSocket is intentionally not implemented for this live version.

If three scan cycles fail in a row, the bot waits 30 seconds before trying again.

## Strategy

The bot scans both BTC call ratio spreads and BTC put ratio spreads.

```toml
[strategy]
enable_calls = true
enable_puts = true
ratio_min = 3
ratio_max = 8
```

It evaluates every dynamic ratio from `1:3` through `1:8`; it is not fixed to `1:5`.

## Premium Calculation

The bot uses raw Delta quote prices directly.

```toml
premium_multiplier_mode = "raw"
```

It does not multiply by `contract_value`, and it does not subtract fees or slippage.

In bid/ask mode:

- Buy leg uses `best_ask`
- Sell leg uses `best_bid`
- If bid/ask is missing and `fallback_to_mark_price = true`, the bot uses `mark_price`
- If `fallback_to_mark_price = false`, that opportunity is skipped

```toml
premium_mode = "bid_ask"
fallback_to_mark_price = true
require_bid_ask = false
```

## Filters

Confirmed BTC filters:

```toml
min_net_inflow_usd = 35
max_net_inflow_usd = 0          # 0 = no upper cap (send all matching)
min_strike_difference = 3000
max_strike_difference = 0       # 0 = no maximum gap cap
min_otm_distance = 2000
require_negative_atm_spread = false
```

Alert condition (strict greater-than, no upper cap):

```text
net_inflow = (ratio * sell_price) - buy_price
alert only if net_inflow > min_net_inflow_usd
```

A net inflow of exactly `35.00` does **not** alert; `35.01` does.
The strike difference must satisfy `abs(sell_strike - buy_strike) >= 3000`.
`max_net_inflow_usd` and `require_negative_atm_spread` are optional capabilities
that the code still supports but are disabled in the confirmed MVP configuration.

For calls:

```text
spot_price < buy_call_strike < sell_call_strike
```

Both call strikes must be at least 2000 points above spot.

For puts:

```text
spot_price > buy_put_strike > sell_put_strike
```

Both put strikes must be at least 2000 points below spot.

The alert displays the nearest selected strike distance:

```text
min(buy_distance, sell_distance)
```

An optional negative same-gap ATM confirmation is available in code (`require_negative_atm_spread`) but is disabled in the confirmed MVP configuration, so it does not block alerts.

## Expiries

All available BTC option expiries are scanned.

```toml
expiry_include = []
expiry_exclude = []
```

Near expiries are not excluded.

## Alerts

The bot sends all matching opportunities by default.

```toml
send_all_matching_opportunities = true
max_alerts_per_scan = 0
```

`max_alerts_per_scan = 0` means no limit.

Duplicate cooldown:

```toml
cooldown_seconds = 900
```

This is 15 minutes.

Re-alert behavior:

```toml
realert_if_inflow_improves = true
realert_if_inflow_improves_by = 20
```

During cooldown, the same setup is normally suppressed. It is sent again only if its new net inflow is at least `$20` better than the previous alert.

## Telegram

Set Telegram credentials in `config.toml` or environment variables:

```bash
export TELEGRAM_BOT_TOKEN="replace_with_bot_token"
export TELEGRAM_CHAT_ID="-100replace_with_group_chat_id"
```

Group chat IDs are often negative.

For live alerts:

```toml
[alerts]
dry_run = false
```

If credentials are missing while `dry_run = false`, the bot logs an error and skips sending that alert.

## Run Commands

Health check without calling Delta:

```bash
python3 -m delta_ratio_bot --config config.toml --health-check
```

Telegram connectivity test without scanning Delta:

```bash
export TELEGRAM_BOT_TOKEN="replace_with_bot_token"
export TELEGRAM_CHAT_ID="-100replace_with_group_chat_id"
python3 -m delta_ratio_bot --config config.toml --test-telegram
```

Local demo while Telegram is unavailable:

```bash
python3 -m delta_ratio_bot --config config.local-demo.toml --once
```

or:

```bash
./scripts/demo_local.sh
```

This uses `dry_run = true` and prints alerts locally.

One-time scan:

```bash
python3 -m delta_ratio_bot --config config.toml --once
```

Continuous polling:

```bash
python3 -m delta_ratio_bot --config config.toml
```

## Deployment Files

- `.env.example` shows the required Telegram environment variables.
- `deployment/delta-ratio-bot.service.example` is a systemd example.

Replace `/opt/delta-ratio-bot` in the service file with your actual deployment path if different. Keep `.env` private and never commit a real Telegram token.

## Current MVP Limitations

1. REST API availability/rate limits can affect scan cycles, but errors are handled safely.
2. No liquidity filters are enforced, so alerts may not always be executable at displayed quantity/price.
3. No trading, margin, fee, slippage, or risk checks are included.
4. The bot is alert-only and does not place trades.
