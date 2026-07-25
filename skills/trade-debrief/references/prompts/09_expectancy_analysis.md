---
version: 1.1.0
last_updated: 2026-03-26
compatible_report_versions: [1, 2]
analysis_type: expectancy_analysis
requires_multi_day: true
---

# Prompt: Statistical Expectancy Analysis

## System Instructions

You are performing statistical analysis on a collection of trades to determine edge presence and expectancy leakage. Your analysis must be purely statistical with no subjective assessment.

### Contract Context

The report includes a `contracts` map with product details. Each trade has `product_name`, `dollar_per_tick`, and dollar P&L (`realized_pnl_dollars`, `mfe_dollars`, `mae_dollars`). Compute expectancy in BOTH R-multiples and dollars. Dollar expectancy varies by product — $0.15R expectancy on ES ($1,875/trade) vs MES ($187.50/trade) has very different portfolio implications.

### Constraints

**STRICT RULES:**
1. **Use only aggregated numeric data** - No interpretation of individual trades
2. **Calculate statistical measures** - Mean, median, standard deviation, percentiles
3. **Identify edge vs execution leakage** - Separate setup quality from management quality
4. **Provide confidence intervals** - Use proper statistical bounds
5. **Dual-unit reporting** - Report all metrics in both R and dollars

### Required Metrics

**Core Metrics:**
- Total trades analyzed
- Win rate (wins / total)
- Average win (R and dollars)
- Average loss (R and dollars)
- Expectancy (R per trade and dollars per trade)
- Profit factor (gross_profit / gross_loss, in both R and dollars)
- Product breakdown (if multiple products traded)

**Execution Metrics:**
- MFE utilization (realized_R / mfe_R)
- Average giveback from MFE (% and dollars)
- MAE discipline (mae_R / initial_risk_R)

---

## Task

Analyze the collection of trades and determine edge presence and execution quality.

### Output Format

**Statistical Summary:**

```json
{
  "dataset": {
    "total_trades": 45,
    "date_range": {
      "start": "2026-01-01",
      "end": "2026-01-31"
    }
  },

  "core_metrics": {
    "win_rate": {
      "value": 0.556,
      "wins": 25,
      "losses": 20
    },
    "avg_win_R": {
      "mean": 0.65,
      "median": 0.60,
      "std_dev": 0.25
    },
    "avg_loss_R": {
      "mean": -0.45,
      "median": -0.40,
      "std_dev": 0.18
    },
    "expectancy_R": {
      "value": 0.162,
      "calculation": "(0.65 * 0.556) - (0.45 * 0.444)",
      "confidence_95": [0.08, 0.24]
    },
    "expectancy_dollars": {
      "value": 202.50,
      "product": "E-Mini S&P 500",
      "dollar_per_tick": 12.50,
      "note": "Based on avg stop_distance_ticks of 16 ($200 risk per contract)"
    },
    "profit_factor": {
      "value": 1.81,
      "gross_profit_R": 16.25,
      "gross_profit_dollars": 20312.50,
      "gross_loss_R": 9.00,
      "gross_loss_dollars": 11250.00
    }
  },

  "execution_metrics": {
    "mfe_utilization": {
      "mean": 0.42,
      "median": 0.35,
      "percentiles": {
        "p25": 0.15,
        "p50": 0.35,
        "p75": 0.65,
        "p95": 0.90
      }
    },
    "avg_giveback_from_mfe_pct": {
      "mean": 58,
      "median": 65,
      "trades_with_full_giveback": 12
    },
    "mae_discipline": {
      "mean": 0.38,
      "trades_exceeding_initial_risk": 3,
      "max_mae_vs_risk": 1.45
    }
  },

  "edge_analysis": {
    "edge_present": true,
    "evidence": [
      "Win rate (55.6%) above breakeven (50%)",
      "Expectancy positive (+0.162R per trade)",
      "Profit factor above 1.5 (1.81)"
    ],
    "edge_quality": "moderate",
    "statistical_significance": {
      "z_score": 2.3,
      "p_value": 0.021,
      "conclusion": "Edge is statistically significant (p < 0.05)"
    }
  },

  "execution_leakage": {
    "present": true,
    "severity": "high",
    "evidence": [
      "MFE utilization: 42% (58% of profit unrealized)",
      "Full giveback occurred in 27% of trades (12 of 45)",
      "Median realized_R / median_mfe_R = 0.35 / 0.82 = 0.43"
    ],
    "estimated_cost_R": {
      "potential_expectancy_with_50pct_mfe_capture": 0.285,
      "current_expectancy": 0.162,
      "leakage": 0.123,
      "leakage_dollars_per_trade": 153.75,
      "leakage_dollars_total": 6918.75,
      "calculation": "Avg MFE (0.82R) * 50% capture * win_rate - avg_loss"
    }
  },

  "primary_recommendation": {
    "focus": "Execution improvement, not edge validation",
    "reasoning": "Edge is proven (expectancy +0.162R), but execution leaks 43% of profit",
    "priority_action": "Implement mandatory scaling at MFE >= 0.7R"
  }
}
```

---

## Statistical Tests

### Edge Validation

**Null Hypothesis:** True expectancy = 0 (no edge)

**Test:** One-sample t-test

```
H0: E[R] = 0
H1: E[R] > 0

t = (mean_R - 0) / (std_R / sqrt(n))
p_value = P(T > t) where T ~ t(n-1)

If p < 0.05: Reject H0, edge is statistically significant
```

**Output in Analysis:**
```json
{
  "statistical_test": {
    "test": "one_sample_t_test",
    "null_hypothesis": "expectancy = 0",
    "t_statistic": 2.3,
    "degrees_of_freedom": 44,
    "p_value": 0.021,
    "conclusion": "Reject H0, edge present (p = 0.021 < 0.05)"
  }
}
```

---

## Confidence Intervals

**Expectancy CI:**

```
CI_95 = mean_R ± (t_critical * std_R / sqrt(n))

Where:
- t_critical = 1.96 for large n (or from t-table for df=n-1)
- std_R = sample standard deviation
- n = trade count
```

**Interpretation:**
```json
{
  "expectancy_R": 0.162,
  "confidence_95": [0.08, 0.24],
  "interpretation": "95% confident true expectancy is between 0.08R and 0.24R"
}
```

---

## Trade Collection

(Multiple trade reports will be appended here in array format)

```yaml
trades_collection:
  - trade_id: "T1"
    realized_R: -0.4
    mfe_R: 0.7
    mae_R: -0.4
    # ...
  - trade_id: "T2"
    realized_R: 0.5
    mfe_R: 0.8
    mae_R: -0.2
    # ...
```
