#!/usr/bin/env python3
"""
detect.py — behavioral anti-pattern checks on recent trading activity.

Runs 5 deterministic detectors. Each emits a flag object {name, severity,
reason, evidence}. Severity is "low" / "med" / "high" — Claude narrates
appropriately.

Detectors:

  1. revenge_trade       : last trade was a loss AND time-since-close
                           < --revenge-window-min (default 5min).
  2. losing_streak       : last N trades were all losses (N >= --streak-min,
                           default 3).
  3. overtrade_count     : trades_today >= --overtrade-threshold (default 5).
  4. size_drift          : proposed.qty > median(recent qty) × factor
                           (default 2.0).
  5. hour_edge           : win rate in current hour-of-day (UTC) across
                           recent trades is < --hour-edge-cutoff (default
                           0.40), with >= --hour-edge-min-samples (default 5)
                           trades in that hour.

Input (stdin JSON):
    {
      "now_iso": "2026-04-20T18:30:00Z",   # current time — user asks now
      "proposed": {                         # optional — for size_drift
        "symbol": "ESU6",
        "qty":    4,
        "direction": "long"
      },
      "recent_trades": [
        {
          "entry_time": ISO, "exit_time": ISO,
          "symbol": "ESU6", "qty": 2, "pnl_usd": 240.0,
          ...
        },
        ...
      ]
    }

`recent_trades` is typically the output of trade-journal's streaks.py
(round-trip paired). Trades should be sorted oldest-first by entry_time.

Output (JSON):
    {
      "now": "...",
      "flags": [
        {"name": "revenge_trade", "severity": "high", "reason": "...",
         "evidence": {...}},
        ...
      ],
      "summary": {
        "trades_today": 4,
        "pnl_today_usd": -425.50,
        "current_hour_win_rate": 0.33,
        ...
      }
    }

Empty flags list = no anti-patterns detected. The skill's SKILL.md
routes from here to narrative + (optional) pause recommendation.

Usage:
    python3 detect.py --file trades.json   # preferred
    echo '<json>' | python3 detect.py
    echo '<json>' | python3 detect.py --revenge-window-min 10 --streak-min 4
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _same_day_utc(a: datetime, b: datetime) -> bool:
    return a.date() == b.date()


def _today_trades(now: datetime, trades: list[dict]) -> list[dict]:
    out = []
    for t in trades:
        et = _parse_iso(t.get("entry_time") or "")
        if et and _same_day_utc(et, now):
            out.append(t)
    return out


def _check_revenge(now: datetime, recent: list[dict], window_min: int) -> Optional[dict]:
    if not recent:
        return None
    # recent sorted oldest-first → pick last
    last = recent[-1]
    pnl = last.get("pnl_usd")
    xt = _parse_iso(last.get("exit_time") or "")
    if pnl is None or xt is None or pnl >= 0:
        return None
    elapsed = now - xt
    # Guard against future-dated trades: negative elapsed indicates
    # the last trade's exit is AFTER `now_iso`, which is nonsensical
    # and should not trigger revenge.
    if elapsed < timedelta(0):
        return None
    if elapsed <= timedelta(minutes=window_min):
        return {
            "name": "revenge_trade",
            "severity": "high",
            "reason": f"Proposing a new trade {int(elapsed.total_seconds() / 60)}min after a losing trade closed for ${pnl:.2f}.",
            "evidence": {
                "last_trade_pnl_usd": pnl,
                "last_trade_exit_time": last.get("exit_time"),
                "minutes_since_exit": round(elapsed.total_seconds() / 60, 1),
                "revenge_window_min": window_min,
            },
        }
    return None


def _check_losing_streak(recent: list[dict], streak_min: int) -> Optional[dict]:
    if len(recent) < streak_min:
        return None
    tail = recent[-streak_min:]
    pnls = [t.get("pnl_usd") for t in tail]
    if any(p is None for p in pnls):
        return None
    if all(p < 0 for p in pnls):
        return {
            "name": "losing_streak",
            "severity": "high",
            "reason": f"Last {streak_min} trades were all losers.",
            "evidence": {
                "streak_len": streak_min,
                "pnls": [round(p, 2) for p in pnls],
                "total_pnl_usd": round(sum(pnls), 2),
            },
        }
    return None


def _check_overtrade(today: list[dict], threshold: int) -> Optional[dict]:
    n = len(today)
    if n >= threshold:
        return {
            "name": "overtrade_count",
            "severity": "med" if n < threshold * 1.5 else "high",
            "reason": f"{n} trades so far today vs soft threshold of {threshold}.",
            "evidence": {"trades_today": n, "threshold": threshold},
        }
    return None


def _check_size_drift(
    proposed: Optional[dict], recent: list[dict], factor: float
) -> Optional[dict]:
    if not proposed:
        return None
    proposed_qty = proposed.get("qty")
    if proposed_qty is None:
        return None
    qtys = [
        t.get("qty") for t in recent if isinstance(t.get("qty"), (int, float)) and t.get("qty") > 0
    ]
    if len(qtys) < 3:
        return None  # not enough baseline
    baseline = statistics.median(qtys)
    if baseline <= 0:
        return None
    if proposed_qty >= baseline * factor:
        return {
            "name": "size_drift",
            "severity": "high" if proposed_qty >= baseline * factor * 1.5 else "med",
            "reason": f"Proposed qty {proposed_qty} is {proposed_qty / baseline:.1f}× your recent median ({baseline}).",
            "evidence": {
                "proposed_qty": proposed_qty,
                "recent_median_qty": baseline,
                "multiple": round(proposed_qty / baseline, 2),
                "factor_threshold": factor,
            },
        }
    return None


def _check_hour_edge(
    now: datetime, recent: list[dict], cutoff: float, min_samples: int
) -> Optional[dict]:
    cur_hour = now.astimezone(timezone.utc).hour
    same_hour = []
    for t in recent:
        et = _parse_iso(t.get("entry_time") or "")
        if et is None:
            continue
        if et.astimezone(timezone.utc).hour == cur_hour:
            same_hour.append(t)
    if len(same_hour) < min_samples:
        return None
    pnls = [t.get("pnl_usd") for t in same_hour if t.get("pnl_usd") is not None]
    if not pnls:
        return None
    winners = sum(1 for p in pnls if p > 0)
    wr = winners / len(pnls)
    if wr < cutoff:
        return {
            "name": "hour_edge",
            "severity": "med",
            "reason": f"Win rate at this hour (UTC {cur_hour:02d}:00) is {wr:.0%} across {len(pnls)} trades — below {cutoff:.0%}.",
            "evidence": {
                "utc_hour": cur_hour,
                "samples": len(pnls),
                "winners": winners,
                "win_rate": round(wr, 4),
                "cutoff": cutoff,
            },
        }
    return None


EPILOG = """\
Examples:
  # Run the bundled synthetic session fixture. Paths are relative to the
  # skill directory.
  python3 scripts/detect.py --file scripts/fixtures/session_synthetic.json

  # Read the payload from stdin, widen the revenge window, and require a
  # 4-trade losing streak.
  cat detect_input.json | python3 scripts/detect.py --revenge-window-min 10 --streak-min 4
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Behavioral anti-pattern detectors.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--revenge-window-min",
        type=int,
        default=5,
        help=(
            "Length of the revenge window after a losing exit. Unit: minutes. "
            "A new trade inside this window raises revenge_trade. Default 5."
        ),
    )
    parser.add_argument(
        "--streak-min",
        type=int,
        default=3,
        help=(
            "Count of consecutive losing trades that raises losing_streak. Unit: trades. Default 3."
        ),
    )
    parser.add_argument(
        "--overtrade-threshold",
        type=int,
        default=5,
        help=(
            "Count of trades today that raises overtrade_count. Unit: trades. "
            "The flag turns high at 1.5 × this value. Default 5."
        ),
    )
    parser.add_argument(
        "--size-drift-factor",
        type=float,
        default=2.0,
        help=(
            "Multiple of the recent median quantity that raises size_drift. "
            "Unit: ratio. The flag turns high at 1.5 × this value. Default 2.0."
        ),
    )
    parser.add_argument(
        "--hour-edge-cutoff",
        type=float,
        default=0.40,
        help=(
            "Win-rate floor for the current UTC hour. Unit: fraction between 0 and 1. "
            "A win rate below this value raises hour_edge. Default 0.40."
        ),
    )
    parser.add_argument(
        "--hour-edge-min-samples",
        type=int,
        default=5,
        help=(
            "Minimum trades in the current UTC hour before hour_edge can fire. "
            "Unit: trades. Below this count the detector stays silent. Default 5."
        ),
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help=(
            "Read the JSON payload from PATH instead of stdin. Unit: filesystem path. "
            "Default: stdin."
        ),
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

    now = _parse_iso(payload.get("now_iso") or "")
    if now is None:
        # Name the accepted formats so the caller can correct the payload
        # from stderr alone.
        print(
            json.dumps(
                {
                    "error": (
                        "missing or unparseable now_iso — supply an ISO 8601 timestamp, "
                        "such as 2026-04-20T18:30:00Z or 2026-04-20T18:30:00+00:00"
                    )
                }
            ),
            file=sys.stderr,
        )
        return 2

    recent = payload.get("recent_trades") or []
    proposed = payload.get("proposed")
    today = _today_trades(now, recent)

    flags: list[dict] = []
    for result in (
        _check_revenge(now, recent, args.revenge_window_min),
        _check_losing_streak(recent, args.streak_min),
        _check_overtrade(today, args.overtrade_threshold),
        _check_size_drift(proposed, recent, args.size_drift_factor),
        _check_hour_edge(now, recent, args.hour_edge_cutoff, args.hour_edge_min_samples),
    ):
        if result is not None:
            flags.append(result)

    pnls_today = [t.get("pnl_usd") for t in today if t.get("pnl_usd") is not None]
    current_hour_trades = [
        t
        for t in recent
        if _parse_iso(t.get("entry_time") or "")
        and _parse_iso(t["entry_time"]).astimezone(timezone.utc).hour
        == now.astimezone(timezone.utc).hour
    ]
    hr_pnls = [t.get("pnl_usd") for t in current_hour_trades if t.get("pnl_usd") is not None]
    hr_wr = round(sum(1 for p in hr_pnls if p > 0) / len(hr_pnls), 4) if hr_pnls else None

    result = {
        "now": payload.get("now_iso"),
        "flags": flags,
        "summary": {
            "trades_today": len(today),
            "pnl_today_usd": round(sum(pnls_today), 2) if pnls_today else 0.0,
            "current_hour_utc": now.astimezone(timezone.utc).hour,
            "current_hour_samples": len(hr_pnls),
            "current_hour_win_rate": hr_wr,
        },
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
