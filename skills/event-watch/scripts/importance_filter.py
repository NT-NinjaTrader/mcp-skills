#!/usr/bin/env python3
"""
importance_filter.py — filter an economic_calendar response to just the
events relevant to the user's current positions AND high-importance.

Two filters applied:

  (1) importance >= --min-importance (default 3 — the upstream API uses
      1–5 where 3+ is typically considered high-impact).
  (2) eventName maps to at least one product family from --products, or
      --products is empty (return every high-importance event).

The product-to-event-keyword mapping is coarse-grained.
`references/event-playbooks.md` covers it in more detail. This script
just routes by substring match on a canonical map.

Input (stdin JSON) — the raw `economic_calendar` response:
    {
      "data": [
        {"date": "2026-04-19T12:30:00Z", "eventName": "CPI (Apr)",
         "importance": 4, "actual": ..., "consensus": ..., "prior": ...},
        ...
      ],
      "hasMore": false
    }

Usage:
    python3 importance_filter.py --file economic_calendar.json \\
        --products ES MNQ CL --min-importance 3   # preferred
    echo '<economic_calendar_json>' | python3 importance_filter.py \\
        --products ES MNQ CL --min-importance 3

Output:
    {
      "kept": 4,
      "dropped_by_importance": 12,
      "dropped_by_relevance": 8,
      "events": [
        {"timestamp": "2026-04-19T12:30:00Z", "name": "CPI (Apr)",
         "importance": 4, "matched_product_groups": ["equity_indexes", "bonds"],
         "actual": ..., "consensus": ..., "prior": ...},
        ...
      ]
    }

Product group relevance map is intentionally coarse:
    equity_indexes : ES, MES, NQ, MNQ, YM, MYM, RTY, M2K
    bonds          : ZB, ZN, ZF, ZT, UB
    energy         : CL, MCL, NG, MNG, RB, HO
    metals         : GC, MGC, SI, SIL, HG
    currency_eur   : 6E, M6E
    currency_gbp   : 6B, M6B
    currency_jpy   : 6J, M6J
    currency_aud   : 6A, M6A
    grains         : ZC, ZS, ZW, ZM, ZL

The reverse of the map turns a position product into the groups it belongs to.
"""

import argparse
import json
import sys

# Canonical product -> group
_PRODUCT_GROUPS: dict[str, set[str]] = {
    # equity_indexes
    "ES": {"equity_indexes"},
    "MES": {"equity_indexes"},
    "NQ": {"equity_indexes"},
    "MNQ": {"equity_indexes"},
    "YM": {"equity_indexes"},
    "MYM": {"equity_indexes"},
    "RTY": {"equity_indexes"},
    "M2K": {"equity_indexes"},
    # bonds
    "ZB": {"bonds"},
    "ZN": {"bonds"},
    "ZF": {"bonds"},
    "ZT": {"bonds"},
    "UB": {"bonds"},
    # energy
    "CL": {"energy"},
    "MCL": {"energy"},
    "NG": {"energy"},
    "MNG": {"energy"},
    "RB": {"energy"},
    "HO": {"energy"},
    # metals
    "GC": {"metals"},
    "MGC": {"metals"},
    "SI": {"metals"},
    "SIL": {"metals"},
    "HG": {"metals"},
    # currencies
    "6E": {"currency_eur"},
    "M6E": {"currency_eur"},
    "6B": {"currency_gbp"},
    "M6B": {"currency_gbp"},
    "6J": {"currency_jpy"},
    "M6J": {"currency_jpy"},
    "6A": {"currency_aud"},
    "M6A": {"currency_aud"},
    # grains
    "ZC": {"grains"},
    "ZS": {"grains"},
    "ZW": {"grains"},
    "ZM": {"grains"},
    "ZL": {"grains"},
}

# Event-name keyword -> the product groups it moves. Lowercase substring match.
_EVENT_KEYWORD_GROUPS: list[tuple[str, set[str]]] = [
    # US macro — moves equity_indexes + bonds together
    ("cpi", {"equity_indexes", "bonds"}),
    ("pce", {"equity_indexes", "bonds"}),
    ("nonfarm", {"equity_indexes", "bonds"}),
    ("nfp", {"equity_indexes", "bonds"}),
    ("unemployment", {"equity_indexes", "bonds"}),
    ("retail sales", {"equity_indexes", "bonds"}),
    ("gdp", {"equity_indexes", "bonds"}),
    ("ism", {"equity_indexes", "bonds"}),
    ("fomc", {"equity_indexes", "bonds", "metals"}),
    ("fed", {"equity_indexes", "bonds", "metals"}),
    ("interest rate", {"equity_indexes", "bonds"}),
    ("pmi", {"equity_indexes", "bonds"}),
    ("durable", {"equity_indexes", "bonds"}),
    ("adp", {"equity_indexes", "bonds"}),
    ("ppi", {"equity_indexes", "bonds"}),
    ("consumer conf", {"equity_indexes"}),
    ("sentiment", {"equity_indexes"}),  # e.g. Michigan consumer sentiment
    ("jobless", {"equity_indexes", "bonds"}),
    # Energy
    ("crude oil inv", {"energy"}),
    ("eia", {"energy"}),
    ("gasoline inv", {"energy"}),
    ("natural gas stor", {"energy"}),
    ("opec", {"energy"}),
    # Europe
    ("ecb", {"currency_eur", "bonds"}),
    ("eurozone cpi", {"currency_eur", "bonds"}),
    ("german cpi", {"currency_eur"}),
    # UK
    ("boe", {"currency_gbp"}),
    ("uk cpi", {"currency_gbp"}),
    # Japan
    ("boj", {"currency_jpy"}),
    ("japan cpi", {"currency_jpy"}),
    # Metals-specific
    ("gold", {"metals"}),
]


def _groups_for_event(name: str) -> set[str]:
    nl = name.lower()
    groups: set[str] = set()
    for keyword, group_set in _EVENT_KEYWORD_GROUPS:
        if keyword in nl:
            groups.update(group_set)
    return groups


def _product_root(symbol: str) -> str:
    """Reduce a dated contract symbol to its product code.

    `NGU6` becomes `NG`, and `M6EU6` becomes `M6E`. A bare product code
    keeps every letter: `MNQ`, `NG`, `MYM`, and `M2K` all end in a
    letter that is also a month letter, so strip the month letter only
    when a year digit followed it.
    """
    stripped = symbol.rstrip("0123456789")
    year_digits_removed = stripped != symbol
    if year_digits_removed and stripped and stripped[-1] in "FGHJKMNQUVXZ":
        stripped = stripped[:-1]
    return stripped


def main() -> int:
    accepted_products = ", ".join(sorted(_PRODUCT_GROUPS))
    parser = argparse.ArgumentParser(
        description="Filter economic_calendar by importance and product relevance.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 importance_filter.py --file economic_calendar.json "
            "--products ES MNQ CL --min-importance 3\n"
            "  python3 importance_filter.py --file economic_calendar.json --min-importance 5\n"
            "  cat economic_calendar.json | python3 importance_filter.py --products NGU6\n"
            "\n"
            f"Accepted --products codes: {accepted_products}\n"
            "\n"
            "Exit codes: 0 = success, 2 = bad input."
        ),
    )
    parser.add_argument(
        "--products",
        nargs="*",
        metavar="CODE",
        default=[],
        help=(
            "Product codes the user holds, as a space-separated list. "
            "A dated symbol such as NGU6 reduces to its product code. "
            f"Accepted codes: {accepted_products}. "
            "Default: empty, which keeps every event at or above --min-importance."
        ),
    )
    parser.add_argument(
        "--min-importance",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=3,
        metavar="{1,2,3,4,5}",
        help=(
            "Lowest importance score to keep, on the upstream 1-to-5 scale. "
            "A score of 3 or more is high impact. Default: 3."
        ),
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help=("Path to the economic_calendar JSON payload. Default: read the payload from stdin."),
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

    # Normalize user products to root codes, then collect exposed groups.
    # An unknown code would match no event, so every event would drop by
    # relevance. Fail early and name the accepted codes instead.
    user_groups: set[str] = set()
    unknown_products: list[str] = []
    for raw in args.products:
        root = _product_root(raw.strip().upper())
        groups = _PRODUCT_GROUPS.get(root)
        if groups is None:
            unknown_products.append(raw)
            continue
        user_groups.update(groups)
    if unknown_products:
        print(
            json.dumps(
                {
                    "error": (
                        f"unknown --products value(s): {', '.join(unknown_products)}. "
                        f"Accepted codes: {accepted_products}."
                    )
                }
            ),
            file=sys.stderr,
        )
        return 2

    events = payload.get("data") or payload.get("events") or []
    kept: list[dict] = []
    dropped_by_importance = 0
    dropped_by_relevance = 0

    for ev in events:
        imp = ev.get("importance") or 0
        if imp < args.min_importance:
            dropped_by_importance += 1
            continue
        name = ev.get("eventName") or ""
        matched = _groups_for_event(name)
        if args.products and user_groups and matched.isdisjoint(user_groups):
            dropped_by_relevance += 1
            continue
        kept.append(
            {
                "timestamp": ev.get("date"),
                "name": name,
                "importance": imp,
                "matched_product_groups": sorted(matched),
                "actual": ev.get("actual"),
                "consensus": ev.get("consensus"),
                "prior": ev.get("prior"),
            }
        )

    print(
        json.dumps(
            {
                "kept": len(kept),
                "dropped_by_importance": dropped_by_importance,
                "dropped_by_relevance": dropped_by_relevance,
                "events": kept,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
