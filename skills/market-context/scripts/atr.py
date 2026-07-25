#!/usr/bin/env python3
"""
atr.py — compute Average True Range, realized volatility, and price-vs-mean
z-score from a `market_history` response.

ATR (Wilder): exponential moving average of True Range across N bars.
True Range = max(high-low, |high-prevClose|, |low-prevClose|).

Realized volatility: annualized standard deviation of per-bar log returns.
--periods-per-year sets the annualization factor (default 252, which
matches daily bars). For intraday bars, use the count of bars per
trading year instead.

Z-score: (latest close - mean close) / stdev(close) across the window.

No histogram or tick size needed. Uses only open / high / low / close.

Usage:
    atr.py --file market_history.json --n 14 [--periods-per-year 252]   # preferred
    echo "$market_history_json" | atr.py --n 14 [--periods-per-year 252]

Output:
    {
      "atr_n": 14,
      "atr": 7.82,
      "realized_vol": 0.21,
      "realized_vol_annualized_pct": 20.9,
      "close_z_score": 0.4,
      "bars_used": 120
    }
"""

import argparse
import json
import math
import sys
from typing import Any


def compute_true_range(bar: dict[str, Any], prev_close: float | None) -> float | None:
    """TR = max(h - l, |h - prevClose|, |l - prevClose|). Returns None if bar is incomplete."""
    h = bar.get("high")
    low = bar.get("low")
    close = bar.get("close")
    if h is None or low is None or close is None:
        return None
    if prev_close is None:
        return h - low
    return max(h - low, abs(h - prev_close), abs(low - prev_close))


def wilder_atr(true_ranges: list[float], n: int) -> float | None:
    """Wilder's ATR: seed with SMA of first N TRs, then smooth."""
    if len(true_ranges) < n:
        return None
    atr = sum(true_ranges[:n]) / n
    for tr in true_ranges[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr


def realized_vol(closes: list[float], periods_per_year: int) -> tuple[float, float] | None:
    """Return (raw_vol, annualized_vol_pct) from log returns of `closes`."""
    if len(closes) < 2:
        return None
    returns = [
        math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0
    ]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    stdev = math.sqrt(variance)
    annualized = stdev * math.sqrt(periods_per_year) * 100.0
    return stdev, annualized


def close_zscore(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    mean = sum(closes) / len(closes)
    variance = sum((c - mean) ** 2 for c in closes) / (len(closes) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return 0.0
    return (closes[-1] - mean) / stdev


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute ATR, realized volatility, and close z-score from market_history JSON on stdin.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  atr.py --file market_history.json --n 14\n"
            "  atr.py --file market_history.json --n 14 --periods-per-year 19656\n"
        ),
    )
    parser.add_argument(
        "--n",
        type=int,
        default=14,
        help="ATR period, in bars. Accepted values: any integer >= 1 (default 14).",
    )
    parser.add_argument(
        "--periods-per-year",
        type=int,
        default=252,
        help="Annualization factor for realized volatility, in bars per trading year "
        "(default 252 = daily bars). For intraday bars, use the count of bars per "
        "trading year, such as 19656 for 5-minute RTH bars.",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Read the JSON payload from PATH instead of stdin (default: read stdin).",
    )
    args = parser.parse_args()

    if args.n < 1:
        print(
            json.dumps({"error": f"--n must be an integer >= 1, got {args.n}"}),
            file=sys.stderr,
        )
        return 2

    try:
        if args.file:
            with open(args.file) as fh:
                payload = json.load(fh)
        else:
            payload = json.load(sys.stdin)
    except OSError as e:
        print(json.dumps({"error": f"cannot read {args.file}: {e}"}), file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        source = f"file {args.file}" if args.file else "stdin"
        print(json.dumps({"error": f"invalid JSON on {source}: {e}"}), file=sys.stderr)
        return 2

    bars = payload.get("bars")
    if not bars:
        print(json.dumps({"error": "no bars in input"}), file=sys.stderr)
        return 2

    true_ranges: list[float] = []
    closes: list[float] = []
    prev_close: float | None = None
    for bar in bars:
        tr = compute_true_range(bar, prev_close)
        if tr is not None:
            true_ranges.append(tr)
        close = bar.get("close")
        if close is not None:
            closes.append(close)
            prev_close = close

    result: dict[str, Any] = {
        "atr_n": args.n,
        "bars_used": len(true_ranges),
    }

    atr = wilder_atr(true_ranges, args.n)
    if atr is not None:
        result["atr"] = round(atr, 4)
    else:
        result["atr"] = None
        result["atr_error"] = (
            f"need at least {args.n} bars with complete OHL data; got {len(true_ranges)}"
        )

    rv = realized_vol(closes, args.periods_per_year)
    if rv is not None:
        raw, annualized = rv
        result["realized_vol"] = round(raw, 5)
        result["realized_vol_annualized_pct"] = round(annualized, 2)

    z = close_zscore(closes)
    if z is not None:
        result["close_z_score"] = round(z, 3)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
