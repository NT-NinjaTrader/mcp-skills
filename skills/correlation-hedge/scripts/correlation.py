#!/usr/bin/env python3
"""
correlation.py — time-aligned cross-symbol Pearson correlation and
regression beta on log returns.

Input (stdin JSON) — one series per symbol, any interval (the script
takes the intersection of timestamps):

    {
      "series": {
        "ES": [{"timestamp": ISO, "close": 7150.00}, ...],
        "NQ": [{"timestamp": ISO, "close": 22450.00}, ...]
      }
    }

Each series key is a label of your choice. The script echoes it back.
A bare product code such as `ES` keeps the label short. A full contract
symbol such as `ESU6` also works.

The input needs exactly 2 series. The script:
  1. Aligns bars by timestamp (intersection).
  2. Computes log returns: r_t = ln(close_t / close_{t-1}).
  3. Reports Pearson r, sample count, mean + stdev of each series'
     returns, and OLS regression β of series B on series A. Series A
     is the "base" / independent variable — typically the position
     you hold.
  4. Optional rolling window: --window N reports the rolling-r series
     with its mean and stdev. It flags regime tightening (current
     window r > rolling mean + 1σ) or loosening (< mean − 1σ).

Output (JSON):
    {
      "symbols": ["ES", "NQ"],
      "samples": 240,
      "aligned_from": "2026-03-15T13:30:00Z",
      "aligned_to":   "2026-04-20T20:00:00Z",
      "pearson_r":    0.87,
      "beta_B_on_A":  0.93,
      "vol_A":        0.0084,
      "vol_B":        0.0091,
      "rolling": {               # present if --window given
        "window": 30,
        "current_r": 0.91,
        "mean_r":   0.83,
        "stdev_r":  0.06,
        "regime":   "tightening"
      }
    }

Usage:
    python3 correlation.py --file series.json   # preferred
    echo '<json>' | python3 correlation.py
    echo '<json>' | python3 correlation.py --window 30
"""

import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from typing import Optional


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _align(series_a: list[dict], series_b: list[dict]) -> list[tuple[datetime, float, float]]:
    by_ts_a: dict[datetime, float] = {}
    for b in series_a:
        t = _parse_iso(b.get("timestamp") or "")
        c = b.get("close")
        if t is None or c is None:
            continue
        by_ts_a[t] = float(c)
    aligned: list[tuple[datetime, float, float]] = []
    for b in series_b:
        t = _parse_iso(b.get("timestamp") or "")
        c = b.get("close")
        if t is None or c is None or t not in by_ts_a:
            continue
        aligned.append((t, by_ts_a[t], float(c)))
    aligned.sort(key=lambda x: x[0])
    return aligned


def _paired_returns(
    prices_a: list[float], prices_b: list[float]
) -> tuple[list[float], list[float]]:
    """Compute log returns for two aligned price series in lockstep.
    Skip an index where EITHER series has a non-positive or null price.
    This preserves pairwise alignment — otherwise independent filtering
    produces mismatched-length series or, worse, same-length-but-
    misaligned returns that silently corrupt correlation."""
    out_a: list[float] = []
    out_b: list[float] = []
    for i in range(1, len(prices_a)):
        p0a, p1a = prices_a[i - 1], prices_a[i]
        p0b, p1b = prices_b[i - 1], prices_b[i]
        if None in (p0a, p1a, p0b, p1b):
            continue
        if p0a <= 0 or p1a <= 0 or p0b <= 0 or p1b <= 0:
            continue
        out_a.append(math.log(p1a / p0a))
        out_b.append(math.log(p1b / p0b))
    return out_a, out_b


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _ols_beta(xs: list[float], ys: list[float]) -> Optional[float]:
    """OLS slope of y regressed on x. β = Cov(x,y) / Var(x)."""
    if len(xs) < 2:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) - 1)
    var_x = sum((x - mx) ** 2 for x in xs) / (len(xs) - 1)
    if var_x == 0:
        return None
    return cov / var_x


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Time-aligned Pearson r + regression β between two symbols.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  correlation.py --file series.json\n"
            "  correlation.py --file series.json --window 30\n"
        ),
    )
    parser.add_argument(
        "--window",
        type=int,
        help="Rolling-window size, in return samples. Accepted values: any integer from 2 "
        "up to the usable sample count. This flag enables the rolling-r output "
        "(default: no rolling output).",
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

    series = payload.get("series") or {}
    if len(series) != 2:
        print(
            json.dumps({"error": f"exactly 2 series required, got {len(series)}"}), file=sys.stderr
        )
        return 2

    symbols = list(series.keys())
    aligned = _align(series[symbols[0]], series[symbols[1]])
    if len(aligned) < 3:
        print(
            json.dumps(
                {
                    "error": f"fewer than 3 overlapping bars (got {len(aligned)}) — extend the history or check timestamp alignment"
                }
            ),
            file=sys.stderr,
        )
        return 2

    prices_a = [row[1] for row in aligned]
    prices_b = [row[2] for row in aligned]
    returns_a, returns_b = _paired_returns(prices_a, prices_b)

    if len(returns_a) < 2:
        print(
            json.dumps(
                {
                    "error": f"fewer than 2 usable return samples (got {len(returns_a)}) — check for zero/null prices"
                }
            ),
            file=sys.stderr,
        )
        return 2

    r = _pearson(returns_a, returns_b)
    beta = _ols_beta(returns_a, returns_b)
    vol_a = statistics.stdev(returns_a) if len(returns_a) >= 2 else 0.0
    vol_b = statistics.stdev(returns_b) if len(returns_b) >= 2 else 0.0

    out = {
        "symbols": symbols,
        "samples": len(returns_a),
        "aligned_from": aligned[0][0].isoformat().replace("+00:00", "Z"),
        "aligned_to": aligned[-1][0].isoformat().replace("+00:00", "Z"),
        "pearson_r": round(r, 4) if r is not None else None,
        "beta_B_on_A": round(beta, 4) if beta is not None else None,
        "vol_A": round(vol_a, 6),
        "vol_B": round(vol_b, 6),
    }

    if args.window is not None:
        w = args.window
        if w < 2 or w > len(returns_a):
            print(
                json.dumps({"error": f"--window must be in [2, {len(returns_a)}]"}), file=sys.stderr
            )
            return 2
        rolling: list[float] = []
        for i in range(w, len(returns_a) + 1):
            window_r = _pearson(returns_a[i - w : i], returns_b[i - w : i])
            if window_r is not None:
                rolling.append(window_r)
        if not rolling:
            out["rolling"] = {
                "window": w,
                "current_r": None,
                "mean_r": None,
                "stdev_r": None,
                "regime": "insufficient_data",
            }
        else:
            current = rolling[-1]
            mean_r = statistics.fmean(rolling)
            stdev_r = statistics.stdev(rolling) if len(rolling) >= 2 else 0.0
            if stdev_r > 0 and current > mean_r + stdev_r:
                regime = "tightening"
            elif stdev_r > 0 and current < mean_r - stdev_r:
                regime = "loosening"
            else:
                regime = "stable"
            out["rolling"] = {
                "window": w,
                "current_r": round(current, 4),
                "mean_r": round(mean_r, 4),
                "stdev_r": round(stdev_r, 4),
                "regime": regime,
            }

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
