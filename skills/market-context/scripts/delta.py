#!/usr/bin/env python3
"""
delta.py — bar-level delta, cumulative delta, and order-flow imbalance
from a `market_history` response.

Every `BarEntry` carries `upVolume` and `downVolume`. `upVolume` counts
contracts that traded at the offer. `downVolume` counts contracts that
traded at the bid. The delta of a bar is:

    delta = upVolume - downVolume

A positive delta means aggressive buyers dominated the bar. A negative
delta means aggressive sellers did. Cumulative delta is the running sum
across the bar sequence — a rough proxy for directional pressure over
the window.

Order-flow imbalance normalizes delta to the bar's total volume, so you
can compare bars of different volume:

    imbalance = delta / (upVolume + downVolume)   (in [-1, +1])

No histogram or tick size needed. Skips a bar if it lacks either volume
field (some Tick-bar or close-only responses omit them).

Usage:
    delta.py --file market_history.json   # preferred
    echo "$market_history_json" | delta.py

Output:
    {
      "bars_used": 78,
      "total_up_volume": 412000,
      "total_down_volume": 310000,
      "net_delta": 102000,
      "cumulative_delta_path": [8400, 4200, -7500, ..., 102000],
      "final_imbalance": 0.141,
      "bar_imbalance_path": [0.46, -0.28, ..., -0.24]
    }

Each `*_path` array has one entry per bar used, in the same order as
the input `bars` array. They are the running-sum and per-bar views.
The caller can plot them (chart-render) or feed them to a pattern
detector.
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute delta + cumulative delta + imbalance from market_history JSON on stdin.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  delta.py --file market_history.json\n"
            "  cat market_history.json | delta.py\n"
        ),
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

    cumulative = 0
    cum_path: list[int] = []
    imb_path: list[float] = []
    total_up = 0
    total_down = 0
    bars_used = 0

    for bar in bars:
        up = bar.get("upVolume")
        down = bar.get("downVolume")
        if up is None or down is None:
            continue
        bar_delta = up - down
        cumulative += bar_delta
        total_up += up
        total_down += down
        bars_used += 1
        cum_path.append(cumulative)
        total = up + down
        imb_path.append(round(bar_delta / total, 4) if total > 0 else 0.0)

    if bars_used == 0:
        print(json.dumps({"error": "no bars with both upVolume and downVolume"}), file=sys.stderr)
        return 2

    total_volume = total_up + total_down
    final_imbalance = round((total_up - total_down) / total_volume, 4) if total_volume > 0 else 0.0

    print(
        json.dumps(
            {
                "bars_used": bars_used,
                "total_up_volume": total_up,
                "total_down_volume": total_down,
                "net_delta": cumulative,
                "cumulative_delta_path": cum_path,
                "final_imbalance": final_imbalance,
                "bar_imbalance_path": imb_path,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
