#!/usr/bin/env python3
"""
DETAILED DCF DIAGNOSTIC
Shows all intermediate calculations to find the problem
"""

import sys
sys.path.insert(0, 'data')

import dcf_engine
import yfinance as yf
import json

print(f"\n{'='*70}")
print(f"DETAILED DCF DIAGNOSTIC - NVDA")
print(f"{'='*70}\n")

ticker = "NVDA"
spot = 180.0
rf = 0.04

# Run DCF
print(f"Running DCF for {ticker}...")
result = dcf_engine.build_dcf(ticker, spot=spot, rf=rf)

print(f"\n{'-'*70}")
print(f"BASIC RESULTS:")
print(f"{'-'*70}\n")

print(f"Intrinsic Value: ${result.get('intrinsic'):.2f}")
print(f"Current Price: ${spot:.2f}")
print(f"Upside: {result.get('upside_pct'):.1f}%")
print(f"Valuation Bias: {result.get('valuation_bias')}")

print(f"\n{'-'*70}")
print(f"WACC BREAKDOWN:")
print(f"{'-'*70}\n")

wacc_inst = result.get('wacc_institutional', {})
print(f"WACC: {result.get('wacc'):.2%}")
print(f"  Cost of Equity: {wacc_inst.get('cost_of_equity', 0):.2%}")
print(f"  Cost of Debt: {wacc_inst.get('cost_of_debt', 0):.2%}")
print(f"  Asset Beta: {wacc_inst.get('asset_beta', 0):.3f}")
print(f"  Levered Beta (target): {wacc_inst.get('levered_beta_target', 0):.3f}")
print(f"  Weight Equity: {wacc_inst.get('weight_equity_target', 0):.1%}")
print(f"  Weight Debt: {wacc_inst.get('weight_debt_target', 0):.1%}")

print(f"\n{'-'*70}")
print(f"ASSUMPTIONS:")
print(f"{'-'*70}\n")

print(f"Revenue Growth: {result.get('rev_growth'):.1%}")
print(f"Operating Margin: {result.get('op_margin'):.1%}")
print(f"CapEx %: {result.get('capex_pct'):.1%}")
print(f"NWC %: {result.get('nwc_pct'):.1%}")

print(f"\n{'-'*70}")
print(f"ROIC ANALYSIS:")
print(f"{'-'*70}\n")

roic = result.get('roic_analysis', {})
print(f"Current ROIC: {roic.get('current_roic', 0):.1%}")
print(f"Terminal ROIC: {roic.get('terminal_roic', 0):.1%}")
print(f"ROIC - WACC Spread: {roic.get('roic_wacc_spread', 0):.1%}")
print(f"Value Creating: {roic.get('is_value_creating', False)}")

print(f"\n{'-'*70}")
print(f"WORKING CAPITAL:")
print(f"{'-'*70}\n")

wc = result.get('working_capital_detail', {})
print(f"DSO (days): {wc.get('dso_days', 0):.1f}")
print(f"DIO (days): {wc.get('dio_days', 0):.1f}")
print(f"DPO (days): {wc.get('dpo_days', 0):.1f}")
print(f"CCC (days): {wc.get('ccc_days', 0):.1f}")
print(f"NWC % Revenue: {wc.get('nwc_pct_revenue', 0):.1%}")

print(f"\n{'-'*70}")
print(f"TAX ANALYSIS:")
print(f"{'-'*70}\n")

tax = result.get('tax_analysis', {})
print(f"Tax Rate Used: {tax.get('tax_rate_used', 0):.1%}")
print(f"Source: {tax.get('source', 'N/A')}")

print(f"\n{'-'*70}")
print(f"TERMINAL VALUE:")
print(f"{'-'*70}\n")

tv = result.get('terminal_value_detail', {})
print(f"Terminal FCF: ${tv.get('terminal_fcf', 0):,.2f}")
print(f"Growth Rate: {tv.get('growth_rate', 0):.2%}")
print(f"Terminal Value: ${tv.get('terminal_value', 0):,.2f}")
print(f"PV(Terminal): ${tv.get('pv_terminal', 0):,.2f}")
print(f"PV(Explicit): ${tv.get('pv_explicit', 0):,.2f}")

print(f"\n{'-'*70}")
print(f"DEBUG INFO:")
print(f"{'-'*70}\n")

debug = result.get('debug', {})
print(f"Ticker: {debug.get('ticker')}")
print(f"Shares: {debug.get('shares', 0):,.0f}")
print(f"Market Cap: ${debug.get('market_cap', 0):,.0f}")
print(f"Total Debt: ${debug.get('total_debt', 0):,.0f}")

# Calculate enterprise value
ev = tv.get('pv_terminal', 0) + tv.get('pv_explicit', 0)
shares = debug.get('shares', 1)
intrinsic_calc = ev / shares

print(f"\n{'-'*70}")
print(f"ENTERPRISE VALUE CALCULATION:")
print(f"{'-'*70}\n")

print(f"PV(Explicit FCFs): ${tv.get('pv_explicit', 0):,.2f}")
print(f"PV(Terminal Value): ${tv.get('pv_terminal', 0):,.2f}")
print(f"Total Enterprise Value: ${ev:,.2f}")
print(f"÷ Shares Outstanding: {shares:,.0f}")
print(f"= Intrinsic per share: ${intrinsic_calc:.2f}")

print(f"\n{'-'*70}")
print(f"SCENARIOS (Bear/Base/Bull):")
print(f"{'-'*70}\n")

band = result.get('band', {})
print(f"Bear: ${band.get('bear', 0):.2f}")
print(f"Base: ${band.get('base', 0):.2f}")
print(f"Bull: ${band.get('bull', 0):.2f}")

# Get actual yfinance data for comparison
print(f"\n{'-'*70}")
print(f"YFINANCE RAW DATA (for comparison):")
print(f"{'-'*70}\n")

t = yf.Ticker(ticker)
info = t.info or {}
fin = t.financials

print(f"Market Cap: ${info.get('marketCap', 0):,}")
print(f"Beta: {info.get('beta', 0):.3f}")
print(f"Total Debt: ${info.get('totalDebt', 0):,}")
print(f"Shares Outstanding: {info.get('sharesOutstanding', 0):,}")

# Try to get revenue
if fin is not None and not fin.empty:
    try:
        if "Total Revenue" in fin.index:
            rev = fin.loc["Total Revenue"].iloc[0]
            print(f"Most Recent Revenue: ${float(rev):,.0f}")
    except:
        pass

print(f"\n{'-'*70}")
print(f"PROBLEM DIAGNOSIS:")
print(f"{'-'*70}\n")

# Check what's wrong
issues = []

if result.get('intrinsic', 0) < 50:
    issues.append("❌ Intrinsic value ($33) is WAY too low for NVDA")

if result.get('wacc', 0) > 0.14:
    issues.append("❌ WACC (15.5%) seems too high")

if tv.get('pv_terminal', 0) < 1e9:
    issues.append("❌ Terminal value PV is tiny - likely the main problem")

if tv.get('terminal_fcf', 0) < 1e9:
    issues.append("❌ Terminal FCF is very small")

if roic.get('current_roic', 0) < 0.10:
    issues.append("⚠️  Current ROIC seems low")

if issues:
    print("Issues found:")
    for issue in issues:
        print(f"  {issue}")
else:
    print("No obvious issues detected (but valuation still wrong!)")

print(f"\n{'-'*70}")
print(f"LIKELY CAUSES:")
print(f"{'-'*70}\n")

print("""
Based on the diagnostics, the most likely issues are:

1. REVENUE DATA PROBLEM:
   - yfinance might be returning wrong/stale revenue data
   - Or revenue growth calculation is broken

2. TERMINAL VALUE TOO LOW:
   - If terminal FCF is tiny, entire valuation collapses
   - This is 70-80% of total value

3. WACC TOO HIGH:
   - 15.5% WACC is very high
   - Beta of 2.314 might be inflated
   - Or cost of equity calculation is wrong

4. MARGIN/REINVESTMENT ISSUES:
   - If margins or reinvestment are way off
   - FCF could be near zero or negative
""")

print(f"\n{'='*70}\n")

