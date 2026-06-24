from datetime import date
import unittest

from delta_ratio_bot.config import StrategyConfig
from delta_ratio_bot.delta_client import parse_option_quote
from delta_ratio_bot.models import OptionKind, OptionQuote
from delta_ratio_bot.scanner import RatioScanner


EXPIRY = date(2026, 6, 28)


def strategy(**overrides: object) -> StrategyConfig:
    values = {
        "enable_calls": True,
        "enable_puts": True,
        "ratio_min": 3,
        "ratio_max": 8,
        "min_net_inflow_usd": 20,
        "max_net_inflow_usd": 100,
        "min_strike_difference": 0,
        "max_strike_difference": 0,
        "min_otm_distance": 2000,
        "require_negative_atm_spread": False,
        "premium_mode": "bid_ask",
        "fallback_to_mark_price": True,
        "require_bid_ask": False,
        "premium_multiplier_mode": "raw",
        "expiry_include": (),
        "expiry_exclude": (),
        "asset_overrides": {},
    }
    values.update(overrides)
    return StrategyConfig(**values)


def quote(
    kind: OptionKind,
    strike: float,
    *,
    symbol: str | None = None,
    mark: float | None = 1,
    bid: float | None = 1,
    ask: float | None = 1,
    contract_value: float | None = None,
) -> OptionQuote:
    suffix = "C" if kind == OptionKind.CALL else "P"
    return OptionQuote(
        underlying_asset="BTC",
        symbol=symbol or f"BTC-{suffix}-{strike}",
        product_id=1,
        kind=kind,
        expiry=EXPIRY,
        strike=strike,
        mark_price=mark,
        best_bid=bid,
        best_ask=ask,
        spot_price=101200,
        contract_value=contract_value,
    )


class RatioScannerTest(unittest.TestCase):
    def test_scans_every_configured_ratio(self) -> None:
        config = strategy(enable_puts=False, min_otm_distance=0)
        quotes = [
            quote(OptionKind.CALL, 105000, mark=12, bid=11, ask=12),
            quote(OptionKind.CALL, 108000, mark=8.5, bid=8.5, ask=9),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual([item.ratio for item in opportunities], [8, 7, 6, 5, 4])
        self.assertEqual([round(item.net_inflow, 2) for item in opportunities], [56, 47.5, 39, 30.5, 22])

    def test_net_inflow_exactly_at_threshold_does_not_alert(self) -> None:
        # net_inflow = 3 * 15 - 10 = 35.00, which equals the threshold and must NOT alert.
        config = strategy(
            enable_puts=False,
            ratio_min=3,
            ratio_max=3,
            min_net_inflow_usd=35,
            max_net_inflow_usd=0,
        )
        quotes = [
            quote(OptionKind.CALL, 104000, ask=10),
            quote(OptionKind.CALL, 107000, bid=15),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities, [])

    def test_net_inflow_just_above_threshold_alerts(self) -> None:
        # net_inflow = 3 * 15.01 - 10 = 35.03 (> 35.00) must alert.
        config = strategy(
            enable_puts=False,
            ratio_min=3,
            ratio_max=3,
            min_net_inflow_usd=35,
            max_net_inflow_usd=0,
        )
        quotes = [
            quote(OptionKind.CALL, 104000, ask=10),
            quote(OptionKind.CALL, 107000, bid=15.01),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(len(opportunities), 1)
        self.assertAlmostEqual(opportunities[0].net_inflow, 35.03, places=2)

    def test_net_inflow_must_not_exceed_max_threshold(self) -> None:
        config = strategy(
            enable_puts=False,
            ratio_min=8,
            ratio_max=8,
            min_net_inflow_usd=20,
            max_net_inflow_usd=100,
        )
        quotes = [
            quote(OptionKind.CALL, 104000, ask=10),
            quote(OptionKind.CALL, 107000, bid=20),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities, [])

    def test_min_otm_distance_blocks_near_strikes(self) -> None:
        config = strategy(enable_puts=False, ratio_min=8, ratio_max=8, min_otm_distance=2000)
        quotes = [
            quote(OptionKind.CALL, 102000, ask=10),
            quote(OptionKind.CALL, 105000, bid=20),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities, [])

    def test_call_direction_requires_buy_above_spot_and_sell_above_buy(self) -> None:
        config = strategy(enable_puts=False, ratio_min=8, ratio_max=8, max_net_inflow_usd=1000)
        quotes = [
            quote(OptionKind.CALL, 104000, ask=10),
            quote(OptionKind.CALL, 107000, bid=20),
            quote(OptionKind.CALL, 103000, bid=100),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertTrue(opportunities)
        self.assertTrue(all(item.buy.strike < item.sell.strike for item in opportunities))
        self.assertTrue(all(item.buy.strike > item.spot_price for item in opportunities))

    def test_put_direction_requires_buy_below_spot_and_sell_below_buy(self) -> None:
        config = strategy(enable_calls=False, ratio_min=8, ratio_max=8, max_net_inflow_usd=1000)
        quotes = [
            quote(OptionKind.PUT, 98000, ask=10),
            quote(OptionKind.PUT, 95000, bid=20),
            quote(OptionKind.PUT, 99000, bid=100),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertTrue(opportunities)
        self.assertTrue(all(item.buy.strike > item.sell.strike for item in opportunities))
        self.assertTrue(all(item.buy.strike < item.spot_price for item in opportunities))

    def test_raw_premium_does_not_multiply_by_contract_value(self) -> None:
        config = strategy(enable_puts=False, ratio_min=3, ratio_max=3, min_net_inflow_usd=0)
        quotes = [
            quote(OptionKind.CALL, 104000, ask=10, contract_value=0.001),
            quote(OptionKind.CALL, 107000, bid=20, contract_value=0.001),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities[0].net_inflow, 50)

    def test_negative_atm_same_gap_same_ratio_is_required(self) -> None:
        config = strategy(
            enable_puts=False,
            ratio_min=3,
            ratio_max=3,
            min_net_inflow_usd=20,
            max_net_inflow_usd=100,
            min_otm_distance=2000,
            require_negative_atm_spread=True,
        )
        quotes = [
            quote(OptionKind.CALL, 101000, ask=100, bid=90),
            quote(OptionKind.CALL, 104000, ask=20, bid=10),
            quote(OptionKind.CALL, 107000, ask=30, bid=20),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].buy.strike, 104000)
        self.assertEqual(opportunities[0].sell.strike, 107000)
        self.assertEqual(opportunities[0].atm_buy.strike, 101000)
        self.assertEqual(opportunities[0].atm_sell.strike, 104000)
        self.assertEqual(opportunities[0].atm_net_inflow, -70)

    def test_positive_atm_same_gap_blocks_alert(self) -> None:
        config = strategy(
            enable_puts=False,
            ratio_min=3,
            ratio_max=3,
            min_net_inflow_usd=20,
            max_net_inflow_usd=100,
            min_otm_distance=2000,
            require_negative_atm_spread=True,
        )
        quotes = [
            quote(OptionKind.CALL, 101000, ask=10, bid=8),
            quote(OptionKind.CALL, 104000, ask=20, bid=10),
            quote(OptionKind.CALL, 107000, ask=30, bid=20),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities, [])

    def test_bid_ask_mode_uses_ask_for_buy_and_bid_for_sell(self) -> None:
        config = strategy(enable_puts=False, ratio_min=3, ratio_max=3, min_net_inflow_usd=0)
        quotes = [
            quote(OptionKind.CALL, 104000, mark=1, bid=1, ask=10),
            quote(OptionKind.CALL, 107000, mark=100, bid=20, ask=100),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities[0].buy_price, 10)
        self.assertEqual(opportunities[0].sell_price, 20)
        self.assertEqual(opportunities[0].net_inflow, 50)

    def test_fallback_to_mark_price_when_bid_ask_missing(self) -> None:
        config = strategy(enable_puts=False, ratio_min=3, ratio_max=3, min_net_inflow_usd=0)
        quotes = [
            quote(OptionKind.CALL, 104000, mark=10, bid=None, ask=None),
            quote(OptionKind.CALL, 107000, mark=20, bid=None, ask=None),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities[0].buy_price, 10)
        self.assertEqual(opportunities[0].sell_price, 20)

    def test_missing_bid_ask_skips_when_fallback_disabled(self) -> None:
        config = strategy(
            enable_puts=False,
            ratio_min=3,
            ratio_max=3,
            min_net_inflow_usd=0,
            fallback_to_mark_price=False,
        )
        quotes = [
            quote(OptionKind.CALL, 104000, mark=10, bid=None, ask=None),
            quote(OptionKind.CALL, 107000, mark=20, bid=None, ask=None),
        ]

        opportunities = RatioScanner(config).scan_expiry(EXPIRY, quotes, spot_price=101200)

        self.assertEqual(opportunities, [])

    def test_parses_delta_symbol_expiry_and_optional_market_fields(self) -> None:
        parsed = parse_option_quote(
            {
                "symbol": "P-BTC-77200-270526",
                "product_id": 294367,
                "contract_type": "put_options",
                "strike_price": "77200",
                "mark_price": "525.62",
                "spot_price": "77076.4",
                "contract_value": "0.001",
                "volume": 3,
                "oi": "0.0010",
                "quotes": {
                    "best_bid": "515",
                    "best_ask": "557",
                    "bid_size": "10",
                    "ask_size": "12",
                },
            }
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.expiry, date(2026, 5, 27))
        self.assertEqual(parsed.kind, OptionKind.PUT)
        self.assertEqual(parsed.underlying_asset, "BTC")
        self.assertEqual(parsed.contract_value, 0.001)
        self.assertEqual(parsed.bid_size, 10)
        self.assertEqual(parsed.ask_size, 12)
        self.assertEqual(parsed.volume, 3)
        self.assertEqual(parsed.open_interest, 0.001)


if __name__ == "__main__":
    unittest.main()
