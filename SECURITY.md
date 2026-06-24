# Security Policy

## Secrets

Telegram credentials must be provided through `.env`, environment variables, or private deployment secrets.

Do not commit:

- `TELEGRAM_BOT_TOKEN`
- real Telegram group chat IDs for private deployments
- Delta private API keys
- runtime logs containing sensitive information

The repository includes `.env.example` only as a template.

## Supported Scope

This bot does not require Delta private API credentials because it is alert-only and uses public REST market data.

## Reporting Issues

For private security issues, contact the repository owner directly through GitHub.

Do not open public issues containing secrets, tokens, or private group IDs.
