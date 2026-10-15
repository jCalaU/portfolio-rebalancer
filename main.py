import os
import sys
from decimal import Decimal

from portfolio import Portfolio, Stock, Trade


# Official Fintual-inspired color palette
BLUE = (0, 90, 230)
SKY = (100, 165, 255)
PALE = (160, 205, 255)
WHITE = (245, 245, 250)
RED = (255, 125, 135)

USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def ink(text: str, rgb: tuple[int, int, int], bold: bool = False) -> str:
    if not USE_COLOR:
        return text

    r, g, b = rgb
    weight = 1 if bold else 22
    return f"\033[{weight};38;2;{r};{g};{b}m{text}\033[0m"


# Five-row pixel lettering for FINTUAL
GLYPHS = {
    "F": ("█████", "█    ", "████ ", "█    ", "█    "),
    "I": ("█████", "  █  ", "  █  ", "  █  ", "█████"),
    "N": ("█   █", "██  █", "█ █ █", "█  ██", "█   █"),
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
    "U": ("█   █", "█   █", "█   █", "█   █", "█████"),
    "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
    "L": ("█    ", "█    ", "█    ", "█    ", "█████"),
}

MARK = (
    "   ▄▄▄▄  ",
    " ▄██████ ",
    "████  ██ ",
    "████▄▀▀  ",
    " ▀██▀    ",
)


def show_banner() -> None:
    metadata = (
        ink("PORTFOLIO REBALANCER", WHITE, True),
        f"{ink('VALUE', SKY, True)}       $10,000.00",
        f"{ink('TARGET', SKY, True)}      FTUL 60% · MELI 20% · NU 20%",
        f"{ink('ENGINE', SKY, True)}      Decimal · Python 3",
        f"{ink('STATUS', SKY, True)}      Simulation only",
    )

    print()

    for row in range(5):
        word = "  ".join(GLYPHS[letter][row] for letter in "FINTUAL")
        mark_color = PALE if row < 2 else BLUE

        print(
            f"  {ink(MARK[row], mark_color)}  "
            f"{ink(word, SKY)}    {metadata[row]}"
        )

    print()


WIDTHS = (9, 8, 20, 16)


def border(left: str, middle: str, right: str) -> str:
    return "  " + left + middle.join("─" * width for width in WIDTHS) + right


def show_trades(trades: tuple[Trade, ...]) -> None:
    print(ink("  REBALANCE PLAN", PALE, True))
    print(border("┌", "┬", "┐"))
    print("  │ Action  │ Stock  │   Estimated shares │    Trade value │")
    print(border("├", "┼", "┤"))

    for trade in trades:
        action_color = RED if trade.action == "SELL" else SKY
        action = ink(f"{trade.action:<7}", action_color, True)

        quantity = f"{trade.estimated_quantity:,.6f}"
        value = f"{trade.value:,.2f}"

        print(
            f"  │ {action} │ {trade.symbol:<6} │ "
            f"{quantity:>18} │ {value:>14} │"
        )

    print(border("└", "┴", "┘"))
    print(ink("  ✓ No holdings changed · No orders executed", PALE))


def main() -> None:
    portfolio = Portfolio(
        stocks=[
            Stock("FTUL", Decimal("500")),
            Stock("MELI", Decimal("250")),
            Stock("NU", Decimal("100")),
        ],
        holdings={
            "FTUL": Decimal("8"),
            "MELI": Decimal("16"),
            "NU": Decimal("20"),
        },
        allocation={
            "FTUL": Decimal("0.60"),
            "MELI": Decimal("0.20"),
            "NU": Decimal("0.20"),
        },
    )

    show_banner()
    show_trades(portfolio.rebalance())


if __name__ == "__main__":
    main()
