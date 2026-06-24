from datetime import date
import asyncio
import unittest

from delta_ratio_bot.alerts import AlertDeduper, TelegramNotifier
from delta_ratio_bot.app import select_opportunities_for_alert
from delta_ratio_bot.config import AlertConfig
from delta_ratio_bot.models import OptionKind, OptionQuote, RatioOpportunity


EXPIRY = date(2026, 6, 28)


def quote(symbol: str, strike: float) -> OptionQuote:
    return OptionQuote(
        underlying_asset="BTC",
        symbol=symbol,
        product_id=1,
        kind=OptionKind.CALL,
        expiry=EXPIRY,
        strike=strike,
        mark_price=1,
        best_bid=1,
        best_ask=1,
        spot_price=100000,
    )


def opportunity(net_inflow: float) -> RatioOpportunity:
    return RatioOpportunity(
        underlying_asset="BTC",
        kind=OptionKind.CALL,
        expiry=EXPIRY,
        ratio=8,
        buy=quote("BTC-C-104000", 104000),
        sell=quote("BTC-C-107000", 107000),
        buy_price=10,
        sell_price=20,
        net_inflow=net_inflow,
        strike_difference=3000,
        spot_price=100000,
        distance_from_spot=4000,
    )


class AlertDeduperTest(unittest.TestCase):
    def test_cooldown_suppresses_duplicate_alert(self) -> None:
        deduper = AlertDeduper(
            cooldown_seconds=900,
            realert_if_inflow_improves=True,
            realert_if_inflow_improves_by=20,
        )

        self.assertTrue(deduper.should_send(opportunity(100)))
        self.assertFalse(deduper.should_send(opportunity(100)))

    def test_realert_triggers_when_inflow_improves_by_at_least_threshold(self) -> None:
        deduper = AlertDeduper(
            cooldown_seconds=900,
            realert_if_inflow_improves=True,
            realert_if_inflow_improves_by=20,
        )

        self.assertTrue(deduper.should_send(opportunity(100)))
        self.assertTrue(deduper.should_send(opportunity(120)))

    def test_realert_does_not_trigger_when_improvement_is_too_small(self) -> None:
        deduper = AlertDeduper(
            cooldown_seconds=900,
            realert_if_inflow_improves=True,
            realert_if_inflow_improves_by=20,
        )

        self.assertTrue(deduper.should_send(opportunity(100)))
        self.assertFalse(deduper.should_send(opportunity(119.99)))


class AlertLimitTest(unittest.TestCase):
    def test_max_alerts_per_scan_zero_means_no_limit(self) -> None:
        opportunities = [object(), object(), object()]

        selected = select_opportunities_for_alert(
            opportunities,
            already_sent=0,
            send_all_matching_opportunities=True,
            max_alerts_per_scan=0,
        )

        self.assertEqual(selected, opportunities)


class TelegramNotifierTest(unittest.TestCase):
    def test_missing_telegram_credentials_with_live_mode_does_not_crash(self) -> None:
        notifier = TelegramNotifier(
            AlertConfig(
                dry_run=False,
                cooldown_seconds=900,
                send_all_matching_opportunities=True,
                max_alerts_per_scan=0,
                realert_if_inflow_improves=True,
                realert_if_inflow_improves_by=20,
                telegram_bot_token="",
                telegram_chat_id="",
            )
        )

        sent = asyncio.run(notifier.send(opportunity(100)))

        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main()
