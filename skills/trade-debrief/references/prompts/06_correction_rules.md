---
version: 1.1.0
last_updated: 2026-03-26
compatible_report_versions: [1, 2]
analysis_type: correction_rules
---

# Prompt: Trade Correction Rule Generation

## System Instructions

You are generating mechanical trading rules to address observed mistakes. Rules must be:
- Measurable (numeric thresholds)
- Executable (clear IF-THEN logic)
- Testable (can be backtested)
- Evidence-based (derived from actual trade data)

### Contract Context

The report includes a `contracts` map with product details. Each trade has `product_name`, `dollar_per_tick`, and dollar P&L (`realized_pnl_dollars`, `mfe_dollars`, `mae_dollars`). When estimating rule impact, express improvements in both R-multiples and dollars — "$750 saved per occurrence" motivates rule compliance better than "0.6R improvement".

### Constraints

**STRICT RULES:**
1. **One rule per identified mistake** - Focus on highest-impact issues
2. **Include trigger condition** - Clear IF statement with thresholds
3. **Include action** - Specific THEN action
4. **Cite evidence** - YAML paths showing the mistake occurred
5. **Estimate impact in dollars and R** - Quantify potential improvement using both `realized_pnl_dollars` and `realized_r`

---

## Task

Generate correction rules for mistakes identified in the trade report.

### Output Format

**Correction Rules:**

```json
{
  "rules": [
    {
      "rule_id": "R1",
      "rule_name": "mandatory_scale_at_mfe",
      "category": "trade_management",
      "priority": "critical",

      "trigger": {
        "condition": "mfe_R >= 0.7 AND participation_rate_vs_session >= 1.3",
        "fields_used": [
          "timeline[N].pnl_R.mfe",
          "timeline[N].minute_volume_features.participation_rate_vs_session"
        ]
      },

      "action": {
        "type": "scale_out",
        "params": {
          "percentage": 50,
          "urgency": "immediate"
        }
      },

      "evidence": {
        "mistake_count": 2,
        "total_trades": 3,
        "frequency": 0.67,
        "citations": [
          "trades[0]: mfe_R = 0.7, scale_out = false, realized_R = -0.4",
          "trades[1]: mfe_R = 0.8, scale_out = false, realized_R = -0.6"
        ]
      },

      "expected_impact": {
        "trades_affected": 2,
        "potential_improvement_R": 1.0,
        "conversion": "2 losers → 2 small winners",
        "calculation": "(0.7 * 0.5 - 0.4) + (0.8 * 0.5 - 0.6) = +0.35 + +0.40 = +0.75R"
      },

      "backtest_parameters": {
        "historical_period": "last_30_days",
        "trades_matching_trigger": 8,
        "simulated_improvement": "+6.2R net"
      }
    },
    {
      "rule_id": "R2",
      "rule_name": "volume_decay_tighten_stop",
      "category": "risk_management",
      "priority": "high",

      "trigger": {
        "condition": "participation_rate_vs_session < 1.0 AND mfe_R > 0.5 AND open_pnl_R > 0",
        "fields_used": [
          "timeline[N].minute_volume_features.participation_rate_vs_session",
          "timeline[N].pnl_R.mfe",
          "timeline[N].pnl_R.open"
        ]
      },

      "action": {
        "type": "move_stop_to_breakeven_or_reduce",
        "params": {
          "stop_target": "entry_price",
          "alternative": "reduce_size_by_50pct"
        }
      },

      "evidence": {
        "mistake_count": 2,
        "citations": [
          "trades[0].timeline[2]: participation = 0.90, mfe = 0.7, action = none",
          "trades[1].timeline[1]: participation = 0.85, mfe = 0.6, action = none"
        ]
      },

      "expected_impact": {
        "trades_affected": 2,
        "potential_improvement_R": 0.8,
        "reasoning": "Protects profit before full reversal occurs"
      }
    }
  ],
  "prioritization": {
    "rank_by": "expected_impact",
    "top_3": ["R1", "R2", "R3"]
  }
}
```

---

## Rule Template

**For each identified mistake, generate:**

```markdown
### Rule {rule_id}: {rule_name}

**Trigger:**
```
IF {condition_1} AND {condition_2}
```

**Action:**
```
THEN {action} WITH {params}
```

**Evidence:**
- Occurred in {count} of {total} trades
- YAML citations: {paths}

**Impact:**
- Potential improvement: {R_amount}
- Conversion: {description}

**Backtest Needed:**
- Historical trades matching trigger: {count}
- Simulated net improvement: {estimate}
```

---

## Trade Timeline Report

(Report YAML/JSON will be appended here)

---

## Additional Context (If Available)

If historical trade data is available, append summary statistics:

```json
{
  "historical_context": {
    "total_trades_last_30d": 45,
    "avg_net_R_last_30d": 0.15,
    "similar_mistakes_frequency": {
      "missed_scale_at_mfe": 0.42,
      "stop_moved_away": 0.08,
      "size_increased_in_dd": 0.12
    }
  }
}
```

This helps prioritize rules based on mistake frequency.
