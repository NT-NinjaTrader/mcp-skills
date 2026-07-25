#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8"]
# ///
"""
candles.py — candlestick chart with optional VWAP overlay and fill
markers. Output is a PNG file at --output.

Input (stdin JSON):
    {
      "symbol": "ESU6",
      "title":  "ES 1m, 2026-04-20 13:00-16:00 UTC",   # optional
      "bars": [
        {"timestamp": ISO, "open": ..., "high": ..., "low": ...,
         "close": ...}, ...
      ],
      "vwap":  [{"timestamp": ISO, "value": ...}, ...],    # optional
      "fills": [                                            # optional
        {"timestamp": ISO, "price": ..., "action": "Buy"|"Sell", "quantity": ...},
        ...
      ],
      "levels": [                                          # optional horizontal lines
        {"label": "stop", "price": 7141.0, "style": "dashed"},
        {"label": "target", "price": 7170.0, "style": "dotted"}
      ]
    }

Usage:
    uv run candles.py --file market_history.json --output /tmp/chart.png   # preferred
    echo '<json>' | uv run candles.py --output /tmp/chart.png
    echo '<json>' | uv run candles.py --output /tmp/chart.png --width 16 --height 7

`uv run` installs matplotlib from the metadata block above. With
matplotlib already installed, `python3 candles.py` works the same way.
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

# Neutral palette — readable on light and dark.
UP_COLOR = "#1f7a1f"  # deep green
DOWN_COLOR = "#b11e1e"  # deep red
WICK_COLOR = "#333333"
VWAP_COLOR = "#1e5fb5"
BUY_MARKER = "#0a5d0a"
SELL_MARKER = "#8b0000"


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a candlestick chart to PNG.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run candles.py --file market_history.json "
            "--output /tmp/chart.png\n"
            "  uv run candles.py --file market_history.json "
            "--output /tmp/chart.png --width 18 --dpi 200\n"
        ),
    )
    parser.add_argument("--output", required=True, help="Path of the PNG file to write. Required.")
    parser.add_argument(
        "--width", type=float, default=14.0, help="Figure width in inches (default 14.0)."
    )
    parser.add_argument(
        "--height", type=float, default=6.0, help="Figure height in inches (default 6.0)."
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=140,
        help="Output resolution in dots per inch (default 140). Use 100 or more so the "
        "image stays readable in a transcript.",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Read the JSON payload from PATH instead of stdin (default: read stdin).",
    )
    args = parser.parse_args()

    try:
        import matplotlib

        matplotlib.use("Agg")  # non-interactive backend; no display required
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            json.dumps(
                {"error": "matplotlib not installed. Install with `pip install matplotlib`."}
            ),
            file=sys.stderr,
        )
        return 3

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
        source = f" in {args.file}" if args.file else ""
        print(json.dumps({"error": f"invalid JSON{source}: {e}"}), file=sys.stderr)
        return 2

    bars = payload.get("bars") or []
    if not bars:
        print(json.dumps({"error": "empty bars list"}), file=sys.stderr)
        return 2

    times, opens, highs, lows, closes = [], [], [], [], []
    for b in bars:
        t = _parse_iso(b.get("timestamp") or "")
        if t is None or None in (b.get("open"), b.get("high"), b.get("low"), b.get("close")):
            continue
        times.append(t)
        opens.append(b["open"])
        highs.append(b["high"])
        lows.append(b["low"])
        closes.append(b["close"])
    if not times:
        print(json.dumps({"error": "no parseable bars"}), file=sys.stderr)
        return 2

    fig, ax = plt.subplots(figsize=(args.width, args.height), dpi=args.dpi)

    # Compute bar width in fractional days (matplotlib's x-unit).
    if len(times) >= 2:
        step = (times[1] - times[0]).total_seconds() / 86400.0
    else:
        step = 1.0 / 1440.0  # 1 min default
    body_w = step * 0.6
    x = mdates.date2num(times)

    for i in range(len(times)):
        color = UP_COLOR if closes[i] >= opens[i] else DOWN_COLOR
        # Wick
        ax.plot([x[i], x[i]], [lows[i], highs[i]], color=WICK_COLOR, linewidth=0.7, zorder=1)
        # Body
        body_low = min(opens[i], closes[i])
        body_high = max(opens[i], closes[i])
        ax.add_patch(
            plt.Rectangle(
                (x[i] - body_w / 2, body_low),
                body_w,
                max(body_high - body_low, step * 0.01),  # minimum visible body for doji
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                zorder=2,
            )
        )

    # VWAP overlay
    vwap = payload.get("vwap") or []
    if vwap:
        vx, vy = [], []
        for pt in vwap:
            t = _parse_iso(pt.get("timestamp") or "")
            v = pt.get("value")
            if t is None or v is None:
                continue
            vx.append(mdates.date2num(t))
            vy.append(v)
        if vx:
            ax.plot(vx, vy, color=VWAP_COLOR, linewidth=1.4, label="VWAP", zorder=3)

    # Horizontal levels
    for lvl in payload.get("levels") or []:
        price = lvl.get("price")
        if price is None:
            continue
        style = lvl.get("style") or "dashed"
        label = lvl.get("label") or ""
        ax.axhline(price, linestyle=style, color="#666666", linewidth=0.8, alpha=0.85, zorder=0)
        ax.annotate(
            f" {label} {price}",
            xy=(x[-1], price),
            xytext=(4, 0),
            textcoords="offset points",
            fontsize=8,
            color="#444444",
            verticalalignment="center",
        )

    # Fill markers
    for f in payload.get("fills") or []:
        t = _parse_iso(f.get("timestamp") or "")
        p = f.get("price")
        action = (f.get("action") or "").lower()
        if t is None or p is None or action not in ("buy", "sell"):
            continue
        marker = "^" if action == "buy" else "v"
        color = BUY_MARKER if action == "buy" else SELL_MARKER
        ax.scatter(
            [mdates.date2num(t)],
            [p],
            marker=marker,
            s=70,
            color=color,
            zorder=4,
            edgecolors="white",
            linewidths=0.8,
        )

    # Cosmetics
    title = payload.get("title") or payload.get("symbol") or "Candlestick"
    ax.set_title(title, fontsize=11, loc="left")
    ax.grid(True, axis="y", alpha=0.25, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    if vwap or any(payload.get("fills") or []):
        ax.legend(loc="upper left", fontsize=8, frameon=False)

    # Audit watermark — states when the script generated the chart,
    # and from what source. Helpful for record-retention and
    # compliance review.
    from datetime import datetime, timezone

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    fig.text(
        0.99,
        0.005,
        f"Generated {generated} from NinjaTrader MCP data — illustrative, not trading advice",
        ha="right",
        va="bottom",
        fontsize=6,
        color="#999999",
    )

    fig.tight_layout()
    fig.savefig(args.output, format="png", bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({"output": args.output, "bars_rendered": len(times)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
