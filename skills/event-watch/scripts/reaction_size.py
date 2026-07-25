#!/usr/bin/env python3
"""
reaction_size.py — typical price-move magnitude around a recurring event.

Input (stdin JSON):
    {
      "events": [
        { "timestamp": "2026-03-12T12:30:00Z",
          "bars": [ {"timestamp": "...", "open": ..., "high": ..., "low": ..., "close": ...}, ... ] },
        { "timestamp": "2026-02-14T13:30:00Z", "bars": [...] },
        ...
      ]
    }

For each event, the script finds the bar whose timestamp is at or
immediately before `event.timestamp`, then tracks the high/low across
the following `--offset-minutes` of bars. Across all events it
aggregates:

    - mean_abs_move        : average |close(t+offset) - close(t0)|
    - mean_max_move_up     : average (max_high - close(t0))
    - mean_max_move_down   : average (close(t0) - min_low)
    - range_mean           : average (max_high - min_low) in the window
    - range_max            : worst-case window range
    - range_stdev          : standard deviation of per-event ranges
    - samples              : number of events with enough bars to measure

Output is in raw price points. Multiply by valuePerPoint × qty for
dollar exposure.

Usage:
    python3 reaction_size.py --file events.json --offset-minutes 5   # preferred
    echo '<events_json>' | python3 reaction_size.py --offset-minutes 5

Tip: the bars inside each event-object can come from a single
market_history call that wraps the event's entire window (say, 10min
before through 30min after). The script ignores bars outside
[t0, t0 + offset].
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _measure_event(event_time: datetime, bars: list[dict], offset: timedelta) -> dict | None:
    """Find the bar at/just-before event_time and measure the next `offset`."""
    anchor_idx = None
    for i, b in enumerate(bars):
        bt = _parse_iso(b.get("timestamp", ""))
        if bt is None:
            continue
        if bt <= event_time:
            anchor_idx = i
        else:
            break
    if anchor_idx is None:
        return None

    anchor = bars[anchor_idx]
    anchor_close = anchor.get("close")
    if anchor_close is None:
        return None

    end_time = event_time + offset
    window = [
        b
        for b in bars[anchor_idx:]
        if _parse_iso(b.get("timestamp", "")) is not None and _parse_iso(b["timestamp"]) <= end_time
    ]
    if len(window) < 2:
        return None

    highs = [b["high"] for b in window if b.get("high") is not None]
    lows = [b["low"] for b in window if b.get("low") is not None]
    last_close = window[-1].get("close")
    if not highs or not lows or last_close is None:
        return None

    max_high = max(highs)
    min_low = min(lows)
    return {
        "anchor_close": anchor_close,
        "abs_move": abs(last_close - anchor_close),
        "max_up": max_high - anchor_close,
        "max_down": anchor_close - min_low,
        "range": max_high - min_low,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Average price reaction to a recurring event.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 reaction_size.py --file events.json --offset-minutes 5\n"
            "  python3 reaction_size.py --file events.json --offset-minutes 30\n"
            "  cat events.json | python3 reaction_size.py --offset-minutes 15\n"
            "\n"
            "Exit codes: 0 = success, 2 = bad input."
        ),
    )
    parser.add_argument(
        "--offset-minutes",
        type=int,
        required=True,
        metavar="MINUTES",
        help=(
            "Width of the measurement window after each event, in whole minutes. "
            "Accepted values: any integer above 0, for example 5, 15, or 30. "
            "Required, so it has no default."
        ),
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help=("Path to the JSON payload of events and bars. Default: read the payload from stdin."),
    )
    args = parser.parse_args()

    if args.offset_minutes <= 0:
        print(
            json.dumps(
                {
                    "error": (
                        "--offset-minutes must be a positive whole number of minutes "
                        f"(for example 5, 15, 30); got {args.offset_minutes}"
                    )
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

    events = payload.get("events") or []
    if not events:
        print(json.dumps({"error": "no events in input"}), file=sys.stderr)
        return 2

    offset = timedelta(minutes=args.offset_minutes)
    measurements: list[dict] = []
    for ev in events:
        et = _parse_iso(ev.get("timestamp", ""))
        bars = ev.get("bars") or []
        if et is None or not bars:
            continue
        m = _measure_event(et, bars, offset)
        if m is not None:
            measurements.append(m)

    if not measurements:
        print(
            json.dumps({"error": "no events had enough bar data in the requested window"}),
            file=sys.stderr,
        )
        return 2

    abs_moves = [m["abs_move"] for m in measurements]
    ups = [m["max_up"] for m in measurements]
    downs = [m["max_down"] for m in measurements]
    ranges = [m["range"] for m in measurements]

    result = {
        "offset_minutes": args.offset_minutes,
        "samples": len(measurements),
        "mean_abs_move": round(sum(abs_moves) / len(abs_moves), 4),
        "mean_max_move_up": round(sum(ups) / len(ups), 4),
        "mean_max_move_down": round(sum(downs) / len(downs), 4),
        "range_mean": round(sum(ranges) / len(ranges), 4),
        "range_max": round(max(ranges), 4),
        "range_stdev": round(statistics.stdev(ranges), 4) if len(ranges) >= 2 else 0.0,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
