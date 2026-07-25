#!/usr/bin/env python3
"""
assemble_report.py — combine MCP tool outputs into the YAML shape
that the debrief prompt library expects (approximated).

Input (stdin JSON):
    {
      "account_id": "DEMO-ACCOUNT-1",
      "trade_date": "2026-04-20",
      "timeline_report": { ...as returned by timeline_report },
      "performance_summary": { ...performance_summary },
      "trades": [ ...output of compute_derived.py ],
      "contracts": {
        "ESZ6": {
          "product_name": "E-Mini S&P 500",
          "contract_name": "ESZ6",
          "tick_size": 0.25,
          "value_per_point": 50.0,
          "dollar_per_tick": 12.50,
          "is_micro": false
        },
        ...
      },
      "market_context": {           # optional; from `market-context` skill output
        "ESZ6": {
          "market_structure": "trend_up" | "trend_down" | "range",
          "market_volatility": "low" | "normal" | "elevated" | "extreme",
          "session_vwap": 7105.25,
          "atr_points": 8.1
        }
      }
    }

Output (stdout JSON): a single object, ready for serialization to
YAML and for appending to any of the `references/prompts/*.md`
templates.

`references/report-schema.md` documents field provenance. This
script leaves fields it cannot source from MCP as `null` (never
fabricated).

Usage:
    python3 assemble_report.py --file combined_input.json   # preferred
    echo '<input>' | python3 assemble_report.py
"""

import argparse
import json
import sys
from typing import Any

EPILOG = """Examples:
  python3 assemble_report.py --file combined_input.json
  cat combined_input.json | python3 assemble_report.py

Input shape (one JSON object):
  {"account_id": "DEMO-ACCOUNT-1",
   "trade_date": "2026-07-20",
   "timeline_report": {...},          # the timeline_report response
   "performance_summary": {...},      # the performance_summary response
   "trades": [...],                   # the compute_derived.py output
   "contracts": {"ESZ6": {"product_name": ..., "value_per_point": ...}},
   "market_context": {"ESZ6": {...}}} # optional

Output: one JSON object on stdout, ready for YAML serialization."""


def _coerce_date(s: str) -> str:
    # Accept "2026-04-20" or "2026-04-20T00:00:00Z" — return date-only.
    return s.split("T", 1)[0] if s else ""


def _find_stat(stats: list[dict], name: str) -> Any:
    """Look up one {name, value} stat entry by its name."""
    for entry in stats:
        if entry.get("name") == name:
            return entry.get("value")
    return None


def _parse_stat_number(value: Any) -> float | None:
    """Parse one performance_summary stat value into a float.

    A stat value is a raw number for counts. It is a formatted string for
    money ("$1,234.56") or a percentage ("65.00%"). A duration string
    ("1h 23min") does not parse to a single number, so this returns None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _per_trade_block(trade: dict, contracts: dict, market_ctx: dict) -> dict:
    symbol = trade.get("symbol") or ""
    derived = trade.get("derived") or {}
    contract = contracts.get(symbol) or {}
    ctx = market_ctx.get(symbol) or {}
    return {
        "trade_id": trade.get("trade_id"),
        "contract_id": symbol,
        "direction": trade.get("direction"),
        "qty": trade.get("qty"),
        "entry": {
            "time": trade.get("entry_time"),
            "price": trade.get("entry_price"),
        },
        "exit": {
            "time": trade.get("exit_time"),
            "price": trade.get("exit_price"),
            "realized_R": derived.get("realized_R"),
            "realized_points": derived.get("realized_points"),
            "realized_pnl_dollars": derived.get("realized_dollars"),
        },
        "planned_stop_points": trade.get("planned_stop_points"),
        "mfe_points": derived.get("mfe_points"),
        "mfe_dollars": derived.get("mfe_dollars"),
        "mfe_R": derived.get("mfe_R"),
        "mae_points": derived.get("mae_points"),
        "mae_dollars": derived.get("mae_dollars"),
        "mae_R": derived.get("mae_R"),
        "derived": {
            "giveback_from_mfe_pct": derived.get("giveback_from_mfe_pct"),
            "realized_vs_mfe_pct": derived.get("realized_vs_mfe_pct"),
            # Fields the prompt library expects but MCP does not source today:
            "scale_out_count": None,
            "stop_modified_count": None,
        },
        # Minute-by-minute timeline is not reconstructable from MCP today.
        # Leave it null. Tell the prompt not to cite fields that do not exist.
        "timeline": None,
        # Context that IS reconstructable when `market-context` runs first.
        "market_context": {
            "market_structure": ctx.get("market_structure"),
            "market_volatility": ctx.get("market_volatility"),
            "session_vwap": ctx.get("session_vwap"),
            "atr_points": ctx.get("atr_points"),
        },
        # Contract metadata the prompts reference.
        "contract_meta": {
            "product_name": contract.get("product_name"),
            "contract_name": contract.get("contract_name") or symbol,
            "tick_size": contract.get("tick_size"),
            "value_per_point": contract.get("value_per_point"),
            "dollar_per_tick": contract.get("dollar_per_tick"),
            "is_micro": contract.get("is_micro"),
        },
    }


def _summary_block(perf: dict, trades: list[dict]) -> dict:
    # Compute locally from derived dollars, but prefer MCP's
    # performance_summary as the authoritative source when present.
    # Some trades have a null realized_dollars, when vpp is missing.
    # These trades drop out of the local aggregate. Flag that in
    # trades_missing_pnl, so the caller can see the recomputed totals
    # are not comprehensive.
    trades_with_pnl: list[float] = []
    trades_missing_pnl = 0
    for t in trades:
        rd = (t.get("derived") or {}).get("realized_dollars")
        if rd is None:
            trades_missing_pnl += 1
        else:
            trades_with_pnl.append(rd)

    n_trades = len(trades)
    n_with_pnl = len(trades_with_pnl)
    total = round(sum(trades_with_pnl), 2) if trades_with_pnl else 0.0
    winners = sum(1 for x in trades_with_pnl if x > 0)
    losers = sum(1 for x in trades_with_pnl if x < 0)
    win_rate = round(winners / n_with_pnl, 4) if n_with_pnl else None

    extra = perf.get("extra") or {}
    all_stats = extra.get("allTradeStats") or []
    loss_stats = extra.get("lossTradeStats") or []

    return {
        "trades_count": n_trades,
        "winners": winners,
        "losers": losers,
        "win_rate": win_rate,
        "total_pnl_dollars": total if n_with_pnl == n_trades else None,
        "trades_missing_pnl": trades_missing_pnl,
        # Derived from performance_summary's {name, value} stat arrays —
        # not a verbatim passthrough. performance_summary has no flat
        # netPnL/winRate/profitFactor/maxDrawdown fields.
        "mcp_reported": {
            "net_pnl": _parse_stat_number(_find_stat(all_stats, "Total P/L")),
            "gross_profit": _parse_stat_number(_find_stat(all_stats, "Gross Profit")),
            "win_rate_pct": _parse_stat_number(_find_stat(all_stats, "% Profitable Trades")),
            "max_drawdown": _parse_stat_number(_find_stat(loss_stats, "Max Drawdown")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combine MCP tool outputs into the assembled debrief report shape.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
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

    trades_in: list[dict] = payload.get("trades") or []
    contracts: dict = payload.get("contracts") or {}
    market_ctx: dict = payload.get("market_context") or {}
    perf: dict = payload.get("performance_summary") or {}
    timeline: Any = payload.get("timeline_report")

    trades_out = [_per_trade_block(t, contracts, market_ctx) for t in trades_in]

    report = {
        "schema_version": 1,
        "source": "tradovate-mcp+mcp-skills",
        "account_id": payload.get("account_id"),
        "trade_date": _coerce_date(payload.get("trade_date") or ""),
        "contracts": contracts,
        "summary": _summary_block(perf, trades_in),
        "trades": trades_out,
        "raw_timeline_report": timeline,
    }
    print(json.dumps(report, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
