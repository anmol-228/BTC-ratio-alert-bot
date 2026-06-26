from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import aiohttp

from .config import AlertConfig
from .models import OptionKind, RatioOpportunity

LOGGER = logging.getLogger(__name__)


@dataclass
class AlertState:
    last_sent_at: float
    last_net_inflow: float


class AlertDeduper:
    def __init__(
        self,
        cooldown_seconds: float,
        realert_if_inflow_improves: bool = True,
        realert_if_inflow_improves_by: float = 20,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.realert_if_inflow_improves = realert_if_inflow_improves
        self.realert_if_inflow_improves_by = realert_if_inflow_improves_by
        self._state: dict[str, AlertState] = {}

    def should_send(self, opportunity: RatioOpportunity) -> bool:
        now = time.monotonic()
        key = opportunity.dedupe_key
        state = self._state.get(key)
        if state is None:
            self._state[key] = AlertState(now, opportunity.net_inflow)
            return True

        in_cooldown = now - state.last_sent_at < self.cooldown_seconds
        improved_enough = (
            self.realert_if_inflow_improves
            and opportunity.net_inflow >= state.last_net_inflow + self.realert_if_inflow_improves_by
        )
        if in_cooldown and not improved_enough:
            return False

        self._state[key] = AlertState(now, opportunity.net_inflow)
        return True


class TelegramNotifier:
    def __init__(self, config: AlertConfig) -> None:
        self.config = config

    async def send(self, opportunity: RatioOpportunity) -> bool:
        return await self.send_text(format_alert(opportunity))

    async def send_text(self, text: str) -> bool:
        if self.config.dry_run:
            LOGGER.info("DRY RUN ALERT:\n%s", text)
            return True
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            LOGGER.error(
                "Telegram token/chat_id are required when alerts.dry_run = false; alert was not sent"
            )
            return False

        url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400 or not data.get("ok", False):
                        LOGGER.error("Telegram API error %s: %s", response.status, data)
                        return False
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            LOGGER.error("Telegram send failed: %s", exc)
            return False
        return True


def format_alert(opportunity: RatioOpportunity) -> str:
    kind_label = "CALL \U0001f7e9" if opportunity.kind == OptionKind.CALL else "PUT \U0001f7e5"
    option_suffix = "CE" if opportunity.kind == OptionKind.CALL else "PE"
    lines = [
            "Trade Opportunity Detected",
            "",
            "Strategy Type:",
            kind_label,
            "",
            f"Expiry: {opportunity.expiry.strftime('%d %B %Y')}",
            f"Ratio: 1:{opportunity.ratio}",
            "",
            "Net Credit/Inflow:",
            f"+${_fmt_money(opportunity.net_inflow)}",
            "",
            "Buy:",
            (
                f"1x {opportunity.underlying_asset} {_fmt_number(opportunity.buy.strike)} {option_suffix} "
                f"@ ${_fmt_money(opportunity.buy_price)}"
            ),
            "Sell:",
            (
                f"{opportunity.ratio}x {opportunity.underlying_asset} {_fmt_number(opportunity.sell.strike)} {option_suffix} "
                f"@ ${_fmt_money(opportunity.sell_price)}"
            ),
            "",
            f"Strike Difference: {_fmt_plain_number(opportunity.strike_difference)}",
            "",
            "Distance From Spot:",
            f"{_fmt_number(opportunity.distance_from_spot)} points OTM",
            "",
            f"{opportunity.underlying_asset} Spot Price:",
            f"${_fmt_money(opportunity.spot_price)}",
    ]
    return "\n".join(lines)


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _fmt_number(value: float) -> str:
    value = float(value)
    return f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}"


def _fmt_plain_number(value: float) -> str:
    value = float(value)
    return f"{value:.0f}" if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
