#!/usr/bin/env python3
"""
slippage.py — per-fill slippage vs arrival mid + interval VWAP.

On-demand only. This script does bar math per fill. Do not run it
over an entire day's fill history. Trigger phrases: "what was the
slippage on fill X?" or "check slippage on this specific trade."

Input (stdin JSON):
    {
      "fill": {
        "symbol": "ESZ6",
        "timestamp": "2026-04-15T14:32:07Z",   # fill time
        "action": "Buy",                        # or "Sell"
        "quantity": 2,
        "price": 7152.25,
        "arrivalTimestamp": "2026-04-15T14:32:03Z"  # order submit time (optional)
      },
      "bars": [
        {"timestamp": "...", "open": ..., "high": ..., "low": ...,
         "close": ..., "upVolume": ..., "downVolume": ...},
        ...
      ]
    }

Bars should span the arrival-to-fill window, plus a short VWAP
lookback. For example, use 30s before and after the fill for 1s
bars, or a 3min window for 30s bars.

`market_history` bars carry no `bid`/`ask`/`volume` field — only
`open`, `high`, `low`, `close`, `upVolume`, `downVolume`, `upTicks`,
`downTicks`, and (with `volumeProfile=true`) a per-price-level
`histogram`. This script uses `close` for the arrival price and
`upVolume + downVolume` for bar volume.

Computed fields (all in price units of the symbol):

  arrival_mid          : the arrival bar's close price
  fill_price           : from input
  slippage_vs_mid      : signed. Positive means adverse — paid more on
                         a buy, or received less on a sell.
  slippage_ticks       : slippage_vs_mid / --tick-size
  interval_vwap        : sum(typical * (upVolume + downVolume)) /
                         sum(upVolume + downVolume) over bars whose
                         timestamp is within [fill - window, fill + window]
  slippage_vs_vwap     : fill_price vs interval_vwap, signed the same way

Usage:
    python3 slippage.py --file fill_and_bars.json \\
        --tick-size 0.25 --vwap-window-seconds 60   # preferred
    echo '<payload>' | python3 slippage.py \\
        --tick-size 0.25 \\
        --vwap-window-seconds 60
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Optional

EPILOG = """Examples:
  python3 slippage.py --file fill_and_bars.json --tick-size 0.25
  python3 slippage.py --file fill_and_bars.json --tick-size 0.25 \\
      --vwap-window-seconds 30
  cat fill_and_bars.json | python3 slippage.py --tick-size 0.25

Input shape (one JSON object):
  {"fill": {"symbol": "ESZ6",
            "timestamp": "2026-07-20T14:32:07Z",
            "action": "Buy",                 # one of: Buy, Sell
            "quantity": 2,
            "price": 7152.25,
            "arrivalTimestamp": "2026-07-20T14:32:03Z"},   # optional
   "bars": [{"timestamp": ..., "open": ..., "high": ..., "low": ...,
             "close": ..., "upVolume": ..., "downVolume": ...}]}

Output: one JSON object on stdout with the slippage fields."""


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _arrival_mid(bars: list[dict], arrival: datetime) -> Optional[float]:
    """Find the bar whose timestamp is at or just before arrival. market_history
    bars carry no bid/ask field, so this uses the bar's close price."""
    anchor = None
    for b in bars:
        bt = _parse_iso(b.get("timestamp") or "")
        if bt is None:
            continue
        if bt <= arrival:
            anchor = b
        else:
            break
    if anchor is None:
        return None
    return anchor.get("close")


def _interval_vwap(bars: list[dict], center: datetime, window: timedelta) -> Optional[float]:
    start = center - window
    end = center + window
    num = 0.0
    denom = 0.0
    for b in bars:
        bt = _parse_iso(b.get("timestamp") or "")
        if bt is None or bt < start or bt > end:
            continue
        high = b.get("high")
        low = b.get("low")
        close = b.get("close")
        # market_history has no single "volume" field — derive it from
        # upVolume + downVolume.
        vol = (b.get("upVolume") or 0) + (b.get("downVolume") or 0)
        if high is None or low is None or close is None or vol <= 0:
            continue
        typical = (high + low + close) / 3.0
        num += typical * vol
        denom += vol
    return num / denom if denom > 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Per-fill slippage vs arrival mid + interval VWAP.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        required=True,
        help=(
            "Minimum price increment of the contract, in price units "
            "(for example, 0.25 for ES). Required: there is no default."
        ),
    )
    parser.add_argument(
        "--vwap-window-seconds",
        type=int,
        default=60,
        help=(
            "Half-width of the interval VWAP window, in seconds, centered on the "
            "fill time. Default: 60."
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

    if args.tick_size <= 0:
        print(
            json.dumps(
                {
                    "error": "--tick-size must be a positive number of price units "
                    "(for example, 0.25)"
                }
            ),
            file=sys.stderr,
        )
        return 2

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

    fill = payload.get("fill") or {}
    bars = payload.get("bars") or []
    fill_price = fill.get("price")
    action = (fill.get("action") or "").lower()
    fill_ts = _parse_iso(fill.get("timestamp") or "")
    arrival_ts = _parse_iso(fill.get("arrivalTimestamp") or "") or fill_ts

    if fill_price is None or action not in ("buy", "sell") or fill_ts is None:
        print(
            json.dumps(
                {"error": "fill must include price, action (one of: Buy, Sell), and timestamp"}
            ),
            file=sys.stderr,
        )
        return 2

    mid = _arrival_mid(bars, arrival_ts)
    vwap = _interval_vwap(bars, fill_ts, timedelta(seconds=args.vwap_window_seconds))

    # Positive means adverse: the buyer paid above mid, or the seller
    # received below mid.
    sign = 1 if action == "buy" else -1

    result = {
        "symbol": fill.get("symbol"),
        "action": fill.get("action"),
        "qty": fill.get("quantity"),
        "fill_price": fill_price,
        "arrival_mid": round(mid, 6) if mid is not None else None,
        "slippage_vs_mid": round(sign * (fill_price - mid), 6) if mid is not None else None,
        "slippage_ticks": round(sign * (fill_price - mid) / args.tick_size, 2)
        if mid is not None
        else None,
        "interval_vwap": round(vwap, 6) if vwap is not None else None,
        "slippage_vs_vwap": round(sign * (fill_price - vwap), 6) if vwap is not None else None,
        "vwap_window_seconds": args.vwap_window_seconds,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
