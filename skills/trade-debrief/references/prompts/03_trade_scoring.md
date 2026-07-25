---
version: 1.1.0
last_updated: 2026-03-26
compatible_report_versions: [1, 2]
analysis_type: trade_scoring
---

# Prompt: Objective Trade Scoring

## System Instructions

You are scoring trades objectively using only numeric fields from the trade report. Your task is to create a composite score (0-100) and explain the formula.

### Contract Context

The report includes a `contracts` map with product details. Each trade has `product_name`, `dollar_per_tick`, and dollar P&L (`realized_pnl_dollars`, `mfe_dollars`, `mae_dollars`). Use `dollar_per_tick` to contextualize stop distances — a 48-tick stop on ES ($600) is very different from a 48-tick stop on MES ($60). Include dollar P&L in the score summary so the trader sees real financial impact alongside the grade.

### Constraints

**STRICT RULES:**
1. **Use only numeric fields** - No subjective assessment
2. **Provide explicit formula** - Show calculation with weights
3. **Cite YAML paths** - Reference fields used in score
4. **Explain components** - Top 3 contributing factors per trade
5. **Include dollar summary** - Show `realized_pnl_dollars` alongside R-based score

### Scoring Dimensions

**Available Metrics:**
- MFE utilization: `realized_R / mfe_R` (higher = better)
- Giveback penalty: `giveback_from_mfe_pct` (lower = better)
- MAE discipline: `mae_R / initial_risk_R` (lower = better)
- Dollar giveback: `mfe_dollars - realized_pnl_dollars` (unrealized profit in dollars)
- Action compliance:
  - `stop_loss_modified = false` (bonus)
  - `size_increased_in_drawdown = false` (bonus)
  - `scale_out_executed = true` when `mfe_R >= threshold` (bonus)

---

## Task

Create a scoring formula and score each trade in the report.

### Output Format

**Scoring Formula:**

```json
{
  "formula": {
    "base_score": 50,
    "components": [
      {
        "name": "mfe_utilization",
        "weight": 25,
        "calculation": "realized_R / max(mfe_R, 0.1) * 25",
        "max_contribution": 25
      },
      {
        "name": "giveback_penalty",
        "weight": -20,
        "calculation": "-(giveback_from_mfe_pct / 100) * 20",
        "max_contribution": -20
      },
      {
        "name": "mae_discipline",
        "weight": 15,
        "calculation": "(1 - abs(mae_R) / 1.0) * 15",
        "max_contribution": 15
      },
      {
        "name": "action_compliance",
        "weight": 10,
        "calculation": "sum of bonuses",
        "bonuses": {
          "stop_not_moved": 3,
          "no_size_increase": 3,
          "scaled_at_mfe": 4
        },
        "max_contribution": 10
      }
    ],
    "min_score": 0,
    "max_score": 100
  }
}
```

**Trade Scores:**

```json
{
  "scores": [
    {
      "trade_id": "T1",
      "total_score": 32,
      "grade": "D",
      "breakdown": [
        {
          "component": "mfe_utilization",
          "value": 0,
          "contribution": 0,
          "citation": "trades[0].derived.realized_R = -0.4, trades[0].derived.mfe_R = 0.7"
        },
        {
          "component": "giveback_penalty",
          "value": 100,
          "contribution": -20,
          "citation": "trades[0].derived.giveback_from_mfe_pct = 100"
        },
        {
          "component": "mae_discipline",
          "value": 0.6,
          "contribution": 9,
          "citation": "trades[0].derived.mae_R = -0.4, initial_risk_R = 1.0"
        },
        {
          "component": "action_compliance",
          "bonuses": ["stop_not_moved", "no_size_increase"],
          "contribution": 6,
          "citation": "trades[0].stop_loss_modified = false, trades[0].size_increased_in_drawdown = false"
        }
      ],
      "primary_detractors": [
        "Full MFE giveback (-20 points)",
        "Zero MFE utilization (0 points)"
      ]
    }
  ],
  "summary": {
    "avg_score": 32,
    "score_distribution": {
      "A (90-100)": 0,
      "B (80-89)": 0,
      "C (70-79)": 0,
      "D (60-69)": 0,
      "F (0-59)": 1
    }
  }
}
```

---

## Grading Scale

| Score | Grade | Interpretation |
|-------|-------|----------------|
| 90-100 | A | Excellent execution |
| 80-89 | B | Good execution, minor issues |
| 70-79 | C | Acceptable, room for improvement |
| 60-69 | D | Poor execution, major issues |
| 0-59 | F | Failed execution |

---

## Trade Timeline Report

(Report YAML/JSON will be appended here)
