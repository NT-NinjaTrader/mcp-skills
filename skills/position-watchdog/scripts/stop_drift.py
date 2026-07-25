#!/usr/bin/env python3
"""
stop_drift.py — detect whether a bracket's stop moved from its original
placement, and in which direction.

`order_history` reports one row per order — its current state only. It
carries no `orderVersions[]` and no other prior-version field, so this
script cannot derive the original stop price from `order_history` alone.
Pass the known original stop price with `--original-stop` instead (for
example, the price you narrated when the bracket was placed, or an
earlier `my_portfolio`/`order_history` snapshot you saved). This script
then diffs that baseline against the current stop price for the given
symbol's working bracket leg.

Logic:
  1. Filter orders to the given symbol.
  2. Among working orders, find the one that carries a `stopPrice`
     (the stop leg). If multiple, use the most recent.
  3. Compare `--original-stop` to the current `stopPrice`. Report the
     drift in ticks and dollars when the caller passes tickSize,
     valuePerPoint, and qty. Report whether the move was against entry
     (more risk) or with entry (less risk, e.g., a trail).

Inputs:
  --orders PATH          JSON — order_history tool response for the account
  --symbol SYMBOL        e.g. "ESU6". Required.
  --original-stop PRICE  The known stop price at bracket placement. Optional —
                         order_history carries no prior-version field to derive
                         this automatically. Without it, the script reports the
                         current stop only and skips the drift comparison.
  --entry-price PRICE    Position entry price (from my_portfolio.netPrice).
                         Required for with/against-entry classification.
  --direction long|short Position direction. Required for same reason.
  --tick-size NUM        Optional — enables tick-distance output.
  --value-per-point NUM  Optional — enables dollar-drift output.
  --net-pos INT          Optional — with --value-per-point, scales the dollar drift to position size.

Usage:
    python3 stop_drift.py --orders orders.json \\
        --symbol ESU6 --original-stop 7145 --entry-price 7150 --direction long \\
        --tick-size 0.25 --value-per-point 50 --net-pos 4

Output:
    {
      "symbol": "ESU6",
      "original_stop": 7145.0,
      "current_stop": 7148.0,
      "drift_ticks": 12,
      "drift_direction": "toward_entry",   # or "away_from_entry"
      "moved_against_entry": false,        # true when drift_direction is away_from_entry
      "risk_removed_dollars": 600.0,       # positive when toward_entry
      "current_risk_dollars": 400.0,
      "original_risk_dollars": 1000.0
    }
"""

import argparse
import json
import sys
from typing import Any

EXAMPLES = """\
Examples:
  # Full drift report, with tick and dollar output.
  python3 stop_drift.py --orders order_history.json --symbol ESU6 \\
      --original-stop 7145 --entry-price 7150 --direction long \\
      --tick-size 0.25 --value-per-point 50 --net-pos 4

  # Current stop only, with no baseline to diff against.
  python3 stop_drift.py --orders order_history.json --symbol ESU6 \\
      --entry-price 7150 --direction long
"""


def _load(path: str) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(json.dumps({"error": f"cannot read {path}: {e}"}))


def _find_working_stop_order(orders: list[dict], symbol: str) -> dict | None:
    """Return the most recent working order that carries a stopPrice for the symbol."""
    candidates = []
    for o in orders:
        if o.get("symbol") != symbol:
            continue
        status = o.get("ordStatus") or o.get("status")
        if status not in ("Working", "PendingNew"):
            continue
        if o.get("stopPrice") is None:
            continue
        candidates.append(o)
    if not candidates:
        return None
    # Prefer the most recently timestamped one if multiple brackets linger.
    candidates.sort(key=lambda o: o.get("timestamp", ""), reverse=True)
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="stop_drift.py",
        description="Detect whether a bracket's stop moved from its original placement.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--orders",
        required=True,
        metavar="PATH",
        help="Path to a saved order_history tool response (JSON). Required, no default.",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        metavar="SYMBOL",
        help="Exact contract symbol to filter on, for example ESU6. Required, no default.",
    )
    parser.add_argument(
        "--original-stop",
        type=float,
        default=None,
        metavar="PRICE",
        help="Known stop price at bracket placement, in contract-native price units. "
        "order_history cannot derive it. Default: none, which skips the drift comparison.",
    )
    parser.add_argument(
        "--entry-price",
        type=float,
        required=True,
        metavar="PRICE",
        help="Position entry price from my_portfolio.netPrice, in contract-native price "
        "units. Required, no default.",
    )
    parser.add_argument(
        "--direction",
        choices=["long", "short"],
        required=True,
        help="Position direction: long or short. Required, no default.",
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        default=None,
        metavar="NUM",
        help="Minimum price increment for the symbol, in price units. "
        "Default: none, which omits the drift_ticks field.",
    )
    parser.add_argument(
        "--value-per-point",
        type=float,
        default=None,
        metavar="NUM",
        help="Account currency per one point of price move, per contract. "
        "Default: none, which omits every dollar field.",
    )
    parser.add_argument(
        "--net-pos",
        type=int,
        default=None,
        metavar="INT",
        help="Position size in contracts. It scales the dollar fields. Default: 1.",
    )
    args = parser.parse_args()

    payload = _load(args.orders)
    orders = payload.get("orders") or payload.get("items") or payload
    if not isinstance(orders, list):
        print(
            json.dumps(
                {
                    "error": "expected order_history response with 'orders' or 'items' array, or top-level array"
                }
            ),
            file=sys.stderr,
        )
        return 2

    stop_order = _find_working_stop_order(orders, args.symbol)
    if stop_order is None:
        print(
            json.dumps(
                {
                    "symbol": args.symbol,
                    "error": "no working stop order found for this symbol — position may have no bracket attached",
                }
            )
        )
        return 0

    current_stop = stop_order.get("stopPrice")
    if current_stop is None:
        print(
            json.dumps(
                {
                    "symbol": args.symbol,
                    "current_stop": current_stop,
                    "original_stop": args.original_stop,
                    "error": "missing current stop price on the working order",
                }
            )
        )
        return 0

    if args.original_stop is None:
        print(
            json.dumps(
                {
                    "symbol": args.symbol,
                    "current_stop": current_stop,
                    "original_stop": None,
                    "error": "no --original-stop given — order_history reports only the "
                    "current stop price, not its history",
                }
            )
        )
        return 0

    original_stop = args.original_stop

    # "Toward entry" = stop got closer to entry (less risk)
    # "Away from entry" = stop got farther from entry (more risk; user moved it after a loss)
    orig_distance = abs(args.entry_price - original_stop)
    curr_distance = abs(args.entry_price - current_stop)
    drift_direction = "toward_entry" if curr_distance < orig_distance else "away_from_entry"
    if curr_distance == orig_distance:
        drift_direction = "unchanged"

    result: dict[str, Any] = {
        "symbol": args.symbol,
        "original_stop": original_stop,
        "current_stop": current_stop,
        "drift_direction": drift_direction,
        "moved_against_entry": drift_direction == "away_from_entry",
    }

    if args.tick_size and args.tick_size > 0:
        result["drift_ticks"] = int(round(abs(current_stop - original_stop) / args.tick_size))

    if args.value_per_point and args.value_per_point > 0:
        qty = abs(args.net_pos) if args.net_pos else 1
        orig_risk_dollars = orig_distance * args.value_per_point * qty
        curr_risk_dollars = curr_distance * args.value_per_point * qty
        result["original_risk_dollars"] = round(orig_risk_dollars, 2)
        result["current_risk_dollars"] = round(curr_risk_dollars, 2)
        if drift_direction == "toward_entry":
            result["risk_removed_dollars"] = round(orig_risk_dollars - curr_risk_dollars, 2)
        elif drift_direction == "away_from_entry":
            result["risk_added_dollars"] = round(curr_risk_dollars - orig_risk_dollars, 2)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
