# Delta BTC Ratio Alert Bot

Async Telegram bot for scanning Delta Exchange BTC options across all expiries, alerting on configurable `1:N` ratio spread credits.

## What it scans

- BTC options
- All live expiries returned by Delta Exchange
- Dynamic ratios from `1:3` through `1:8` by default
- OTM buy/sell strike pairs at least 3000 points apart and 2000 points from spot
- Net credit/inflow strictly greater than `min_net_inflow_usd` (default 35), no upper cap
- Sends all matching opportunities (subject to cooldown / re-alert rules)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml
python3 -m delta_ratio_bot --config config.toml --health-check
```

Local demo while Telegram is unavailable:

```bash
python3 -m delta_ratio_bot --config config.local-demo.toml --once
```

or:

```bash
./scripts/demo_local.sh
```

This prints matching alerts locally instead of sending Telegram messages.

The live config uses `dry_run = false`. Set Telegram credentials in `config.toml` or via environment variables:

```bash
export TELEGRAM_BOT_TOKEN="replace_with_bot_token"
export TELEGRAM_CHAT_ID="-100replace_with_group_chat_id"
```

Test Telegram connectivity without scanning Delta:

```bash
python3 -m delta_ratio_bot --config config.toml --test-telegram
```

Run one scan:

```bash
python3 -m delta_ratio_bot --config config.toml --once
```

Then run continuously:

```bash
python3 -m delta_ratio_bot --config config.toml
```

## Notes

This live version uses Delta Global REST endpoints for products, tickers, and indices. It is configured for BTC only with `delta.underlying_assets = ["BTC"]`.

See [LIVE_SETTINGS.md](/Users/mypc/Documents/PUTAN/LIVE_SETTINGS.md) for the full live configuration and trading-logic assumptions.

## MVP Limitations

1. REST API availability/rate limits can affect scan cycles, but errors are handled safely.
2. No liquidity filters are enforced, so alerts may not always be executable at displayed quantity/price.
3. No trading, margin, fee, slippage, or risk checks are included.
4. The bot is alert-only and does not place trades.

## systemd

See [deployment/delta-ratio-bot.service.example](/Users/mypc/Documents/PUTAN/deployment/delta-ratio-bot.service.example).

Replace `/opt/delta-ratio-bot` with the real deployment path if different. Keep `.env` private and never commit a real Telegram token.
