#!/usr/bin/env python3
"""
rollover.py — classify a product's rollover status from market_snapshot.

Takes the same input as resolve.py (a `market_snapshot` response with all
maturities for a product) and produces a rollover-status classification
plus narrative fragments.

Classification. The code applies these rules in this order, and the
first match wins:

  1. `rolled` — next_oi > front_oi, at any days_to_expiry. The next
     contract already took over as the liquidity center.

  2. `imminent` — days_to_expiry <= 5, at any open interest. Proximity
     overrides open interest here. The holder must roll or close, so a
     thin next month does not make the deadline go away.

  3. `not_imminent` — days_to_expiry > 15 AND the next month cannot
     absorb a roll. Either the next month holds no open interest, or
     the front holds more than 5x it. The front contract is the clear
     liquidity center.

  4. `imminent` — 5 < days_to_expiry <= 15 AND next_oi >= 0.5 *
     front_oi. Rollover happens now. Liquidity splits between the two
     contracts, so execution can be thinner than usual.

  5. `approaching` — every other case. Either expiration is near, or
     the next month gains open interest early. Watch for rollover.

Input: `market_snapshot` response on stdin, same shape as resolve.py.

Output. This example is the real output of the command in the Usage
section below:
    {
      "product": "ES",                     # inferred from the most-common symbol root
      "status": "imminent",
      "days_to_expiry": 3,
      "front": {"symbol": "ESU6", "oi": 1600000, "expiration": "2026-09-18"},
      "next":  {"symbol": "ESZ6", "oi": 1400000, "expiration": "2026-12-18"},
      "oi_ratio_front_over_next": 1.143,
      "calendar_spread_candidate": true,   # true when 0.3 < ratio < 3 during imminent/approaching
      "narrative": "ES rollover is due — ESU6 (1,600,000 OI) expires in 3 days. Roll to ESZ6 (1,400,000 OI, 94 days) or close the position before expiration."
    }

The `calendar_spread_candidate` flag is a simple heuristic. A tradeable
spread needs enough liquidity on both legs. That condition holds during
the rollover window, when neither contract dominates.

Usage:
    python3 rollover.py --file market_snapshot.json   # preferred
    market_snapshot(product="ES") | python3 rollover.py

    # Pin the reference date, so a fixture always returns one state:
    python3 rollover.py --file fixtures/es_rollover_imminent.json --today 2026-09-15
"""

import argparse
import json
import sys
from datetime import date

# CME month codes used to infer a product root from a symbol
_MONTH_CODES = "FGHJKMNQUVXZ"


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s.split("T")[0])
    except (ValueError, AttributeError):
        return None


def _product_root(symbol: str) -> str:
    """Reduce a dated contract symbol to its product code.

    `ESU6` becomes `ES`, and `M6EU6` becomes `M6E`. A bare product code
    keeps every letter: `MNQ`, `NG`, `MYM`, `M2K`, `HG` and `MNG` all
    end in a letter that is also a month letter. So strip the month
    letter only when a year digit followed it.
    """
    stripped = symbol.rstrip("0123456789")
    year_digits_removed = stripped != symbol
    if year_digits_removed and stripped and stripped[-1] in _MONTH_CODES:
        stripped = stripped[:-1]
    return stripped


def _classify(front_days: int, front_oi: int, next_oi: int) -> str:
    if next_oi > front_oi:
        return "rolled"
    # Proximity dominates open interest. A holder 5 days from expiry must
    # roll or close, however thin the next month is.
    if front_days <= 5:
        return "imminent"
    # A next month at zero open interest cannot absorb a roll, so treat it
    # as the least imminent case instead of dividing by zero.
    if front_days > 15 and (next_oi == 0 or front_oi / next_oi > 5):
        return "not_imminent"
    if front_days > 15:
        # More than 15 days out, but the OI ratio is 5 or less — early rollover
        return "approaching"
    # 5 < days_to_expiry <= 15 from here
    if next_oi >= 0.5 * front_oi:
        return "imminent"
    return "approaching"


def _build_narrative(
    product: str, status: str, front: dict, next_: dict | None, front_days: int, today: date
) -> str:
    if next_ is None:
        return f"{product}: front is {front['symbol']} ({front_days} days to expiry). No next-month contract visible in the snapshot."
    front_oi_fmt = f"{front['oi']:,}"
    next_oi_fmt = f"{next_['oi']:,}"
    next_days = (date.fromisoformat(next_["expiration"]) - today).days
    if status == "rolled":
        return (
            f"{product} has already rolled — {next_['symbol']} ({next_oi_fmt} OI, {next_days} days) "
            f"has overtaken {front['symbol']} ({front_oi_fmt} OI, {front_days} days). "
            f"Trade {next_['symbol']}."
        )
    if status == "imminent":
        if front_days <= 5:
            # Proximity forced the classification. State the deadline and the
            # choice, because open interest alone can still favour the front.
            return (
                f"{product} rollover is due — {front['symbol']} ({front_oi_fmt} OI) "
                f"expires in {front_days} days. "
                f"Roll to {next_['symbol']} ({next_oi_fmt} OI, {next_days} days) "
                f"or close the position before expiration."
            )
        return (
            f"{product} rollover in progress — {front['symbol']} ({front_oi_fmt} OI, {front_days} days) "
            f"vs {next_['symbol']} ({next_oi_fmt} OI, {next_days} days). "
            f"Rollover window; execution may be thinner than usual."
        )
    if status == "approaching":
        return (
            f"{product} rollover approaching — {front['symbol']} still dominant "
            f"({front_oi_fmt} OI, {front_days} days) but {next_['symbol']} "
            f"({next_oi_fmt} OI, {next_days} days) is picking up. "
            f"Prefer {front['symbol']} for now."
        )
    # not_imminent
    return (
        f"{product} liquidity is firmly in {front['symbol']} ({front_oi_fmt} OI, "
        f"{front_days} days to expiry). {next_['symbol']} is {next_oi_fmt} OI."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify rollover status from a market_snapshot response."
    )
    parser.add_argument(
        "--file", metavar="PATH", help="Read the JSON payload from PATH instead of stdin."
    )
    parser.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        help=(
            "Treat this date as today for every days-to-expiry calculation. "
            "Default: the system date. Use it to pin a fixture's answer."
        ),
    )
    args = parser.parse_args()

    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print(
                json.dumps(
                    {"error": f"--today must be an ISO date in YYYY-MM-DD form, got {args.today!r}"}
                ),
                file=sys.stderr,
            )
            return 2
    else:
        today = date.today()

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

    enriched: list[tuple[dict, date, int]] = []
    for s in snapshots:
        exp = _parse_iso_date(s.get("expirationDate"))
        if exp is None:
            continue
        days = (exp - today).days
        if days < 0:
            continue
        enriched.append((s, exp, days))

    if not enriched:
        print(
            json.dumps({"error": "no non-expired snapshots with expirationDate"}), file=sys.stderr
        )
        return 2

    enriched.sort(key=lambda t: t[1])

    # Front / next stay in expiration order. Unlike resolve.py, this
    # script does not reorder by OI. The classification explicitly
    # handles the "rolled" case through OI comparison.
    front_snap, front_exp, front_days = enriched[0]
    front_oi = front_snap.get("openInterest") or 0
    next_info: dict | None = None
    next_oi = 0
    if len(enriched) >= 2:
        next_snap, next_exp, next_days = enriched[1]
        next_oi = next_snap.get("openInterest") or 0
        next_info = {
            "symbol": next_snap.get("symbol"),
            "oi": next_oi,
            "expiration": next_exp.isoformat(),
        }

    status = _classify(front_days, front_oi, next_oi)
    front_info = {
        "symbol": front_snap.get("symbol"),
        "oi": front_oi,
        "expiration": front_exp.isoformat(),
    }

    # Calendar-spread candidate when both legs have meaningful liquidity
    oi_ratio = None
    calendar_spread_candidate = False
    if next_oi > 0:
        oi_ratio = round(front_oi / next_oi, 3)
        if status in ("imminent", "approaching") and 0.3 < oi_ratio < 3:
            calendar_spread_candidate = True

    product = _product_root(front_snap.get("symbol") or "")
    narrative = _build_narrative(product, status, front_info, next_info, front_days, today)

    result = {
        "product": product,
        "status": status,
        "days_to_expiry": front_days,
        "front": front_info,
        "next": next_info,
        "oi_ratio_front_over_next": oi_ratio,
        "calendar_spread_candidate": calendar_spread_candidate,
        "narrative": narrative,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
