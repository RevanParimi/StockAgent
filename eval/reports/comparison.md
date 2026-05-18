# StockAgent Eval Comparison Report

| | Value |
|---|---|
| **Before** | `before.json` (2026-05-18) |
| **After**  | `after.json` (2026-05-18) |

## Overall

| Metric | Before | After | Delta | Verdict |
|--------|-------:|------:|------:|---------|
| Direction Hit Rate | 61.0% | 61.0% | +0.0% | &#x2014; Same |
| Avg Price Error    | 1.5240% | 1.5240% | +0.0000% | &#x2014; Same |

## By Sector

| Sector | Before HR | After HR | Delta | Verdict |
|--------|----------:|---------:|------:|---------|
| automobile | 59.4% | 59.4% | +0.0% | &#x2014; Same |
| banking_bfsi | 60.0% | 60.0% | +0.0% | &#x2014; Same |
| it_sector | 63.9% | 63.9% | +0.0% | &#x2014; Same |
| renewable_energy | 60.6% | 60.6% | +0.0% | &#x2014; Same |

## By Agent

### Automobile

| Agent | Before HR | After HR | Delta | Verdict |
|-------|----------:|---------:|------:|---------|
| competitive_intel | 59.4% | 59.4% | +0.0% | &#x2014; Same |
| fundamentals | 60.6% | 60.6% | +0.0% | &#x2014; Same |
| pattern_analysis | 61.1% | 61.1% | +0.0% | &#x2014; Same |
| policy_regulatory | 55.0% | 55.0% | +0.0% | &#x2014; Same |
| raw_materials | 61.1% | 61.1% | +0.0% | &#x2014; Same |
| risk_macro | 60.6% | 60.6% | +0.0% | &#x2014; Same |
| sales_demand | 60.6% | 60.6% | +0.0% | &#x2014; Same |
| sentiment | 57.8% | 57.8% | +0.0% | &#x2014; Same |
| valuation_catalyst | 56.1% | 56.1% | +0.0% | &#x2014; Same |

### Banking Bfsi

| Agent | Before HR | After HR | Delta | Verdict |
|-------|----------:|---------:|------:|---------|
| fundamentals | 58.9% | 58.9% | +0.0% | &#x2014; Same |
| institutional | 62.8% | 62.8% | +0.0% | &#x2014; Same |
| macro_policy | 57.8% | 57.8% | +0.0% | &#x2014; Same |
| pattern_analysis | 63.3% | 63.3% | +0.0% | &#x2014; Same |
| risk | 57.2% | 57.2% | +0.0% | &#x2014; Same |
| universe_setup | 63.3% | 63.3% | +0.0% | &#x2014; Same |

### It Sector

| Agent | Before HR | After HR | Delta | Verdict |
|-------|----------:|---------:|------:|---------|
| fundamentals | 66.7% | 66.7% | +0.0% | &#x2014; Same |
| global_macro | 59.4% | 59.4% | +0.0% | &#x2014; Same |
| insider_smart_money | 63.9% | 63.9% | +0.0% | &#x2014; Same |
| pattern_analysis | 63.9% | 63.9% | +0.0% | &#x2014; Same |
| peer_benchmark | 65.6% | 65.6% | +0.0% | &#x2014; Same |
| risk_macro | 66.7% | 66.7% | +0.0% | &#x2014; Same |
| sentiment | 63.3% | 63.3% | +0.0% | &#x2014; Same |
| transcript_nlp | 62.8% | 62.8% | +0.0% | &#x2014; Same |

### Renewable Energy

| Agent | Before HR | After HR | Delta | Verdict |
|-------|----------:|---------:|------:|---------|
| business | 60.6% | 60.6% | +0.0% | &#x2014; Same |
| fundamentals | 56.1% | 56.1% | +0.0% | &#x2014; Same |
| risk | 66.1% | 66.1% | +0.0% | &#x2014; Same |
| sentiment_policy | 60.0% | 60.0% | +0.0% | &#x2014; Same |
| technical | 60.6% | 60.6% | +0.0% | &#x2014; Same |
| valuation | 55.0% | 55.0% | +0.0% | &#x2014; Same |

---

**Legend**

- &#x25B2; Better &mdash; hit rate improved by > 1 pp
- &#x25BC; Worse &mdash; hit rate dropped by > 1 pp
- &#x2014; Same &mdash; change within +/- 1 pp

> Hit Rate = fraction of direction predictions (up/down) that matched actual outcome.
> Lower price error is better; its verdict is inverted accordingly.
