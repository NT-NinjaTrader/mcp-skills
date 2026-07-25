#!/usr/bin/env python3
"""
hedge_sizing.py — dollar-neutral hedge proposal for an open position.

Given an open position in symbol A and a hedge candidate in symbol B
with a known regression β (series B's returns on A's returns), compute
how many hedge contracts produce a dollar-neutral offset.

Math:
  position $-move-per-1pct-A = qty_A × price_A × vpp_A × 0.01
  hedge    $-move-per-1pct-B = qty_B × price_B × vpp_B × 0.01
  For every 1% move in A, B moves β% (in expectation).
  Dollar-neutral: hedge $-move = position $-move.
  qty_B × price_B × vpp_B × β = qty_A × price_A × vpp_A
  → qty_B = (qty_A × price_A × vpp_A) / (price_B × vpp_B × β)

Signs:
  - Position long  → hedge is opposite side (short hedge)
  - Position short → hedge is opposite side (long hedge)
  - β > 0 (positive correlation, typical case): opposite-side hedge
  - β < 0 (negative correlation, e.g., stocks vs bonds): SAME-side
    hedge (hedge is a long to offset a long — rare but valid)

Input (stdin JSON) — `scripts/fixtures/hedge_sizing.json` holds this
exact payload:
    {
      "position": {
        "symbol": "ESU6",
        "direction": "long" | "short",
        "qty":   4,
        "price": 7150.0,
        "value_per_point": 50.0
      },
      "hedge_candidate": {
        "symbol":          "NQU6",
        "price":           22450.0,
        "value_per_point": 20.0,
        "beta":            0.93        # regression β of hedge-on-position
      }
    }

Output for that input, with the default --round nearest:
    {
      "position": {
        "symbol": "ESU6",
        "direction": "long",
        "qty": 4,
        "dollars_per_1pct_move": 14300.0
      },
      "hedge": {
        "symbol": "NQU6",
        "side": "Sell",
        "beta": 0.93,
        "raw_qty": 3.4246,
        "rounded_qty": 3,
        "residual_pct": 12.4          # |raw - rounded| / raw × 100
      },
      "coverage": {
        "position_dollars_per_1pct": 14300.0,
        "hedge_dollars_per_1pct_at_rounded": 12527.1,   # at rounded qty, with β applied
        "coverage_pct": 87.6,
        "residual_exposure_dollars": 1772.9
      }
    }

The script adds a `note` key only when `rounded_qty` is 0, or when
`residual_pct` reaches 30. The example above stays under both limits,
so it carries no `note`.

Usage:
    python3 hedge_sizing.py --file hedge_input.json   # preferred
    echo '<json>' | python3 hedge_sizing.py
    echo '<json>' | python3 hedge_sizing.py --round nearest|up|down
"""

import argparse
import json
import math
import sys


def _round_mode(raw: float, mode: str) -> int:
    if mode == "up":
        return math.ceil(raw) if raw > 0 else math.floor(raw)
    if mode == "down":
        return math.floor(raw) if raw > 0 else math.ceil(raw)
    # nearest (default)
    return int(raw + 0.5) if raw >= 0 else -int(-raw + 0.5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dollar-neutral hedge sizing.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  hedge_sizing.py --file hedge_input.json\n"
            "  hedge_sizing.py --file hedge_input.json --round down\n"
        ),
    )
    parser.add_argument(
        "--round",
        choices=["nearest", "up", "down"],
        default="nearest",
        help="Rounding mode that turns the raw hedge qty into whole contracts (default nearest).",
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

    pos = payload.get("position") or {}
    hc = payload.get("hedge_candidate") or {}

    required_pos = ["symbol", "direction", "qty", "price", "value_per_point"]
    required_hc = ["symbol", "price", "value_per_point", "beta"]
    for k in required_pos:
        if pos.get(k) is None:
            print(json.dumps({"error": f"position.{k} required"}), file=sys.stderr)
            return 2
    for k in required_hc:
        if hc.get(k) is None:
            print(json.dumps({"error": f"hedge_candidate.{k} required"}), file=sys.stderr)
            return 2

    direction = pos["direction"].lower()
    if direction not in ("long", "short"):
        print(
            json.dumps({"error": "position.direction must be 'long' or 'short'"}), file=sys.stderr
        )
        return 2

    beta = float(hc["beta"])
    if beta == 0:
        print(
            json.dumps({"error": "beta=0 — no correlation, cannot size a hedge"}), file=sys.stderr
        )
        return 2

    pos_qty = int(pos["qty"])
    pos_price = float(pos["price"])
    pos_vpp = float(pos["value_per_point"])
    hc_price = float(hc["price"])
    hc_vpp = float(hc["value_per_point"])

    # Validate positive price + vpp — zero breaks the division and
    # negative is nonsensical for futures contract specs.
    for name, val in (
        ("position.qty", pos_qty),
        ("position.price", pos_price),
        ("position.value_per_point", pos_vpp),
        ("hedge_candidate.price", hc_price),
        ("hedge_candidate.value_per_point", hc_vpp),
    ):
        if val <= 0:
            print(json.dumps({"error": f"{name} must be > 0, got {val}"}), file=sys.stderr)
            return 2

    # Position $ move per 1% move in A
    pos_per_1pct = pos_qty * pos_price * pos_vpp * 0.01
    hc_per_1pct_unit = hc_price * hc_vpp * 0.01  # per 1 contract per 1% of B

    # For every 1% in A, B moves β%. Hedge $-move at qty H:
    # H × hc_price × hc_vpp × β × 0.01 = pos_per_1pct  (A-% basis)
    # → H = pos_per_1pct / (hc_per_1pct_unit × β)
    raw_qty = pos_per_1pct / (hc_per_1pct_unit * beta)

    # Hedge side: opposite for positive β on a long; same for negative β.
    pos_sign = 1 if direction == "long" else -1
    hedge_sign = -pos_sign if beta > 0 else pos_sign
    rounded_qty_abs = _round_mode(abs(raw_qty), args.round)
    hedge_side = "Sell" if hedge_sign < 0 else "Buy"

    # Coverage at rounded qty
    rounded_move = rounded_qty_abs * hc_per_1pct_unit * abs(beta)
    coverage_pct = round(100.0 * rounded_move / pos_per_1pct, 2) if pos_per_1pct else 0.0
    residual_pct = (
        round(100.0 * abs(abs(raw_qty) - rounded_qty_abs) / abs(raw_qty), 2) if raw_qty else 0.0
    )

    note = None
    if rounded_qty_abs == 0:
        note = (
            "Rounded hedge qty is 0 — the hedge candidate's per-contract "
            "exposure is larger than the position's. Consider a micro "
            "(MES, MNQ, MCL, MGC) or scaling up the position instead."
        )
    elif residual_pct >= 30.0:
        note = (
            f"Residual {residual_pct}% after rounding is high. Consider "
            "a micro contract or a different hedge symbol for finer sizing."
        )

    result = {
        "position": {
            "symbol": pos["symbol"],
            "direction": direction,
            "qty": pos_qty,
            "dollars_per_1pct_move": round(pos_per_1pct, 2),
        },
        "hedge": {
            "symbol": hc["symbol"],
            "side": hedge_side,
            "beta": beta,
            "raw_qty": round(abs(raw_qty), 4),
            "rounded_qty": rounded_qty_abs,
            "residual_pct": residual_pct,
        },
        "coverage": {
            "position_dollars_per_1pct": round(pos_per_1pct, 2),
            "hedge_dollars_per_1pct_at_rounded": round(rounded_move, 2),
            "coverage_pct": coverage_pct,
            "residual_exposure_dollars": round(pos_per_1pct - rounded_move, 2),
        },
    }
    if note:
        result["note"] = note
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
