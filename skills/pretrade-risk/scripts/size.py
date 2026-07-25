#!/usr/bin/env python3
"""
size.py — position-sizing math for a proposed trade.

Standard formula:

    risk_dollars = netLiq × risk_pct / 100
    stop_distance_points = ATR × stop_multiplier   (when --atr given)
                         = --stop-distance-points   (when explicit)
    qty = floor( risk_dollars / (stop_distance_points × value_per_point) )

Pending-qty awareness: futures risk systems include pending orders
(`filled + openBuy + openSell`) when evaluating exposure. Sizing that
ignores pending qty is a loophole. Pass --existing-net-pos and
--existing-pending-qty so the output reflects what the trader can
ACTUALLY add on top of what is already in motion.

Inputs are plain CLI flags — no JSON file gymnastics. The LLM extracts
values from the upstream tool responses:
  - netLiq         ← my_portfolio.account.netLiq
  - value-per-point ← market_snapshot.valuePerPoint
  - atr            ← market-context atr.py output
  - daily-loss-budget ← risk_settings.dailyLossAutoLiq (absolute value)
  - max-contracts  ← optional caller-supplied cap. risk_settings has no
    per-order contract-count field — source a hard cap from
    estimate_order's pre-trade validation response instead.

Usage:
    python3 size.py --netliq 50000 --atr 8.0 --value-per-point 50
    python3 size.py --netliq 50000 --stop-distance-points 12 --value-per-point 50 \\
        --daily-loss-budget 500 --existing-net-pos 2 --existing-pending-qty 1

Output:
    {
      "proposed_qty": 4,
      "risk_dollars": 480.0,
      "stop_distance_points": 12.0,
      "risk_pct_of_netliq": 0.96,
      "risk_pct_of_daily_budget": 96.0,
      "combined_qty_after_fill": 7,       # existing_net_pos + existing_pending_qty + proposed_qty
      "flags": [
        "exceeds_max_contracts: proposed + existing 7 > 5"
      ]
    }
"""

import argparse
import json
import math
import sys

EPILOG = """\
Examples:
  # ATR-derived stop. 1% of a $100,000 account. ES value per point.
  python3 size.py --netliq 100000 --risk-pct 1.0 --atr 6.0 --value-per-point 50

  # Explicit stop distance, a daily loss budget, and existing exposure.
  python3 size.py --netliq 50000 --stop-distance-points 12 --value-per-point 50 \\
      --daily-loss-budget 500 --max-contracts 5 \\
      --existing-net-pos 2 --existing-pending-qty 1
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute position size from equity risk, ATR stop, and contract specs.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--netliq",
        type=float,
        required=True,
        help=(
            "Account net liquidation value. Unit: dollars. "
            "Source: my_portfolio.account.netLiq. Required, no default."
        ),
    )
    parser.add_argument(
        "--risk-pct",
        type=float,
        default=1.0,
        help=(
            "Equity risk per trade. Unit: percent of --netliq, in (0, 100]. Default 1.0 (= 1%%)."
        ),
    )
    parser.add_argument(
        "--value-per-point",
        type=float,
        required=True,
        help=(
            "Contract value of one full point of price movement. Unit: dollars per point. "
            "Source: market_snapshot.valuePerPoint. Examples: 50 for ES, 20 for NQ, 5 for YM. "
            "Required, no default."
        ),
    )

    stop_group = parser.add_mutually_exclusive_group(required=True)
    stop_group.add_argument(
        "--atr",
        type=float,
        help=(
            "Average True Range. Unit: points. --stop-multiplier scales it into a stop "
            "distance. No default. Give either --atr or --stop-distance-points."
        ),
    )
    stop_group.add_argument(
        "--stop-distance-points",
        type=float,
        help=(
            "Explicit stop distance. Unit: points. This value replaces the ATR-derived "
            "stop. No default. Give either --atr or --stop-distance-points."
        ),
    )

    parser.add_argument(
        "--stop-multiplier",
        type=float,
        default=1.5,
        help=(
            "Multiplier on --atr. Unit: ratio, must be positive. "
            "Stop distance = --atr × this value. Default 1.5."
        ),
    )

    parser.add_argument(
        "--daily-loss-budget",
        type=float,
        default=None,
        help=(
            "Daily loss limit. Unit: dollars, absolute value. Source: "
            "risk_settings.dailyLossAutoLiq. The script flags a trade that risks more "
            "than 100%% of this budget. Default: no budget check."
        ),
    )
    parser.add_argument(
        "--max-contracts",
        type=int,
        default=None,
        help=(
            "Caller-supplied cap on combined size after the fill. Unit: contracts. "
            "estimate_order remains the authoritative cap. Default: no cap."
        ),
    )
    parser.add_argument(
        "--existing-net-pos",
        type=int,
        default=0,
        help=(
            "Signed size of the current filled position. Unit: contracts. "
            "Source: my_portfolio.positions[].netPos. Default 0."
        ),
    )
    parser.add_argument(
        "--existing-pending-qty",
        type=int,
        default=0,
        help=(
            "Sum of pending Buy and Sell order quantities for this symbol. "
            "Unit: contracts. Source: my_portfolio.workingOrders[].quantity. Default 0."
        ),
    )

    args = parser.parse_args()

    if args.risk_pct <= 0 or args.risk_pct > 100:
        print(json.dumps({"error": "--risk-pct must be in (0, 100]"}), file=sys.stderr)
        return 2
    if args.value_per_point <= 0:
        print(json.dumps({"error": "--value-per-point must be positive"}), file=sys.stderr)
        return 2

    if args.stop_distance_points is not None:
        stop_distance = args.stop_distance_points
    else:
        if args.stop_multiplier <= 0:
            print(json.dumps({"error": "--stop-multiplier must be positive"}), file=sys.stderr)
            return 2
        stop_distance = args.atr * args.stop_multiplier

    if stop_distance <= 0:
        print(json.dumps({"error": "stop distance must be positive"}), file=sys.stderr)
        return 2

    risk_dollars_budget = args.netliq * args.risk_pct / 100.0
    dollars_per_contract_at_stop = stop_distance * args.value_per_point
    proposed_qty = math.floor(risk_dollars_budget / dollars_per_contract_at_stop)
    if proposed_qty < 1:
        proposed_qty = 0

    actual_risk_dollars = proposed_qty * dollars_per_contract_at_stop
    combined_qty = abs(args.existing_net_pos) + args.existing_pending_qty + proposed_qty

    flags: list[str] = []
    if proposed_qty == 0:
        flags.append("stop_too_wide_for_risk_budget")

    if args.daily_loss_budget and args.daily_loss_budget > 0:
        pct_of_budget = round(100.0 * actual_risk_dollars / args.daily_loss_budget, 2)
        if pct_of_budget > 100:
            flags.append(f"exceeds_daily_loss_budget: risk_pct_of_daily_budget={pct_of_budget}%")
    else:
        pct_of_budget = None

    if args.max_contracts and combined_qty > args.max_contracts:
        flags.append(f"exceeds_max_contracts: combined {combined_qty} > {args.max_contracts}")

    if args.existing_pending_qty > 0:
        flags.append(
            f"pending_qty_awareness: {args.existing_pending_qty} contracts in pending orders counted "
            f"toward combined size"
        )

    result: dict[str, object] = {
        "proposed_qty": proposed_qty,
        "risk_dollars": round(actual_risk_dollars, 2),
        "stop_distance_points": round(stop_distance, 4),
        "risk_pct_of_netliq": round(100.0 * actual_risk_dollars / args.netliq, 3),
        "combined_qty_after_fill": combined_qty,
        "flags": flags,
    }
    if pct_of_budget is not None:
        result["risk_pct_of_daily_budget"] = pct_of_budget

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
