#!/usr/bin/env python3
"""
whatif_live.py — informational alternate-exit math for the currently open
position. Never emits order payloads. That is scale-manager's job.

Three scenarios (pick one per invocation):

  --new-stop PRICE         Move the stop to PRICE. Reports new risk in
                           dollars and as % of daily loss budget, plus the
                           R-multiple change.

  --new-target PRICE       Extend (or tighten) the profit target to PRICE.
                           Reports new expected payoff at target and the
                           R-multiple it represents.

  --breakeven              Move stop to the net entry price (snapped to
                           tick grid). Reports remaining upside at the
                           current target.

Consumes one JSON file that describes the position and the relevant
context. Expected shape (all floats; tickSize and valuePerPoint come
from market_snapshot):

    {
      "symbol": "ESU6",
      "net_pos": 4,
      "net_price": 7150.0,
      "last_price": 7158.25,
      "tick_size": 0.25,
      "value_per_point": 50.0,
      "current_stop": 7145.0,     (optional)
      "current_target": 7162.0,   (optional)
      "daily_loss_budget": 500.0  (optional — enables pct_of_budget output)
    }

This shape is a subset of what `health.py` emits per-position, so a
typical workflow saves that output to a file and pipes it here.

Usage:
    python3 whatif_live.py --new-stop 7148 --file position.json   # preferred
    python3 whatif_live.py --new-stop 7148 < position.json
    python3 whatif_live.py --new-target 7170 < position.json
    python3 whatif_live.py --breakeven < position.json
"""

import argparse
import json
import sys

EXAMPLES = """\
Examples:
  # Move the stop to 7148 (preferred: read the position from a file).
  python3 whatif_live.py --file position.json --new-stop 7148

  # Move the stop to entry, from stdin.
  python3 whatif_live.py --breakeven < position.json

  # Extend the target to 7170.
  python3 whatif_live.py --file position.json --new-target 7170
"""


def _direction(net_pos: int) -> str:
    return "long" if net_pos > 0 else "short" if net_pos < 0 else "flat"


def _snap_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return price
    return round(round(price / tick_size) * tick_size, 8)


def _risk_dollars(entry: float, stop: float, net_pos: int, value_per_point: float) -> float:
    """Dollars at risk = |entry - stop| * |net_pos| * valuePerPoint."""
    return abs(entry - stop) * abs(net_pos) * value_per_point


def _payoff_dollars(entry: float, target: float, net_pos: int, value_per_point: float) -> float:
    """Expected payoff at target — sign follows the position direction so
    a target above entry on a long is positive, below on a short is positive."""
    direction = _direction(net_pos)
    gain_points = (target - entry) if direction == "long" else (entry - target)
    return gain_points * abs(net_pos) * value_per_point


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="whatif_live.py",
        description="Informational what-if math for an open position.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--new-stop",
        type=float,
        metavar="PRICE",
        help="Proposed new stop price, in contract-native price units. "
        "Pick exactly one of --new-stop, --new-target, or --breakeven. No default.",
    )
    group.add_argument(
        "--new-target",
        type=float,
        metavar="PRICE",
        help="Proposed new profit-target price, in contract-native price units. "
        "Pick exactly one of --new-stop, --new-target, or --breakeven. No default.",
    )
    group.add_argument(
        "--breakeven",
        action="store_true",
        help="Move the stop to the entry price, snapped to the tick grid. Takes no value. "
        "Pick exactly one of --new-stop, --new-target, or --breakeven. Default: off.",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Path to the position JSON. Default: none, which reads stdin instead.",
    )
    args = parser.parse_args()

    try:
        if args.file:
            with open(args.file) as fh:
                pos = json.load(fh)
        else:
            pos = json.load(sys.stdin)
    except OSError as e:
        print(json.dumps({"error": f"cannot read {args.file}: {e}"}), file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        source = f"file {args.file}" if args.file else "stdin"
        print(json.dumps({"error": f"invalid JSON on {source}: {e}"}), file=sys.stderr)
        return 2

    net_pos = int(pos.get("net_pos") or 0)
    if net_pos == 0:
        print(
            json.dumps(
                {
                    "error": "position is flat — no what-if math applicable. "
                    "net_pos accepts any non-zero integer: positive for long, "
                    "negative for short."
                }
            ),
            file=sys.stderr,
        )
        return 2

    entry = float(pos.get("net_price") or 0)
    tick_size = float(pos.get("tick_size") or 0.25)
    value_per_point = float(pos.get("value_per_point") or 0)
    last = pos.get("last_price")
    current_stop = pos.get("current_stop") or pos.get("stop_price")
    current_target = pos.get("current_target") or pos.get("target_price")
    daily_budget = pos.get("daily_loss_budget")
    direction = _direction(net_pos)

    if value_per_point <= 0:
        print(
            json.dumps(
                {
                    "error": "value_per_point is required and must be positive. "
                    "It accepts any number greater than 0. Take it from "
                    "market_snapshot.valuePerPoint."
                }
            ),
            file=sys.stderr,
        )
        return 2

    # Original risk (for R-multiple denominators)
    original_risk_dollars = (
        _risk_dollars(entry, current_stop, net_pos, value_per_point)
        if current_stop is not None
        else None
    )

    result: dict[str, object] = {
        "symbol": pos.get("symbol"),
        "direction": direction,
        "net_pos": net_pos,
        "entry": entry,
        "last_price": last,
    }

    if args.breakeven:
        new_stop = _snap_to_tick(entry, tick_size)
        new_risk = _risk_dollars(entry, new_stop, net_pos, value_per_point)
        # At breakeven stop, worst-case outcome is flat.
        if current_stop is not None:
            locked_in_from_original = abs(current_stop - new_stop) * abs(net_pos) * value_per_point
            result["risk_removed_dollars"] = round(locked_in_from_original, 2)
        result["scenario"] = "breakeven"
        result["new_stop"] = new_stop
        result["new_risk_dollars"] = round(new_risk, 2)  # 0.0 at breakeven
        if current_target is not None:
            remaining = _payoff_dollars(entry, current_target, net_pos, value_per_point)
            result["remaining_payoff_at_target_dollars"] = round(remaining, 2)
            if original_risk_dollars and original_risk_dollars > 0:
                result["remaining_r_multiple_at_target"] = round(
                    remaining / original_risk_dollars, 3
                )

    elif args.new_stop is not None:
        new_stop = _snap_to_tick(args.new_stop, tick_size)
        # Validate the proposed stop is on the correct side of entry for the direction
        if direction == "long" and new_stop >= entry:
            result["warning"] = (
                "new_stop is at or above entry for a long position — consider --breakeven or --new-target"
            )
        if direction == "short" and new_stop <= entry:
            result["warning"] = (
                "new_stop is at or below entry for a short position — consider --breakeven or --new-target"
            )
        new_risk = _risk_dollars(entry, new_stop, net_pos, value_per_point)
        result["scenario"] = "new_stop"
        result["new_stop"] = new_stop
        result["new_risk_dollars"] = round(new_risk, 2)
        if daily_budget and daily_budget > 0:
            result["new_risk_pct_of_daily_budget"] = round(100.0 * new_risk / daily_budget, 2)
        if original_risk_dollars and original_risk_dollars > 0:
            result["new_risk_r_multiple"] = round(new_risk / original_risk_dollars, 3)

    else:  # --new-target
        new_target = _snap_to_tick(args.new_target, tick_size)
        if direction == "long" and new_target <= entry:
            result["warning"] = (
                "new_target is at or below entry for a long position — that's a losing exit"
            )
        if direction == "short" and new_target >= entry:
            result["warning"] = (
                "new_target is at or above entry for a short position — that's a losing exit"
            )
        payoff = _payoff_dollars(entry, new_target, net_pos, value_per_point)
        result["scenario"] = "new_target"
        result["new_target"] = new_target
        result["payoff_at_target_dollars"] = round(payoff, 2)
        if original_risk_dollars and original_risk_dollars > 0:
            result["payoff_r_multiple"] = round(payoff / original_risk_dollars, 3)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
