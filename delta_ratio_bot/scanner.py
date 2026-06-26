from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import logging

from .config import StrategyConfig
from .models import OptionKind, OptionQuote, RatioOpportunity

LOGGER = logging.getLogger(__name__)


class RatioScanner:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def scan_expiry(
        self,
        expiry: date,
        quotes: Iterable[OptionQuote],
        spot_price: float,
    ) -> list[RatioOpportunity]:
        by_kind: dict[OptionKind, list[OptionQuote]] = {
            OptionKind.CALL: [],
            OptionKind.PUT: [],
        }
        for quote in quotes:
            if quote.expiry == expiry:
                by_kind[quote.kind].append(quote)

        opportunities: list[RatioOpportunity] = []
        if self.config.enable_calls:
            opportunities.extend(self._scan_kind(OptionKind.CALL, by_kind[OptionKind.CALL], spot_price))
        if self.config.enable_puts:
            opportunities.extend(self._scan_kind(OptionKind.PUT, by_kind[OptionKind.PUT], spot_price))
        return sorted(opportunities, key=lambda item: item.net_inflow, reverse=True)

    def _scan_kind(
        self,
        kind: OptionKind,
        quotes: list[OptionQuote],
        spot_price: float,
    ) -> list[RatioOpportunity]:
        sorted_quotes = sorted(quotes, key=lambda quote: quote.strike)
        by_strike = {quote.strike: quote for quote in sorted_quotes}
        atm = self._nearest_atm_quote(sorted_quotes, spot_price)
        opportunities: list[RatioOpportunity] = []
        for buy in sorted_quotes:
            if not self._is_otm(kind, buy.strike, spot_price):
                continue
            buy_distance = abs(buy.strike - spot_price)
            if buy_distance < self.config.min_otm_distance:
                continue
            buy_price = self.get_buy_price(buy)
            if buy_price is None or buy_price <= 0:
                continue

            for sell in sorted_quotes:
                if buy.symbol == sell.symbol:
                    continue
                if not self._valid_sell_strike(kind, buy.strike, sell.strike):
                    continue
                strike_difference = abs(sell.strike - buy.strike)
                if strike_difference < self.config.min_strike_difference:
                    continue
                if (
                    self.config.max_strike_difference > 0
                    and strike_difference > self.config.max_strike_difference
                ):
                    continue
                sell_distance = abs(sell.strike - spot_price)
                if sell_distance < self.config.min_otm_distance:
                    continue
                sell_price = self.get_sell_price(sell)
                if sell_price is None or sell_price <= 0:
                    continue
                if (
                    self.config.max_sell_premium_percent_of_buy > 0
                    and sell_price > buy_price * self.config.max_sell_premium_percent_of_buy / 100
                ):
                    continue

                for ratio in self.config.ratios:
                    # Current live mode uses raw Delta quote prices only. Do not multiply by contract_value.
                    net_inflow = ratio * sell_price - buy_price
                    if net_inflow < self.config.min_net_inflow_usd:
                        continue
                    if (
                        self.config.max_net_inflow_usd > 0
                        and net_inflow > self.config.max_net_inflow_usd
                    ):
                        continue
                    atm_buy = None
                    atm_sell = None
                    atm_net_inflow = None
                    if self.config.require_negative_atm_spread:
                        atm_result = self._negative_atm_spread(
                            kind=kind,
                            atm=atm,
                            by_strike=by_strike,
                            strike_difference=strike_difference,
                            ratio=ratio,
                        )
                        if atm_result is None:
                            continue
                        atm_buy, atm_sell, atm_net_inflow = atm_result
                    opportunities.append(
                        RatioOpportunity(
                            underlying_asset=buy.underlying_asset,
                            kind=kind,
                            expiry=buy.expiry,
                            ratio=ratio,
                            buy=buy,
                            sell=sell,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            net_inflow=net_inflow,
                            strike_difference=strike_difference,
                            spot_price=spot_price,
                            distance_from_spot=min(buy_distance, sell_distance),
                            atm_buy=atm_buy,
                            atm_sell=atm_sell,
                            atm_net_inflow=atm_net_inflow,
                        )
                    )
        return opportunities

    @staticmethod
    def _is_otm(kind: OptionKind, strike: float, spot_price: float) -> bool:
        if kind == OptionKind.CALL:
            return strike > spot_price
        return strike < spot_price

    @staticmethod
    def _valid_sell_strike(kind: OptionKind, buy_strike: float, sell_strike: float) -> bool:
        if kind == OptionKind.CALL:
            return sell_strike > buy_strike
        return sell_strike < buy_strike

    def get_buy_price(self, option: OptionQuote) -> float | None:
        if self.config.premium_mode == "mark":
            return _positive_or_none(option.mark_price)
        if option.best_ask and option.best_ask > 0:
            return option.best_ask
        if self.config.require_bid_ask or not self.config.fallback_to_mark_price:
            return None
        return _positive_or_none(option.mark_price)

    def get_sell_price(self, option: OptionQuote) -> float | None:
        if self.config.premium_mode == "mark":
            return _positive_or_none(option.mark_price)
        if option.best_bid and option.best_bid > 0:
            return option.best_bid
        if self.config.require_bid_ask or not self.config.fallback_to_mark_price:
            return None
        return _positive_or_none(option.mark_price)

    @staticmethod
    def _nearest_atm_quote(quotes: list[OptionQuote], spot_price: float) -> OptionQuote | None:
        if not quotes:
            return None
        return min(quotes, key=lambda quote: abs(quote.strike - spot_price))

    def _negative_atm_spread(
        self,
        *,
        kind: OptionKind,
        atm: OptionQuote | None,
        by_strike: dict[float, OptionQuote],
        strike_difference: float,
        ratio: int,
    ) -> tuple[OptionQuote, OptionQuote, float] | None:
        if atm is None:
            return None
        atm_sell_strike = (
            atm.strike + strike_difference
            if kind == OptionKind.CALL
            else atm.strike - strike_difference
        )
        atm_sell = by_strike.get(atm_sell_strike)
        if atm_sell is None:
            return None
        atm_buy_price = self.get_buy_price(atm)
        atm_sell_price = self.get_sell_price(atm_sell)
        if atm_buy_price is None or atm_sell_price is None:
            return None
        atm_net_inflow = ratio * atm_sell_price - atm_buy_price
        if atm_net_inflow >= 0:
            return None
        return atm, atm_sell, atm_net_inflow


def _positive_or_none(value: float | None) -> float | None:
    if value is not None and value > 0:
        return value
    return None
