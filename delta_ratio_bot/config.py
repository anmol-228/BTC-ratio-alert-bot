from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class DeltaConfig:
    base_url: str
    underlying_assets: tuple[str, ...]
    request_timeout_seconds: float


@dataclass(frozen=True)
class MarketDataConfig:
    mode: str
    use_websocket: bool
    scan_frequency_seconds: float
    max_consecutive_failures_before_backoff: int
    backoff_seconds: float


@dataclass(frozen=True)
class StrategyConfig:
    enable_calls: bool
    enable_puts: bool
    ratio_min: int
    ratio_max: int
    min_net_inflow_usd: float
    max_net_inflow_usd: float
    min_strike_difference: float
    max_strike_difference: float
    min_otm_distance: float
    max_sell_premium_percent_of_buy: float
    require_negative_atm_spread: bool
    premium_mode: str
    fallback_to_mark_price: bool
    require_bid_ask: bool
    premium_multiplier_mode: str
    expiry_include: tuple[str, ...]
    expiry_exclude: tuple[str, ...]
    asset_overrides: dict[str, dict]

    @property
    def ratios(self) -> range:
        return range(self.ratio_min, self.ratio_max + 1)

    def for_underlying(self, underlying_asset: str) -> StrategyConfig:
        overrides = self.asset_overrides.get(underlying_asset.upper(), {})
        if not overrides:
            return self
        merged = replace(self)
        for key, value in overrides.items():
            if key in {"expiry_include", "expiry_exclude"}:
                value = tuple(str(item) for item in value)
            merged = replace(merged, **{key: value})
        return merged


@dataclass(frozen=True)
class AlertConfig:
    dry_run: bool
    cooldown_seconds: float
    send_all_matching_opportunities: bool
    max_alerts_per_scan: int
    realert_if_inflow_improves: bool
    realert_if_inflow_improves_by: float
    telegram_bot_token: str
    telegram_chat_id: str


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    save_alerts_csv: bool
    save_opportunities_db: bool


@dataclass(frozen=True)
class AppConfig:
    delta: DeltaConfig
    market_data: MarketDataConfig
    strategy: StrategyConfig
    alerts: AlertConfig
    logging: LoggingConfig


def load_config(path: str | Path) -> AppConfig:
    raw = tomllib.loads(Path(path).read_text())
    delta = raw.get("delta", {})
    market_data = raw.get("market_data", {})
    strategy = raw.get("strategy", {})
    alerts = raw.get("alerts", {})
    logging = raw.get("logging", {})

    ratio_min = int(strategy.get("ratio_min", 3))
    ratio_max = int(strategy.get("ratio_max", 8))
    if ratio_min < 1 or ratio_max < ratio_min:
        raise ValueError("strategy.ratio_min and ratio_max must define a valid positive range")

    premium_mode = str(strategy.get("premium_mode", "bid_ask"))
    if premium_mode not in {"bid_ask", "mark"}:
        raise ValueError('strategy.premium_mode must be either "bid_ask" or "mark"')
    premium_multiplier_mode = str(strategy.get("premium_multiplier_mode", "raw"))
    if premium_multiplier_mode != "raw":
        raise ValueError('strategy.premium_multiplier_mode currently supports only "raw"')
    mode = str(market_data.get("mode", "rest"))
    if mode != "rest":
        raise ValueError('market_data.mode currently supports only "rest"')
    use_websocket = bool(market_data.get("use_websocket", False))
    if use_websocket:
        raise ValueError("market_data.use_websocket must be false for the REST live version")
    underlying_assets = _load_underlying_assets(delta)
    min_net_inflow_usd = float(strategy.get("min_net_inflow_usd", 20))
    # 0 disables the optional upper cap.
    max_net_inflow_usd = float(strategy.get("max_net_inflow_usd", 0))
    min_strike_difference = float(strategy.get("min_strike_difference", 0))
    max_strike_difference = float(strategy.get("max_strike_difference", 0))
    min_otm_distance = float(strategy.get("min_otm_distance", 2000))
    max_sell_premium_percent_of_buy = float(
        strategy.get("max_sell_premium_percent_of_buy", 60)
    )
    cooldown_seconds = float(alerts.get("cooldown_seconds", 900))
    realert_by = float(alerts.get("realert_if_inflow_improves_by", 20))
    max_alerts_per_scan = int(alerts.get("max_alerts_per_scan", 0))
    scan_frequency_seconds = float(
        market_data.get(
            "scan_frequency_seconds",
            delta.get("scan_frequency_seconds", 5),
        )
    )
    max_failures = int(market_data.get("max_consecutive_failures_before_backoff", 3))
    backoff_seconds = float(market_data.get("backoff_seconds", 30))
    _validate_non_negative(
        {
            "strategy.min_net_inflow_usd": min_net_inflow_usd,
            "strategy.max_net_inflow_usd": max_net_inflow_usd,
            "strategy.min_strike_difference": min_strike_difference,
            "strategy.max_strike_difference": max_strike_difference,
            "strategy.min_otm_distance": min_otm_distance,
            "strategy.max_sell_premium_percent_of_buy": max_sell_premium_percent_of_buy,
            "alerts.cooldown_seconds": cooldown_seconds,
            "alerts.realert_if_inflow_improves_by": realert_by,
            "alerts.max_alerts_per_scan": float(max_alerts_per_scan),
            "market_data.scan_frequency_seconds": scan_frequency_seconds,
            "market_data.max_consecutive_failures_before_backoff": float(max_failures),
            "market_data.backoff_seconds": backoff_seconds,
        }
    )

    return AppConfig(
        delta=DeltaConfig(
            base_url=str(delta.get("base_url", "https://api.delta.exchange")).rstrip("/"),
            underlying_assets=underlying_assets,
            request_timeout_seconds=float(delta.get("request_timeout_seconds", 15)),
        ),
        market_data=MarketDataConfig(
            mode=mode,
            use_websocket=use_websocket,
            scan_frequency_seconds=scan_frequency_seconds,
            max_consecutive_failures_before_backoff=max_failures,
            backoff_seconds=backoff_seconds,
        ),
        strategy=StrategyConfig(
            enable_calls=bool(strategy.get("enable_calls", True)),
            enable_puts=bool(strategy.get("enable_puts", True)),
            ratio_min=ratio_min,
            ratio_max=ratio_max,
            min_net_inflow_usd=min_net_inflow_usd,
            max_net_inflow_usd=max_net_inflow_usd,
            min_strike_difference=min_strike_difference,
            max_strike_difference=max_strike_difference,
            min_otm_distance=min_otm_distance,
            max_sell_premium_percent_of_buy=max_sell_premium_percent_of_buy,
            require_negative_atm_spread=bool(strategy.get("require_negative_atm_spread", True)),
            premium_mode=premium_mode,
            fallback_to_mark_price=bool(strategy.get("fallback_to_mark_price", True)),
            require_bid_ask=bool(strategy.get("require_bid_ask", False)),
            premium_multiplier_mode=premium_multiplier_mode,
            expiry_include=tuple(str(x) for x in strategy.get("expiry_include", [])),
            expiry_exclude=tuple(str(x) for x in strategy.get("expiry_exclude", [])),
            asset_overrides=_load_asset_overrides(strategy.get("asset_overrides", {})),
        ),
        alerts=AlertConfig(
            dry_run=bool(alerts.get("dry_run", True)),
            cooldown_seconds=cooldown_seconds,
            send_all_matching_opportunities=bool(
                alerts.get("send_all_matching_opportunities", True)
            ),
            max_alerts_per_scan=max_alerts_per_scan,
            realert_if_inflow_improves=bool(alerts.get("realert_if_inflow_improves", True)),
            realert_if_inflow_improves_by=realert_by,
            telegram_bot_token=str(
                alerts.get("telegram_bot_token", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
            ),
            telegram_chat_id=str(
                alerts.get("telegram_chat_id", "") or os.getenv("TELEGRAM_CHAT_ID", "")
            ),
        ),
        logging=LoggingConfig(
            level=str(logging.get("level", "INFO")).upper(),
            save_alerts_csv=bool(logging.get("save_alerts_csv", False)),
            save_opportunities_db=bool(logging.get("save_opportunities_db", False)),
        ),
    )


def _load_underlying_assets(delta: dict) -> tuple[str, ...]:
    raw_assets = delta.get("underlying_assets")
    if raw_assets is None:
        raw_assets = [delta.get("underlying_asset", "BTC")]
    if isinstance(raw_assets, str):
        raw_assets = [raw_assets]
    assets = tuple(dict.fromkeys(str(asset).upper() for asset in raw_assets if str(asset).strip()))
    if not assets:
        raise ValueError("delta.underlying_assets must contain at least one symbol")
    return assets


def _load_asset_overrides(raw_overrides: dict) -> dict[str, dict]:
    allowed_keys = {
        "enable_calls",
        "enable_puts",
        "ratio_min",
        "ratio_max",
        "min_net_inflow_usd",
        "max_net_inflow_usd",
        "min_strike_difference",
        "max_strike_difference",
        "min_otm_distance",
        "max_sell_premium_percent_of_buy",
        "require_negative_atm_spread",
        "premium_mode",
        "fallback_to_mark_price",
        "require_bid_ask",
        "premium_multiplier_mode",
        "expiry_include",
        "expiry_exclude",
    }
    overrides: dict[str, dict] = {}
    for asset, raw_values in raw_overrides.items():
        values = {key: value for key, value in dict(raw_values).items() if key in allowed_keys}
        if "ratio_min" in values:
            values["ratio_min"] = int(values["ratio_min"])
        if "ratio_max" in values:
            values["ratio_max"] = int(values["ratio_max"])
        for key in (
            "min_net_inflow_usd",
            "max_net_inflow_usd",
            "min_strike_difference",
            "max_strike_difference",
            "min_otm_distance",
            "max_sell_premium_percent_of_buy",
        ):
            if key in values:
                values[key] = float(values[key])
        for key in (
            "enable_calls",
            "enable_puts",
            "fallback_to_mark_price",
            "require_bid_ask",
            "require_negative_atm_spread",
        ):
            if key in values:
                values[key] = bool(values[key])
        if "premium_mode" in values and values["premium_mode"] not in {"bid_ask", "mark"}:
            raise ValueError(f"strategy.asset_overrides.{asset}.premium_mode is invalid")
        if (
            "premium_multiplier_mode" in values
            and values["premium_multiplier_mode"] != "raw"
        ):
            raise ValueError(
                f"strategy.asset_overrides.{asset}.premium_multiplier_mode is invalid"
            )
        overrides[str(asset).upper()] = values
    return overrides


def _validate_non_negative(values: dict[str, float]) -> None:
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
