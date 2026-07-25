#!/usr/bin/env python3
"""
streaks.py — post-trade journal analytics over fill history.

Takes a `fill_history` response on stdin, pairs fills into round-trip
trades per symbol via running-position matching (FIFO), and reports:

  - trades             : count of completed round-trips
  - winners / losers   : by $ P&L sign
  - win_rate           : winners / trades
  - total_pnl_usd      : sum of round-trip P&L in USD
  - avg_pnl_usd        : mean per-trade P&L
  - avg_hold_minutes_{winners, losers}
  - streaks            : longest winning / losing run; current streak
  - by_symbol          : same stats, grouped by symbol
  - by_hour            : P&L + count, bucketed by entry hour of day (UTC)

Input (stdin JSON) — the raw `fill_history` response, in either format
the tool can return:

    {
      "items": [
        {"symbol": "ESZ6", "timestamp": "...", "action": "Buy"|"Sell",
         "quantity": 2, "price": 7150.25, ...},
        ...
      ]
    }

    {
      "columns": ["symbol", "timestamp", "action", "quantity", "price", ...],
      "rows": [
        ["ESZ6", "...", "Buy", 2, 7150.25, ...],
        ...
      ]
    }

The second shape is `fill_history(format="columns")` — the compact form
this skill recommends for result sets over 50 fills (see SKILL.md and
`describe(topic='response_format')`). Both shapes normalize to the same
fill list before pairing; see `_fills_from_payload`.

On the open side, P&L math uses position-weighted-average cost. On
the close side, it uses the fill price. Sign convention: long P&L =
exit − entry, short P&L = entry − exit. `fill_history` has no
commission/fee field, so all P&L here is gross.

Requires `--value-per-point` as a flat multiplier, applied per
symbol. This is a simplification. A mixed-symbol session should pass
the smallest common denominator. The script then reports per-symbol
results separately, so the user can eyeball the mix. For accurate
per-symbol dollar math across a mixed session, pass
`--value-per-point-map ES:50 MES:5 NQ:20 ...`.

Usage:
    python3 streaks.py --file fill_history.json --value-per-point 50   # preferred
    echo '<fill_history_json>' | python3 streaks.py \\
        --value-per-point 50
    echo '<fill_history_json>' | python3 streaks.py \\
        --value-per-point-map ES:50 MES:5 NQ:20 MNQ:2
"""

import argparse
import json
import sys
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

EPILOG = """Examples:
  python3 streaks.py --file fill_history.json --value-per-point 50
  python3 streaks.py --file fill_history.json \\
      --value-per-point-map ES:50 MES:5 NQ:20 MNQ:2
  cat fill_history.json | python3 streaks.py --value-per-point 50

Input shape (one JSON object): the raw fill_history response, in either
format the tool returns.
  {"items": [{"symbol": "ESZ6", "timestamp": ..., "action": "Buy",
              "quantity": 2, "price": 7150.25}]}
  {"columns": ["symbol", "timestamp", "action", "quantity", "price"],
   "rows": [["ESZ6", ..., "Buy", 2, 7150.25]]}

Output: one JSON object on stdout with overall, by_symbol, and
by_hour_utc blocks."""


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _product_root(symbol: str) -> str:
    """Reduce a dated contract symbol to its product code.

    `NGU6` becomes `NG`, and `M6EU6` becomes `M6E`. A bare product code
    keeps every letter: `MNQ`, `NG`, `MYM`, `M2K`, `HG` and `MNG` all
    end in a letter that is also a month letter. So strip the month
    letter only when a year digit followed it. Without that guard,
    `MNQ` becomes `MN`, the value-per-point lookup misses, and the
    fallback reports raw points as dollars.
    """
    stripped = symbol.rstrip("0123456789")
    year_digits_removed = stripped != symbol
    if year_digits_removed and stripped and stripped[-1] in "FGHJKMNQUVXZ":
        stripped = stripped[:-1]
    return stripped


def _fills_from_payload(payload: dict) -> list[dict]:
    """Extract the fill list from a `fill_history` response, in either
    response format the tool can return: `items` (the default) or
    `columns`/`rows` (`format="columns"`, recommended for large result
    sets — see SKILL.md and `describe(topic='response_format')`).

    A columnar response has no `items` key. Reading `items` alone
    silently returns zero fills for a valid columnar payload instead of
    raising or reporting the mismatch. This function normalizes both
    shapes into the same list-of-dict form so the rest of the script
    stays format-agnostic.
    """
    items = payload.get("items")
    if items is not None:
        return items
    columns = payload.get("columns")
    rows = payload.get("rows")
    if columns is not None and rows is not None:
        return [dict(zip(columns, row)) for row in rows]
    return []


def _pair_roundtrips(fills: list[dict]) -> list[dict]:
    """FIFO-match fills into completed round-trip trades per symbol."""
    by_symbol: dict[str, deque] = defaultdict(deque)
    trades: list[dict] = []

    for f in fills:
        sym = f.get("symbol") or ""
        action = (f.get("action") or "").lower()
        qty = f.get("quantity")
        price = f.get("price")
        ts = _parse_iso(f.get("timestamp") or "")
        if not sym or action not in ("buy", "sell") or qty is None or price is None or ts is None:
            continue

        signed_qty = qty if action == "buy" else -qty
        queue = by_symbol[sym]

        # Match against opposing-side opens (FIFO).
        remaining = signed_qty
        while queue and remaining != 0 and (queue[0]["signed_qty"] * remaining) < 0:
            head = queue[0]
            match_qty = min(abs(head["signed_qty"]), abs(remaining))
            # open was long (signed_qty > 0) → close is sell → P&L = exit - entry
            # open was short → close is buy → P&L = entry - exit
            if head["signed_qty"] > 0:
                pnl_points = price - head["price"]
            else:
                pnl_points = head["price"] - price
            trades.append(
                {
                    "symbol": sym,
                    "entry_time": head["timestamp"],
                    "exit_time": ts,
                    "qty": match_qty,
                    "entry_price": head["price"],
                    "exit_price": price,
                    "pnl_points": pnl_points,
                }
            )
            # consume
            if abs(head["signed_qty"]) == match_qty:
                queue.popleft()
            else:
                sign = 1 if head["signed_qty"] > 0 else -1
                head["signed_qty"] = sign * (abs(head["signed_qty"]) - match_qty)
            remaining = (1 if remaining > 0 else -1) * (abs(remaining) - match_qty)

        # Anything left opens a new position fragment.
        if remaining != 0:
            queue.append(
                {
                    "signed_qty": remaining,
                    "price": price,
                    "timestamp": ts,
                }
            )

    return trades


def _streak_stats(pnl_series: list[float]) -> dict:
    if not pnl_series:
        return {"longest_win_streak": 0, "longest_loss_streak": 0, "current_streak": 0}
    longest_win = longest_loss = 0
    run = 0
    run_sign = 0  # +1 winning, -1 losing, 0 flat
    for p in pnl_series:
        sign = 1 if p > 0 else (-1 if p < 0 else 0)
        if sign == run_sign and sign != 0:
            run += 1
        else:
            run = 1 if sign != 0 else 0
            run_sign = sign
        if sign == 1 and run > longest_win:
            longest_win = run
        if sign == -1 and run > longest_loss:
            longest_loss = run
    current = run * run_sign
    return {
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "current_streak": current,
    }


def _summarize(trades: list[dict], vpp_for: callable) -> dict:
    if not trades:
        return {"trades": 0}

    pnl_usd: list[float] = []
    hold_winners: list[float] = []
    hold_losers: list[float] = []

    for t in trades:
        vpp = vpp_for(t["symbol"])
        # fill_history has no commission/fee field, so this P&L is gross.
        gross = t["pnl_points"] * vpp * t["qty"]
        t["pnl_usd"] = round(gross, 2)
        pnl_usd.append(gross)
        hold_min = (t["exit_time"] - t["entry_time"]).total_seconds() / 60.0
        t["hold_minutes"] = round(hold_min, 2)
        if gross > 0:
            hold_winners.append(hold_min)
        elif gross < 0:
            hold_losers.append(hold_min)

    winners = sum(1 for p in pnl_usd if p > 0)
    losers = sum(1 for p in pnl_usd if p < 0)

    def _avg(xs: list[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "trades": len(trades),
        "winners": winners,
        "losers": losers,
        "win_rate": round(winners / len(trades), 4),
        "total_pnl_usd": round(sum(pnl_usd), 2),
        "avg_pnl_usd": _avg(pnl_usd),
        "avg_hold_minutes_winners": _avg(hold_winners),
        "avg_hold_minutes_losers": _avg(hold_losers),
        **_streak_stats(pnl_usd),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post-trade TCA from fill_history.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--value-per-point",
        type=float,
        default=None,
        help=(
            "Dollar value of one point, applied to every symbol. Use it for a "
            "single-product session. Default: none, which reports raw points "
            "(a multiplier of 1.0)."
        ),
    )
    parser.add_argument(
        "--value-per-point-map",
        nargs="*",
        default=[],
        metavar="ROOT:VALUE",
        help=(
            "Dollar value of one point per product root, as ROOT:VALUE pairs "
            "(for example, ES:50 MES:5 NQ:20). Use it for a mixed-product "
            "session. Default: empty."
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

    vpp_map: dict[str, float] = {}
    for entry in args.value_per_point_map:
        if ":" not in entry:
            print(
                json.dumps(
                    {
                        "error": f"bad --value-per-point-map entry {entry!r}: "
                        "expected ROOT:VALUE, for example ES:50"
                    }
                ),
                file=sys.stderr,
            )
            return 2
        root, v = entry.split(":", 1)
        try:
            vpp_map[root.strip().upper()] = float(v)
        except ValueError:
            print(
                json.dumps(
                    {
                        "error": f"non-numeric VPP in {entry!r}: "
                        "expected ROOT:VALUE with a number, for example ES:50"
                    }
                ),
                file=sys.stderr,
            )
            return 2

    def _vpp_for(sym: str) -> float:
        root = _product_root(sym.upper())
        if root in vpp_map:
            return vpp_map[root]
        if args.value_per_point is not None:
            return args.value_per_point
        return 1.0  # raw points if nothing provided

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

    fills = _fills_from_payload(payload)
    trades = _pair_roundtrips(fills)
    overall = _summarize(trades, _vpp_for)

    # By symbol
    by_sym_buckets: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_sym_buckets[t["symbol"]].append(t)
    by_symbol = {sym: _summarize(ts, _vpp_for) for sym, ts in by_sym_buckets.items()}

    # By entry hour
    by_hour_buckets: dict[int, list[dict]] = defaultdict(list)
    for t in trades:
        hour = t["entry_time"].astimezone().hour
        by_hour_buckets[hour].append(t)
    by_hour = {
        f"{h:02d}": {
            "trades": len(ts),
            "pnl_usd": round(sum(x["pnl_usd"] for x in ts), 2),
        }
        for h, ts in sorted(by_hour_buckets.items())
    }

    result = {
        "overall": overall,
        "by_symbol": by_symbol,
        "by_hour_utc": by_hour,
    }
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
