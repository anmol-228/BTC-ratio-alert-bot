# Final Handover — Delta Exchange BTC Options Ratio Alert Bot

Last updated: 2026-06-23

This is the authoritative handover document. Where any other document disagrees with this one, this document wins.

## 1. Project summary

An **alert-only** Telegram bot that scans Delta Exchange BTC options over REST and detects
ratio-spread opportunities (buy 1 leg, sell N legs, where N ranges from 3 to 8). When a setup
meets every configured condition it sends a Telegram alert. It never places trades, never uses
private/trading API keys, and never manages positions, margin, or risk.

## 2. Final confirmed settings

These values live in `config.toml` (and mirror `config.example.toml`).

| Setting | Value | Meaning |
|---|---|---|
| `delta.underlying_assets` | `["BTC"]` | BTC only (ETH disabled) |
| `market_data.mode` | `"rest"` | REST polling only (no WebSocket) |
| `market_data.use_websocket` | `false` | WebSocket disabled |
| `market_data.scan_frequency_seconds` | `5` | Scan every 5 seconds |
| `market_data.max_consecutive_failures_before_backoff` | `3` | Backoff trigger |
| `market_data.backoff_seconds` | `30` | Backoff duration |
| `strategy.enable_calls` / `enable_puts` | `true` / `true` | Scan call + put ratio spreads |
| `strategy.ratio_min` / `ratio_max` | `3` / `8` | Evaluates 1:3, 1:4, 1:5, 1:6, 1:7, 1:8 (8 included) |
| `strategy.min_net_inflow_usd` | `35` | Alert only if `net_inflow > 35` (strict; 35.00 no, 35.01 yes) |
| `strategy.max_net_inflow_usd` | `0` | 0 = no upper cap (send all matching) |
| `strategy.min_strike_difference` | `3000` | `abs(sell_strike - buy_strike) >= 3000` |
| `strategy.max_strike_difference` | `0` | 0 = no maximum gap cap |
| `strategy.min_otm_distance` | `2000` | Both legs at least 2000 points from spot |
| `strategy.require_negative_atm_spread` | `false` | Optional filter, disabled per MVP |
| `strategy.premium_mode` | `"bid_ask"` | Buy = best ask, Sell = best bid |
| `strategy.fallback_to_mark_price` | `true` | Use mark price if bid/ask missing |
| `strategy.require_bid_ask` | `false` | Do not force bid/ask presence |
| `strategy.premium_multiplier_mode` | `"raw"` | Raw Delta quote price; no contract_value/fees/slippage |
| `strategy.expiry_include` / `expiry_exclude` | `[]` / `[]` | Scan every active BTC expiry |
| `alerts.dry_run` | `false` | Live: sends to Telegram |
| `alerts.cooldown_seconds` | `900` | 15-minute dedupe cooldown |
| `alerts.send_all_matching_opportunities` | `true` | Send all matches |
| `alerts.max_alerts_per_scan` | `0` | 0 = no per-scan limit |
| `alerts.realert_if_inflow_improves` | `true` | Re-alert on improvement |
| `alerts.realert_if_inflow_improves_by` | `20` | Re-alert if `new >= previous + 20` |

Net inflow formula: `net_inflow = (ratio * sell_price) - buy_price`.

Dedupe key: `underlying | strategy_type | expiry | ratio | buy_symbol | sell_symbol`
(strategy_type is the explicit `CALL RATIO SPREAD` / `PUT RATIO SPREAD`).

> The `max_net_inflow_usd` upper cap and `require_negative_atm_spread` confirmation remain in
> the code as optional capabilities, but are disabled (`0` / `false`) to match the confirmed
> requirements (send all matching opportunities, strict `> 35`).

## 3. What the bot does

- Scans BTC options on Delta Exchange via REST, across all live expiries.
- Evaluates both call and put ratio spreads for ratios 1:3 through 1:8.
- Uses raw Delta quote prices (best ask to buy, best bid to sell, mark-price fallback).
- Alerts when net inflow is strictly greater than 35, strikes are at least 3000 apart, and both
  legs are at least 2000 points OTM.
- Sends every matching opportunity to Telegram, with a 15-minute cooldown and re-alert on a
  `>= +20` improvement.
- Logs clearly on Delta timeouts, 429 rate limits, 5xx errors, empty chains, and no-match cycles,
  and backs off after repeated failures instead of crashing.

## 4. What the bot does NOT do

No auto-trading, order placement, private/trading API keys, balance/margin/liquidation checks,
position management, fee/slippage adjustment, risk engine, dashboard, database, WebSocket, ETH,
or liquidity filters (bid/ask size, depth, volume, open interest). It is alert-only.

## 5. Commands

Run these from the project root (where `config.toml` lives). Requires Python 3.11+.

```bash
# Health check (validates config, prints live-readiness summary; does not call Delta)
python3 -m delta_ratio_bot --config config.toml --health-check

# Telegram connectivity test (does not call Delta)
python3 -m delta_ratio_bot --config config.toml --test-telegram

# One-time scan and exit
python3 -m delta_ratio_bot --config config.toml --once

# Continuous live run (used by systemd)
python3 -m delta_ratio_bot --config config.toml
```

Behavior notes:

- With `dry_run = false` and Telegram credentials **present**, health-check and test-telegram
  succeed and alerts are sent live.
- With `dry_run = false` and credentials **missing**, health-check and test-telegram exit non-zero
  with a clear error (no traceback). `--once` still scans and simply logs that alerts were skipped.
- With `dry_run = true`, test-telegram prints the test message and `--once` prints alerts locally
  without contacting Telegram.

## 6. Telegram setup

1. **Create the bot:** open a chat with `@BotFather`, send `/newbot`, follow the prompts, and copy
   the bot **token** (looks like `1234567890:AA...`).
2. **Add the bot to your group:** add the new bot as a member of the Telegram group that should
   receive alerts. (For posting, the bot must be a member; for some groups, an admin.)
3. **Get the group chat ID:** send any message in the group, then visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and read `result[].message.chat.id`.
   Group IDs are negative (e.g. `-1001234567890`). Alternatively use a helper bot like `@getidsbot`.
4. **Put credentials in `.env`** (never in git):

   ```bash
   TELEGRAM_BOT_TOKEN=1234567890:AA-your-real-token
   TELEGRAM_CHAT_ID=-1001234567890
   ```

   The bot reads these from `.env` (in the working directory or next to `config.toml`) or from real
   environment variables. You can also set them in `config.toml` under `[alerts]`, but `.env` is
   preferred so secrets stay out of config files.

## 7. VPS deployment

```bash
# 1. Install Python 3.11+ and venv (Ubuntu/Debian example)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version    # must be 3.11 or newer

# 2. Place the project (adjust path to taste)
sudo mkdir -p /opt/delta-ratio-bot
# upload the project files into /opt/delta-ratio-bot (scp/rsync/git), then:
cd /opt/delta-ratio-bot

# 3. Create a virtualenv and install dependencies
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 4. Configure secrets (create .env with your real values; keep it private)
cp .env.example .env
nano .env            # set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
chmod 600 .env

# 5. Sanity-check before going live
.venv/bin/python -m delta_ratio_bot --config config.toml --health-check
.venv/bin/python -m delta_ratio_bot --config config.toml --test-telegram
.venv/bin/python -m delta_ratio_bot --config config.toml --once
```

If you deploy to a path other than `/opt/delta-ratio-bot`, update `WorkingDirectory`,
`EnvironmentFile`, and `ExecStart` in the systemd unit accordingly.

## 8. systemd

Copy `deployment/delta-ratio-bot.service.example` to the systemd directory and manage it:

```bash
sudo cp deployment/delta-ratio-bot.service.example /etc/systemd/system/delta-ratio-bot.service
sudo systemctl daemon-reload
sudo systemctl enable delta-ratio-bot
sudo systemctl start delta-ratio-bot
sudo systemctl status delta-ratio-bot
journalctl -u delta-ratio-bot -f        # live logs
journalctl -u delta-ratio-bot --since "1 hour ago"
```

The unit restarts the bot automatically (`Restart=always`, `RestartSec=10`).

## 9. Expected monthly server cost

A small VPS is sufficient (the bot is lightweight: one REST poll every 5 seconds). Budget roughly
**₹500–₹1,500 per month** for an entry-level VPS (1 vCPU, 1–2 GB RAM) from common providers.
Actual cost depends on provider, region, and plan.

## 10. Known limitations (accepted)

1. **REST availability / rate limits.** Delta REST can occasionally fail or rate-limit. The bot
   logs a clear error, continues on the next cycle, and backs off after repeated failures. It does
   not permanently crash.
2. **No liquidity filters.** Bid/ask size, depth, volume, and open interest are not enforced, so
   some alerts may not be fully executable at the displayed price or quantity.
3. **No trading / risk calculations.** No margin, fees, slippage, or risk/reward analytics, and no
   order execution. Ratio spreads carry real tail risk that this tool does not evaluate.

## 11. Client handover checklist

- [ ] Python 3.11+ installed on the VPS.
- [ ] Project uploaded; virtualenv created; `requirements.txt` installed.
- [ ] Telegram bot created via BotFather; token saved.
- [ ] Bot added to the target Telegram group; group chat ID obtained.
- [ ] `.env` created with real `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (chmod 600).
- [ ] `--health-check` passes.
- [ ] `--test-telegram` posts the test message to the group.
- [ ] `--once` runs and scans BTC without errors.
- [ ] systemd service installed, enabled, and started.
- [ ] Logs confirmed via `journalctl`.

## 12. Security notes

- **Never commit `.env`.** It is already listed in `.gitignore`.
- **Never share the Telegram bot token.** Anyone with it can post as your bot.
- **Rotate the token immediately if it is ever exposed** (BotFather → `/revoke`), then update `.env`.
- Keep `.env` permissions tight (`chmod 600`).
- A real token/chat ID is currently present in the local `.env` in this folder. It is gitignored,
  but treat it as a live secret: do not paste it into chats, screenshots, or commits, and rotate it
  if there is any doubt about exposure.
