#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8"]
# ///
"""
profile_chart.py — horizontal volume-profile histogram, with POC /
VAH / VAL lines. Output is PNG.

Input (stdin JSON):
    {
      "symbol": "ESU6",
      "title":  "ES profile, 2026-04-20 session",     # optional
      "profile": [
        {"price": 7150.0, "volume": 1230},
        {"price": 7151.0, "volume": 890},
        ...
      ],
      "poc":  7158.0,          # optional
      "vah":  7165.0,          # optional (value-area high)
      "val":  7148.0,          # optional (value-area low)
      "price_range": [7140, 7175]  # optional — clip the price axis
    }

Usage:
    uv run profile_chart.py --file profile.json --output /tmp/profile.png   # preferred
    echo '<json>' | uv run profile_chart.py --output /tmp/profile.png

`uv run` installs matplotlib from the metadata block above. With
matplotlib already installed, `python3 profile_chart.py` works the same
way.

Typical source: `market-context`'s `profile.py` output. The caller
reshapes it first.
"""

import argparse
import json
import sys

PROFILE_COLOR = "#4a7fb8"
POC_COLOR = "#b11e1e"
VA_COLOR = "#4a7fb8"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a volume-profile histogram to PNG.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run profile_chart.py --file profile.json "
            "--output /tmp/profile.png\n"
            "  uv run profile_chart.py --file profile.json "
            "--output /tmp/profile.png --height 12\n"
        ),
    )
    parser.add_argument("--output", required=True, help="Path of the PNG file to write. Required.")
    parser.add_argument(
        "--width", type=float, default=8.0, help="Figure width in inches (default 8.0)."
    )
    parser.add_argument(
        "--height", type=float, default=10.0, help="Figure height in inches (default 10.0)."
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

        matplotlib.use("Agg")
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

    profile = payload.get("profile") or []
    rows = [(p["price"], p["volume"]) for p in profile if "price" in p and "volume" in p]
    if not rows:
        print(json.dumps({"error": "empty profile"}), file=sys.stderr)
        return 2

    rows.sort(key=lambda r: r[0])
    prices = [r[0] for r in rows]
    volumes = [r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(args.width, args.height), dpi=args.dpi)

    # Horizontal bars — price on Y, volume on X
    if len(prices) >= 2:
        step = prices[1] - prices[0]
    else:
        step = 1.0
    ax.barh(prices, volumes, height=step * 0.9, color=PROFILE_COLOR, alpha=0.85, edgecolor="none")

    # POC line
    poc = payload.get("poc")
    if poc is not None:
        ax.axhline(poc, color=POC_COLOR, linewidth=1.8, zorder=3)
        ax.annotate(
            f"POC {poc}",
            xy=(max(volumes), poc),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=9,
            color=POC_COLOR,
            verticalalignment="center",
            fontweight="bold",
        )

    # Value-area lines (high/low)
    for val, label in ((payload.get("vah"), "VAH"), (payload.get("val"), "VAL")):
        if val is None:
            continue
        ax.axhline(val, color=VA_COLOR, linewidth=0.8, linestyle="dashed", alpha=0.8, zorder=2)
        ax.annotate(
            f"{label} {val}",
            xy=(max(volumes), val),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=8,
            color=VA_COLOR,
            verticalalignment="center",
        )

    price_range = payload.get("price_range")
    if isinstance(price_range, list) and len(price_range) == 2:
        ax.set_ylim(price_range)

    title = payload.get("title") or f"Volume profile — {payload.get('symbol', '')}".strip(" —")
    ax.set_title(title, fontsize=11, loc="left")
    ax.set_xlabel("Volume", fontsize=9)
    ax.set_ylabel("Price", fontsize=9)
    ax.grid(True, axis="x", alpha=0.25, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

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

    print(json.dumps({"output": args.output, "bins_rendered": len(rows)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
