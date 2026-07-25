---
version: 1.1.0
last_updated: 2026-03-26
compatible_report_versions: [1, 2]
analysis_type: pattern_clustering
requires_multi_trade: true
---

# Prompt: Multi-Trade Pattern Clustering

## System Instructions

You are clustering trades into behavioral patterns using unsupervised learning concepts applied to numeric features only. Your task is to identify 3-6 distinct trade archetypes and provide characteristics for each.

### Contract Context

The report includes a `contracts` map with product details. Each trade has `product_name`, `dollar_per_tick`, and dollar P&L (`realized_pnl_dollars`, `mfe_dollars`, `mae_dollars`). Include dollar aggregate impact per cluster (`total_realized_dollars`, `opportunity_cost_dollars`) alongside R-multiples.

### Constraints

**STRICT RULES:**
1. **Use numeric features only** - No categorical judgments
2. **Define clusters by centroids** - Numeric thresholds for each dimension
3. **Provide cluster statistics** - Count, avg metrics, variance
4. **Rank by dollar impact** - Prioritize patterns by aggregate dollar and R-multiple loss/gain

### Clustering Features

**Primary Dimensions:**
- `mfe_R` - Maximum favorable excursion
- `mae_R` - Maximum adverse excursion
- `giveback_from_mfe_pct` - Profit giveback percentage
- `time_in_trade_minutes` - Trade duration
- `scale_out_count` - Number of partial exits

**Secondary Dimensions (Volume):**
- `avg_participation_rate` - Average participation during trade
- `avg_top3_concentration` - Average volume concentration
- `poc_drift_ticks` - POC movement during trade

---

## Task

Cluster the trades below into distinct behavioral patterns.

### Output Format

**Clusters:**

```json
{
  "clustering_method": "threshold_based_archetypes",
  "feature_weights": {
    "mfe_R": 0.25,
    "giveback_pct": 0.25,
    "mae_R": 0.20,
    "scale_out_count": 0.15,
    "time_in_trade": 0.15
  },

  "clusters": [
    {
      "cluster_id": 1,
      "cluster_name": "high_mfe_full_giveback",
      "trade_count": 8,
      "trade_ids": ["T1", "T3", "T7", "T12", "T15", "T18", "T22", "T25"],

      "centroid": {
        "mfe_R": 0.78,
        "mae_R": -0.42,
        "giveback_from_mfe_pct": 95,
        "time_in_trade_minutes": 14,
        "scale_out_count": 0
      },

      "defining_thresholds": {
        "mfe_R": {"min": 0.7},
        "giveback_from_mfe_pct": {"min": 90},
        "scale_out_count": {"equals": 0}
      },

      "aggregate_impact": {
        "total_realized_R": -3.2,
        "potential_with_50pct_scale_R": +3.1,
        "opportunity_cost_R": 6.3
      },

      "statistics": {
        "avg_realized_R": -0.40,
        "avg_mfe_R": 0.78,
        "avg_giveback_pct": 95,
        "std_dev_mfe_R": 0.12
      },

      "primary_issue": "Systematic failure to monetize favorable excursion",
      "recommended_action": "Implement mandatory scale at MFE >= 0.7R"
    },

    {
      "cluster_id": 2,
      "cluster_name": "disciplined_winners",
      "trade_count": 12,

      "centroid": {
        "mfe_R": 0.65,
        "mae_R": -0.15,
        "giveback_from_mfe_pct": 25,
        "time_in_trade_minutes": 8,
        "scale_out_count": 1
      },

      "defining_thresholds": {
        "scale_out_count": {"min": 1},
        "giveback_from_mfe_pct": {"max": 40},
        "realized_R": {"min": 0}
      },

      "aggregate_impact": {
        "total_realized_R": +7.8,
        "avg_realized_R": 0.65
      },

      "primary_characteristic": "Proper trade management with profit protection"
    },

    {
      "cluster_id": 3,
      "cluster_name": "weak_setup_quick_loss",
      "trade_count": 5,

      "centroid": {
        "mfe_R": 0.12,
        "mae_R": -0.55,
        "time_in_trade_minutes": 3,
        "pre_entry_participation_rate": 0.82
      },

      "defining_thresholds": {
        "mfe_R": {"max": 0.25},
        "mae_R": {"min": -0.7},
        "time_in_trade_minutes": {"max": 5}
      },

      "aggregate_impact": {
        "total_realized_R": -2.75,
        "avg_realized_R": -0.55
      },

      "primary_issue": "Low-conviction entries in weak momentum",
      "recommended_action": "Add entry filter: participation_rate >= 1.2"
    }
  ],

  "summary": {
    "total_trades": 25,
    "trades_clustered": 25,
    "clusters_identified": 3,
    "highest_impact_cluster": 1,
    "total_opportunity_cost_R": 6.3
  }
}
```

---

## Clustering Algorithm (For Reference)

**Simple Threshold-Based Approach:**

```python
def cluster_trades(trades):
    clusters = {
        "high_mfe_full_giveback": [],
        "disciplined_winners": [],
        "weak_setup_quick_loss": [],
        "standard_losses": []
    }

    for trade in trades:
        if trade.mfe_R >= 0.7 and trade.giveback_pct >= 90:
            clusters["high_mfe_full_giveback"].append(trade)
        elif trade.scale_out_count >= 1 and trade.realized_R > 0:
            clusters["disciplined_winners"].append(trade)
        elif trade.mfe_R <= 0.25 and trade.mae_R <= -0.5:
            clusters["weak_setup_quick_loss"].append(trade)
        else:
            clusters["standard_losses"].append(trade)

    return clusters
```

---

## Trade Collection

(Array of trade reports will be appended here)

```yaml
trades:
  - trade_id: "T1"
    entry_time: "2026-01-29T10:14:32"
    realized_R: -0.4
    mfe_R: 0.7
    mae_R: -0.4
    giveback_from_mfe_pct: 100
    scale_out_count: 0
    time_in_trade_minutes: 11
    pre_entry:
      volume:
        last_5m_vs_session_avg: 1.38

  - trade_id: "T2"
    # ...
```
