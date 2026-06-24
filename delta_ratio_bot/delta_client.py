from __future__ import annotations

import asyncio
from datetime import date, datetime
import logging
import ssl
from typing import Any

import aiohttp
import certifi

from .models import OptionKind, OptionQuote

LOGGER = logging.getLogger(__name__)


class DeltaClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"Accept": "application/json"},
            connector=connector,
        )

    async def close(self) -> None:
        await self._session.close()

    async def get_spot_price(self, underlying_asset: str) -> float:
        indices = await self._get_json("/v2/indices")
        candidates = indices if isinstance(indices, list) else []
        wanted = underlying_asset.upper()
        for index in candidates:
            symbol = str(index.get("symbol", "")).upper()
            if wanted in symbol:
                price = await self._price_from_spot_ticker(symbol)
                if price is not None:
                    return price
        tickers = await self.get_option_tickers(underlying_asset)
        for ticker in tickers:
            spot = _to_float(ticker.get("spot_price"))
            if spot and spot > 0:
                return spot
        raise RuntimeError(f"Could not resolve spot price for {underlying_asset}")

    async def get_expiries(self, underlying_asset: str) -> list[date]:
        params = {
            "contract_types": "call_options,put_options",
            "states": "live",
            "page_size": "500",
        }
        products = await self._get_paginated("/v2/products", params)
        expiries: set[date] = set()
        for product in products:
            if not _matches_underlying(product, underlying_asset):
                continue
            expiry = _parse_expiry(product.get("settlement_time") or product.get("expiry"))
            if expiry:
                expiries.add(expiry)
        if expiries:
            return sorted(expiries)

        LOGGER.warning("No expiries found from products; falling back to all option tickers")
        tickers = await self.get_option_tickers(underlying_asset)
        return sorted({q.expiry for q in map(parse_option_quote, tickers) if q})

    async def get_option_chain(self, underlying_asset: str, expiry: date) -> list[OptionQuote]:
        params = {
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": underlying_asset.upper(),
            "expiry_date": expiry.strftime("%d-%m-%Y"),
        }
        tickers = await self._get_json("/v2/tickers", params)
        quotes = [
            quote
            for ticker in tickers
            for quote in [parse_option_quote(ticker, underlying_asset)]
            if quote
        ]
        return sorted(quotes, key=lambda q: (q.kind.value, q.strike, q.symbol))

    async def get_option_tickers(self, underlying_asset: str) -> list[dict[str, Any]]:
        params = {
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": underlying_asset.upper(),
        }
        tickers = await self._get_json("/v2/tickers", params)
        return list(tickers or [])

    async def _price_from_spot_ticker(self, symbol: str) -> float | None:
        try:
            payload = await self._get_json(f"/v2/tickers/{symbol}")
        except Exception as exc:
            LOGGER.debug("Spot ticker lookup failed for %s: %s", symbol, exc)
            return None
        if not payload:
            return None
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            return None
        for field in ("mark_price", "spot_price", "close"):
            price = _to_float(payload.get(field))
            if price and price > 0:
                return price
        return None

    async def _get_paginated(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(20):
            page_params = dict(params)
            if cursor:
                page_params["after"] = cursor
            payload = await self._request(path, page_params)
            result = payload.get("result") or []
            if isinstance(result, dict):
                items = result.get("data") or result.get("items") or []
                meta = result.get("meta") or payload.get("meta") or {}
            else:
                items = result
                meta = payload.get("meta") or {}
            all_items.extend(items)
            cursor = (
                meta.get("after")
                or meta.get("next")
                or meta.get("next_cursor")
                or meta.get("after_cursor")
            )
            if not cursor:
                break
            await asyncio.sleep(0)
        return all_items

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        payload = await self._request(path, params or {})
        return payload.get("result")

    async def _request(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with self._session.get(url, params=params) as response:
            data = await response.json(content_type=None)
            if response.status >= 400 or not data.get("success", False):
                if response.status == 429:
                    LOGGER.warning("Delta API rate limit hit for %s: %s", path, data)
                elif response.status >= 500:
                    LOGGER.warning("Delta API server error %s for %s: %s", response.status, path, data)
                else:
                    LOGGER.warning("Delta API error %s for %s: %s", response.status, path, data)
                raise RuntimeError(f"Delta API error {response.status} for {path}: {data}")
            return data


def parse_option_quote(ticker: dict[str, Any], fallback_underlying: str | None = None) -> OptionQuote | None:
    contract_type = str(ticker.get("contract_type", "")).lower()
    if contract_type == "call_options":
        kind = OptionKind.CALL
    elif contract_type == "put_options":
        kind = OptionKind.PUT
    else:
        return None

    expiry = _parse_expiry(
        ticker.get("settlement_time")
        or ticker.get("expiry")
        or ticker.get("expiry_date")
        or _expiry_from_symbol(str(ticker.get("symbol", "")))
    )
    strike = _to_float(ticker.get("strike_price"))
    if expiry is None or strike is None:
        return None

    quotes = ticker.get("quotes") or {}
    return OptionQuote(
        underlying_asset=str(
            ticker.get("underlying_asset_symbol")
            or fallback_underlying
            or _underlying_from_symbol(str(ticker.get("symbol", "")))
            or ""
        ).upper(),
        symbol=str(ticker.get("symbol", "")),
        product_id=_to_int(ticker.get("product_id")),
        kind=kind,
        expiry=expiry,
        strike=strike,
        mark_price=_to_float(ticker.get("mark_price")),
        best_bid=_to_float(quotes.get("best_bid")),
        best_ask=_to_float(quotes.get("best_ask")),
        spot_price=_to_float(ticker.get("spot_price")),
        contract_value=_to_float(ticker.get("contract_value")),
        bid_size=_to_float(quotes.get("bid_size")),
        ask_size=_to_float(quotes.get("ask_size")),
        volume=_to_float(ticker.get("volume")),
        open_interest=_to_float(ticker.get("oi") or ticker.get("open_interest")),
    )


def _matches_underlying(product: dict[str, Any], underlying_asset: str) -> bool:
    wanted = underlying_asset.upper()
    for key in ("underlying_asset", "contract_unit_currency"):
        value = product.get(key)
        if isinstance(value, dict) and str(value.get("symbol", "")).upper() == wanted:
            return True
        if str(value).upper() == wanted:
            return True
    return wanted in str(product.get("symbol", "")).upper()


def _parse_expiry(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _expiry_from_symbol(symbol: str) -> str | None:
    parts = symbol.replace("_", "-").split("-")
    for part in parts:
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
        if len(part) == 6 and part.isdigit():
            try:
                return datetime.strptime(part, "%d%m%y").date().isoformat()
            except ValueError:
                continue
    return None


def _underlying_from_symbol(symbol: str) -> str | None:
    parts = symbol.replace("_", "-").split("-")
    if len(parts) >= 2 and parts[0] in {"C", "P"}:
        return parts[1]
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
