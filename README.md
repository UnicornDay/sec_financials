# SEC Financials Toolkit

Pull fundamental financial data directly from the **SEC EDGAR XBRL API** — no API key required. Three CLI tools for fetching structured financial metrics, historical time series, and narrative sections from 10-K filings.

## Tools

| Script | Purpose |
|--------|---------|
| `sec_financials.py` | Income statement, balance sheet, cost of debt, effective tax rate |
| `sec_facts.py` | Historical annual time series for key accounting tags (Revenue, Net Income, etc.) |
| `sec_10k.py` | Narrative sections from latest 10-K: Business overview, Risk Factors, Legal Proceedings |

## Setup

```bash
pip install requests
```

No API keys. No registration. The SEC EDGAR API is free and public.

## Usage

### sec_financials.py — Company Fundamentals + Cost of Debt

```bash
py sec_financials.py --ticker NVDA
```

Returns latest Revenue, Gross Margin, Pre-Tax Income, Net Income, Effective Tax Rate, Cash, Debt breakdown, and Pre-Tax/After-Tax Cost of Debt.

### sec_facts.py — Historical Annual Series

```bash
py sec_facts.py --ticker AAPL
```

Returns a multi-year table of Revenue, COGS, Net Income, Total Assets, Operating Cash Flows, and Shares Outstanding pulled from SEC XBRL tags.

### sec_10k.py — Narrative Sections

```bash
py sec_10k.py --ticker AAPL --items 1,1A,3
```

Extracts specific items from the latest 10-K filing. Default items are 1 (Business), 1A (Risk Factors), and 3 (Legal Proceedings).

## Data Source

All data comes from the SEC's public EDGAR system:
- **Company Facts**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
- **Ticker-to-CIK mapping**: `https://www.sec.gov/files/company_tickers.json`
- **10-K filings**: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}`

## Notes

- Cost of Debt is estimated. After-Tax CoD requires a valid Effective Tax Rate derived from actual filings.
- Pre-Tax Income may be calculated as Net Income + Tax Expense if not directly reported.
- Accuracy depends on XBRL tagging consistency across companies.
- The SEC API requires a `User-Agent` header with an email address. Update the `HEADERS` dict if you encounter rate limiting.
