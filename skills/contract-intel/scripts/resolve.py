#!/usr/bin/env python3
"""
resolve.py — bare product code -> front-month contract symbol by OI ranking.

When the user says "buy ES" or "what's NQ doing", the right actual
contract to trade is the most-liquid maturity — usually the nearest
expiration, but once rollover starts the next maturity can take over.
This script reads a `market_snapshot` response for a product (all
maturities at once) and returns the front-month plus the next-month
pair for context.

Input: JSON on stdin — the `market_snapshot` tool response when called
with `product: "<code>"`. Shape:

    {
      "snapshots": [
        {"symbol": "ESU6", "openInterest": 2100000, "expirationDate": "2026-09-18", ...},
        {"symbol": "ESU6", "openInterest":   35000, "expirationDate": "2026-09-18", ...},
        ...
      ]
    }

Output:
    {
      "front_month": {"symbol": "ESU6", "open_interest": 2100000,
                      "expiration_date": "2026-06-19", "days_to_expiry": 45},
      "next_month":  {"symbol": "ESU6", "open_interest":   35000,
                      "expiration_date": "2026-09-18", "days_to_expiry": 136},
      "oi_ratio": 68.57,                # front / next, for rollover awareness
      "rolled_already": false           # true when next_oi > front_oi
    }

Note: `oi_ratio` is front-over-next. A very high value means the
rollover is not yet active. Use `rollover.py` for the full rollover
narrative.

Usage:
    python3 resolve.py --file market_snapshot.json   # preferred
    market_snapshot(product="ES") | python3 resolve.py
"""

import argparse
import json
import sys
from datetime import date


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    # Handle either "YYYY-MM-DD" or full ISO "YYYY-MM-DDTHH:MM:SSZ"
    try:
        return date.fromisoformat(s.split("T")[0])
    except (ValueError, AttributeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a bare product code to the front-month contract."
    )
    parser.add_argument(
        "--file", metavar="PATH", help="Read the JSON payload from PATH instead of stdin."
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

    snapshots = payload.get("snapshots") or []
    today = date.today()

    # Build a list of (snapshot, expiration_date, days_to_expiry). Drop any
    # snapshot that lacks either field.
    enriched: list[tuple[dict, date, int]] = []
    for s in snapshots:
        exp = _parse_iso_date(s.get("expirationDate"))
        if exp is None:
            continue
        days = (exp - today).days
        if days < 0:
            continue  # expired
        enriched.append((s, exp, days))

    if not enriched:
        print(
            json.dumps(
                {
                    "error": "no non-expired snapshots with expirationDate — check the market_snapshot response"
                }
            ),
            file=sys.stderr,
        )
        return 2

    # Sort by expiration ascending (nearest first)
    enriched.sort(key=lambda t: t[1])

    # Front = highest OI among the nearest two. This handles mid-rollover,
    # when the next maturity overtakes the front.
    candidates = enriched[:2] if len(enriched) >= 2 else enriched
    by_oi = sorted(candidates, key=lambda t: t[0].get("openInterest") or 0, reverse=True)
    front_snap, front_exp, front_days = by_oi[0]

    # Next = the maturity immediately after the chosen front (by expiration date)
    next_candidates = [t for t in enriched if t[1] > front_exp]
    next_info: dict | None = None
    if next_candidates:
        next_snap, next_exp, next_days = next_candidates[0]
        next_info = {
            "symbol": next_snap.get("symbol"),
            "open_interest": next_snap.get("openInterest"),
            "expiration_date": next_exp.isoformat(),
            "days_to_expiry": next_days,
        }

    front_oi = front_snap.get("openInterest") or 0
    # Check whether rollover already completed: next-by-date has more OI
    # than the chosen front.
    rolled_already = False
    if len(enriched) >= 2:
        nearest_snap, _, _ = enriched[0]
        second_snap, _, _ = enriched[1]
        nearest_oi = nearest_snap.get("openInterest") or 0
        second_oi = second_snap.get("openInterest") or 0
        if second_oi > nearest_oi:
            rolled_already = True

    oi_ratio: float | None = None
    if next_info and next_info["open_interest"]:
        next_oi = next_info["open_interest"]
        if next_oi > 0:
            oi_ratio = round(front_oi / next_oi, 3)

    result = {
        "front_month": {
            "symbol": front_snap.get("symbol"),
            "open_interest": front_oi,
            "expiration_date": front_exp.isoformat(),
            "days_to_expiry": front_days,
        },
        "next_month": next_info,
        "oi_ratio": oi_ratio,
        "rolled_already": rolled_already,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
