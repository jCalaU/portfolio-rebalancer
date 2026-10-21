from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Context, Decimal, Inexact, ROUND_HALF_EVEN, Underflow, localcontext
from types import MappingProxyType
from typing import Literal


# Use extra digits to reduce rounding errors.
CALCULATION_PRECISION = 50
ALLOCATION_TOLERANCE = Decimal("0.000001")
ZERO = Decimal("0")
ONE = Decimal("1")


def _money_context() -> Context:
    # Use a local context so caller settings do not change results.
    context = Context(prec=CALCULATION_PRECISION, rounding=ROUND_HALF_EVEN)
    context.traps[Inexact] = False
    context.traps[Underflow] = True
    return context


def _exact_sum(values: Iterable[Decimal]) -> Decimal:
    values = [value for value in values if value != ZERO]
    if not values:
        return ZERO
    # Keep small amounts when adding values of different sizes.
    with localcontext(_money_context()) as context:
        context.prec = max(
            CALCULATION_PRECISION,
            max(value.adjusted() for value in values)
            - min(value.as_tuple().exponent for value in values)
            + len(str(len(values))) + 1,
        )
        context.traps[Inexact] = True
        return sum(values, ZERO)


def _exact_product(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_money_context()) as context:
        context.prec = max(
            CALCULATION_PRECISION,
            len(left.as_tuple().digits) + len(right.as_tuple().digits),
        )
        context.traps[Inexact] = True
        return left * right


def _validate_symbol(symbol: str) -> None:
    if not isinstance(symbol, str):
        raise TypeError("Stock symbols must be strings")
    if not symbol or symbol != symbol.strip():
        raise ValueError("Stock symbols must be nonempty without surrounding whitespace")


def _validate_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class Stock:
    symbol: str
    last_available_price: Decimal

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)
        _validate_decimal(self.last_available_price, "Stock price")
        if self.last_available_price <= ZERO:
            raise ValueError("Stock price must be positive")

    def current_price(self) -> Decimal:
        return self.last_available_price


@dataclass(frozen=True)
class Trade:
    symbol: str
    action: Literal["BUY", "SELL"]
    value: Decimal
    reference_price: Decimal

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)
        if self.action not in ("BUY", "SELL"):
            raise ValueError("Trade action must be BUY or SELL")
        _validate_decimal(self.value, "Trade value")
        _validate_decimal(self.reference_price, "Reference price")
        if self.value <= ZERO or self.reference_price <= ZERO:
            raise ValueError("Trade value and reference price must be positive")

    @property
    def estimated_quantity(self) -> Decimal:
        with localcontext(_money_context()):
            return self.value / self.reference_price


@dataclass(frozen=True, init=False)
class Portfolio:
    stocks: Mapping[str, Stock]
    holdings: Mapping[str, Decimal]
    allocation: Mapping[str, Decimal]

    def __init__(
        self,
        stocks: Iterable[Stock],
        holdings: Mapping[str, Decimal],
        allocation: Mapping[str, Decimal],
    ) -> None:
        stock_by_symbol = {}
        for stock in stocks:
            if not isinstance(stock, Stock):
                raise TypeError("Stocks must contain Stock instances")
            if stock.symbol in stock_by_symbol:
                raise ValueError(f"Duplicate stock symbol: {stock.symbol}")
            stock_by_symbol[stock.symbol] = stock

        quantities = dict(holdings)
        weights = dict(allocation)

        for symbol, quantity in quantities.items():
            if symbol not in stock_by_symbol:
                raise ValueError(f"Unknown stock symbol: {symbol!r}")
            _validate_decimal(quantity, "Holding quantity")
            if quantity < ZERO:
                raise ValueError("Holding quantities must be nonnegative")

        for symbol, weight in weights.items():
            if symbol not in stock_by_symbol:
                raise ValueError(f"Unknown stock symbol: {symbol!r}")
            _validate_decimal(weight, "Allocation weight")
            if not ZERO <= weight <= ONE:
                raise ValueError("Allocation weights must be between 0 and 1")

        weight_total = _exact_sum(weights.values())
        weight_error = _exact_sum((weight_total, ONE.copy_negate())).copy_abs()
        if weight_error > ALLOCATION_TOLERANCE:
            raise ValueError(
                f"Allocation weights must sum to 1 within {ALLOCATION_TOLERANCE}"
            )
        if weight_total != ONE:
            with localcontext(_money_context()):
                weights = {
                    symbol: weights[symbol] / weight_total for symbol in sorted(weights)
                }
            # Give the small remainder to the largest weight; ties use the symbol.
            residual_symbol = max(sorted(weights), key=weights.__getitem__)
            weights[residual_symbol] = _exact_sum(
                [ONE]
                + [weight.copy_negate() for symbol, weight in weights.items()
                   if symbol != residual_symbol]
            )

        object.__setattr__(self, "stocks", MappingProxyType(stock_by_symbol))
        object.__setattr__(self, "holdings", MappingProxyType(quantities))
        object.__setattr__(self, "allocation", MappingProxyType(weights))

    def rebalance(self) -> tuple[Trade, ...]:
        # Return a plan so trades can be reviewed first.
        with localcontext(_money_context()):
            symbols = sorted(self.holdings.keys() | self.allocation.keys())
            prices = {
                symbol: self.stocks[symbol].current_price() for symbol in symbols
            }
            current_values = {
                symbol: _exact_product(self.holdings.get(symbol, ZERO), prices[symbol])
                for symbol in symbols
            }
            total_value = _exact_sum(current_values.values())
            target_values = {
                symbol: total_value * self.allocation.get(symbol, ZERO)
                for symbol in symbols
            }
            # Keep the full portfolio value after rounding the targets.
            residual_symbol = max(
                sorted(self.allocation), key=self.allocation.__getitem__
            )
            target_values[residual_symbol] = _exact_sum(
                [total_value]
                + [value.copy_negate() for symbol, value in target_values.items()
                   if symbol != residual_symbol]
            )
            trades = []

            for symbol in symbols:
                difference = _exact_sum(
                    (target_values[symbol], current_values[symbol].copy_negate())
                )
                if difference == ZERO:
                    continue
                trades.append(
                    Trade(
                        symbol=symbol,
                        action="BUY" if difference > ZERO else "SELL",
                        value=difference.copy_abs(),
                        reference_price=prices[symbol],
                    )
                )

        # List sells first to help fund buys.
        return tuple(
            sorted(trades, key=lambda trade: (trade.action == "BUY", trade.symbol))
        )
