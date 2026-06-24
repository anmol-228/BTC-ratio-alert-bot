# BTC Ratio Alert Bot

Alert-only Telegram bot for scanning Delta Exchange BTC options and detecting configurable `1:N` ratio spread opportunities across all available expiries.

[![Python Tests](https://github.com/anmol-228/BTC-ratio-alert-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/anmol-228/BTC-ratio-alert-bot/actions/workflows/tests.yml)

## What It Does

- Scans BTC options only.
- Uses Delta Exchange REST market data.
- Monitors all active BTC option expiries.
- Evaluates call and put ratio spreads.
- Checks dynamic ratios from `1:3` through `1:8` by default.
- Uses raw Delta quote premiums.
- Uses best ask for the buy leg and best bid for the sell leg.
- Falls back to mark price when bid/ask is missing, if configured.
- Requires the buy leg to be at least `2000` points away from BTC spot by default.
- Requires net inflow inside the configured range, currently greater than `$20` and up to `$100`.
- Requires a negative same-gap, same-ratio ATM reference spread before alerting.
- Sends matching opportunities to a Telegram group.

## Strategy Rule Summary

For each candidate:

```text
net_inflow = (ratio * sell_price) - buy_price
```

Current live filters:

- Underlying: BTC only
- Data mode: REST polling
- Ratios: `1:3` to `1:8`
- Net inflow: `> 20` and `<= 100`
- Minimum buy-leg OTM distance: `2000`
- Strike gap: configurable, currently no fixed min/max
- Confirmation: same-gap ATM spread must be negative
- Cooldown: `900` seconds
- Re-alert: enabled if net inflow improves by `$20` or more

The bot does not place trades.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.toml config.toml
python3 -m delta_ratio_bot --config config.toml --health-check
```

Set Telegram credentials in `.env`:

```bash
TELEGRAM_BOT_TOKEN=replace_with_bot_token
TELEGRAM_CHAT_ID=-100replace_with_group_chat_id
```

Never commit a real `.env` file.

## Commands

Test Telegram without scanning Delta:

```bash
python3 -m delta_ratio_bot --config config.toml --test-telegram
```

Run one live scan:

```bash
python3 -m delta_ratio_bot --config config.toml --once
```

Run continuously:

```bash
python3 -m delta_ratio_bot --config config.toml
```

Run a local dry-run demo without Telegram:

```bash
python3 -m delta_ratio_bot --config config.local-demo.toml --once
```

or:

```bash
./scripts/demo_local.sh
```

## Deployment

For a persistent Linux deployment, use the example systemd unit:

[deployment/delta-ratio-bot.service.example](deployment/delta-ratio-bot.service.example)

Replace `/opt/delta-ratio-bot` with your actual deployment path. Keep `.env` private.

## Documentation

- [LIVE_SETTINGS.md](LIVE_SETTINGS.md): current live configuration and strategy assumptions
- [PROJECT_VALIDATION_DOCUMENT.md](PROJECT_VALIDATION_DOCUMENT.md): detailed technical and market validation notes
- [RUNBOOK.md](RUNBOOK.md): operational commands
- [FINAL_HANDOVER.md](FINAL_HANDOVER.md): client handover summary

## Safety And Scope

This is an alert-only scanner.

It does not:

- place trades
- use private Delta API keys
- check account balance
- check margin
- calculate liquidation risk
- apply fees or slippage
- enforce liquidity filters
- store alerts in a database

## Limitations

1. REST API availability and rate limits can affect scan cycles.
2. Alerts may not always be executable at displayed prices because no liquidity filter is enforced.
3. Mark-price fallback can produce less executable signals than strict bid/ask mode.
4. The strategy has tail risk because ratio spreads sell more options than they buy.
5. This repository is software only, not financial advice.

## License

MIT License. See [LICENSE](LICENSE).
