#!/usr/bin/env python3
"""
whatif.py — alternate-exit counterfactual simulator for one closed trade.

Walks the trade's bar window and tests what happens under a
different exit rule. Returns realized P&L + R for each scenario,
plus the bar timestamp that triggered the exit.

Simulated scenarios (choose one via --scenario):

  r_target        : exit at a fixed R-multiple. Requires --r-target N.
                    Exit price = entry ± (N × planned_stop_points).
                    If the bars never touch the target, scenario returns
                    "not_triggered" with the final close as the hypothetical
                    exit.

  atr_trail       : trailing stop at N × atr_points below the running
                    high (long) or above the running low (short). Stop
                    starts at entry − planned_stop_points (long) /
                    entry + planned_stop_points (short). Updates ONLY
                    in the favorable direction. Requires --atr-points
                    and --atr-multiple.

  breakeven_after : move stop to entry once trade reaches --trigger-R
                    favorable. Before that, stop = planned_stop_points.
                    After trigger, stop = entry_price.

  time_exit       : exit at entry_time + --minutes, regardless of price.
                    Uses the close of the bar that contains that timestamp.

Input (stdin JSON):
    {
      "trade": {
        "symbol": "ESZ6",
        "direction": "long" | "short",
        "entry_price": 7150.0,
        "entry_time": "2026-04-20T13:32:00Z",
        "qty": 4,
        "value_per_point": 50.0,
        "planned_stop_points": 8.0,
        "actual_exit_price": 7164.0,     # optional — for realized comparison
        "actual_exit_time":  "..."
      },
      "bars": [ {"timestamp": ISO, "open": ..., "high": ..., "low": ..., "close": ...}, ... ]
    }

Output:
    {
      "scenario": "r_target",
      "params": {...},
      "exit": {
        "triggered": true,
        "time":      ISO,
        "price":     7166.0,
        "reason":    "r_target_hit"
      },
      "realized": {"points": ..., "dollars": ..., "R": ...},
      "vs_actual": {                    # present if trade.actual_exit_price given
        "delta_points": ...,
        "delta_dollars": ...,
        "delta_R": ...
      }
    }

Usage:
    python3 whatif.py --file trade_with_bars.json --scenario r_target \\
        --r-target 2.0   # preferred
    echo '<json>' | python3 whatif.py --scenario r_target --r-target 2.0
    echo '<json>' | python3 whatif.py --scenario atr_trail --atr-points 8 --atr-multiple 1.0
    echo '<json>' | python3 whatif.py --scenario breakeven_after --trigger-R 1.0
    echo '<json>' | python3 whatif.py --scenario time_exit --minutes 30
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Optional

EPILOG = """Examples:
  python3 whatif.py --file trade_with_bars.json --scenario r_target \\
      --r-target 2.0
  python3 whatif.py --file trade_with_bars.json --scenario atr_trail \\
      --atr-points 8 --atr-multiple 1.0
  python3 whatif.py --file trade_with_bars.json --scenario breakeven_after \\
      --trigger-R 1.0
  python3 whatif.py --file trade_with_bars.json --scenario time_exit \\
      --minutes 30

Input shape (one JSON object):
  {"trade": {"symbol": "ESZ6",
             "direction": "long",          # one of: long, short
             "entry_price": 7150.0,
             "entry_time": "2026-07-20T13:32:00Z",
             "qty": 4,
             "value_per_point": 50.0,      # optional; omit for null dollars
             "planned_stop_points": 8.0,
             "actual_exit_price": 7164.0}, # optional; adds the vs_actual block
   "bars": [{"timestamp": ..., "open": ..., "high": ..., "low": ...,
             "close": ...}]}

Output: one JSON object on stdout with scenario, params, exit,
realized, and vs_actual blocks."""


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _dollars(points: Optional[float], vpp: Optional[float], qty: int) -> Optional[float]:
    if points is None or vpp is None or vpp <= 0:
        return None
    return round(points * vpp * qty, 2)


def _R(points: Optional[float], stop: Optional[float]) -> Optional[float]:
    if points is None or not stop or stop <= 0:
        return None
    return round(points / stop, 3)


def _filter_bars(bars: list[dict], entry_time: datetime) -> list[tuple[datetime, dict]]:
    out: list[tuple[datetime, dict]] = []
    for b in bars:
        bt = _parse_iso(b.get("timestamp") or "")
        if bt is None or bt < entry_time:
            continue
        if None in (b.get("high"), b.get("low"), b.get("close")):
            continue
        out.append((bt, b))
    return out


def _sim_r_target(trade: dict, bars: list[tuple[datetime, dict]], r_target: float) -> dict:
    direction = trade["direction"]
    entry = trade["entry_price"]
    stop = trade["planned_stop_points"]
    if stop is None or stop <= 0:
        return {"error": "r_target requires planned_stop_points > 0"}
    target_dist = r_target * stop
    target_price = entry + target_dist if direction == "long" else entry - target_dist
    for bt, b in bars:
        if direction == "long" and b["high"] >= target_price:
            # Gap-through handling: if the bar opened already past the
            # target, a limit order fills at the open. This is better
            # than the target, for a long profit-take.
            open_price = b.get("open")
            fill = (
                max(target_price, open_price)
                if open_price is not None and open_price > target_price
                else target_price
            )
            reason = "r_target_hit_at_open_gap" if fill != target_price else "r_target_hit"
            return {"triggered": True, "time": b["timestamp"], "price": fill, "reason": reason}
        if direction == "short" and b["low"] <= target_price:
            open_price = b.get("open")
            fill = (
                min(target_price, open_price)
                if open_price is not None and open_price < target_price
                else target_price
            )
            reason = "r_target_hit_at_open_gap" if fill != target_price else "r_target_hit"
            return {"triggered": True, "time": b["timestamp"], "price": fill, "reason": reason}
    # Not triggered — fall through to last bar close
    if bars:
        last_bt, last_b = bars[-1]
        return {
            "triggered": False,
            "time": last_b["timestamp"],
            "price": last_b["close"],
            "reason": "r_target_not_reached_fell_through",
        }
    return {"error": "no bars after entry"}


def _stop_fill_long(stop: float, bar: dict) -> tuple[float, str]:
    """When a long stop is hit on a bar, the fill happens at the stop.
    If the bar opened already below the stop (a gap-down through it),
    the fill happens at the open instead."""
    open_price = bar.get("open")
    if open_price is not None and open_price < stop:
        return open_price, "gap_through_stop"
    return stop, "stop_hit"


def _stop_fill_short(stop: float, bar: dict) -> tuple[float, str]:
    open_price = bar.get("open")
    if open_price is not None and open_price > stop:
        return open_price, "gap_through_stop"
    return stop, "stop_hit"


def _sim_atr_trail(
    trade: dict, bars: list[tuple[datetime, dict]], atr_points: float, atr_mult: float
) -> dict:
    direction = trade["direction"]
    entry = trade["entry_price"]
    initial_stop_dist = trade["planned_stop_points"]
    if initial_stop_dist is None or initial_stop_dist <= 0:
        return {"error": "atr_trail requires planned_stop_points > 0 for the initial stop"}
    trail_dist = atr_points * atr_mult
    if direction == "long":
        stop = entry - initial_stop_dist
        running_peak = entry
        for bt, b in bars:
            if b["low"] <= stop:
                fill, gap_flag = _stop_fill_long(stop, b)
                reason = f"atr_trail_{gap_flag}"
                return {"triggered": True, "time": b["timestamp"], "price": fill, "reason": reason}
            if b["high"] > running_peak:
                running_peak = b["high"]
                stop = max(stop, running_peak - trail_dist)
    else:
        stop = entry + initial_stop_dist
        running_trough = entry
        for bt, b in bars:
            if b["high"] >= stop:
                fill, gap_flag = _stop_fill_short(stop, b)
                reason = f"atr_trail_{gap_flag}"
                return {"triggered": True, "time": b["timestamp"], "price": fill, "reason": reason}
            if b["low"] < running_trough:
                running_trough = b["low"]
                stop = min(stop, running_trough + trail_dist)
    if bars:
        last_bt, last_b = bars[-1]
        return {
            "triggered": False,
            "time": last_b["timestamp"],
            "price": last_b["close"],
            "reason": "atr_trail_not_triggered_fell_through",
        }
    return {"error": "no bars after entry"}


def _sim_breakeven_after(trade: dict, bars: list[tuple[datetime, dict]], trigger_R: float) -> dict:
    direction = trade["direction"]
    entry = trade["entry_price"]
    initial_stop_dist = trade["planned_stop_points"]
    if initial_stop_dist is None or initial_stop_dist <= 0:
        return {"error": "breakeven_after requires planned_stop_points > 0"}
    trigger_dist = trigger_R * initial_stop_dist
    stop = entry - initial_stop_dist if direction == "long" else entry + initial_stop_dist
    armed = False
    for bt, b in bars:
        # Check stop hit FIRST with current stop.
        if direction == "long" and b["low"] <= stop:
            fill, gap_flag = _stop_fill_long(stop, b)
            base = "stop_hit_breakeven" if armed else "stop_hit_initial"
            return {
                "triggered": True,
                "time": b["timestamp"],
                "price": fill,
                "reason": f"{base}_{gap_flag}" if gap_flag == "gap_through_stop" else base,
            }
        if direction == "short" and b["high"] >= stop:
            fill, gap_flag = _stop_fill_short(stop, b)
            base = "stop_hit_breakeven" if armed else "stop_hit_initial"
            return {
                "triggered": True,
                "time": b["timestamp"],
                "price": fill,
                "reason": f"{base}_{gap_flag}" if gap_flag == "gap_through_stop" else base,
            }
        # Then check if the bar's favorable extreme armed the breakeven move.
        if not armed:
            if direction == "long" and b["high"] - entry >= trigger_dist:
                stop = entry
                armed = True
            elif direction == "short" and entry - b["low"] >= trigger_dist:
                stop = entry
                armed = True
    if bars:
        last_bt, last_b = bars[-1]
        reason = "fell_through_armed" if armed else "fell_through_not_armed"
        return {
            "triggered": False,
            "time": last_b["timestamp"],
            "price": last_b["close"],
            "reason": reason,
        }
    return {"error": "no bars after entry"}


def _sim_time_exit(trade: dict, bars: list[tuple[datetime, dict]], minutes: int) -> dict:
    entry_time = _parse_iso(trade["entry_time"])
    target_time = entry_time + timedelta(minutes=minutes)
    # Find first bar whose timestamp >= target_time
    for bt, b in bars:
        if bt >= target_time:
            return {
                "triggered": True,
                "time": b["timestamp"],
                "price": b["close"],
                "reason": "time_exit",
            }
    if bars:
        last_bt, last_b = bars[-1]
        return {
            "triggered": False,
            "time": last_b["timestamp"],
            "price": last_b["close"],
            "reason": "time_horizon_beyond_bars",
        }
    return {"error": "no bars after entry"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alternate-exit counterfactual simulator for a single trade.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["r_target", "atr_trail", "breakeven_after", "time_exit"],
        help=(
            "Exit rule to simulate. One of: r_target, atr_trail, "
            "breakeven_after, time_exit. Required: there is no default."
        ),
    )
    parser.add_argument(
        "--r-target",
        type=float,
        help=(
            "Profit target as an R-multiple of planned_stop_points, for "
            "--scenario r_target (for example, 2.0). Required for that "
            "scenario: there is no default."
        ),
    )
    parser.add_argument(
        "--atr-points",
        type=float,
        help=(
            "ATR value in points, for --scenario atr_trail (for example, 8). "
            "Required for that scenario: there is no default."
        ),
    )
    parser.add_argument(
        "--atr-multiple",
        type=float,
        help=(
            "Trail distance as a multiple of --atr-points, for --scenario "
            "atr_trail (for example, 1.0). Required for that scenario: there "
            "is no default."
        ),
    )
    parser.add_argument(
        "--trigger-R",
        type=float,
        help=(
            "R-multiple that arms the move of the stop to breakeven, for "
            "--scenario breakeven_after (for example, 1.0). Required for that "
            "scenario: there is no default."
        ),
    )
    parser.add_argument(
        "--minutes",
        type=int,
        help=(
            "Whole minutes to hold after the entry, for --scenario time_exit "
            "(for example, 30). Required for that scenario: there is no default."
        ),
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help=(
            "Path to the JSON payload described in the examples below. "
            "Default: read the payload from stdin."
        ),
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

    trade = payload.get("trade") or {}
    bars_raw = payload.get("bars") or []

    direction = (trade.get("direction") or "").lower()
    entry_price = trade.get("entry_price")
    entry_time = _parse_iso(trade.get("entry_time") or "")
    if direction not in ("long", "short") or entry_price is None or entry_time is None:
        print(
            json.dumps(
                {
                    "error": "trade requires direction (one of: long, short), "
                    "entry_price, and entry_time"
                }
            ),
            file=sys.stderr,
        )
        return 2
    trade["direction"] = direction

    bars = _filter_bars(bars_raw, entry_time)
    if not bars:
        print(json.dumps({"error": "no bars after entry_time"}), file=sys.stderr)
        return 2

    if args.scenario == "r_target":
        if args.r_target is None:
            print(
                json.dumps(
                    {
                        "error": "--r-target required for --scenario r_target "
                        "(an R-multiple, for example 2.0)"
                    }
                ),
                file=sys.stderr,
            )
            return 2
        exit_obj = _sim_r_target(trade, bars, args.r_target)
        params = {"r_target": args.r_target}
    elif args.scenario == "atr_trail":
        if args.atr_points is None or args.atr_multiple is None:
            print(
                json.dumps(
                    {
                        "error": "--atr-points and --atr-multiple required for "
                        "--scenario atr_trail (ATR in points and a trail "
                        "multiple, for example 8 and 1.0)"
                    }
                ),
                file=sys.stderr,
            )
            return 2
        exit_obj = _sim_atr_trail(trade, bars, args.atr_points, args.atr_multiple)
        params = {"atr_points": args.atr_points, "atr_multiple": args.atr_multiple}
    elif args.scenario == "breakeven_after":
        if args.trigger_R is None:
            print(
                json.dumps(
                    {
                        "error": "--trigger-R required for --scenario "
                        "breakeven_after (an R-multiple, for example 1.0)"
                    }
                ),
                file=sys.stderr,
            )
            return 2
        exit_obj = _sim_breakeven_after(trade, bars, args.trigger_R)
        params = {"trigger_R": args.trigger_R}
    else:  # time_exit
        if args.minutes is None:
            print(
                json.dumps(
                    {
                        "error": "--minutes required for --scenario time_exit "
                        "(whole minutes, for example 30)"
                    }
                ),
                file=sys.stderr,
            )
            return 2
        exit_obj = _sim_time_exit(trade, bars, args.minutes)
        params = {"minutes": args.minutes}

    if "error" in exit_obj:
        print(json.dumps(exit_obj), file=sys.stderr)
        return 1

    sign = 1.0 if direction == "long" else -1.0
    sim_exit_price = exit_obj["price"]
    sim_points = sign * (sim_exit_price - entry_price)
    sim_dollars = _dollars(sim_points, trade.get("value_per_point"), trade.get("qty") or 1)
    sim_R = _R(sim_points, trade.get("planned_stop_points"))

    result = {
        "scenario": args.scenario,
        "params": params,
        "exit": exit_obj,
        "realized": {
            "points": round(sim_points, 4),
            "dollars": sim_dollars,
            "R": sim_R,
        },
    }

    # Compare to the actual exit, when given.
    actual_price = trade.get("actual_exit_price")
    if actual_price is not None:
        actual_points = sign * (actual_price - entry_price)
        actual_dollars = _dollars(
            actual_points, trade.get("value_per_point"), trade.get("qty") or 1
        )
        actual_R = _R(actual_points, trade.get("planned_stop_points"))
        result["vs_actual"] = {
            "actual_points": round(actual_points, 4),
            "actual_dollars": actual_dollars,
            "actual_R": actual_R,
            "delta_points": round(sim_points - actual_points, 4),
            "delta_dollars": round(sim_dollars - actual_dollars, 2)
            if sim_dollars is not None and actual_dollars is not None
            else None,
            "delta_R": round(sim_R - actual_R, 3)
            if sim_R is not None and actual_R is not None
            else None,
        }

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
