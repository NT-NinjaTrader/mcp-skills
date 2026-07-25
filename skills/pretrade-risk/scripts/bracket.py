#!/usr/bin/env python3
"""
bracket.py — propose a stop + target for an entry, given stop distance
and R-multiple. Math only. Emits no order payloads.

    stop_distance = absolute distance (points) between entry and stop
    r_multiple    = target payoff in units of stop_distance (2.0 = 2R)

    direction = long:
        stop   = entry - stop_distance
        target = entry + stop_distance × r_multiple

    direction = short: mirror.

This script snaps all prices to the tick grid. It computes risk and
payoff dollars from qty × value_per_point.

Usage:
    python3 bracket.py --entry 7150 --direction long --stop-distance-points 12 \\
        --tick-size 0.25 --qty 4 --value-per-point 50 [--r-multiple 2.0]

Output:
    {
      "entry": 7150.0,
      "direction": "long",
      "qty": 4,
      "stop_price": 7138.0,
      "target_price": 7174.0,
      "stop_distance_points": 12.0,
      "target_distance_points": 24.0,
      "r_multiple": 2.0,
      "risk_dollars": 2400.0,
      "target_payoff_dollars": 4800.0,
      "payoff_risk_ratio": 2.0
    }

To place the trade, use the entry / stop / target triple with
`place_order` (market order + OCO brackets). This script does not
submit — decision stays with the user.
"""

import argparse
import json
import sys


def _snap(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    return round(round(price / tick) * tick, 8)


EPILOG = """\
Examples:
  # Long ES bracket at 2R. 4 contracts. 0.25 tick grid.
  python3 bracket.py --entry 7150 --direction long --stop-distance-points 9 \\
      --r-multiple 2.0 --tick-size 0.25 --qty 4 --value-per-point 50

  # Short NQ bracket at 1.5R. 1 contract.
  python3 bracket.py --entry 24000 --direction short --stop-distance-points 40 \\
      --r-multiple 1.5 --tick-size 0.25 --qty 1 --value-per-point 20
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propose a stop + target bracket for an entry.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--entry",
        type=float,
        required=True,
        help=(
            "Entry working price. Unit: the contract's own price units, not ticks. "
            "Required, no default."
        ),
    )
    parser.add_argument(
        "--direction",
        choices=["long", "short"],
        required=True,
        help=(
            "Trade direction. Valid values: long, short. A long puts the stop below the "
            "entry. A short mirrors it. Required, no default."
        ),
    )
    parser.add_argument(
        "--stop-distance-points",
        type=float,
        required=True,
        help=(
            "Absolute distance from the entry to the stop. Unit: points, must be positive. "
            "Source: size.py's stop_distance_points. Required, no default."
        ),
    )
    parser.add_argument(
        "--r-multiple",
        type=float,
        default=2.0,
        help=(
            "Target payoff in units of the stop distance. Unit: ratio, must be positive. "
            "Target distance = --stop-distance-points × this value. Default 2.0."
        ),
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        required=True,
        help=(
            "Minimum price increment of the contract. Unit: price units, must be positive. "
            "Source: market_snapshot.tickSize. Example: 0.25 for ES. A wrong value snaps "
            "the stop and the target to the wrong grid. Required, no default."
        ),
    )
    parser.add_argument(
        "--qty",
        type=int,
        required=True,
        help=(
            "Quantity the bracket covers. Unit: contracts, must be positive. "
            "Source: size.py's proposed_qty. Required, no default."
        ),
    )
    parser.add_argument(
        "--value-per-point",
        type=float,
        required=True,
        help=(
            "Contract value of one full point of price movement. Unit: dollars per point, "
            "must be positive. Source: market_snapshot.valuePerPoint. Examples: 50 for ES, "
            "20 for NQ. Required, no default."
        ),
    )

    args = parser.parse_args()

    if args.stop_distance_points <= 0:
        print(json.dumps({"error": "--stop-distance-points must be positive"}), file=sys.stderr)
        return 2
    if args.r_multiple <= 0:
        print(json.dumps({"error": "--r-multiple must be positive"}), file=sys.stderr)
        return 2
    if args.qty <= 0:
        print(json.dumps({"error": "--qty must be positive"}), file=sys.stderr)
        return 2
    # Report the failed flag by name. A combined message hides which value
    # the caller must correct.
    if args.tick_size <= 0:
        print(json.dumps({"error": "--tick-size must be positive"}), file=sys.stderr)
        return 2
    if args.value_per_point <= 0:
        print(json.dumps({"error": "--value-per-point must be positive"}), file=sys.stderr)
        return 2

    stop_raw = (
        (args.entry - args.stop_distance_points)
        if args.direction == "long"
        else (args.entry + args.stop_distance_points)
    )
    target_raw = (
        (args.entry + args.stop_distance_points * args.r_multiple)
        if args.direction == "long"
        else (args.entry - args.stop_distance_points * args.r_multiple)
    )

    stop = _snap(stop_raw, args.tick_size)
    target = _snap(target_raw, args.tick_size)

    # Risk & payoff after snapping (may drift slightly from the raw multiple)
    stop_distance_snapped = abs(args.entry - stop)
    target_distance_snapped = abs(args.entry - target)
    risk_dollars = stop_distance_snapped * args.qty * args.value_per_point
    payoff_dollars = target_distance_snapped * args.qty * args.value_per_point
    ratio = round(payoff_dollars / risk_dollars, 3) if risk_dollars > 0 else None

    result = {
        "entry": args.entry,
        "direction": args.direction,
        "qty": args.qty,
        "stop_price": stop,
        "target_price": target,
        "stop_distance_points": round(stop_distance_snapped, 4),
        "target_distance_points": round(target_distance_snapped, 4),
        "r_multiple": args.r_multiple,
        "risk_dollars": round(risk_dollars, 2),
        "target_payoff_dollars": round(payoff_dollars, 2),
        "payoff_risk_ratio": ratio,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
