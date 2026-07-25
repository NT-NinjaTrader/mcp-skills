#!/usr/bin/env python3
"""
compute_derived.py — derived per-trade fields that the debrief
prompt library needs, but that the MCP tools do not ship directly.

Fields computed:
  - mfe_points / mfe_dollars   : maximum favorable excursion across the
                                 trade's lifetime, in points and dollars
  - mae_points / mae_dollars   : maximum adverse excursion, same units
  - giveback_from_mfe_pct      : 100 × (mfe − realized) / mfe, if mfe > 0
                                 else null. Cap at 100.
  - realized_vs_mfe_pct        : 100 × realized / mfe, if mfe > 0 else null
  - realized_R                 : realized / planned_risk_per_contract
  - mfe_R / mae_R              : mfe / planned_risk, mae / planned_risk

Input (stdin JSON):
    {
      "trades": [
        { "trade_id": "T-001",
          "symbol": "ESZ6",
          "direction": "long" | "short",
          "entry_price": 7100.00,
          "exit_price":  7105.25,
          "entry_time":  "2026-04-20T13:32:00Z",
          "exit_time":   "2026-04-20T13:47:00Z",
          "qty": 2,
          "value_per_point": 50.0,
          "tick_size": 0.25,
          "planned_stop_points": 4.0,         # optional — required for R fields
          "bars": [
            {"timestamp": "...", "high": ..., "low": ..., "close": ...},
            ...
          ]
        },
        ...
      ]
    }

Bars inside each trade should cover at least [entry_time, exit_time].
The script ignores bars outside the trade window.

Usage:
    python3 compute_derived.py --file trades_with_bars.json   # preferred
    echo '<trades_json>' | python3 compute_derived.py

Output: same trade objects with a `derived` sub-object added.
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

EPILOG = """Examples:
  python3 compute_derived.py --file trades_with_bars.json
  cat trades_with_bars.json | python3 compute_derived.py

Input shape (one JSON object):
  {"trades": [
     {"trade_id": "T-001",
      "symbol": "ESZ6",
      "direction": "long",             # one of: long, short
      "entry_price": 7100.0,
      "exit_price": 7105.25,
      "entry_time": "2026-07-20T13:32:00Z",
      "exit_time": "2026-07-20T13:47:00Z",
      "qty": 2,
      "value_per_point": 50.0,         # optional; omit for null dollar fields
      "planned_stop_points": 4.0,      # optional; omit for null R fields
      "bars": [{"timestamp": ..., "high": ..., "low": ..., "close": ...}]}]}

Output: the same trades on stdout, each with a `derived` sub-object."""


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _derive(trade: dict) -> dict:
    direction = (trade.get("direction") or "").lower()
    entry_price = trade.get("entry_price")
    exit_price = trade.get("exit_price")
    entry_time = _parse_iso(trade.get("entry_time") or "")
    exit_time = _parse_iso(trade.get("exit_time") or "")
    qty = trade.get("qty") or 1
    vpp = trade.get("value_per_point")
    planned_stop = trade.get("planned_stop_points")
    bars = trade.get("bars") or []

    if direction not in ("long", "short") or entry_price is None or exit_price is None:
        return {
            "_error": "trade missing direction / entry_price / exit_price "
            "(direction must be one of: long, short)"
        }

    sign = 1.0 if direction == "long" else -1.0
    realized_points = sign * (exit_price - entry_price)
    # Dollar fields have a value only when vpp is given. Otherwise,
    # they are null.
    if vpp is not None and vpp > 0:
        realized_dollars: Optional[float] = round(realized_points * vpp * qty, 2)
    else:
        realized_dollars = None

    # MFE and MAE require both entry_time and at least one usable bar.
    # Without entry_time, the scan could include bars from before the
    # trade began (false peaks). With no bars, there is no intra-trade
    # excursion data at all. In either case, the script returns null,
    # not a misleading 0.
    mfe_points: Optional[float] = None
    mae_points: Optional[float] = None
    if entry_time is not None and bars:
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
            # Peak favorable movement — use high for longs, low for shorts.
            if direction == "long":
                fav = high - entry_price
                adv = entry_price - low
            else:
                fav = entry_price - low
                adv = high - entry_price
            if fav > mfe_points:
                mfe_points = fav
            if adv > mae_points:
                mae_points = adv

    def _to_dollars(points: Optional[float]) -> Optional[float]:
        if points is None or vpp is None or vpp <= 0:
            return None
        return round(points * vpp * qty, 2)

    mfe_dollars = _to_dollars(mfe_points)
    mae_dollars = _to_dollars(mae_points)

    giveback_pct: Optional[float] = None
    realized_vs_mfe_pct: Optional[float] = None
    if mfe_points is not None and mfe_points > 0:
        giveback_pct = round(
            max(0.0, min(100.0, 100.0 * (mfe_points - realized_points) / mfe_points)), 2
        )
        realized_vs_mfe_pct = round(100.0 * realized_points / mfe_points, 2)

    realized_R: Optional[float] = None
    mfe_R: Optional[float] = None
    mae_R: Optional[float] = None
    if planned_stop and planned_stop > 0:
        realized_R = round(realized_points / planned_stop, 3)
        if mfe_points is not None:
            mfe_R = round(mfe_points / planned_stop, 3)
        if mae_points is not None:
            mae_R = round(mae_points / planned_stop, 3)

    return {
        "realized_points": round(realized_points, 4),
        "realized_dollars": realized_dollars,
        "realized_R": realized_R,
        "mfe_points": round(mfe_points, 4) if mfe_points is not None else None,
        "mfe_dollars": mfe_dollars,
        "mfe_R": mfe_R,
        "mae_points": round(mae_points, 4) if mae_points is not None else None,
        "mae_dollars": mae_dollars,
        "mae_R": mae_R,
        "giveback_from_mfe_pct": giveback_pct,
        "realized_vs_mfe_pct": realized_vs_mfe_pct,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute derived per-trade fields (MFE/MAE/R) for a list of trades.",
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

    trades = payload.get("trades") or []
    out = []
    for t in trades:
        derived = _derive(t)
        out.append({**t, "derived": derived})
    print(json.dumps({"trades": out}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
