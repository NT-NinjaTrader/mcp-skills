---
version: 1.1.0
last_updated: 2026-03-26
compatible_report_versions: [1, 2]
analysis_type: pattern_extraction
---

# Prompt: Trade Pattern Extraction

## System Instructions

You are analyzing fact-only trade timelines to extract repeating patterns. Your goal is to cluster trades into groups based on observable characteristics, then identify measurable KPIs for each pattern.

### Contract Context

The report includes a `contracts` map with product details per contract_id. Each trade has `product_name`, `contract_name`, `dollar_per_tick`, and dollar P&L fields (`realized_pnl_dollars`, `mfe_dollars`, `mae_dollars`). Reference products by name and include dollar aggregate impact for each pattern cluster.

### Constraints

**STRICT RULES:**
1. **Only use numeric fields** - MFE/MAE, action flags, volume features, dollar P&L
2. **Define patterns by thresholds** - Numerical boundaries, not descriptions
3. **Cite YAML paths** - Reference exact fields used
4. **Provide actionable KPIs** - Measurable improvements, not advice
5. **Include dollar impact** - Aggregate `realized_pnl_dollars` per pattern to show real cost

### Clustering Dimensions

Use ONLY these fields for clustering:
- `derived.mfe_R`, `derived.mae_R`, `derived.giveback_from_mfe_pct`
- `trade_state.stop_loss_modified`, `trade_state.size_increased`, `trade_state.scale_out_count`
- `minute_volume_features.participation_rate_vs_session`
- `minute_volume_features.volume_per_tick`
- `minute_volume_features.top3_concentration`
- `minute_volume_features.poc_shift`
- `minute_volume_features.imbalance`

---

## Task

Given the collection of trades below, cluster them into 3-6 groups and provide defining thresholds for each pattern.

### Output Format

**Pattern Clusters:**

```json
{
  "patterns": [
    {
      "pattern_id": 1,
      "pattern_name": "high_mfe_full_giveback",
      "trade_count": 8,
      "defining_thresholds": {
        "mfe_R": {"min": 0.7},
        "giveback_from_mfe_pct": {"min": 90},
        "scale_out_executed": false
      },
      "field_citations": [
        "derived.mfe_R",
        "derived.giveback_from_mfe_pct",
        "trade_state.scale_out_executed"
      ],
      "kpis": [
        {
          "metric": "Scale execution rate at MFE >= 0.7R",
          "current": "0%",
          "target": ">= 80%",
          "expected_impact": "Convert 6-7 losers to winners"
        }
      ]
    },
    {
      "pattern_id": 2,
      "pattern_name": "weak_momentum_entries",
      "trade_count": 5,
      "defining_thresholds": {
        "pre_entry.volume.last_5m_vs_session_avg": {"max": 1.0},
        "timeline[0].minute_volume_features.participation_rate_vs_session": {"max": 1.1},
        "mae_R": {"min": -0.5}
      },
      "kpis": [
        {
          "metric": "Entry volume threshold",
          "current": "< 1.0x session avg",
          "target": ">= 1.2x session avg",
          "expected_impact": "Reduce MAE by ~40%"
        }
      ]
    }
  ],
  "summary": {
    "total_trades": 15,
    "patterns_identified": 2,
    "trades_unclustered": 2
  }
}
```

---

## Multi-Day Analysis

For analyzing multiple days of trades, append all trade reports and identify patterns across the full dataset.

### Input Format

```yaml
days:
  - date: "2026-01-29"
    trades: [...]
  - date: "2026-01-30"
    trades: [...]
  - date: "2026-01-31"
    trades: [...]
```

### Output Format

Same as above, but with additional temporal analysis:

```json
{
  "patterns": [...],
  "temporal_trends": [
    {
      "pattern_id": 1,
      "occurrence_trend": "increasing",
      "days": ["2026-01-29", "2026-01-30", "2026-01-31"],
      "frequency": [2, 3, 3]
    }
  ]
}
```

---

## Trade Timeline Reports

(Multiple trade reports will be appended here)
