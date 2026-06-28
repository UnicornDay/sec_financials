import requests
import re
import argparse
from html.parser import HTMLParser

HEADERS = {
    'User-Agent': 'MyFinancialAnalysisTool/1.3 (myemail@example.com)',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'text/html,application/json',
    'Connection': 'keep-alive'
}

def lookup_cik(ticker):
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            cik_str = str(entry["cik_str"]).zfill(10)
            return cik_str, entry.get("title", ticker_upper)
    raise ValueError(f"Ticker '{ticker}' not found")

def find_latest_10k(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    for i, form in enumerate(forms):
        if form == "10-K":
            accession = filings["accessionNumber"][i].replace("-", "")
            primary_doc = filings["primaryDocument"][i]
            filing_date = filings["filingDate"][i]
            period_end = filings.get("reportDate", [None])[i] if len(filings.get("reportDate", [])) > i else None
            return {
                "accession": accession,
                "primary_doc": primary_doc,
                "filing_date": filing_date,
                "period_end": period_end,
                "cik_raw": cik.lstrip("0")
            }
    raise ValueError("No 10-K filing found")

def fetch_filing_text(cik_raw, accession, primary_doc):
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_raw}/{accession}/{primary_doc}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {"script", "style", "noscript"}
        self.in_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.in_skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags:
            self.in_skip = max(0, self.in_skip - 1)
        if tag.lower() in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text.append("\n")

    def handle_data(self, data):
        if self.in_skip == 0:
            self.text.append(data)

def strip_html(html):
    extractor = TextExtractor()
    extractor.feed(html)
    raw = "".join(extractor.text)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    raw = re.sub(r' {2,}', ' ', raw)
    return raw

def extract_item(text, item_number, alt_names=None):
    patterns = [
        rf'ITEM\s+{item_number}\s*[\.\-\u2013]\s*',
        rf'Item\s+{item_number}\s*[\.\-\u2013]\s*',
    ]
    if alt_names:
        for alt in alt_names:
            patterns.append(rf'{item_number}\s*[\.\-\u2013]\s*{re.escape(alt)}')

    # Find ALL candidate start positions (reverse order to skip TOC)
    candidates = []
    for p in patterns:
        for m in re.finditer(p, text):
            candidates.append(m.start())
    candidates.sort(reverse=True)  # search from end to skip TOC

    if not candidates:
        return None

    # Try each candidate from the end; pick first with real prose
    start = None
    for cand in candidates:
        snippet = text[cand:cand + 2000]
        # Count words in the 500 chars after first line
        after_header = snippet.split('\n', 1)
        body = after_header[1] if len(after_header) > 1 else ''
        body = re.sub(r'<[^>]+>', '', body)
        words = body.split()
        # Real section has 50+ words; TOC has only headers and page numbers
        if len(words) > 50:
            start = cand
            break

    if start is None:
        start = candidates[0]  # fallback to first

    # Find the next item boundary
    next_item_pattern = r'\bITEM\s+\d+[A-Z]?\s*[\.\-\u2013]|\bItem\s+\d+[A-Z]?\s*[\.\-\u2013]'
    remaining = text[start + 300:]
    end_match = re.search(next_item_pattern, remaining)

    if end_match:
        section = text[start:start + 300 + end_match.start()]
    else:
        section = text[start:start + 15000]

    section = re.sub(r'\n{3,}', '\n\n', section)
    section = re.sub(r' {2,}', ' ', section)
    return section.strip()

def summarize_section(text, label):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}\n")
    # Print first 3000 chars as executive summary
    lines = text.split('\n')
    printed = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip boilerplate SEC headers
        if re.match(r'^(table of contents|index to|signatures|exhibit)', stripped, re.IGNORECASE):
            break
        print(f"  {stripped}")
        printed += len(stripped)
        if printed > 15000:
            print(f"\n  ... [truncated — full section available in output]")
            break

def main():
    parser = argparse.ArgumentParser(description="SEC 10-K Narrative Extractor")
    parser.add_argument('--ticker', '-t', type=str, required=True, help='Stock ticker symbol')
    parser.add_argument('--items', '-i', type=str, default="1,1A,3",
                        help='Comma-separated item numbers to extract (default: 1,1A,3)')
    args = parser.parse_args()

    ticker = args.ticker.upper()
    items_to_extract = [x.strip() for x in args.items.split(",")]

    print(f"Looking up CIK for {ticker}...")
    cik, company_name = lookup_cik(ticker)
    print(f"Found: {company_name} (CIK: {cik})")

    print(f"Finding latest 10-K...")
    filing_info = find_latest_10k(cik)
    print(f"Latest 10-K filed: {filing_info['filing_date']}")
    if filing_info['period_end']:
        print(f"Period end: {filing_info['period_end']}")

    print(f"Fetching filing document...")
    html = fetch_filing_text(filing_info['cik_raw'], filing_info['accession'], filing_info['primary_doc'])
    print(f"Document size: {len(html):,} bytes")

    text = strip_html(html)
    print(f"Extracted text: {len(text):,} characters")

    item_names = {
        "1": "ITEM 1 — BUSINESS",
        "1A": "ITEM 1A — RISK FACTORS",
        "1B": "ITEM 1B — UNRESOLVED STAFF COMMENTS",
        "3": "ITEM 3 — LEGAL PROCEEDINGS",
        "7": "ITEM 7 — MANAGEMENT'S DISCUSSION AND ANALYSIS",
    }

    results = {}
    for item in items_to_extract:
        alt_names = None
        if item == "1":
            alt_names = ["BUSINESS"]
        elif item == "1A":
            alt_names = ["RISK FACTORS"]
        elif item == "3":
            alt_names = ["LEGAL PROCEEDINGS"]

        section = extract_item(text, item, alt_names)
        if section:
            results[item] = section
        else:
            print(f"\n  [!] Item {item} not found in filing.")

    print(f"\n{'='*70}")
    print(f"  10-K EXECUTIVE SUMMARY: {ticker}")
    print(f"  Filing date: {filing_info['filing_date']}")
    print(f"  Period end:  {filing_info.get('period_end', 'N/A')}")
    print(f"{'='*70}")

    for item in items_to_extract:
        if item in results:
            label = item_names.get(item, f"ITEM {item}")
            summarize_section(results[item], label)

    print(f"\n{'='*70}")
    print(f"  End of 10-K Executive Summary for {ticker}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
