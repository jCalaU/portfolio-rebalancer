import random
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal, Inexact, ROUND_UP, Underflow, localcontext
from fractions import Fraction

from portfolio import Portfolio, Stock


D = Decimal


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.stocks = [
            Stock("FTUL", D("500")),
            Stock("MELI", D("250")),
            Stock("NU", D("100")),
        ]
        self.holdings = {"FTUL": D("8"), "MELI": D("16"), "NU": D("20")}
        self.allocation = {"FTUL": D("0.6"), "MELI": D("0.2"), "NU": D("0.2")}

    def portfolio(self, **overrides):
        inputs = {
            "stocks": self.stocks,
            "holdings": self.holdings,
            "allocation": self.allocation,
        }
        inputs.update(overrides)
        return Portfolio(**inputs)

    def resulting_values(self, portfolio):
        values = {
            symbol: Fraction(portfolio.holdings.get(symbol, D("0")))
            * Fraction(stock.current_price())
            for symbol, stock in portfolio.stocks.items()
        }
        initial_total = sum(values.values(), Fraction(0))
        trades = portfolio.rebalance()
        sales = purchases = Fraction(0)
        for trade in trades:
            value = Fraction(trade.value)
            self.assertGreater(value, 0)
            if trade.action == "SELL":
                self.assertLessEqual(value, values[trade.symbol])
                values[trade.symbol] -= value
                sales += value
            else:
                self.assertEqual(trade.action, "BUY")
                values[trade.symbol] += value
                purchases += value
        self.assertEqual(sum(values.values(), Fraction(0)), initial_total)
        self.assertEqual(sales, purchases)
        self.assertEqual(
            [trade.action for trade in trades],
            sorted((trade.action for trade in trades), reverse=True),
        )
        return values

    def test_current_price_returns_supplied_snapshot(self):
        self.assertEqual(Stock("MELI", D("250.01")).current_price(), D("250.01"))

    def test_rebalance_returns_expected_sales_and_purchases(self):
        trades = self.portfolio().rebalance()

        self.assertIsInstance(trades, tuple)
        self.assertEqual(
            [(trade.symbol, trade.action, trade.value, trade.reference_price,
              trade.estimated_quantity) for trade in trades],
            [("MELI", "SELL", D("2000"), D("250"), D("8")),
             ("FTUL", "BUY", D("2000"), D("500"), D("4"))],
        )

    def test_weights_use_position_values_instead_of_share_counts(self):
        trades = self.portfolio(
            holdings={"FTUL": D("10"), "MELI": D("10"), "NU": D("10")},
        ).rebalance()

        self.assertEqual([(trade.action, trade.value) for trade in trades],
                         [("SELL", D("800")), ("BUY", D("100")),
                          ("BUY", D("700"))])

    def test_balanced_portfolio_returns_no_trades(self):
        self.assertEqual(self.portfolio(
            holdings={"FTUL": D("12"), "MELI": D("8"), "NU": D("20")},
        ).rebalance(), ())

    def test_unallocated_holdings_are_sold_and_new_targets_are_bought(self):
        stocks = self.stocks + [Stock("NVDA", D("1000"))]
        trades = self.portfolio(
            stocks=stocks,
            holdings={"FTUL": D("10"), "NVDA": D("5")},
        ).rebalance()

        self.assertEqual(
            [(trade.symbol, trade.action, trade.value) for trade in trades],
            [("NVDA", "SELL", D("5000")),
             ("FTUL", "BUY", D("1000")),
             ("MELI", "BUY", D("2000")),
             ("NU", "BUY", D("2000"))],
        )

    def test_explicit_zero_target_liquidates_the_position(self):
        trades = self.portfolio(
            allocation={"FTUL": D("0"), "MELI": D("1"), "NU": D("0")},
        ).rebalance()
        self.assertEqual(trades[0].symbol, "FTUL")
        self.assertEqual(trades[0].estimated_quantity, self.holdings["FTUL"])

    def test_empty_or_zero_holdings_do_not_create_value(self):
        for holdings in ({}, {"FTUL": D("0"), "MELI": D("0"), "NU": D("0")}):
            with self.subTest(holdings=holdings):
                self.assertEqual(self.portfolio(holdings=holdings).rebalance(), ())

    def test_decimal_prices_preserve_small_trade_values(self):
        portfolio = Portfolio(
            [Stock("FTUL", D("0.10")), Stock("MELI", D("0.20"))],
            {"FTUL": D("3"), "MELI": D("1")},
            {"FTUL": D("0.5"), "MELI": D("0.5")},
        )
        self.assertEqual([trade.value for trade in portfolio.rebalance()],
                         [D("0.05"), D("0.05")])

    def test_repeating_share_estimate_does_not_round_the_authoritative_value(self):
        portfolio = Portfolio(
            [Stock("FTUL", D("2")), Stock("MELI", D("3"))],
            {"FTUL": D("1")}, {"MELI": D("1")},
        )
        purchase = portfolio.rebalance()[1]
        self.assertEqual(purchase.value, D("2"))
        self.assertEqual(purchase.estimated_quantity, D("0." + "6" * 49 + "7"))

    def test_share_estimate_underflow_raises_instead_of_returning_zero(self):
        portfolio = Portfolio(
            [Stock("FTUL", D("1e999999")), Stock("MELI", D("1"))],
            {"FTUL": D("1e-1000049")},
            {"FTUL": D("0.5"), "MELI": D("0.5")},
        )
        sale = portfolio.rebalance()[0]
        self.assertGreater(sale.value, D("0"))
        with self.assertRaises(Underflow):
            sale.estimated_quantity

    def test_rebalance_and_quantity_estimates_ignore_callers_decimal_context(self):
        portfolio = self.portfolio()
        expected = portfolio.rebalance()
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            before = (context.prec, context.rounding, dict(context.traps),
                      dict(context.flags))
            constructed = self.portfolio()
            self.assertEqual(constructed.rebalance(), expected)
            self.assertEqual(portfolio.rebalance(), expected)
            self.assertEqual(expected[0].estimated_quantity, D("8"))
            self.assertEqual((context.prec, context.rounding, dict(context.traps),
                              dict(context.flags)), before)

        repeating = Portfolio(
            [Stock("FTUL", D("2")), Stock("MELI", D("3"))],
            {"FTUL": D("1")}, {"MELI": D("1")},
        ).rebalance()[1]
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            before_flags = dict(context.flags)
            self.assertEqual(repeating.estimated_quantity, D("0." + "6" * 49 + "7"))
            self.assertEqual(dict(context.flags), before_flags)

    def test_totals_beyond_fifty_digits_keep_exact_value_after_target_rounding(self):
        portfolio = Portfolio(
            [Stock("FTUL", D("1")), Stock("MELI", D("1"))],
            {"FTUL": D("1e50"), "MELI": D("1")},
            {"FTUL": D("0.5"), "MELI": D("0.5")},
        )
        values = self.resulting_values(portfolio)
        self.assertEqual(values["FTUL"], Fraction(10 ** 50, 2) + 1)
        self.assertEqual(values["MELI"], Fraction(10 ** 50, 2))

    def test_position_values_beyond_fifty_digits_are_preserved_exactly(self):
        portfolio = Portfolio(
            [Stock("FTUL", D("123456789012345678901234567890123456789012345678901234567890.123")),
             Stock("MELI", D("0.0001"))],
            {"FTUL": D("2.01"), "MELI": D("1")},
            {"FTUL": D("0.6"), "MELI": D("0.4")},
        )
        self.resulting_values(portfolio)

    def test_trade_differences_keep_residuals_beyond_fifty_digits(self):
        tiny = D("1e-60")
        portfolio = Portfolio(
            [Stock("FTUL", D("1")), Stock("MELI", D("1"))],
            {"FTUL": D("1"), "MELI": tiny},
            {"FTUL": D("0.5"), "MELI": D("0.5")},
        )
        values = self.resulting_values(portfolio)
        self.assertEqual(values["FTUL"], Fraction(1, 2) + Fraction(tiny))
        self.assertEqual(values["MELI"], Fraction(1, 2))
        self.assertEqual(
            [(trade.action, Fraction(trade.value)) for trade in portfolio.rebalance()],
            [("SELL", Fraction(1, 2) - Fraction(tiny)),
             ("BUY", Fraction(1, 2) - Fraction(tiny))],
        )

    def test_tiny_allocation_excess_is_accepted_and_normalized(self):
        portfolio = self.portfolio(
            allocation={"FTUL": D("1"), "MELI": D("1e-60"), "NU": D("0")},
        )
        self.assertEqual(sum(map(Fraction, portfolio.allocation.values())), 1)
        self.assertGreater(portfolio.allocation["MELI"], D("0"))
        self.assertEqual(portfolio.allocation["NU"], D("0"))
        self.resulting_values(portfolio)

    def test_allocation_tolerance_includes_both_boundaries(self):
        with localcontext() as context:
            context.prec = 200
            tolerance = D("0.000001")
            tiny = D("1e-60")
            for sign in (-1, 1):
                for distance in (tolerance - tiny, tolerance):
                    allocation = {"FTUL": D("0.5"),
                                  "MELI": D("0.5") + sign * distance}
                    with self.subTest(sign=sign, distance=distance):
                        portfolio = self.portfolio(allocation=allocation)
                        self.assertEqual(
                            sum(map(Fraction, portfolio.allocation.values())), 1,
                        )
                        self.resulting_values(portfolio)

    def test_allocation_tolerance_rejects_values_just_outside_both_boundaries(self):
        with localcontext() as context:
            context.prec = 200
            distance = D("0.000001") + D("1e-60")
            for sign in (-1, 1):
                allocation = {"FTUL": D("0.5"),
                              "MELI": D("0.5") + sign * distance}
                with self.subTest(sign=sign), self.assertRaises(ValueError):
                    self.portfolio(allocation=allocation)

    def test_approximate_thirds_are_normalized_with_a_deterministic_residual(self):
        allocation = dict.fromkeys(("NU", "MELI", "FTUL"), D("0.333333"))
        portfolio = self.portfolio(allocation=allocation)
        third = D("0." + "3" * 50)
        self.assertEqual(dict(portfolio.allocation), {
            "FTUL": D("0." + "3" * 49 + "4"),
            "MELI": third,
            "NU": third,
        })
        self.assertEqual(allocation, dict.fromkeys(allocation, D("0.333333")))
        self.resulting_values(portfolio)

    def test_normalization_assigns_its_residual_to_the_largest_weight(self):
        portfolio = self.portfolio(
            allocation={"FTUL": D("0.1666665"), "MELI": D("0.666666"),
                        "NU": D("0.1666665")},
        )
        sixth = D("0.1" + "6" * 48 + "7")
        self.assertEqual(dict(portfolio.allocation), {
            "FTUL": sixth, "MELI": D("0." + "6" * 50), "NU": sixth,
        })
        self.resulting_values(portfolio)

    def test_target_rounding_residual_goes_to_the_largest_weight(self):
        with localcontext() as context:
            context.prec = 200
            third = D("0." + "3" * 60)
            largest = D("1") - third * 2
        portfolio = self.portfolio(
            stocks=[Stock(symbol, D("1")) for symbol in ("FTUL", "MELI", "NU")],
            holdings={"FTUL": D("1")},
            allocation={"FTUL": third, "MELI": third, "NU": largest},
        )
        self.assertEqual(portfolio.allocation["NU"], largest)
        values = self.resulting_values(portfolio)
        self.assertEqual(values["FTUL"], Fraction(D("0." + "3" * 50)))
        self.assertEqual(values["MELI"], Fraction(D("0." + "3" * 50)))
        self.assertEqual(values["NU"], Fraction(D("0." + "3" * 49 + "4")))

    def test_normalization_preserves_zero_targets(self):
        portfolio = self.portfolio(
            allocation={"FTUL": D("0"), "MELI": D("0.999999"), "NU": D("0")},
        )
        self.assertEqual(dict(portfolio.allocation), {
            "FTUL": D("0"), "MELI": D("1"), "NU": D("0"),
        })
        values = self.resulting_values(portfolio)
        self.assertEqual(values["FTUL"], 0)
        self.assertEqual(values["NU"], 0)

    def test_normalization_and_rounded_targets_ignore_callers_decimal_context(self):
        allocation = dict.fromkeys(self.allocation, D("0.333333"))
        expected = self.portfolio(allocation=allocation)
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            before = (context.prec, context.rounding, dict(context.traps),
                      dict(context.flags))
            actual = self.portfolio(allocation=allocation)
            self.assertEqual(actual.allocation, expected.allocation)
            self.assertEqual(actual.rebalance(), expected.rebalance())
            self.assertEqual((context.prec, context.rounding, dict(context.traps),
                              dict(context.flags)), before)

    def test_normalized_plans_are_deterministic_and_do_not_mutate_inputs(self):
        allocation = dict.fromkeys(self.allocation, D("0.333333"))
        original = dict(allocation)
        portfolio = self.portfolio(allocation=allocation)
        before = (dict(portfolio.stocks), dict(portfolio.holdings),
                  dict(portfolio.allocation))
        trades = portfolio.rebalance()
        reordered = self.portfolio(
            stocks=reversed(self.stocks),
            holdings=dict(reversed(list(self.holdings.items()))),
            allocation=dict(reversed(list(allocation.items()))),
        )
        self.assertEqual(portfolio.rebalance(), trades)
        self.assertEqual(reordered.rebalance(), trades)
        self.assertEqual((dict(portfolio.stocks), dict(portfolio.holdings),
                          dict(portfolio.allocation)), before)
        self.assertEqual(allocation, original)
        self.assertEqual(self.holdings, {"FTUL": D("8"), "MELI": D("16"), "NU": D("20")})

    def test_input_collection_order_does_not_change_the_plan(self):
        expected = self.portfolio().rebalance()
        actual = self.portfolio(
            stocks=reversed(self.stocks),
            holdings=dict(reversed(list(self.holdings.items()))),
            allocation=dict(reversed(list(self.allocation.items()))),
        ).rebalance()
        self.assertEqual(actual, expected)

    def test_rebalance_does_not_mutate_the_portfolio(self):
        portfolio = self.portfolio()
        before = (dict(portfolio.stocks), dict(portfolio.holdings),
                  dict(portfolio.allocation))
        self.assertEqual(portfolio.rebalance(), portfolio.rebalance())
        self.assertEqual((dict(portfolio.stocks), dict(portfolio.holdings),
                          dict(portfolio.allocation)), before)

    def test_portfolio_copies_input_collections(self):
        portfolio = self.portfolio()
        self.stocks.clear()
        self.holdings["FTUL"] = D("999")
        self.allocation.clear()
        self.assertEqual(set(portfolio.stocks), {"FTUL", "MELI", "NU"})
        self.assertEqual(portfolio.holdings["FTUL"], D("8"))
        self.assertEqual(portfolio.allocation["FTUL"], D("0.6"))

    def test_exposed_mappings_are_read_only(self):
        portfolio = self.portfolio()
        for mapping in (portfolio.stocks, portfolio.holdings, portfolio.allocation):
            with self.subTest(mapping=mapping):
                with self.assertRaises(TypeError):
                    mapping["FTUL"] = D("0")

    def test_stock_and_trade_snapshots_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.stocks[0].last_available_price = D("1")
        trade = self.portfolio().rebalance()[0]
        with self.assertRaises(FrozenInstanceError):
            trade.value = D("1")

    def test_reapplying_a_finite_share_plan_is_balanced(self):
        portfolio = self.portfolio()
        holdings = dict(portfolio.holdings)
        for trade in portfolio.rebalance():
            direction = D("1") if trade.action == "BUY" else D("-1")
            holdings[trade.symbol] = holdings.get(trade.symbol, D("0")) + (
                direction * trade.estimated_quantity
            )
        self.assertEqual(self.portfolio(holdings=holdings).rebalance(), ())

    def test_invalid_stock_symbols_are_rejected(self):
        for symbol in ("", " ", " FTUL", "FTUL "):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                Stock(symbol, D("1"))
        with self.assertRaises(TypeError):
            Stock(None, D("1"))

    def test_invalid_prices_are_rejected(self):
        for price in (D("0"), D("-1"), D("NaN"), D("sNaN"),
                      D("Infinity"), D("-Infinity")):
            with self.subTest(price=price), self.assertRaises(ValueError):
                Stock("FTUL", price)

    def test_non_decimal_numeric_inputs_are_rejected(self):
        for value in (1, 0.5, "1", True, None):
            with self.subTest(field="price", value=value), self.assertRaises(TypeError):
                Stock("FTUL", value)
            with self.subTest(field="holding", value=value), self.assertRaises(TypeError):
                self.portfolio(holdings={"FTUL": value})
            with self.subTest(field="allocation", value=value), self.assertRaises(TypeError):
                self.portfolio(allocation={"FTUL": value})

    def test_invalid_holdings_are_rejected(self):
        for quantity in (D("-1"), D("NaN"), D("sNaN"),
                         D("Infinity"), D("-Infinity")):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.portfolio(holdings={"FTUL": quantity})

    def test_invalid_allocations_are_rejected(self):
        invalid_allocations = [
            {}, {"FTUL": D("0.9")}, {"FTUL": D("1.1")},
            {"FTUL": D("-0.1"), "MELI": D("1.1")},
            *({"FTUL": value} for value in (
                D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"),
            )),
        ]
        for allocation in invalid_allocations:
            with self.subTest(allocation=allocation), self.assertRaises(ValueError):
                self.portfolio(allocation=allocation)

    def test_duplicate_stocks_are_rejected(self):
        with self.assertRaises(ValueError):
            self.portfolio(stocks=self.stocks + [Stock("FTUL", D("501"))])

    def test_holdings_and_targets_require_known_stocks(self):
        with self.assertRaises(ValueError):
            self.portfolio(holdings={"UNKNOWN": D("0")})
        with self.assertRaises(ValueError):
            self.portfolio(allocation={"FTUL": D("1"), "UNKNOWN": D("0")})

    def test_randomized_plans_conserve_value_and_reach_target_values(self):
        generator = random.Random(42)
        with localcontext() as context:
            context.prec = 50
            for case in range(50):
                symbols = ["FTUL", "MELI", "NU"]
                prices = {symbol: D(generator.randint(1, 100000)) / D("100")
                          for symbol in symbols}
                holdings = {symbol: D(generator.randint(0, 1000))
                            for symbol in symbols}
                cuts = [0, *sorted(generator.sample(range(1, 10000), 2)), 10000]
                allocation = {symbol: D(cuts[index + 1] - cuts[index]) / D("10000")
                              for index, symbol in enumerate(symbols)}
                portfolio = Portfolio(
                    [Stock(symbol, prices[symbol]) for symbol in symbols],
                    holdings, allocation,
                )
                current_values = {symbol: holdings[symbol] * prices[symbol]
                                  for symbol in symbols}
                total = sum(current_values.values(), D("0"))
                trades = portfolio.rebalance()
                resulting_values = dict(current_values)
                with self.subTest(case=case):
                    for trade in trades:
                        self.assertGreater(trade.value, D("0"))
                        if trade.action == "SELL":
                            self.assertLessEqual(trade.value, current_values[trade.symbol])
                            resulting_values[trade.symbol] -= trade.value
                        else:
                            self.assertEqual(trade.action, "BUY")
                            resulting_values[trade.symbol] += trade.value
                    self.assertEqual(sum(resulting_values.values(), D("0")), total)
                    self.assertEqual(
                        resulting_values,
                        {symbol: total * allocation[symbol] for symbol in symbols},
                    )
                    self.assertEqual(
                        sum((trade.value if trade.action == "BUY" else -trade.value
                             for trade in trades), D("0")), D("0"),
                    )


if __name__ == "__main__":
    unittest.main()
