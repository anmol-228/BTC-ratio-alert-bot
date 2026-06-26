# Final Handover — BTC Ratio Alert Bot

Last updated: 2026-06-26

## Summary

This is an alert-only Telegram bot for Delta Exchange BTC options. It scans public REST market data, evaluates BTC call ratio spreads across all active expiries, and sends Telegram alerts when the configured conditions match.

It does not place trades, use private Delta API keys, check balances, calculate margin, or manage risk.

## Current Confirmed Settings

| Setting | Value |
|---|---|
| Asset | BTC only |
| Market data | REST polling |
| Strategy side | CALL only |
| Puts | Disabled |
| Ratio range | `1:3` to `1:8` |
| Net inflow | `>= 20` and `<= 100` |
| Strike difference | No fixed min/max by default |
| Buy-leg OTM distance | Minimum `2000` points from spot |
| Sell premium vs buy premium | Sell premium must be `<= 60%` of buy premium |
| ATM confirmation | Required: same-gap same-ratio ATM spread must be negative |
| Premium mode | Buy at best ask, sell at best bid |
| Mark fallback | Enabled |
| Cooldown | `900` seconds |
| Re-alert | If same setup improves by at least `$20` |
| Auto-trading | Not included |

## Alert Logic

For each call ratio candidate:

```text
spot_price < buy_call_strike < sell_call_strike
net_inflow = (ratio * sell_price) - buy_price
```

The bot alerts only if:

1. Buy strike is at least `2000` points above spot.
2. Sell premium is no more than `60%` of buy premium.
3. Net inflow is `>= 20` and `<= 100`.
4. The same-gap, same-ratio ATM reference spread is negative.

## Telegram Alert Format

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

## Commands

Run from the project root:

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

## Telegram Setup

Create `.env`:

```bash
TELEGRAM_BOT_TOKEN=replace_with_bot_token
TELEGRAM_CHAT_ID=-100replace_with_group_chat_id
```

Never commit `.env`.

## VPS Deployment

Use the systemd example:

```text
deployment/delta-ratio-bot.service.example
```

Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Then run health check, Telegram test, and one scan before enabling continuous mode.

## Security Notes

- `.env` is gitignored.
- Telegram tokens must be kept private.
- Rotate the Telegram token if it is exposed.
- This project needs no Delta trading API keys.
