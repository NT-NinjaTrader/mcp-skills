#!/usr/bin/env python3
"""
excursion.py — MFE / MAE and bar-by-bar path for a single closed trade.

Same math as `trade-debrief/scripts/compute_derived.py`. This script
ships as a focused per-trade tool for trade-replay's deep-dive
workflow. Keep the two files in sync when the math evolves.

Input (stdin JSON):
    {
      "trade": {
        "symbol": "ESZ6",
        "direction": "long" | "short",
        "entry_price": 7150.0,
        "exit_price":  7164.0,
        "entry_time":  "2026-04-20T13:32:00Z",
        "exit_time":   "2026-04-20T14:19:00Z",
        "qty": 4,
        "value_per_point": 50.0,
        "planned_stop_points": 8.0
      },
      "bars": [ { "timestamp": ISO, "high": ..., "low": ..., "close": ... }, ... ]
    }

Output:
    {
      "symbol": "...",
      "direction": "long",
      "entry_price": ..., "exit_price": ...,
      "entry_time": ..., "exit_time": ...,
      "qty": ..., "value_per_point": ...,
      "realized": {"points": ..., "dollars": ..., "R": ...},
      "mfe":      {"points": ..., "dollars": ..., "R": ..., "at_timestamp": ISO, "at_price": ...},
      "mae":      {"points": ..., "dollars": ..., "R": ..., "at_timestamp": ISO, "at_price": ...},
      "derived": {
        "giveback_from_mfe_pct": ...,
        "realized_vs_mfe_pct": ...,
        "adverse_used_pct_of_stop": ...,  # mae / planned_stop × 100
        "hold_minutes": ...
      }
    }

Usage:
    python3 excursion.py --file trade_with_bars.json   # preferred
    echo '<json>' | python3 excursion.py
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

EPILOG = """Examples:
  python3 excursion.py --file trade_with_bars.json
  cat trade_with_bars.json | python3 excursion.py

Input shape (one JSON object):
  {"trade": {"symbol": "ESZ6",
             "direction": "long",          # one of: long, short
             "entry_price": 7150.0,
             "exit_price": 7164.0,
             "entry_time": "2026-07-20T13:32:00Z",
             "exit_time": "2026-07-20T14:19:00Z",
             "qty": 4,
             "value_per_point": 50.0,      # optional; omit for null dollars
             "planned_stop_points": 8.0},  # optional; omit for null R
   "bars": [{"timestamp": ..., "high": ..., "low": ..., "close": ...}]}

Output: one JSON object on stdout with realized, mfe, mae, and derived
blocks."""


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _compute(trade: dict, bars: list[dict]) -> dict:
    direction = (trade.get("direction") or "").lower()
    entry_price = trade.get("entry_price")
    exit_price = trade.get("exit_price")
    entry_time = _parse_iso(trade.get("entry_time") or "")
    exit_time = _parse_iso(trade.get("exit_time") or "")
    qty = trade.get("qty") or 1
    vpp = trade.get("value_per_point")
    planned_stop = trade.get("planned_stop_points")

    if direction not in ("long", "short") or entry_price is None or exit_price is None:
        return {
            "error": "trade missing direction / entry_price / exit_price "
            "(direction must be one of: long, short)"
        }
    if entry_time is None:
        return {"error": "trade missing entry_time (cannot bound the bar scan)"}

    sign = 1.0 if direction == "long" else -1.0
    realized_points = sign * (exit_price - entry_price)

    def _dollars(points: Optional[float]) -> Optional[float]:
        if points is None or vpp is None or vpp <= 0:
            return None
        return round(points * vpp * qty, 2)

    def _R(points: Optional[float]) -> Optional[float]:
        if points is None or not planned_stop or planned_stop <= 0:
            return None
        return round(points / planned_stop, 3)

    mfe_points: Optional[float] = None
    mae_points: Optional[float] = None
    mfe_at_ts: Optional[str] = None
    mae_at_ts: Optional[str] = None
    mfe_at_price: Optional[float] = None
    mae_at_price: Optional[float] = None

    if bars:
        mfe_points = 0.0
        mae_points = 0.0
        for b in bars:
            bt = _parse_iso(b.get("timestamp") or "")
            if bt is None or bt < entry_time:
                continue
            if exit_time and bt > exit_time:
                continue
            high = b.get("high")
            low = b.get("low")
            if high is None or low is None:
                continue
            if direction == "long":
                fav = high - entry_price
                adv = entry_price - low
                fav_price = high
                adv_price = low
            else:
                fav = entry_price - low
                adv = high - entry_price
                fav_price = low
                adv_price = high
            if fav > mfe_points:
                mfe_points = fav
                mfe_at_ts = b.get("timestamp")
                mfe_at_price = fav_price
            if adv > mae_points:
                mae_points = adv
                mae_at_ts = b.get("timestamp")
                mae_at_price = adv_price

    hold_minutes = None
    if exit_time is not None:
        hold_minutes = round((exit_time - entry_time).total_seconds() / 60.0, 2)

    giveback = None
    realized_vs_mfe = None
    if mfe_points is not None and mfe_points > 0:
        giveback = round(
            max(0.0, min(100.0, 100.0 * (mfe_points - realized_points) / mfe_points)), 2
        )
        realized_vs_mfe = round(100.0 * realized_points / mfe_points, 2)

    adverse_saved_pct = None
    if mae_points is not None and planned_stop and planned_stop > 0:
        # 100% means the trade stopped at the worst price. 50% means
        # mae used half the stop budget. 0% means mae never ticked
        # against entry.
        adverse_saved_pct = round(min(100.0, 100.0 * mae_points / planned_stop), 2)

    return {
        "symbol": trade.get("symbol"),
        "direction": direction,
        "entry_price": round(entry_price, 6),
        "exit_price": round(exit_price, 6),
        "entry_time": trade.get("entry_time"),
        "exit_time": trade.get("exit_time"),
        "qty": qty,
        "value_per_point": vpp,
        "planned_stop_points": planned_stop,
        "realized": {
            "points": round(realized_points, 4),
            "dollars": _dollars(realized_points),
            "R": _R(realized_points),
        },
        "mfe": {
            "points": round(mfe_points, 4) if mfe_points is not None else None,
            "dollars": _dollars(mfe_points),
            "R": _R(mfe_points),
            "at_timestamp": mfe_at_ts,
            "at_price": round(mfe_at_price, 6) if mfe_at_price is not None else None,
        },
        "mae": {
            "points": round(mae_points, 4) if mae_points is not None else None,
            "dollars": _dollars(mae_points),
            "R": _R(mae_points),
            "at_timestamp": mae_at_ts,
            "at_price": round(mae_at_price, 6) if mae_at_price is not None else None,
        },
        "derived": {
            "giveback_from_mfe_pct": giveback,
            "realized_vs_mfe_pct": realized_vs_mfe,
            "adverse_used_pct_of_stop": adverse_saved_pct,
            "hold_minutes": hold_minutes,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MFE/MAE and derived metrics for a single closed trade.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
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
    bars = payload.get("bars") or []
    result = _compute(trade, bars)
    print(json.dumps(result))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
