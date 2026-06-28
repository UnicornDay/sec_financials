import requests
import argparse
from datetime import datetime

HEADERS = {
    'User-Agent': 'MyFinancialAnalysisTool/1.3 (myemail@example.com)',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'application/json',
    'Connection': 'keep-alive'
}

TAG_MAP = {
    "Revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "Cost of Goods Sold": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "Net Income": ["NetIncomeLoss"],
    "Total Assets": ["Assets"],
    "Operating Cash Flows": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "Shares Outstanding": ["CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"],
}

SHARES_UNIT_TAGS = {"Shares Outstanding"}

def lookup_cik(ticker):
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10), entry.get("title", ticker_upper)
    raise ValueError(f"Ticker '{ticker}' not found")

def fetch_company_facts(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()

def get_annual_series(data, concepts, is_shares=False):
    best_concept = None
    best_series = []
    for concept in concepts:
        try:
            us_gaap = data['facts']['us-gaap'][concept]
        except KeyError:
            continue
        units_to_try = ['shares'] if is_shares else ['USD']
        for unit in units_to_try:
            try:
                entries = us_gaap['units'][unit]
            except KeyError:
                continue
            annual = {}
            for e in entries:
                if e.get('fp') == 'FY' and 'fy' in e and 'end' in e and 'val' in e:
                    fy = e['fy']
                    if fy not in annual or e['end'] > annual[fy]['end']:
                        annual[fy] = {'end': e['end'], 'val': e['val']}
            if len(annual) > len(best_series):
                best_concept = concept
                best_series = [(fy, annual[fy]['end'], annual[fy]['val']) for fy in sorted(annual)]
    return best_concept, best_series

def main():
    parser = argparse.ArgumentParser(description="SEC Company Facts - Historical Series")
    parser.add_argument('--ticker', '-t', type=str, required=True, help='Stock ticker')
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"Fetching company facts for {ticker}...")
    cik, company = lookup_cik(ticker)
    data = fetch_company_facts(cik)
    print(f"Found {company}")

    results = {}
    for label, concepts in TAG_MAP.items():
        is_shares = label in SHARES_UNIT_TAGS
        concept, series = get_annual_series(data, concepts, is_shares)
        if series:
            results[label] = (concept, series)
            print(f"  {label:<22} -> {concept} ({len(series)} fiscal years)")
        else:
            print(f"  {label:<22} -> NOT FOUND")

    if not results:
        print("No data found.")
        return

    # Gather all years across all tags
    all_years = set()
    for label, (concept, series) in results.items():
        for fy, _, _ in series:
            all_years.add(fy)
    all_years = sorted(all_years)

    # Build table
    headers = ["Fiscal Year", "Period End"]
    labels_in_order = list(TAG_MAP.keys())
    for label in labels_in_order:
        headers.append(label)

    col_widths = [14, 14]
    for label in labels_in_order:
        col_widths.append(max(len(label), 16))

    sep = "  " + "-+-".join("-" * w for w in col_widths)

    total_width = sum(col_widths) + len(col_widths) * 3
    print(f"\n{'=' * total_width}")
    print(f"  {ticker} - ANNUAL FUNDAMENTALS (SEC XBRL)")
    print(f"  Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * total_width}")
    print("  " + " | ".join(h.center(w) for h, w in zip(headers, col_widths)))
    print(sep)

    for fy in reversed(all_years):
        row = [str(fy)]
        # Period end
        period_end = ""
        for label in labels_in_order:
            if label in results:
                _, series = results[label]
                for y, end, _ in series:
                    if y == fy:
                        period_end = end[:10]
                        break
                if period_end:
                    break
        row.append(period_end)

        for label in labels_in_order:
            val_str = ""
            if label in results:
                _, series = results[label]
                for y, _, val in series:
                    if y == fy:
                        if label == "Shares Outstanding":
                            val_str = f"{val/1e6:,.0f}M"
                        else:
                            val_str = f"${val/1e9:,.2f}B"
                        break
            row.append(val_str)

        print("  " + " | ".join(v.rjust(w) for v, w in zip(row, col_widths)))

    print(f"{'=' * total_width}")
    print()

if __name__ == "__main__":
    main()
