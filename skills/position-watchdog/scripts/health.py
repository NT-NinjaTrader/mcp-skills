#!/usr/bin/env python3
"""
health.py — live health dashboard for currently open positions.

Consumes MCP tool responses (each as a saved JSON file) and produces
a per-position dashboard:

  - Distance to stop: ticks, dollars, and percent-of-daily-loss-budget
  - Distance to target: ticks and R-multiple achieved so far
  - Margin utilization: total used margin as a percent of netLiq
  - Guardrail flags: no stop attached, position added without a bracket,
    correlated exposure that stacks across index futures (ES/NQ/YM/RTY)

MFE/MAE "so far" needs market_history per position, which costs one
extra tool call per symbol. This script does not compute it, so the
dashboard stays fast (no bar data). The `trade-replay` skill covers the
same excursion math for closed trades.

Bracket legs (stop/target price) come from `my_portfolio`'s own
`workingOrders[]` array, not from `order_details`. `order_details` is a
per-orderId event/comment log (`id`, `timestamp`, `description`,
`comments`, `clientApp`) — it carries no price fields at all, so this
script does not read it.

A working order only counts as a position's stop or target when its
`action` opposes the position's direction. A same-side working order
(for example a Buy Stop on a long position) is an add-on entry, not
protection, even though it carries a `stopPrice`. When the server links
an order to a bracket (`bracket.parentId`/`bracket.ocoId`), that linkage
wins over the action/orderType heuristic. When more than one candidate
remains for a leg, this script reports `ambiguous_protection` instead
of guessing — see `_classify_bracket_legs`.

`my_portfolio`'s position entries carry no entry-timestamp field, so
this script does not report time in trade. Use `stop_drift.py` for
whether a stop moved since it was placed — that needs a caller-known
baseline stop price, because `order_history` reports only the current
order state, not prior versions.

Inputs:
  --portfolio        JSON, required — my_portfolio tool response (positions + workingOrders)
  --snapshot         JSON, required — a market_snapshot response that covers every open position's symbol
  --risk-settings    JSON, required — risk_settings tool response for the account

Usage:
    python3 health.py \\
        --portfolio portfolio.json \\
        --snapshot snapshot.json \\
        --risk-settings risk.json

Output (per position in `positions` array):
    {
      "account": "DEMO-ACCOUNT-1",
      "daily_loss_budget": 500.0,
      "margin_utilization_pct": 42.1,
      "positions": [
        {
          "symbol": "ESU6",
          "direction": "long",           # or "short"
          "net_pos": 4,
          "net_price": 7150.0,
          "last_price": 7158.25,
          "value_per_point": 50.0,
          "tick_size": 0.25,
          "open_pl_dollars": 1650.0,

          # Bracket state (null when no stop / target attached)
          "stop_price": 7145.0,
          "target_price": 7162.0,
          "distance_to_stop_ticks": 53,
          "distance_to_stop_dollars": 662.5,
          "distance_to_stop_pct_of_daily_budget": 132.5,
          "distance_to_target_ticks": 15,
          "r_multiple_achieved": 1.65,

          "flags": []
        }
      ],
      "account_flags": ["correlated_long_exposure: ES, NQ"]
    }

The `flags` per position are keyed for reference (see
references/guardrails.md for what each means and how to triage).
"""

import argparse
import json
import sys
from typing import Any

EXAMPLES = """\
Examples:
  # Full dashboard from three saved tool responses.
  python3 health.py --portfolio portfolio.json --snapshot snapshot.json \\
      --risk-settings risk.json

  # Same call against the bundled fixtures.
  python3 health.py --portfolio scripts/fixtures/portfolio.json \\
      --snapshot scripts/fixtures/snapshot.json \\
      --risk-settings scripts/fixtures/risk_settings.json
"""


def _load(path: str) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(json.dumps({"error": f"cannot read {path}: {e}"}))


_STOP_ORDER_TYPES = {"Stop", "StopLimit", "TrailingStop", "TrailingStopLimit"}
_TARGET_ORDER_TYPES = {"Limit"}


def _exit_action(direction: str) -> str | None:
    """The order `action` that closes (not adds to) a position in this direction."""
    if direction == "long":
        return "Sell"
    if direction == "short":
        return "Buy"
    return None


def _classify_bracket_legs(
    working_orders: list[dict], symbol: str, direction: str
) -> tuple[float | None, float | None, list[str]]:
    """Classify a position's protective stop and target from `my_portfolio`'s
    `workingOrders[]`. Returns (stop_price, target_price, flags).

    A same-side working order (for example a Buy Stop on a long position)
    is an add-on entry, not a stop-loss, even though it carries a
    `stopPrice`. So a candidate leg only counts as protection when its
    `action` opposes the position's `direction`.

    `bracket.parentId` (set on a leg the server spawned via an
    `OrderStrategy`) is the strongest signal that an order is a genuine
    bracket leg. When any opposing-action order on this symbol carries
    `bracket` metadata, only those linked orders count — this excludes a
    manually placed, opposing-action order that happens to share the
    stop/limit shape. Without bracket metadata, classification falls back
    to `orderType` plus price-field shape: the stop leg has `stopPrice`
    set and a stop-family `orderType`; the target leg has `price` set,
    `stopPrice` unset, and a `Limit` `orderType`.

    `workingOrders[]` reports current order state only — it carries no
    version history, so this function cannot recover a prior stop price.
    Use `stop_drift.py` for that, with a caller-known baseline.

    If more than one candidate remains for either leg, this function
    reports `ambiguous_protection` rather than guessing — `workingOrders[]`
    gives no further signal to break the tie.
    """
    exit_action = _exit_action(direction)
    if exit_action is None:
        return None, None, []

    same_symbol = [
        o
        for o in working_orders
        if o.get("symbol") == symbol and o.get("ordStatus") in ("Working", "PendingNew")
    ]
    opposing = [o for o in same_symbol if o.get("action") == exit_action]

    # Prefer orders the server has already linked into a bracket strategy.
    linked = [o for o in opposing if o.get("bracket")]
    pool = linked if linked else opposing

    stop_candidates = [
        o
        for o in pool
        if o.get("stopPrice") is not None and o.get("orderType") in _STOP_ORDER_TYPES
    ]
    target_candidates = [
        o
        for o in pool
        if o.get("price") is not None
        and o.get("stopPrice") is None
        and o.get("orderType") in _TARGET_ORDER_TYPES
    ]

    flags: list[str] = []
    stop = target = None
    if len(stop_candidates) == 1:
        stop = stop_candidates[0]["stopPrice"]
    elif len(stop_candidates) > 1:
        flags.append("ambiguous_protection: stop")
    if len(target_candidates) == 1:
        target = target_candidates[0]["price"]
    elif len(target_candidates) > 1:
        flags.append("ambiguous_protection: target")

    return stop, target, flags


def _direction_from_net_pos(net_pos: int) -> str:
    return "long" if net_pos > 0 else "short" if net_pos < 0 else "flat"


def _distance_ticks(p1: float, p2: float, tick_size: float) -> int:
    if tick_size <= 0:
        return 0
    return int(round(abs(p1 - p2) / tick_size))


def _r_multiple(entry: float, stop: float | None, current: float, direction: str) -> float | None:
    """Gained price move as a multiple of the original risk (entry -> stop)."""
    if stop is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    gain = (current - entry) if direction == "long" else (entry - current)
    return round(gain / risk, 3)


def _flags(stop: float | None, classification_flags: list[str]) -> list[str]:
    """A single `my_portfolio` snapshot carries no prior stop price, so this
    function cannot flag a stop that moved against entry. Use `stop_drift.py`
    for that check, with a caller-known baseline stop price.

    `classification_flags` carries `ambiguous_protection` flags from
    `_classify_bracket_legs`. An ambiguous stop is a distinct situation
    from a genuinely missing one, so it suppresses `no_stop_attached`."""
    flags: list[str] = list(classification_flags)
    stop_ambiguous = any(f.startswith("ambiguous_protection: stop") for f in classification_flags)
    if stop is None and not stop_ambiguous:
        flags.append("no_stop_attached")
    return flags


INDEX_PRODUCTS = {"ES", "MES", "NQ", "MNQ", "YM", "MYM", "RTY", "M2K"}
# CME futures month codes — single uppercase letter immediately before the year digits
_MONTH_CODES = "FGHJKMNQUVXZ"


def _product_root(symbol: str) -> str:
    """Extract the product root from a futures contract symbol.

    Convention: <ROOT><MONTH_LETTER><YEAR_DIGITS>, where MONTH_LETTER is one
    of FGHJKMNQUVXZ and YEAR_DIGITS is 1–2 digits.

    A bare product code keeps every letter. `MNQ`, `NG`, `MYM`, `M2K`,
    `HG` and `MNG` all end in a letter that is also a month letter. So
    strip the month letter only when a year digit followed it.

    Examples:
        ESU6  -> ES
        MNQZ6 -> MNQ
        RTYZ25 -> RTY
        MNQ   -> MNQ
        NG    -> NG
    """
    stripped = symbol.rstrip("0123456789")
    year_digits_removed = stripped != symbol
    if year_digits_removed and stripped and stripped[-1] in _MONTH_CODES:
        stripped = stripped[:-1]
    return stripped


def _correlated_index_exposure(positions: list[dict]) -> str | None:
    """Flag if the user is long (or short) more than one index-futures product
    simultaneously. Signals a single big beta bet."""
    long_products: set[str] = set()
    short_products: set[str] = set()
    for pos in positions:
        if pos["net_pos"] == 0:
            continue
        product = _product_root(pos["symbol"])
        if product in INDEX_PRODUCTS:
            (long_products if pos["net_pos"] > 0 else short_products).add(product)
    if len(long_products) > 1:
        return f"correlated_long_exposure: {', '.join(sorted(long_products))}"
    if len(short_products) > 1:
        return f"correlated_short_exposure: {', '.join(sorted(short_products))}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="health.py",
        description="Live position-watchdog health dashboard.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        metavar="PATH",
        help="Path to a saved my_portfolio tool response (JSON). Required, no default. "
        "It supplies positions[] and workingOrders[].",
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        metavar="PATH",
        help="Path to a saved market_snapshot tool response (JSON). Required, no default. "
        "It must cover every open position's symbol.",
    )
    parser.add_argument(
        "--risk-settings",
        required=True,
        metavar="PATH",
        help="Path to a saved risk_settings tool response (JSON). Required, no default. "
        "It supplies the daily-loss budget in account currency.",
    )
    args = parser.parse_args()

    portfolio = _load(args.portfolio)
    snapshot = _load(args.snapshot)
    risk = _load(args.risk_settings)

    # Build a symbol -> snapshot lookup
    snap_by_symbol: dict[str, dict] = {}
    for s in snapshot.get("snapshots", []):
        if s.get("symbol"):
            snap_by_symbol[s["symbol"]] = s

    working_orders: list[dict] = portfolio.get("workingOrders") or []

    # Risk budget fields: dailyLossAutoLiq is absolute (negative -> absolute), plus trailing
    daily_loss_limit = abs(risk.get("dailyLossAutoLiq") or 0)
    total_used_margin = risk.get("totalUsedMargin") or 0
    max_net_liq = risk.get("maxNetLiq") or 0

    out_positions: list[dict] = []
    for pos in portfolio.get("positions", []):
        net_pos = pos.get("netPos") or 0
        if net_pos == 0:
            continue
        symbol = pos.get("symbol") or pos.get("contract") or ""
        snap = snap_by_symbol.get(symbol, {})
        last_price = snap.get("lastPrice")
        tick_size = snap.get("tickSize") or 0.25
        value_per_point = snap.get("valuePerPoint") or 0
        entry = pos.get("netPrice") or 0
        direction = _direction_from_net_pos(net_pos)

        stop, target, bracket_flags = _classify_bracket_legs(working_orders, symbol, direction)

        open_pl = pos.get("openPnL") or 0

        entry_dict: dict[str, Any] = {
            "symbol": symbol,
            "direction": direction,
            "net_pos": net_pos,
            "net_price": entry,
            "last_price": last_price,
            "value_per_point": value_per_point,
            "tick_size": tick_size,
            "open_pl_dollars": open_pl,
            "stop_price": stop,
            "target_price": target,
        }

        if stop is not None and last_price is not None:
            ticks = _distance_ticks(last_price, stop, tick_size)
            dist_dollars = ticks * tick_size * value_per_point * abs(net_pos)
            entry_dict["distance_to_stop_ticks"] = ticks
            entry_dict["distance_to_stop_dollars"] = round(dist_dollars, 2)
            if daily_loss_limit > 0:
                entry_dict["distance_to_stop_pct_of_daily_budget"] = round(
                    100.0 * dist_dollars / daily_loss_limit, 2
                )

        if target is not None and last_price is not None:
            t_ticks = _distance_ticks(last_price, target, tick_size)
            entry_dict["distance_to_target_ticks"] = t_ticks

        r = _r_multiple(entry, stop, last_price or entry, direction)
        if r is not None:
            entry_dict["r_multiple_achieved"] = r

        entry_dict["flags"] = _flags(stop, bracket_flags)
        if stop is None and target is None and net_pos != 0:
            # Add the "no bracket attached at all" variant. Skip it when
            # either leg is ambiguous: an ambiguous leg means protection
            # may still exist, just with more than one candidate order —
            # a different (and less severe) case than none at all.
            has_ambiguity = any(f.startswith("ambiguous_protection") for f in entry_dict["flags"])
            if "no_stop_attached" not in entry_dict["flags"] and not has_ambiguity:
                entry_dict["flags"].append("no_bracket_attached")

        out_positions.append(entry_dict)

    # Account-level flags
    account_flags: list[str] = []
    corr = _correlated_index_exposure(out_positions)
    if corr:
        account_flags.append(corr)

    margin_util_pct = None
    if max_net_liq > 0:
        margin_util_pct = round(100.0 * total_used_margin / max_net_liq, 2)
        if margin_util_pct > 80:
            account_flags.append(f"high_margin_utilization: {margin_util_pct}%")

    result = {
        "account": risk.get("account"),
        "daily_loss_budget": daily_loss_limit if daily_loss_limit > 0 else None,
        "margin_utilization_pct": margin_util_pct,
        "positions": out_positions,
        "account_flags": account_flags,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
