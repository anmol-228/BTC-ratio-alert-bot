# Delta Ratio Bot Runbook

Use this file to run the bot on a local machine or server.

## 1. Install

```bash
cd /path/to/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure Telegram

Create `.env` from the example:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
TELEGRAM_BOT_TOKEN=replace_with_real_bot_token
TELEGRAM_CHAT_ID=-100replace_with_real_group_chat_id
```

Keep `.env` private. Do not commit real secrets.

## 3. Health Check

```bash
./scripts/health_check.sh
```

Expected result:

```text
status: OK
```

## 4. Telegram Test

```bash
./scripts/test_telegram.sh
```

Expected result:

```text
Delta Ratio Bot Telegram test successful. Alerts are connected.
```

appears in the Telegram group.

## 5. One-Time Scan

```bash
./scripts/run_once.sh
```

This scans BTC options once and exits.

## 6. Local Demo Without Telegram

If Telegram is unavailable, use:

```bash
./scripts/demo_local.sh
```

This uses `config.local-demo.toml` with `dry_run = true` and prints alerts locally.

## 7. Live Run

```bash
./scripts/run_live.sh
```

This keeps scanning every 5 seconds.

## Notes

- The bot is BTC-only.
- The bot is alert-only.
- It does not place trades.
- It uses REST polling only.
- Telegram credentials can be set in `.env`, shell environment variables, or `config.toml`.
