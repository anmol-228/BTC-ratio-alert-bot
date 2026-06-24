# Contributing

This project is currently focused on a BTC-only, REST-based, alert-only MVP.

## Local Checks

Run these before submitting changes:

```bash
python3 -m compileall delta_ratio_bot tests
python3 -m unittest discover -s tests
python3 -m delta_ratio_bot --config config.local-demo.toml --health-check
```

## Scope Rules

Keep changes aligned with the current production scope:

- BTC only
- REST polling only
- Telegram alerts only
- no order execution
- no private Delta API keys
- no margin or balance checks
- no database requirement

Open a separate design discussion before adding trading, liquidity filters, WebSocket feeds, dashboards, or persistent storage.

## Secrets

Never commit:

- `.env`
- Telegram bot tokens
- Telegram chat IDs for private groups
- logs
- local backup files
