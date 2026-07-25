#!/usr/bin/env python3
"""
cross_symbol.py — intra-day relative-strength snapshot across related symbols.

Measures how each symbol moved today versus the others. Produces two views:
  (a) per-symbol change from first to latest close in the bar set
  (b) pairwise relative strength — for every pair (A, B), the
      percentage-point spread (%A - %B), so the LLM can spot divergences

This is intra-day only. Historical rolling correlation / beta lives in
the `correlation-hedge` skill, not here.

Usage:
    cross_symbol.py --symbol ES=es.json --symbol NQ=nq.json --symbol RTY=rty.json

Where each `<name>=<path>` pair points to a market_history response JSON file.
Any number of symbols supported; at least two are required for pairwise view.

The three fixtures under `scripts/fixtures/` hold the input for the
example below:

    cross_symbol.py \
      --symbol ES=scripts/fixtures/es_cross_symbol.json \
      --symbol NQ=scripts/fixtures/nq_cross_symbol.json \
      --symbol RTY=scripts/fixtures/rty_cross_symbol.json

Output for that input:
    {
      "per_symbol": {
        "ES":  {"start": 7100.0, "end": 7140.5, "change_pct": 0.57, "bars": 3},
        "NQ":  {"start": 18200.0, "end": 18350.0, "change_pct": 0.824, "bars": 3},
        "RTY": {"start":  2110.0, "end":  2095.0, "change_pct": -0.711, "bars": 3}
      },
      "pairwise_rs": [
        {"pair": "ES/NQ", "spread_pct": -0.254},
        {"pair": "ES/RTY", "spread_pct":  1.281},
        {"pair": "NQ/RTY", "spread_pct":  1.535}
      ]
    }

Every `change_pct` and `spread_pct` value carries three decimal places.

Interpretation:
  spread_pct = (A_change_pct - B_change_pct). Positive means A outperformed B today.
"""

import argparse
import itertools
import json
import sys


def parse_symbol_arg(arg: str) -> tuple[str, str]:
    if "=" not in arg:
        raise ValueError(f"--symbol must be NAME=PATH, got: {arg}")
    name, path = arg.split("=", 1)
    return name.strip(), path.strip()


def first_close(bars: list[dict]) -> float | None:
    for bar in bars:
        if bar.get("close") is not None:
            return bar["close"]
    return None


def last_close(bars: list[dict]) -> float | None:
    for bar in reversed(bars):
        if bar.get("close") is not None:
            return bar["close"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Intra-day relative-strength across N symbols.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  cross_symbol.py --symbol ES=es.json --symbol NQ=nq.json\n"
            "  cross_symbol.py --symbol ES=es.json --symbol NQ=nq.json "
            "--symbol RTY=rty.json\n"
        ),
    )
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="One symbol to compare, as NAME=PATH. NAME is any label, such as ES. "
        "PATH is a market_history JSON file. Repeat the flag once per symbol. "
        "Pass at least two (no default).",
    )
    args = parser.parse_args()

    if len(args.symbol) < 2:
        print(
            json.dumps({"error": "at least two --symbol args required for cross-symbol view"}),
            file=sys.stderr,
        )
        return 2

    per_symbol: dict[str, dict] = {}
    for entry in args.symbol:
        try:
            name, path = parse_symbol_arg(entry)
        except ValueError as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            return 2

        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(json.dumps({"error": f"cannot read {path}: {e}"}), file=sys.stderr)
            return 2

        bars = payload.get("bars") or []
        start = first_close(bars)
        end = last_close(bars)
        if start is None or end is None or start == 0:
            per_symbol[name] = {"error": "insufficient close data"}
            continue
        per_symbol[name] = {
            "start": start,
            "end": end,
            "change_pct": round((end - start) / start * 100.0, 3),
            "bars": len(bars),
        }

    valid_names = [n for n, v in per_symbol.items() if "change_pct" in v]
    pairwise = []
    for a, b in itertools.combinations(valid_names, 2):
        spread = per_symbol[a]["change_pct"] - per_symbol[b]["change_pct"]
        pairwise.append({"pair": f"{a}/{b}", "spread_pct": round(spread, 3)})

    print(json.dumps({"per_symbol": per_symbol, "pairwise_rs": pairwise}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
