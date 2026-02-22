#!/usr/bin/env python3
"""
DCF DIAGNOSTIC SCRIPT
Tests the DCF engine directly to find errors

Usage:
    python3 test_dcf_direct.py
"""

import sys
import os

# Test both old and new engines
print(f"\n{'='*70}")
print(f"DCF ENGINE DIAGNOSTIC")
print(f"{'='*70}\n")

# ========================================
# TEST 1: CHECK IF FILES EXIST
# ========================================

print(f"TEST 1: Checking file locations...")
print(f"{'-'*70}\n")

files_to_check = [
    ("data/dcf_engine.py", "Current DCF engine"),
    ("data/dcf_engine_OLD.py", "Old DCF backup"),
    ("dcf_engine_v2.py", "New DCF v2"),
]

for filepath, description in files_to_check:
    exists = os.path.exists(filepath)
    status = "✅ EXISTS" if exists else "❌ MISSING"
    print(f"{status}: {filepath} ({description})")

print(f"")

# ========================================
# TEST 2: TRY IMPORTING CURRENT ENGINE
# ========================================

print(f"\nTEST 2: Testing current dcf_engine.py...")
print(f"{'-'*70}\n")

try:
    sys.path.insert(0, 'data')
    import dcf_engine
    print(f"✅ Successfully imported dcf_engine")
    print(f"   Functions available: {[f for f in dir(dcf_engine) if not f.startswith('_')]}")
    
    # Check if build_dcf exists
    if hasattr(dcf_engine, 'build_dcf'):
        print(f"✅ build_dcf() function found")
    else:
        print(f"❌ build_dcf() function NOT found!")
        
except Exception as e:
    print(f"❌ Failed to import dcf_engine")
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()

# ========================================
# TEST 3: TRY RUNNING DCF
# ========================================

print(f"\nTEST 3: Testing DCF calculation with NVDA...")
print(f"{'-'*70}\n")

try:
    import dcf_engine
    
    ticker = "NVDA"
    spot = 180.0
    rf = 0.04
    
    print(f"Calling: build_dcf('{ticker}', spot={spot}, rf={rf})")
    print(f"Please wait (downloading data from yfinance)...\n")
    
    result = dcf_engine.build_dcf(ticker, spot=spot, rf=rf)
    
    if result is None:
        print(f"❌ DCF returned None!")
    elif not isinstance(result, dict):
        print(f"❌ DCF returned wrong type: {type(result)}")
    else:
        print(f"✅ DCF executed successfully!\n")
        print(f"Results:")
        print(f"  Intrinsic: ${result.get('intrinsic', 'N/A')}")
        print(f"  Upside: {result.get('upside_pct', 'N/A')}%")
        print(f"  WACC: {result.get('wacc', 'N/A')}")
        
        # Check for v2 fields
        if 'methodology' in result:
            print(f"  Methodology: {result['methodology']}")
            print(f"  Version: {result.get('version', 'N/A')}")
            print(f"\n✅ This is the NEW institutional-grade engine!")
        else:
            print(f"\n⚠️  This is still the OLD engine")
        
        # Show all keys
        print(f"\nAll keys in result:")
        for key in sorted(result.keys()):
            print(f"  - {key}")
            
except Exception as e:
    print(f"❌ DCF calculation failed!")
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()

# ========================================
# TEST 4: CHECK YFINANCE
# ========================================

print(f"\n{'-'*70}")
print(f"TEST 4: Testing yfinance data access...")
print(f"{'-'*70}\n")

try:
    import yfinance as yf
    print(f"✅ yfinance imported successfully")
    
    print(f"Fetching NVDA data...")
    t = yf.Ticker("NVDA")
    info = t.info
    
    if info:
        print(f"✅ Got NVDA data")
        print(f"  Market Cap: ${info.get('marketCap', 'N/A'):,}")
        print(f"  Beta: {info.get('beta', 'N/A')}")
    else:
        print(f"⚠️  yfinance returned empty info")
        
except Exception as e:
    print(f"❌ yfinance failed: {e}")

# ========================================
# SUMMARY & RECOMMENDATIONS
# ========================================

print(f"\n{'='*70}")
print(f"DIAGNOSTIC SUMMARY")
print(f"{'='*70}\n")

print(f"If you see errors above, here's what to do:\n")

print(f"1. FILE MISSING:")
print(f"   → Make sure dcf_engine_v2.py is in your current directory")
print(f"   → Copy it to data/dcf_engine.py")
print(f"")

print(f"2. IMPORT ERRORS:")
print(f"   → Check for syntax errors in dcf_engine.py")
print(f"   → Make sure you copied the ENTIRE file")
print(f"")

print(f"3. DCF RETURNS NONE:")
print(f"   → Check yfinance can access data")
print(f"   → Look for exceptions in the traceback")
print(f"")

print(f"4. YFINANCE ERRORS:")
print(f"   → Install: pip install yfinance --break-system-packages")
print(f"   → Check internet connection")
print(f"")

print(f"{'='*70}\n")


