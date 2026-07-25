#!/usr/bin/env python3
"""
profile.py — compute Market Profile statistics (POC, Value Area) from a
`market_history` response with volumeProfile=true.

POC (Point of Control) = price level with the highest aggregate volume.
Value Area = the contiguous range around POC that accounts for 70% of total
volume (default — CME convention). VAH / VAL are its top / bottom prices.

Requires --tick-size because histogram[].price is a tick offset from bar.open
(see references/histogram-offset.md).

Usage:
    profile.py --file market_history.json --tick-size 0.25 [--value-area 0.70]   # preferred
    echo "$market_history_json" | profile.py --tick-size 0.25 [--value-area 0.70]

Output:
    {
      "poc": 7150.00,
      "vah": 7162.25,
      "val": 7143.50,
      "value_area_pct": 0.70,
      "total_volume": 123456,
      "levels_in_value_area": 47,
      "total_levels": 124
    }
"""

import argparse
import json
import sys
from collections import defaultdict
from typing import Any


def aggregate_by_price(bars: list[dict[str, Any]], tick_size: float) -> dict[float, int]:
    """Fold every bar's histogram into a single {price: total_volume} map."""
    agg: dict[float, int] = defaultdict(int)
    for bar in bars:
        open_price = bar.get("open")
        hist = bar.get("histogram")
        if open_price is None or not hist:
            continue
        for level in hist:
            actual_price = open_price + level["price"] * tick_size
            vol = level.get("bid", 0) + level.get("offer", 0)
            # Round to tick precision so floating-point open-price drift
            # across bars does not split what should be one price level.
            key = round(actual_price / tick_size) * tick_size
            agg[key] += vol
    return agg


def compute_value_area(
    levels: dict[float, int], target_pct: float
) -> tuple[float, float, float, int]:
    """Expand contiguously outward from the POC until the window captures
    `target_pct` of total volume. Returns (poc, vah, val, levels_in_value_area).

    Raises ValueError if levels is empty.
    """
    if not levels:
        raise ValueError("no histogram levels to build a profile from")

    total_volume = sum(levels.values())
    target_volume = total_volume * target_pct

    # Sort ascending by price; find POC index.
    sorted_prices = sorted(levels.keys())
    poc = max(levels.keys(), key=lambda p: levels[p])
    poc_idx = sorted_prices.index(poc)

    accumulated = levels[poc]
    low_idx = poc_idx
    high_idx = poc_idx

    while accumulated < target_volume and (low_idx > 0 or high_idx < len(sorted_prices) - 1):
        # Peek one step in each direction. Pick whichever adds more volume
        # (standard CME double-edge expansion).
        candidate_below = levels[sorted_prices[low_idx - 1]] if low_idx > 0 else -1
        candidate_above = (
            levels[sorted_prices[high_idx + 1]] if high_idx < len(sorted_prices) - 1 else -1
        )
        if candidate_below == -1 and candidate_above == -1:
            break
        if candidate_above >= candidate_below:
            high_idx += 1
            accumulated += candidate_above
        else:
            low_idx -= 1
            accumulated += candidate_below

    return poc, sorted_prices[high_idx], sorted_prices[low_idx], (high_idx - low_idx + 1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute market profile (POC, VAH, VAL) from market_history JSON on stdin.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  profile.py --file market_history.json --tick-size 0.25\n"
            "  profile.py --file market_history.json --tick-size 0.25 --value-area 0.50\n"
        ),
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        required=True,
        help="Minimum price increment of the contract, in price units. Accepted values: "
        "any positive number, such as 0.25 for ES, 1.00 for YM, or 0.01 for CL. "
        "histogram[].price is a tick offset from bar.open. Required (no default).",
    )
    parser.add_argument(
        "--value-area",
        type=float,
        default=0.70,
        help="Target share of total volume for the value area, as a fraction. Accepted "
        "values: greater than 0 and up to 1.0, such as 0.50 or 0.70 "
        "(default 0.70 = CME convention).",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Read the JSON payload from PATH instead of stdin (default: read stdin).",
    )
    args = parser.parse_args()

    if not 0.0 < args.value_area <= 1.0:
        print(
            json.dumps(
                {
                    "error": f"--value-area must be in (0, 1], got {args.value_area}. "
                    "Accepted values: a fraction greater than 0 and up to 1.0, "
                    "such as 0.50 or 0.70."
                }
            ),
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

    if not any(bar.get("histogram") for bar in bars):
        print(
            json.dumps(
                {"error": "no histogram data — re-run market_history with volumeProfile=true"}
            ),
            file=sys.stderr,
        )
        return 2

    levels = aggregate_by_price(bars, args.tick_size)
    total_volume = sum(levels.values())
    if total_volume == 0:
        print(
            json.dumps({"error": "histogram levels present but all have zero volume"}),
            file=sys.stderr,
        )
        return 2

    poc, vah, val, levels_in_va = compute_value_area(levels, args.value_area)

    print(
        json.dumps(
            {
                "poc": round(poc, 4),
                "vah": round(vah, 4),
                "val": round(val, 4),
                "value_area_pct": args.value_area,
                "total_volume": total_volume,
                "levels_in_value_area": levels_in_va,
                "total_levels": len(levels),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
