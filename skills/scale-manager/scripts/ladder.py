#!/usr/bin/env python3
"""
ladder.py — split a planned entry into N laddered orders.

Given a total qty, an anchor price, and a spacing mode, returns the
per-leg price/qty pairs plus a combined weighted basis.

Modes:

  even         : evenly-spaced band. Requires --band-points (total
                 band width in price points). Legs span
                 [anchor, anchor - band] for long; [anchor, anchor + band]
                 for short.
  atr          : ATR-proportional spacing — --atr-points and --atr-fraction
                 set the step size (step = atr × fraction). Legs are
                 anchor, anchor ± step, anchor ± 2×step, ...
  custom       : caller supplies --prices "7148,7145,7142"

Weight allocation:
  equal        : floor(qty/N) per leg; remainder goes to the first leg
  front        : heavier on the first (closest-to-anchor) leg; 50% / 30% / 20% style
  back         : heavier on the back leg — for aggressive mean-reversion
  custom       : --weights "0.5,0.3,0.2"

Input (stdin JSON):
    {
      "direction":       "long" | "short",
      "anchor_price":    7148.0,
      "total_qty":       3,
      "tick_size":       0.25,
      "value_per_point": 50.0
    }

Output (JSON):
    {
      "direction": "...",
      "legs": [{"price": ..., "qty": ...}, ...],
      "combined_qty": ...,
      "weighted_basis": ...,
      "spread_points":     # anchor - farthest leg (abs)
      "worst_case_fill_basis": ...,   # all legs fill at the band edge
      "best_case_fill_basis": ...     # only anchor leg fills
    }

Usage:
    python3 ladder.py --file position.json --mode even --band-points 6 --legs 3   # preferred
    echo '<json>' | python3 ladder.py --mode even --band-points 6 --legs 3
    echo '<json>' | python3 ladder.py --mode atr --atr-points 8 --atr-fraction 0.5 --legs 3
    echo '<json>' | python3 ladder.py --mode custom --prices 7148,7145,7142
    echo '<json>' | python3 ladder.py --mode even --band-points 6 --legs 3 \\
        --weighting front
"""

import argparse
import json
import sys
from typing import Optional

VALID_MODES = ("even", "atr", "custom")
VALID_WEIGHTINGS = ("equal", "front", "back", "custom")
VALID_DIRECTIONS = ("long", "short")

EXAMPLES = """\
Examples:
  # 3-leg ladder across a 6-point band (preferred: payload from a file).
  python3 ladder.py --file anchor_state.json --mode even --band-points 6 --legs 3

  # ATR-proportional spacing: step = 8 x 0.5 = 4 points.
  python3 ladder.py --file anchor_state.json --mode atr --atr-points 8 \\
      --atr-fraction 0.5 --legs 3

  # Explicit leg prices, front-loaded.
  python3 ladder.py --file anchor_state.json --mode custom \\
      --prices 7148,7145,7142 --weighting front

  # Same call from stdin.
  echo '<json>' | python3 ladder.py --mode even --band-points 6 --legs 3
"""


def _snap(price: float, tick: float) -> float:
    return round(round(price / tick) * tick, 6)


def _compute_prices(
    mode: str,
    direction: str,
    anchor: float,
    legs: int,
    band_points: Optional[float],
    atr_points: Optional[float],
    atr_fraction: Optional[float],
    custom_prices: list[float],
    tick: float,
) -> list[float]:
    sign = -1.0 if direction == "long" else 1.0  # ladder below anchor on long
    if mode == "even":
        if band_points is None:
            raise ValueError(
                "--band-points required for --mode=even (total band width in price points, "
                "any number > 0). The other modes are: atr (needs --atr-points and "
                "--atr-fraction), custom (needs --prices)."
            )
        if legs == 1:
            return [anchor]
        step = band_points / (legs - 1)
        return [_snap(anchor + sign * i * step, tick) for i in range(legs)]
    if mode == "atr":
        if atr_points is None or atr_fraction is None:
            raise ValueError(
                "--atr-points and --atr-fraction required for --mode=atr (both any number "
                "> 0). The other modes are: even (needs --band-points), custom (needs "
                "--prices)."
            )
        step = atr_points * atr_fraction
        return [_snap(anchor + sign * i * step, tick) for i in range(legs)]
    if mode == "custom":
        if not custom_prices:
            raise ValueError(
                "--prices required for --mode=custom (a comma-separated price list, for "
                "example 7148,7145,7142). The other modes are: even (needs --band-points), "
                "atr (needs --atr-points and --atr-fraction)."
            )
        return [_snap(p, tick) for p in custom_prices]
    raise ValueError(f"unknown mode {mode!r} — accepted values: {', '.join(VALID_MODES)}")


def _compute_weights(weighting: str, legs: int, custom: list[float]) -> list[float]:
    if weighting == "equal":
        return [1.0 / legs] * legs
    if weighting == "front":
        # classic 50/30/20 for 3 legs; 40/30/20/10 for 4; otherwise
        # arithmetic decay normalized.
        raw = [legs - i for i in range(legs)]
        total = sum(raw)
        return [r / total for r in raw]
    if weighting == "back":
        raw = [i + 1 for i in range(legs)]
        total = sum(raw)
        return [r / total for r in raw]
    if weighting == "custom":
        if not custom:
            raise ValueError(
                "--weights required for --weighting=custom (a comma-separated list of "
                "fractions that sum to 1.0, for example 0.5,0.3,0.2). The other weightings "
                f"are: {', '.join(w for w in VALID_WEIGHTINGS if w != 'custom')}."
            )
        if abs(sum(custom) - 1.0) > 0.01:
            raise ValueError(
                f"--weights must sum to 1.0, got {sum(custom)} — accepted values: any "
                "fractions that sum to 1.0, within a 0.01 tolerance."
            )
        if len(custom) != legs:
            raise ValueError(
                f"--weights has {len(custom)} values, need {legs} — pass exactly one "
                "fraction per leg."
            )
        return custom
    raise ValueError(
        f"unknown weighting {weighting!r} — accepted values: {', '.join(VALID_WEIGHTINGS)}"
    )


def _allocate_qty(total_qty: int, weights: list[float]) -> list[int]:
    # This integer allocation keeps the sum equal to total_qty (the largest-remainder method).
    raw = [total_qty * w for w in weights]
    floors = [int(x) for x in raw]
    remainders = [(raw[i] - floors[i], i) for i in range(len(weights))]
    remainders.sort(reverse=True)
    missing = total_qty - sum(floors)
    for _, i in remainders[:missing]:
        floors[i] += 1
    return floors


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ladder.py",
        description="Ladder an entry into multiple legs.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=list(VALID_MODES),
        help="Price-spacing mode. Required, no default. Accepted values: even (evenly "
        "spaced band, needs --band-points), atr (ATR-proportional step, needs --atr-points "
        "and --atr-fraction), custom (explicit prices, needs --prices).",
    )
    parser.add_argument(
        "--legs",
        type=int,
        default=3,
        metavar="INT",
        help="Number of legs, as a count. Default: 3. Ignored when --mode=custom, which "
        "infers the count from --prices.",
    )
    parser.add_argument(
        "--band-points",
        type=float,
        default=None,
        metavar="NUM",
        help="Total band width in price points, for --mode=even. Default: none, which "
        "makes --mode=even an error.",
    )
    parser.add_argument(
        "--atr-points",
        type=float,
        default=None,
        metavar="NUM",
        help="ATR value in price points, for --mode=atr. Default: none, which makes "
        "--mode=atr an error.",
    )
    parser.add_argument(
        "--atr-fraction",
        type=float,
        default=None,
        metavar="NUM",
        help="Fraction of --atr-points per step, as a decimal such as 0.5. For --mode=atr. "
        "Default: none, which makes --mode=atr an error.",
    )
    parser.add_argument(
        "--prices",
        type=str,
        default=None,
        metavar="LIST",
        help="Comma-separated leg prices in price units, for --mode=custom, for example "
        "7148,7145,7142. Default: none, which makes --mode=custom an error.",
    )
    parser.add_argument(
        "--weighting",
        choices=list(VALID_WEIGHTINGS),
        default="equal",
        help="Quantity allocation across the legs. Default: equal. Accepted values: equal "
        "(same size per leg), front (heavier on the anchor leg), back (heavier on the far "
        "leg), custom (needs --weights).",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        metavar="LIST",
        help="Comma-separated weights as fractions that sum to 1.0, for "
        "--weighting=custom, for example 0.5,0.3,0.2. Default: none.",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Path to the anchor-state JSON. Default: none, which reads stdin instead.",
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

    direction = payload["direction"].lower()
    if direction not in VALID_DIRECTIONS:
        print(
            json.dumps(
                {
                    "error": f"unknown direction {direction!r} in the payload — accepted "
                    f"values: {', '.join(VALID_DIRECTIONS)}"
                }
            ),
            file=sys.stderr,
        )
        return 2
    anchor = float(payload["anchor_price"])
    total_qty = int(payload["total_qty"])
    tick = float(payload.get("tick_size", 0.01))

    custom_prices = [float(x) for x in args.prices.split(",")] if args.prices else []
    if args.mode == "custom":
        legs = len(custom_prices)
    else:
        legs = args.legs

    custom_weights = [float(x) for x in args.weights.split(",")] if args.weights else []

    if total_qty < legs:
        print(
            json.dumps(
                {
                    "error": f"total_qty ({total_qty}) is less than legs ({legs}) — some legs would be qty 0. "
                    f"Reduce --legs or increase total_qty."
                }
            ),
            file=sys.stderr,
        )
        return 2

    try:
        prices = _compute_prices(
            args.mode,
            direction,
            anchor,
            legs,
            args.band_points,
            args.atr_points,
            args.atr_fraction,
            custom_prices,
            tick,
        )
        weights = _compute_weights(args.weighting, legs, custom_weights)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2

    qtys = _allocate_qty(total_qty, weights)
    legs_out = [
        {"price": p, "qty": q, "weight_pct": round(100 * w, 2)}
        for p, q, w in zip(prices, qtys, weights)
    ]

    # Combined weighted basis (if all legs fill).
    total_filled = sum(qtys)
    weighted_basis = (
        sum(p * q for p, q in zip(prices, qtys)) / total_filled if total_filled else None
    )
    spread = abs(anchor - prices[-1]) if prices else 0.0

    # Direction-neutral naming: "best"/"worst" depends on whether the
    # ladder is mean-reversion (a deeper fill gives a better average) or
    # breakout retest (only the first fill means an early entry). The
    # script cannot know which one applies. The caller interprets the
    # result based on the trade thesis.
    out = {
        "direction": direction,
        "anchor_price": anchor,
        "legs": legs_out,
        "combined_qty": total_filled,
        "weighted_basis": _snap(weighted_basis, tick) if weighted_basis else None,
        "spread_points": round(spread, 6),
        "basis_if_only_first_leg_fills": prices[0],
        "basis_if_all_legs_fill": _snap(weighted_basis, tick) if weighted_basis else None,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
