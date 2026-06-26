from __future__ import annotations

import argparse
import asyncio
from datetime import date
import logging
import os
from pathlib import Path
import sys

from .alerts import AlertDeduper, TelegramNotifier
from .config import AppConfig, load_config
from .delta_client import DeltaClient
from .scanner import RatioScanner

LOGGER = logging.getLogger(__name__)
TELEGRAM_TEST_MESSAGE = "✅ Delta Ratio Bot Telegram test successful. Alerts are connected."


async def run_once(config: AppConfig) -> int:
    scanner = RatioScanner(config.strategy)
    deduper = AlertDeduper(
        config.alerts.cooldown_seconds,
        config.alerts.realert_if_inflow_improves,
        config.alerts.realert_if_inflow_improves_by,
    )
    notifier = TelegramNotifier(config.alerts)
    client = DeltaClient(config.delta.base_url, config.delta.request_timeout_seconds)
    try:
        try:
            return await scan_cycle(config, client, scanner, deduper, notifier)
        except Exception:
            LOGGER.exception("Scan cycle failed")
            return 0
    finally:
        await client.close()


async def run_forever(config: AppConfig) -> None:
    scanner = RatioScanner(config.strategy)
    deduper = AlertDeduper(
        config.alerts.cooldown_seconds,
        config.alerts.realert_if_inflow_improves,
        config.alerts.realert_if_inflow_improves_by,
    )
    notifier = TelegramNotifier(config.alerts)
    client = DeltaClient(config.delta.base_url, config.delta.request_timeout_seconds)
    consecutive_failures = 0
    try:
        while True:
            try:
                count = await scan_cycle(config, client, scanner, deduper, notifier)
                LOGGER.info("Scan complete; sent %s alert(s)", count)
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                log_scan_failure(consecutive_failures)
                if (
                    consecutive_failures
                    >= config.market_data.max_consecutive_failures_before_backoff
                ):
                    LOGGER.warning(
                        "Reached %s consecutive scan failure(s); backing off for %.0f seconds",
                        consecutive_failures,
                        config.market_data.backoff_seconds,
                    )
                    await asyncio.sleep(config.market_data.backoff_seconds)
            await asyncio.sleep(config.market_data.scan_frequency_seconds)
    finally:
        await client.close()


async def scan_cycle(
    config: AppConfig,
    client: DeltaClient,
    scanner: RatioScanner,
    deduper: AlertDeduper,
    notifier: TelegramNotifier,
) -> int:
    counts = await asyncio.gather(
        *(
            scan_underlying(config, client, scanner, deduper, notifier, underlying_asset)
            for underlying_asset in config.delta.underlying_assets
        )
    )
    return sum(counts)


async def scan_underlying(
    config: AppConfig,
    client: DeltaClient,
    scanner: RatioScanner,
    deduper: AlertDeduper,
    notifier: TelegramNotifier,
    underlying_asset: str,
) -> int:
    strategy = config.strategy.for_underlying(underlying_asset)
    scanner = RatioScanner(strategy)
    spot_price, expiries = await asyncio.gather(
        client.get_spot_price(underlying_asset),
        client.get_expiries(underlying_asset),
    )
    expiries = filter_expiries(expiries, strategy.expiry_include, strategy.expiry_exclude)
    LOGGER.info("Scanning %s expiries with %s spot %.2f", len(expiries), underlying_asset, spot_price)
    if not expiries:
        LOGGER.warning("No expiries found for %s after include/exclude filtering", underlying_asset)
        return 0

    chains = await asyncio.gather(
        *(client.get_option_chain(underlying_asset, expiry) for expiry in expiries)
    )

    sent = 0
    for expiry, quotes in zip(expiries, chains, strict=True):
        opportunities = scanner.scan_expiry(expiry, quotes, spot_price)
        if not quotes:
            LOGGER.warning("Empty option chain for %s expiry %s", underlying_asset, expiry.isoformat())
        if not opportunities:
            LOGGER.info("No matching opportunities found for %s expiry %s", underlying_asset, expiry.isoformat())
        LOGGER.info(
            "Expiry %s: %s quotes, %s matching opportunities",
            f"{underlying_asset} {expiry.isoformat()}",
            len(quotes),
            len(opportunities),
        )
        opportunities = select_opportunities_for_alert(
            opportunities,
            already_sent=sent,
            send_all_matching_opportunities=config.alerts.send_all_matching_opportunities,
            max_alerts_per_scan=config.alerts.max_alerts_per_scan,
        )
        if not opportunities and config.alerts.max_alerts_per_scan > 0:
            break
        for opportunity in opportunities:
            if not deduper.should_send(opportunity):
                continue
            if await notifier.send(opportunity):
                sent += 1
    return sent


def select_opportunities_for_alert(
    opportunities: list,
    *,
    already_sent: int,
    send_all_matching_opportunities: bool,
    max_alerts_per_scan: int,
) -> list:
    if not send_all_matching_opportunities:
        return []
    if max_alerts_per_scan == 0:
        return opportunities
    remaining = max_alerts_per_scan - already_sent
    if remaining <= 0:
        return []
    return opportunities[:remaining]


def filter_expiries(
    expiries: list[date],
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> list[date]:
    include_set = set(include)
    exclude_set = set(exclude)
    filtered = [
        expiry
        for expiry in expiries
        if (not include_set or expiry.isoformat() in include_set)
        and expiry.isoformat() not in exclude_set
    ]
    return filtered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delta Exchange options ratio alert bot")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config file")
    parser.add_argument("--once", action="store_true", help="Run one scan cycle and exit")
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a Telegram connectivity test message and exit without scanning Delta",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Validate config and print a live-readiness summary without scanning Delta",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def log_scan_failure(consecutive_failures: int) -> None:
    _, exc, _ = sys.exc_info()
    if isinstance(exc, TimeoutError):
        LOGGER.exception("Delta API timeout during scan; consecutive failures: %s", consecutive_failures)
    else:
        LOGGER.exception("Scan cycle failed; consecutive failures: %s", consecutive_failures)


async def run_telegram_test(config: AppConfig) -> int:
    notifier = TelegramNotifier(config.alerts)
    if config.alerts.dry_run:
        print(TELEGRAM_TEST_MESSAGE)
        return 0
    if not config.alerts.telegram_bot_token or not config.alerts.telegram_chat_id:
        LOGGER.error(
            "Telegram test failed: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or config values are required when dry_run = false"
        )
        return 1
    return 0 if await notifier.send_text(TELEGRAM_TEST_MESSAGE) else 1


def run_health_check(config: AppConfig) -> int:
    errors = validate_health(config)
    telegram_configured = bool(config.alerts.telegram_bot_token and config.alerts.telegram_chat_id)
    print("Delta Ratio Bot health check")
    print(f"asset scope: {', '.join(config.delta.underlying_assets)}")
    print(f"data mode: {config.market_data.mode}")
    print(f"use websocket: {config.market_data.use_websocket}")
    print(f"scan frequency seconds: {config.market_data.scan_frequency_seconds:g}")
    print(f"strategy sides enabled: calls={config.strategy.enable_calls}, puts={config.strategy.enable_puts}")
    print(f"ratio range: 1:{config.strategy.ratio_min} to 1:{config.strategy.ratio_max}")
    print(f"premium mode: {config.strategy.premium_mode}")
    print(f"mark fallback: {config.strategy.fallback_to_mark_price}")
    inflow_cap = (
        "no cap"
        if config.strategy.max_net_inflow_usd <= 0
        else f"{config.strategy.max_net_inflow_usd:g}"
    )
    print(
        "net inflow range: "
        f"{config.strategy.min_net_inflow_usd:g} to {inflow_cap}"
    )
    print(f"min strike difference: {config.strategy.min_strike_difference:g}")
    print(f"max strike difference: {config.strategy.max_strike_difference:g}")
    print(f"min OTM distance: {config.strategy.min_otm_distance:g}")
    sell_to_buy_cap = (
        "no cap"
        if config.strategy.max_sell_premium_percent_of_buy <= 0
        else f"{config.strategy.max_sell_premium_percent_of_buy:g}%"
    )
    print(f"max sell premium vs buy premium: {sell_to_buy_cap}")
    print(f"negative ATM same-gap required: {config.strategy.require_negative_atm_spread}")
    print(f"cooldown seconds: {config.alerts.cooldown_seconds:g}")
    print(f"Telegram configured: {'yes' if telegram_configured else 'no'}")
    if errors:
        for error in errors:
            LOGGER.error("Health check failed: %s", error)
        return 1
    print("status: OK")
    return 0


def validate_health(config: AppConfig) -> list[str]:
    errors: list[str] = []
    if config.delta.underlying_assets != ("BTC",):
        errors.append('asset scope must be BTC only: underlying_assets = ["BTC"]')
    if config.market_data.mode != "rest":
        errors.append('market_data.mode must be "rest"')
    if config.market_data.use_websocket:
        errors.append("market_data.use_websocket must be false")
    if config.strategy.ratio_min > config.strategy.ratio_max:
        errors.append("strategy.ratio_min must be <= ratio_max")
    if config.alerts.cooldown_seconds < 0:
        errors.append("alerts.cooldown_seconds must be >= 0")
    if not config.alerts.dry_run and not (
        config.alerts.telegram_bot_token and config.alerts.telegram_chat_id
    ):
        errors.append(
            "Telegram credentials are required when alerts.dry_run = false"
        )
    return errors


def load_env_file(path: Path) -> int:
    if not path.exists():
        return 0
    loaded = 0
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def load_env_files(config_path: Path) -> None:
    candidates = []
    cwd_env = Path.cwd() / ".env"
    config_env = config_path.resolve().parent / ".env"
    for candidate in (cwd_env, config_env):
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        loaded = load_env_file(candidate)
        if loaded:
            LOGGER.info("Loaded %s value(s) from %s", loaded, candidate)


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    load_env_files(config_path)
    try:
        config = load_config(config_path)
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
        LOGGER.error("Config load failed: %s", exc)
        raise SystemExit(1) from exc
    setup_logging(config.logging.level)
    if args.health_check:
        raise SystemExit(run_health_check(config))
    if args.test_telegram:
        raise SystemExit(asyncio.run(run_telegram_test(config)))
    if args.once:
        sent = asyncio.run(run_once(config))
        LOGGER.info("Finished one scan; sent %s alert(s)", sent)
        return
    asyncio.run(run_forever(config))
