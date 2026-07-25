#!/usr/bin/env python3
"""
scale_math.py — math for a scale-in or scale-out on an existing position.

Handles three actions via --action:

  scale_in     : add qty at a new price → weighted cost basis + new
                 dollar-risk + new R at current mark
  scale_out    : remove qty at a price → realized $ + remaining position
                 state + remaining dollar-risk
  partial_exit : shorthand for scale_out where price = current mark
                 (take X off at market). round-half-up converts `--pct`
                 to integer contracts (50% of 3 → 2, 50% of 5 → 3). The
                 script clamps the result to [1, qty-1], so a partial
                 never exits the whole position (use --action scale_out
                 for that instead). Requires qty >= 2.

Inputs (stdin JSON):
    {
      "direction":        "long" | "short",
      "current_qty":      4,                # existing (signed magnitude)
      "current_basis":    7150.0,           # weighted entry of existing
      "stop_price":       7141.0,           # current bracket stop
      "current_mark":     7164.0,           # last / market price
      "value_per_point":  50.0,
      "tick_size":        0.25,

      "action_qty":       2,                # contracts to add or remove
      "action_price":     7168.0            # assumed fill price
    }

Output (JSON):
    Action-specific fields. Common fields present on all actions:

      new_qty, new_basis, realized_dollars, remaining_risk_dollars,
      R_before, R_after, dollar_risk_before_action, dollar_risk_after_action

Sign convention:
  - long: profit when price > basis
  - short: profit when price < basis
  - realized_dollars > 0 means money taken off the table

R math uses |basis - stop_price| as the risk-per-contract. If the stop
ends up on the wrong side (e.g., stop above basis on a long after a
scale-in at a lower basis), the script returns R fields as null.

Usage:
    python3 scale_math.py --file position.json --action scale_in   # preferred
    echo '<json>' | python3 scale_math.py --action scale_in
    echo '<json>' | python3 scale_math.py --action scale_out
    echo '<json>' | python3 scale_math.py --action partial_exit --pct 0.5
"""

import argparse
import json
import sys
from typing import Optional

VALID_ACTIONS = ("scale_in", "scale_out", "partial_exit")
VALID_DIRECTIONS = ("long", "short")

EXAMPLES = """\
Examples:
  # Add to the position (preferred: payload from a file).
  python3 scale_math.py --file position.json --action scale_in

  # Remove the payload's action_qty at action_price.
  python3 scale_math.py --file position.json --action scale_out

  # Take half off at the current mark.
  python3 scale_math.py --file position.json --action partial_exit --pct 0.5

  # Same call from stdin.
  echo '<json>' | python3 scale_math.py --action scale_in
"""


def _validate_direction(p: dict) -> Optional[dict]:
    """Return an error dict when the payload's `direction` is not long or short.

    Every downstream branch treats an unknown value as a short. So catch
    it here instead, and report the accepted values.
    """
    direction = str(p.get("direction", "")).lower()
    if direction in VALID_DIRECTIONS:
        return None
    return {
        "error": f"unknown direction {direction!r} in the payload — accepted values: "
        f"{', '.join(VALID_DIRECTIONS)}"
    }


def _risk_per_contract(direction: str, basis: float, stop: float) -> Optional[float]:
    # Stop must be on the losing side of basis for R math to be meaningful.
    if direction == "long":
        if stop >= basis:
            return None
        return basis - stop
    else:
        if stop <= basis:
            return None
        return stop - basis


def _R_at(direction: str, basis: float, stop: float, mark: float) -> Optional[float]:
    rpc = _risk_per_contract(direction, basis, stop)
    if rpc is None or rpc == 0:
        return None
    if direction == "long":
        return round((mark - basis) / rpc, 3)
    return round((basis - mark) / rpc, 3)


def _dollar_risk(
    direction: str, qty: int, basis: float, stop: float, vpp: float
) -> Optional[float]:
    rpc = _risk_per_contract(direction, basis, stop)
    if rpc is None:
        return None
    return round(qty * rpc * vpp, 2)


def _snap(price: float, tick: float) -> float:
    return round(round(price / tick) * tick, 6)


def _common_fields(
    direction: str,
    qty_before: int,
    basis_before: float,
    stop: float,
    mark: float,
    vpp: float,
    qty_after: int,
    basis_after: float,
    realized_dollars: float,
) -> dict:
    return {
        "direction": direction,
        "qty_before": qty_before,
        "qty_after": qty_after,
        "basis_before": round(basis_before, 6),
        "basis_after": round(basis_after, 6) if qty_after > 0 else None,
        "stop_price": round(stop, 6),
        "current_mark": round(mark, 6),
        "realized_dollars": round(realized_dollars, 2),
        "dollar_risk_before_action": _dollar_risk(direction, qty_before, basis_before, stop, vpp),
        "dollar_risk_after_action": _dollar_risk(direction, qty_after, basis_after, stop, vpp)
        if qty_after > 0
        else 0.0,
        "R_before": _R_at(direction, basis_before, stop, mark),
        "R_after": _R_at(direction, basis_after, stop, mark) if qty_after > 0 else None,
    }


def scale_in(p: dict) -> dict:
    bad_direction = _validate_direction(p)
    if bad_direction:
        return bad_direction
    direction = p["direction"].lower()
    qty = int(p["current_qty"])
    basis = float(p["current_basis"])
    stop = float(p["stop_price"])
    mark = float(p["current_mark"])
    vpp = float(p["value_per_point"])
    add_qty = int(p["action_qty"])
    add_price = float(p["action_price"])
    tick = float(p.get("tick_size", 0.01))

    if add_qty <= 0:
        return {"error": "action_qty must be positive for scale_in"}

    new_qty = qty + add_qty
    new_basis = (qty * basis + add_qty * add_price) / new_qty
    new_basis = _snap(new_basis, tick)

    # A scale-in does not realize anything on the original position.
    # The script marks the add to the current price.
    unrealized_on_add = (
        (mark - add_price) * vpp * add_qty
        if direction == "long"
        else (add_price - mark) * vpp * add_qty
    )

    out = _common_fields(
        direction, qty, basis, stop, mark, vpp, new_qty, new_basis, realized_dollars=0.0
    )
    out.update(
        {
            "action": "scale_in",
            "add_qty": add_qty,
            "add_price": round(add_price, 6),
            "unrealized_on_add_dollars": round(unrealized_on_add, 2),
        }
    )
    return out


def scale_out(p: dict) -> dict:
    bad_direction = _validate_direction(p)
    if bad_direction:
        return bad_direction
    direction = p["direction"].lower()
    qty = int(p["current_qty"])
    basis = float(p["current_basis"])
    stop = float(p["stop_price"])
    mark = float(p["current_mark"])
    vpp = float(p["value_per_point"])
    off_qty = int(p["action_qty"])
    off_price = float(p["action_price"])

    if off_qty <= 0 or off_qty > qty:
        return {"error": f"action_qty ({off_qty}) must be in [1, {qty}]"}

    realized_points = (off_price - basis) if direction == "long" else (basis - off_price)
    realized_dollars = realized_points * vpp * off_qty
    # The remaining basis does not change — the weighted-average cost
    # basis stays the same for the surviving contracts.
    new_qty = qty - off_qty

    out = _common_fields(direction, qty, basis, stop, mark, vpp, new_qty, basis, realized_dollars)
    out.update(
        {
            "action": "scale_out",
            "off_qty": off_qty,
            "off_price": round(off_price, 6),
            "realized_points": round(realized_points, 6),
        }
    )
    return out


def partial_exit(p: dict, pct: float) -> dict:
    bad_direction = _validate_direction(p)
    if bad_direction:
        return bad_direction
    if not (0 < pct < 1):
        return {
            "error": f"--pct must be in (0,1), got {pct} — accepted values: any fraction "
            "greater than 0 and less than 1, for example 0.25, 0.5, or 0.75"
        }
    qty = int(p["current_qty"])
    # Round to nearest integer (traditional rounding, not banker's):
    # 50% of 3 → 2, 50% of 5 → 3. Clamp to [1, qty-1] so partial_exit
    # never exits the whole position (the user should use scale_out for
    # that, with explicit qty).
    off_qty = int(qty * pct + 0.5)
    off_qty = max(1, min(qty - 1, off_qty))
    if qty < 2:
        return {
            "error": f"partial_exit requires qty >= 2 (current_qty={qty}) — use scale_out with full qty to close"
        }
    scaled = dict(p)
    scaled["action_qty"] = off_qty
    scaled["action_price"] = float(p.get("action_price") or p["current_mark"])
    out = scale_out(scaled)
    out["action"] = "partial_exit"
    out["pct_requested"] = pct
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="scale_math.py",
        description="Scale-in / scale-out / partial-exit math.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=list(VALID_ACTIONS),
        help="Which math to run. Required, no default. Accepted values: scale_in (add "
        "action_qty at action_price), scale_out (remove action_qty at action_price), "
        "partial_exit (remove --pct of the position at the current mark).",
    )
    parser.add_argument(
        "--pct",
        type=float,
        default=None,
        metavar="FRACTION",
        help="Fraction of the position to remove, for --action=partial_exit only. Accepted "
        "values: any fraction greater than 0 and less than 1, such as 0.5. Default: none, "
        "which makes --action=partial_exit an error.",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Path to the position-state JSON. Default: none, which reads stdin instead.",
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

    if args.action == "scale_in":
        out = scale_in(payload)
    elif args.action == "scale_out":
        out = scale_out(payload)
    else:
        if args.pct is None:
            print(
                json.dumps(
                    {
                        "error": "--pct required for partial_exit — accepted values: any "
                        "fraction greater than 0 and less than 1, for example 0.5"
                    }
                ),
                file=sys.stderr,
            )
            return 2
        out = partial_exit(payload, args.pct)

    print(json.dumps(out))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
