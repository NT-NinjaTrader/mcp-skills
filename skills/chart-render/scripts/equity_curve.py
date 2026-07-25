#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8"]
# ///
"""
equity_curve.py — cumulative P&L curve from a list of trades. Output
is PNG with optional max-drawdown shading.

Input (stdin JSON):
    {
      "title":  "Equity curve, 2026-04-15 - 2026-04-20",     # optional
      "trades": [
        {"exit_time": ISO, "pnl_usd": 180.0},
        {"exit_time": ISO, "pnl_usd": -120.0},
        ...
      ]
    }

The caller should sort trades oldest-first, by exit_time. A typical
source is `trade-journal`'s round-trip output.

Usage:
    uv run equity_curve.py --file trades.json --output /tmp/equity.png   # preferred
    echo '<json>' | uv run equity_curve.py --output /tmp/equity.png

`uv run` installs matplotlib from the metadata block above. With
matplotlib already installed, `python3 equity_curve.py` works the same
way.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Optional

LINE_COLOR = "#1e5fb5"
DD_COLOR = "#b11e1e"
ZERO_LINE_COLOR = "#888888"


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render cumulative-P&L equity curve to PNG.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run equity_curve.py --file trades.json "
            "--output /tmp/equity.png\n"
            "  uv run equity_curve.py --file trades.json "
            "--output /tmp/equity.png --shade-drawdown\n"
        ),
    )
    parser.add_argument("--output", required=True, help="Path of the PNG file to write. Required.")
    parser.add_argument(
        "--width", type=float, default=12.0, help="Figure width in inches (default 12.0)."
    )
    parser.add_argument(
        "--height", type=float, default=5.0, help="Figure height in inches (default 5.0)."
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=140,
        help="Output resolution in dots per inch (default 140). Use 100 or more so the "
        "image stays readable in a transcript.",
    )
    parser.add_argument(
        "--shade-drawdown",
        action="store_true",
        help="Shade the underwater region between peak and current equity (default off).",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Read the JSON payload from PATH instead of stdin (default: read stdin).",
    )
    args = parser.parse_args()

    try:
        import matplotlib

        matplotlib.use("Agg")
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

    trades = payload.get("trades") or []
    points: list[tuple[datetime, float]] = []
    cum = 0.0
    for t in trades:
        et = _parse_iso(t.get("exit_time") or "")
        pnl = t.get("pnl_usd")
        if et is None or pnl is None:
            continue
        cum += float(pnl)
        points.append((et, cum))
    if not points:
        print(
            json.dumps({"error": "no trades with parseable exit_time + pnl_usd"}), file=sys.stderr
        )
        return 2

    xs = [mdates.date2num(p[0]) for p in points]
    ys = [p[1] for p in points]

    fig, ax = plt.subplots(figsize=(args.width, args.height), dpi=args.dpi)
    ax.plot(xs, ys, color=LINE_COLOR, linewidth=1.4, marker="o", markersize=3.5, zorder=3)

    # Running-peak drawdown shade
    if args.shade_drawdown:
        peak = ys[0]
        peak_series = []
        for v in ys:
            if v > peak:
                peak = v
            peak_series.append(peak)
        ax.fill_between(
            xs,
            peak_series,
            ys,
            where=[ps > y for ps, y in zip(peak_series, ys)],
            color=DD_COLOR,
            alpha=0.18,
            zorder=1,
            step="post",
        )

    # Zero line
    ax.axhline(0.0, color=ZERO_LINE_COLOR, linewidth=0.8, linestyle="dashed", alpha=0.7, zorder=0)

    # Cosmetics
    title = payload.get("title") or "Equity curve (cumulative P&L)"
    ax.set_title(title, fontsize=11, loc="left")
    ax.set_ylabel("Cumulative P&L ($)", fontsize=9)
    ax.grid(True, axis="y", alpha=0.25, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()

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

    print(
        json.dumps(
            {
                "output": args.output,
                "trades_rendered": len(points),
                "final_pnl_usd": round(ys[-1], 2),
                "peak_pnl_usd": round(max(ys), 2),
                "trough_pnl_usd": round(min(ys), 2),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
