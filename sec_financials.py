import requests
import time
import argparse
from datetime import datetime

HEADERS = {
    'User-Agent': 'MyFinancialAnalysisTool/1.3 (myemail@example.com)',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'application/json',
    'Connection': 'keep-alive'
}

FALLBACK_TAX_RATE_DISPLAY = 0.15

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
    raise ValueError(f"Ticker '{ticker}' not found in SEC mapping")

def extract_latest_metric(data, concept, unit='USD'):
    try:
        if not data or 'facts' not in data or 'us-gaap' not in data['facts'] or \
           concept not in data['facts']['us-gaap'] or \
           unit not in data['facts']['us-gaap'][concept].get('units', {}):
            return None
        entries = data['facts']['us-gaap'][concept]['units'][unit]
        valid_entries_end = [e for e in entries if 'end' in e and 'fy' in e and 'fp' in e]
        if valid_entries_end:
            valid_entries_end.sort(key=lambda x: x['end'], reverse=True)
            latest = valid_entries_end[0]
        else:
            valid_entries_filed = [e for e in entries if 'filed' in e and 'fy' in e and 'fp' in e]
            if not valid_entries_filed:
                return None
            valid_entries_filed.sort(key=lambda x: x['filed'], reverse=True)
            latest = valid_entries_filed[0]
        value = latest.get('val')
        if value is None:
            return None
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            return None
        return {
            'value': numeric_value,
            'period_desc': f"{latest.get('form', 'N/A')} {latest.get('fp', '')}{latest.get('fy', '')}",
            'period_end_date': latest.get('end', 'N/A'),
            'filed_date': latest.get('filed', 'N/A'),
            'unit': unit,
            'raw_entry': latest
        }
    except Exception as e:
        print(f"Error extracting latest metric for {concept}: {e}")
        return None

def extract_latest_segment(data, concept, segment_value, unit='USD'):
    try:
        if not data or 'facts' not in data or 'us-gaap' not in data['facts'] or \
           concept not in data['facts']['us-gaap'] or \
           unit not in data['facts']['us-gaap'][concept].get('units', {}):
            return None
        entries = data['facts']['us-gaap'][concept]['units'][unit]
        segment_entries_end = [
            e for e in entries
            if 'segment' in e and isinstance(e['segment'], dict)
            and e['segment'].get('value', '').lower() == segment_value.lower()
            and 'end' in e and 'fy' in e and 'fp' in e
        ]
        if segment_entries_end:
            segment_entries_end.sort(key=lambda x: x['end'], reverse=True)
            latest = segment_entries_end[0]
        else:
            segment_entries_filed = [
                e for e in entries
                if 'segment' in e and isinstance(e['segment'], dict)
                and e['segment'].get('value', '').lower() == segment_value.lower()
                and 'filed' in e and 'fy' in e and 'fp' in e
            ]
            if not segment_entries_filed:
                return None
            segment_entries_filed.sort(key=lambda x: x['filed'], reverse=True)
            latest = segment_entries_filed[0]
        value = latest.get('val')
        if value is None:
            return None
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            return None
        return {
            'value': numeric_value,
            'period_desc': f"{latest.get('form', 'N/A')} {latest.get('fp', '')}{latest.get('fy', '')}",
            'period_end_date': latest.get('end', 'N/A'),
            'filed_date': latest.get('filed', 'N/A'),
            'unit': unit,
            'segment': segment_value,
            'raw_entry': latest
        }
    except Exception as e:
        print(f"Error extracting latest segment for {concept} - {segment_value}: {e}")
        return None

def fetch_financials(cik):
    print(f"Fetching latest financial data for CIK {cik}...")
    api_data = None
    try:
        time.sleep(0.15)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        api_data = response.json()
        print("Data fetched successfully.")
    except Exception as e:
        print(f"API Request Error: {str(e)}")
        return None

    if not api_data or 'facts' not in api_data or 'us-gaap' not in api_data['facts']:
        print("Error: Fetched data is missing 'facts' or 'us-gaap' section.")
        return None

    print("Extracting financial metrics...")
    metrics = {}

    metrics['Revenue'] = extract_latest_metric(api_data, 'Revenues')
    metrics['NetIncome'] = extract_latest_metric(api_data, 'NetIncomeLoss')
    metrics['GrossProfit'] = extract_latest_metric(api_data, 'GrossProfit')
    metrics['InterestExpense'] = extract_latest_metric(api_data, 'InterestExpense') \
                                 or extract_latest_metric(api_data, 'InterestExpenseDebt') \
                                 or extract_latest_metric(api_data, 'InterestAndDebtExpense')
    metrics['IncomeTaxExpense'] = extract_latest_metric(api_data, 'IncomeTaxExpenseBenefit')

    metrics['PreTaxIncome'] = extract_latest_metric(api_data, 'IncomeLossFromContinuingOperationsBeforeIncomeTaxExpenseBenefit') \
                             or extract_latest_metric(api_data, 'IncomeLossBeforeIncomeTaxExpenseBenefit')

    pre_tax_income_source = "Fetched"
    if metrics.get('PreTaxIncome') is None:
        print("Direct PreTaxIncome not found. Attempting to calculate from NetIncome + IncomeTaxExpense...")
        ni = metrics.get('NetIncome')
        tax_exp_for_calc = metrics.get('IncomeTaxExpense')
        if ni and ni.get('value') is not None and \
           tax_exp_for_calc and tax_exp_for_calc.get('value') is not None and \
           ni.get('period_end_date') == tax_exp_for_calc.get('period_end_date'):
            calculated_pre_tax_val = ni['value'] + tax_exp_for_calc['value']
            metrics['PreTaxIncome'] = {
                'value': calculated_pre_tax_val,
                'period_desc': ni['period_desc'],
                'period_end_date': ni['period_end_date'],
                'filed_date': ni['filed_date'],
                'unit': 'USD',
                'raw_entry': {
                    'form': ni['raw_entry'].get('form'),
                    'fy': ni['raw_entry'].get('fy'),
                    'fp': ni['raw_entry'].get('fp'),
                    'end': ni['raw_entry'].get('end')
                }
            }
            pre_tax_income_source = "Calculated (NI + TaxExp)"
            print(f"Successfully calculated PreTaxIncome: {calculated_pre_tax_val/1e9:.2f}B for period {ni['period_desc']}")
        else:
            reason_calc_fail = []
            if not ni or ni.get('value') is None:
                reason_calc_fail.append("NetIncome missing")
            if not tax_exp_for_calc or tax_exp_for_calc.get('value') is None:
                reason_calc_fail.append("IncomeTaxExpense missing")
            if ni and tax_exp_for_calc and ni.get('period_end_date') != tax_exp_for_calc.get('period_end_date'):
                reason_calc_fail.append(f"Mismatched periods (NI: {ni.get('period_desc')}, Tax: {tax_exp_for_calc.get('period_desc')})")
            print(f"Could not calculate PreTaxIncome: {'; '.join(reason_calc_fail)}.")
    if metrics.get('PreTaxIncome'):
        metrics['PreTaxIncome']['source'] = pre_tax_income_source

    metrics['EPS'] = extract_latest_metric(api_data, 'EarningsPerShareDiluted', 'USD/shares')
    metrics['Cash'] = extract_latest_metric(api_data, 'CashAndCashEquivalentsAtCarryingValue')
    metrics['LongTermDebt'] = extract_latest_metric(api_data, 'LongTermDebt')
    metrics['ShortTermDebt'] = extract_latest_metric(api_data, 'DebtCurrent') \
                              or extract_latest_metric(api_data, 'ShortTermBorrowings') \
                              or extract_latest_metric(api_data, 'CommercialPaper') \
                              or extract_latest_metric(api_data, 'CurrentPortionOfLongTermDebt')
    metrics['iPhoneRevenue'] = extract_latest_segment(api_data, 'RevenueFromContractWithCustomerExcludingAssessedTax', 'iphone')
    metrics['ServicesRevenue'] = extract_latest_segment(api_data, 'RevenueFromContractWithCustomerExcludingAssessedTax', 'services')

    metrics['GrossMargin'] = None
    rev = metrics.get('Revenue')
    gp = metrics.get('GrossProfit')
    if rev and gp and rev.get('value') is not None and rev['value'] != 0 and gp.get('value') is not None and \
       rev.get('period_end_date') == gp.get('period_end_date'):
        try:
            metrics['GrossMargin'] = {
                'value': (gp['value'] / rev['value']) * 100,
                'period_desc': rev['period_desc'],
                'unit': '%'
            }
        except (TypeError, ZeroDivisionError) as e:
            print(f"Could not calculate Gross Margin: {e}")

    metrics['EffectiveTaxRate'] = None
    etr_calculation_successful = False
    successfully_calculated_etr_value = None
    etr_source_period = "N/A"

    tax_exp_for_etr = metrics.get('IncomeTaxExpense')
    pre_tax_for_etr = metrics.get('PreTaxIncome')

    if tax_exp_for_etr and tax_exp_for_etr.get('value') is not None and \
       pre_tax_for_etr and pre_tax_for_etr.get('value') is not None and \
       tax_exp_for_etr.get('period_end_date') == pre_tax_for_etr.get('period_end_date') and \
       pre_tax_for_etr['value'] > 0:
        try:
            etr_value = tax_exp_for_etr['value'] / pre_tax_for_etr['value']
            if -0.5 < etr_value < 1.0:
                successfully_calculated_etr_value = etr_value
                etr_calculation_successful = True
                etr_source_period = tax_exp_for_etr['period_desc']
                metrics['EffectiveTaxRate'] = {
                    'value': successfully_calculated_etr_value,
                    'period_desc': etr_source_period,
                    'unit': 'decimal',
                    'source': f'Calculated ({pre_tax_for_etr.get("source", "Fetched")} PreTax)'
                }
                print(f"Successfully calculated ETR: {successfully_calculated_etr_value:.3f} based on {etr_source_period} (using {pre_tax_for_etr.get('source', 'Fetched')} PreTaxIncome)")
            else:
                print(f"Warning: Calculated ETR ({etr_value:.3f}) seems unreasonable. Cannot use for CoD.")
        except (TypeError, ZeroDivisionError) as e:
            print(f"Could not calculate ETR due to error: {e}. Cannot use for CoD.")

    if not etr_calculation_successful:
        reason = []
        if not tax_exp_for_etr or tax_exp_for_etr.get('value') is None:
            reason.append("IncomeTaxExpense missing")
        if not pre_tax_for_etr or pre_tax_for_etr.get('value') is None:
            reason.append(f"PreTaxIncome missing")
        if tax_exp_for_etr and pre_tax_for_etr and tax_exp_for_etr.get('period_end_date') != pre_tax_for_etr.get('period_end_date'):
            reason.append(f"Mismatched periods (Tax: {tax_exp_for_etr.get('period_desc')}, PreTax: {pre_tax_for_etr.get('period_desc')})")
        if pre_tax_for_etr and pre_tax_for_etr.get('value') is not None and pre_tax_for_etr['value'] <= 0:
            reason.append(f"Pre-tax income zero or negative ({pre_tax_for_etr.get('value'):.2f})")
        if successfully_calculated_etr_value is None and not reason and tax_exp_for_etr and pre_tax_for_etr:
            reason.append("Calculated ETR value unreasonable")
        if reason:
            print(f"Warning: Cannot use calculated ETR ({'; '.join(reason)}). After-Tax CoD will not be calculated.")
        else:
            print(f"Warning: ETR calculation not performed. After-Tax CoD will not be calculated.")
        metrics['EffectiveTaxRate'] = {
            'value': FALLBACK_TAX_RATE_DISPLAY,
            'period_desc': 'N/A',
            'unit': 'decimal',
            'source': 'Fallback (Not Used for CoD)'
        }

    metrics['CostOfDebt'] = None
    interest = metrics.get('InterestExpense')
    if interest and interest.get('value') is not None:
        interest_val = interest['value']
        is_fy_period = interest['raw_entry'].get('fp') == 'FY'
        annualized_interest = interest_val if is_fy_period else interest_val * 4
        ltd = metrics.get('LongTermDebt')
        std = metrics.get('ShortTermDebt')
        ltd_val = ltd['value'] if ltd and ltd.get('value') is not None else 0
        std_val = std['value'] if std and std.get('value') is not None else 0
        total_debt = ltd_val + std_val
        if total_debt > 0:
            try:
                pre_tax_cod_pct = (annualized_interest / total_debt) * 100
                after_tax_cod_pct = None
                tax_rate_used_for_cod = None
                tax_rate_source_for_cod = "N/A (ETR calculation failed/invalid)"
                if etr_calculation_successful and successfully_calculated_etr_value is not None:
                    after_tax_cod_pct = pre_tax_cod_pct * (1 - successfully_calculated_etr_value)
                    tax_rate_used_for_cod = successfully_calculated_etr_value
                    tax_rate_source_for_cod = f"Calculated ({etr_source_period}, using {pre_tax_for_etr.get('source', 'Fetched')} PreTax)"
                metrics['CostOfDebt'] = {
                    'pre_tax_pct': pre_tax_cod_pct,
                    'after_tax_pct': after_tax_cod_pct,
                    'total_debt_used': total_debt,
                    'annualized_interest_used': annualized_interest,
                    'interest_period': interest['period_desc'],
                    'debt_period_ltd': ltd['period_desc'] if ltd else 'N/A',
                    'debt_period_std': std['period_desc'] if std else 'N/A',
                    'tax_rate_used_for_cod': tax_rate_used_for_cod,
                    'tax_rate_source_for_cod': tax_rate_source_for_cod
                }
            except (TypeError, ZeroDivisionError) as e:
                print(f"Error calculating cost of debt: {e}")
                metrics['CostOfDebt'] = None
        else:
            print("Warning: Total debt is zero or missing, cannot calculate Cost of Debt.")
    else:
        print("Warning: Interest Expense data not found or invalid, cannot calculate Cost of Debt.")

    print("Extraction complete.")
    return metrics

def fmt_currency(metric_data, divisor=1, suffix=''):
    if metric_data and metric_data.get('value') is not None:
        try:
            v = metric_data['value']
            return f"${v/divisor:,.2f}{suffix} ({metric_data.get('period_desc', 'N/A')})"
        except (TypeError, ValueError):
            return "Error formatting"
    return "N/A"

def fmt_percent(metric_data, decimals=2):
    if metric_data and metric_data.get('value') is not None:
        try:
            v = metric_data['value']
            return f"{v:.{decimals}f}% ({metric_data.get('period_desc', 'N/A')})"
        except (TypeError, ValueError):
            return "Error formatting"
    return "N/A"

def fmt_rate(metric_data, decimals=1):
    if metric_data and metric_data.get('value') is not None:
        try:
            v = metric_data['value']
            src = metric_data.get('source', '')
            src_info = f" ({src})" if src else ""
            return f"{v:.{decimals}%} ({metric_data.get('period_desc', 'N/A')}){src_info}"
        except (TypeError, ValueError):
            return "Error formatting"
    return "N/A"

def fmt_pre_tax(metric_data):
    if metric_data and metric_data.get('value') is not None:
        try:
            v = metric_data['value']
            src = metric_data.get('source', '')
            src_info = f" ({src})" if src else ""
            return f"${v/1e9:,.2f}B ({metric_data.get('period_desc', 'N/A')}){src_info}"
        except (TypeError, ValueError):
            return "Error formatting"
    return "N/A"

def display_results(ticker, company_name, metrics):
    print("\n" + "=" * 70)
    print(f"  SEC FINANCIAL ANALYSIS: {ticker.upper()} ({company_name})")
    print("=" * 70)

    print("\n--- Income Statement ---")
    print(f"  {'Revenue':<20} {fmt_currency(metrics.get('Revenue'), divisor=1e9, suffix='B')}")
    print(f"  {'Gross Profit':<20} {fmt_currency(metrics.get('GrossProfit'), divisor=1e9, suffix='B')}")
    print(f"  {'Gross Margin':<20} {fmt_percent(metrics.get('GrossMargin'), decimals=1)}")
    print(f"  {'Pre-Tax Income':<20} {fmt_pre_tax(metrics.get('PreTaxIncome'))}")
    print(f"  {'Income Tax Exp.:':<20} {fmt_currency(metrics.get('IncomeTaxExpense'), divisor=1e9, suffix='B')}")
    print(f"  {'Net Income':<20} {fmt_currency(metrics.get('NetIncome'), divisor=1e9, suffix='B')}")
    print(f"  {'Eff. Tax Rate':<20} {fmt_rate(metrics.get('EffectiveTaxRate'))}")
    print(f"  {'Diluted EPS':<20} {fmt_currency(metrics.get('EPS'), suffix='/share')}")

    print("\n--- Balance Sheet & Debt ---")
    print(f"  {'Cash & Equiv.:':<20} {fmt_currency(metrics.get('Cash'), divisor=1e9, suffix='B')}")
    print(f"  {'Short-Term Debt':<20} {fmt_currency(metrics.get('ShortTermDebt'), divisor=1e9, suffix='B')}")
    print(f"  {'Long-Term Debt':<20} {fmt_currency(metrics.get('LongTermDebt'), divisor=1e9, suffix='B')}")
    print(f"  {'Interest Exp.:':<20} {fmt_currency(metrics.get('InterestExpense'), divisor=1e6, suffix='M')}")

    print("\n--- Segment Revenues ---")
    print(f"  {'iPhone Revenue':<20} {fmt_currency(metrics.get('iPhoneRevenue'), divisor=1e9, suffix='B')}")
    print(f"  {'Services Rev.':<20} {fmt_currency(metrics.get('ServicesRevenue'), divisor=1e9, suffix='B')}")

    print("\n--- Estimated Cost of Debt ---")
    cod = metrics.get('CostOfDebt')
    if cod:
        print(f"  {'Total Debt Used':<20} ${cod['total_debt_used']/1e9:,.2f}B  (LTD: {cod['debt_period_ltd']}, STD: {cod['debt_period_std']})")
        print(f"  {'Annualized Interest':<20} ${cod['annualized_interest_used']/1e6:,.2f}M  (Based on {cod['interest_period']})")
        print(f"  {'Pre-Tax Cost of Debt':<20} {cod['pre_tax_pct']:.2f}%")
        if cod.get('after_tax_pct') is not None and cod.get('tax_rate_used_for_cod') is not None:
            print(f"  {'Eff. Tax Rate Used':<20} {cod['tax_rate_used_for_cod']:.1%} ({cod['tax_rate_source_for_cod']})")
            print(f"  {'After-Tax Cost of Debt':<20} {cod['after_tax_pct']:.2f}%")
        else:
            print(f"  {'Eff. Tax Rate Used':<20} N/A ({cod.get('tax_rate_source_for_cod', 'ETR calculation failed')})")
            print(f"  {'After-Tax Cost of Debt':<20} N/A (Requires successfully calculated ETR)")
    else:
        print("  Cost of Debt: Could not be calculated (Missing Interest Expense or Total Debt).")

    print("\n" + "=" * 70)
    print(f"  * Values based on latest SEC filings as of {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  * Cost of Debt is estimated. After-Tax CoD calculated ONLY if ETR derived from data.")
    print(f"  * Displayed ETR may show fallback ({FALLBACK_TAX_RATE_DISPLAY:.1%}) for context if calculation failed.")
    print(f"  * Pre-Tax Income may be calculated (Net Income + Tax Expense) if not directly found.")
    print(f"  * Accuracy depends on SEC API availability and XBRL tagging consistency.")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="SEC Financial Analysis Tool")
    parser.add_argument('--ticker', '-t', type=str, required=True, help='Stock ticker symbol (e.g., AAPL, MSFT, NVDA)')
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"Looking up CIK for {ticker}...")
    cik, company_name = lookup_cik(ticker)
    print(f"Found: {company_name} (CIK: {cik})")

    metrics = fetch_financials(cik)
    if metrics:
        display_results(ticker, company_name, metrics)
    else:
        print("\nFailed to fetch or process financial data.")

if __name__ == "__main__":
    main()
