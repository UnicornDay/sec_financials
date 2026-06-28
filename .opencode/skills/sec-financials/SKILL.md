---
name: sec-financials
description: Pull SEC fundamental metrics, cost of debt, and financial structure analysis for any US-listed ticker via the SEC EDGAR API
---

## What I do

Fetch real-time fundamental financial metrics directly from the SEC EDGAR XBRL API for any US-listed company. Calculate cost of debt (pre-tax and after-tax), effective tax rate, and key financial structure metrics.

## How to Call

```
py sec_financials.py --ticker [TICKER]
```

## Metrics Returned

### Income Statement
- Revenue, Gross Profit, Gross Margin %
- Pre-Tax Income (direct or calculated as Net Income + Tax Expense)
- Income Tax Expense, Net Income
- Effective Tax Rate (calculated from data, not estimated)
- Diluted EPS

### Balance Sheet & Debt
- Cash & Equivalents
- Short-Term Debt, Long-Term Debt
- Total Debt
- Interest Expense

### Cost of Debt
- Pre-Tax Cost of Debt % (annualized interest / total debt)
- After-Tax Cost of Debt % (pre-tax * (1 - effective tax rate))
- Effective Tax Rate used (with source note: fetched vs calculated)
- Total debt used in calculation
- Annualized interest used

### Segment Data (company-specific)
- Revenue by segment (when available, e.g., iPhone, Services for AAPL)

## Notes
- Cost of Debt is estimated based on latest SEC filing data
- After-Tax CoD is calculated only if ETR can be derived from actual data
- Pre-Tax Income may be calculated as Net Income + Tax Expense if not directly reported
- Accuracy depends on SEC API availability and XBRL tagging consistency

## Example

"Analyze the current debt structure and cost of debt for MSFT"
-> py sec_financials.py --ticker MSFT

"Pull down the latest SEC fundamental metrics for ticker NVDA"
-> py sec_financials.py --ticker NVDA

## Files

- `sec_financials.py` — Core script: ticker-to-CIK lookup, SEC API fetch, metric extraction, cost of debt calculation

## Data Source

- **SEC EDGAR XBRL API**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
- **Ticker-to-CIK mapping**: `https://www.sec.gov/files/company_tickers.json`
