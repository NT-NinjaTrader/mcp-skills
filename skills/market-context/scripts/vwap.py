#!/usr/bin/env python3
"""
vwap.py — compute Volume-Weighted Average Price from a `market_history` response.

Accepts JSON on stdin (the full `market_history` tool response) and prints JSON
to stdout. Two modes:

  - True histogram VWAP: when bars carry `histogram` (volumeProfile=true).
    Every histogram level contributes (bid+offer) volume at the reconstructed
    price. Requires --tick-size since histogram[].price is a tick offset from
    bar.open (see references/histogram-offset.md).

  - Typical-price VWAP: a fallback for when there is no histogram. It weights
    the standard (high+low+close)/3 by (upVolume+downVolume).

Usage:
    vwap.py --file market_history.json --tick-size 0.25   # preferred
    echo "$market_history_json" | vwap.py --tick-size 0.25

Output:
    {
      "vwap": 7151.43,
      "mode": "histogram" | "typical_price",
      "bars_used": 78,
      "total_volume": 123456,
      "price_z_score": -0.3        // current price vs VWAP, normalized by stdev
    }
"""

import argparse
import json
import math
import sys
from typing import Any


def compute_histogram_vwap(bars: list[dict[str, Any]], tick_size: float) -> tuple[float, int, int]:
    """Sum(price × vol) / Sum(vol) across every histogram level of every bar.
    Returns (vwap, bars_used, total_volume). Raises if no histogram data present."""
    total_pv = 0.0
    total_volume = 0
    bars_used = 0
    for bar in bars:
        open_price = bar.get("open")
        hist = bar.get("histogram")
        if open_price is None or not hist:
            continue
        bars_used += 1
        for level in hist:
            offset = level["price"]
            actual_price = open_price + offset * tick_size
            vol = level.get("bid", 0) + level.get("offer", 0)
            total_pv += actual_price * vol
            total_volume += vol
    if total_volume == 0:
        raise ValueError("no histogram volume — fall back to typical-price mode")
    return total_pv / total_volume, bars_used, total_volume


def compute_typical_vwap(bars: list[dict[str, Any]]) -> tuple[float, int, int]:
    """Weight (h+l+c)/3 by (upVolume + downVolume). Returns (vwap, bars_used, total_volume)."""
    total_pv = 0.0
    total_volume = 0
    bars_used = 0
    for bar in bars:
        high = bar.get("high")
        low = bar.get("low")
        close = bar.get("close")
        if high is None or low is None or close is None:
            continue
        vol = (bar.get("upVolume") or 0) + (bar.get("downVolume") or 0)
        if vol <= 0:
            continue
        bars_used += 1
        typical = (high + low + close) / 3.0
        total_pv += typical * vol
        total_volume += vol
    if total_volume == 0:
        raise ValueError("no volume data across bars — cannot compute VWAP")
    return total_pv / total_volume, bars_used, total_volume


def compute_price_zscore(bars: list[dict[str, Any]], vwap: float) -> float | None:
    """Z-score of the latest close vs VWAP, normalized by per-bar close stddev."""
    closes = [bar["close"] for bar in bars if bar.get("close") is not None]
    if len(closes) < 2:
        return None
    mean = sum(closes) / len(closes)
    variance = sum((c - mean) ** 2 for c in closes) / (len(closes) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return 0.0
    return (closes[-1] - vwap) / stdev


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute VWAP from market_history JSON on stdin.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  vwap.py --file market_history.json --tick-size 0.25\n"
            "  cat market_history.json | vwap.py --tick-size 1.00\n"
        ),
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        required=False,
        help="Minimum price increment of the contract, in price units. Accepted values: "
        "any positive number, such as 0.25 for ES, 1.00 for YM, or 0.01 for CL. "
        "Required for histogram mode. Ignored in the typical-price fallback (no default).",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Read the JSON payload from PATH instead of stdin (default: read stdin).",
    )
    args = parser.parse_args()

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

    # Prefer histogram mode if any bar has histogram data.
    has_histogram = any(bar.get("histogram") for bar in bars)

    if has_histogram:
        if args.tick_size is None:
            print(
                json.dumps(
                    {
                        "error": "--tick-size is required when bars contain histogram data. "
                        "Accepted values: any positive number, such as 0.25 for ES, "
                        "1.00 for YM, or 0.01 for CL."
                    }
                ),
                file=sys.stderr,
            )
            return 2
        try:
            vwap, bars_used, total_volume = compute_histogram_vwap(bars, args.tick_size)
            mode = "histogram"
        except ValueError:
            # Fall back if the caller requested histogram mode but the bars had zero volume
            vwap, bars_used, total_volume = compute_typical_vwap(bars)
            mode = "typical_price"
    else:
        try:
            vwap, bars_used, total_volume = compute_typical_vwap(bars)
        except ValueError as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            return 2
        mode = "typical_price"

    z = compute_price_zscore(bars, vwap)

    result = {
        "vwap": round(vwap, 4),
        "mode": mode,
        "bars_used": bars_used,
        "total_volume": total_volume,
    }
    if z is not None:
        result["price_z_score"] = round(z, 3)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
