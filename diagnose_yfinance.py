#!/usr/bin/env python3
# Test what data yfinance actually returns for NVDA

import yfinance as yf
import pandas as pd

print("=" * 80)
print("TESTING YFINANCE DATA FOR NVDA")
print("=" * 80)

ticker = "NVDA"
t = yf.Ticker(ticker)

# Test 1: Earnings Dates
print("\n1. EARNINGS DATES:")
print("-" * 80)
try:
    earnings_dates = t.get_earnings_dates(limit=4)
    if earnings_dates is not None and not earnings_dates.empty:
        print(f"✅ Got {len(earnings_dates)} earnings events")
        print("\nColumns available:")
        print(earnings_dates.columns.tolist())
        print("\nFirst event:")
        print(earnings_dates.iloc[0])
        
        # Check what revenue data is available
        if 'Revenue Estimate' in earnings_dates.columns:
            print("\n✅ Revenue Estimate column exists")
        else:
            print("\n❌ No Revenue Estimate column")
            
        if 'Revenue Actual' in earnings_dates.columns:
            print("✅ Revenue Actual column exists")
        else:
            print("❌ No Revenue Actual column")
    else:
        print("❌ No earnings dates returned")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Quarterly Financials (Revenue backup)
print("\n\n2. QUARTERLY FINANCIALS (Revenue backup):")
print("-" * 80)
try:
    financials = t.quarterly_financials
    if financials is not None and not financials.empty:
        print(f"✅ Got quarterly financials")
        print("\nRows available:")
        print(financials.index.tolist()[:10])
        
        if 'Total Revenue' in financials.index:
            print("\n✅ Total Revenue row exists")
            print("\nLast 4 quarters revenue:")
            print(financials.loc['Total Revenue'].head(4))
        else:
            print("\n❌ No Total Revenue row")
    else:
        print("❌ No quarterly financials")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: News/Headlines
print("\n\n3. NEWS/HEADLINES:")
print("-" * 80)
try:
    news = t.news
    if news and len(news) > 0:
        print(f"✅ Got {len(news)} news articles")
        print("\nFirst article:")
        print(f"Title: {news[0].get('title', 'N/A')}")
        print(f"Publisher: {news[0].get('publisher', 'N/A')}")
        print(f"Timestamp: {news[0].get('providerPublishTime', 'N/A')}")
        
        # Show first 5 titles
        print("\nFirst 5 headlines:")
        for i, article in enumerate(news[:5]):
            print(f"{i+1}. {article.get('title', 'N/A')}")
    else:
        print("❌ No news articles returned")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 4: Info (for general data)
print("\n\n4. COMPANY INFO:")
print("-" * 80)
try:
    info = t.info
    if info:
        print(f"✅ Got company info")
        # Check for earnings-related fields
        earnings_fields = ['recommendationKey', 'numberOfAnalystOpinions', 
                          'targetHighPrice', 'targetLowPrice', 'targetMeanPrice']
        print("\nEarnings-related fields:")
        for field in earnings_fields:
            if field in info:
                print(f"  {field}: {info[field]}")
    else:
        print("❌ No company info")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 5: Calendar (alternative earnings source)
print("\n\n5. CALENDAR (Alternative earnings data):")
print("-" * 80)
try:
    calendar = t.calendar
    if calendar is not None and not calendar.empty:
        print("✅ Got calendar data")
        print(calendar)
    else:
        print("❌ No calendar data")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)

