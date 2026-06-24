from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class OptionKind(StrEnum):
    CALL = "call"
    PUT = "put"


@dataclass(frozen=True)
class OptionQuote:
    underlying_asset: str
    symbol: str
    product_id: int | None
    kind: OptionKind
    expiry: date
    strike: float
    mark_price: float | None
    best_bid: float | None
    best_ask: float | None
    spot_price: float | None
    contract_value: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    volume: float | None = None
    open_interest: float | None = None


@dataclass(frozen=True)
class RatioOpportunity:
    underlying_asset: str
    kind: OptionKind
    expiry: date
    ratio: int
    buy: OptionQuote
    sell: OptionQuote
    buy_price: float
    sell_price: float
    net_inflow: float
    strike_difference: float
    spot_price: float
    distance_from_spot: float
    atm_buy: OptionQuote | None = None
    atm_sell: OptionQuote | None = None
    atm_net_inflow: float | None = None

    @property
    def strategy_type(self) -> str:
        return "CALL RATIO SPREAD" if self.kind == OptionKind.CALL else "PUT RATIO SPREAD"

    @property
    def dedupe_key(self) -> str:
        return "|".join(
            [
                self.underlying_asset,
                self.strategy_type,
                self.expiry.isoformat(),
                str(self.ratio),
                self.buy.symbol,
                self.sell.symbol,
            ]
        )
