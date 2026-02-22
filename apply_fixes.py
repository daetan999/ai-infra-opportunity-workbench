#!/usr/bin/env python3
"""
AUTOMATED FIX SCRIPT
Applies all 4 critical fixes to your app.py and Gemini files
"""

import re
import shutil
from pathlib import Path

def backup_file(filepath):
    """Create backup before modifying"""
    backup_path = f"{filepath}.backup"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backed up: {backup_path}")
    return backup_path

def fix_app_py():
    """Fix all issues in app.py"""
    
    app_path = "app.py"
    print(f"\n📝 Fixing {app_path}...")
    
    # Backup first
    backup_file(app_path)
    
    with open(app_path, 'r') as f:
        content = f.read()
    
    original_lines = len(content.split('\n'))
    
    # FIX #1: Replace earn_track with earnings_track
    print("🔧 Fix #1: Replacing earn_track → earnings_track...")
    content = content.replace('earn_track', 'earnings_track')
    
    # FIX #2: Move earnings_info initialization before mode branching
    print("🔧 Fix #2: Moving earnings_info initialization...")
    
    # Find the line "if analysis_mode == "stock":"
    stock_mode_pattern = r'(\s+if analysis_mode == "stock":)'
    
    # Earnings initialization code to insert
    earnings_init_code = '''
    # =========================
    # Earnings Info (SHARED BY BOTH MODES)
    # =========================
    # CRITICAL FIX: Initialize earnings_info BEFORE mode branching
    print(f"🔍 Fetching earnings info for {ticker}...")
    
    earnings_info = None
    try:
        earnings_info = EARNINGS_CACHE.get_or_set(
            f"earn:{ticker}",
            lambda: get_earnings_info(t, ticker),
            ttl_sec=6 * 3600,
        )
        print(f"✅ Earnings info loaded")
    except Exception as e:
        print(f"❌ Earnings info fetch failed: {e}")
        earnings_info = None
    
    # Earnings fallback
    try:
        if not earnings_info or not any(earnings_info.values()):
            try:
                cal = t.calendar if hasattr(t, "calendar") else {}
                edates = None
                try:
                    edates = t.get_earnings_dates()
                except Exception:
                    edates = None
                
                fallback = {}
                if isinstance(cal, dict) and cal:
                    fallback["calendar"] = str(cal)
                if edates:
                    fallback["earnings_dates_raw"] = str(edates)
                if fallback:
                    earnings_info = earnings_info or {}
                    earnings_info.update({"__note__": "fallback used", "fallback": fallback})
                    print(f"📊 Earnings fallback used for {ticker}")
            except Exception as e:
                print(f"⚠️ Earnings fallback error: {e}")
    except Exception:
        pass
    
    # Ensure always a dict
    if earnings_info is None:
        earnings_info = {"__note__": "earnings unavailable"}
    
    # Refresh if empty
    try:
        if not (earnings_info.get('earnings_date_us') or earnings_info.get('earnings_date_utc')):
            fresh = get_earnings_info(t, ticker)
            if fresh and (fresh.get('earnings_date_us') or fresh.get('earnings_date_utc')):
                earnings_info = fresh
                EARNINGS_CACHE.set(f"earn:{ticker}", earnings_info, ttl_sec=2 * 3600)
                print(f"🔄 Earnings cache refreshed")
    except Exception as e:
        print(f"⚠️ Earnings refresh skipped: {e}")
    
'''
    
    # Insert before "if analysis_mode == "stock":"
    content = re.sub(stock_mode_pattern, earnings_init_code + r'\1', content, count=1)
    
    # FIX #3: Remove duplicate earnings_info code from stock mode (lines ~1440-1487)
    print("🔧 Fix #3: Removing duplicate earnings code from stock mode...")
    
    # Pattern to match the duplicate code block in stock mode
    duplicate_stock_pattern = r'        # earnings \(still included; best-effort\)[\s\S]*?        except Exception as e:\s*print\("earnings refresh skipped:", e\)'
    
    content = re.sub(duplicate_stock_pattern, '        # earnings_info now initialized before mode branching', content, count=1)
    
    # FIX #4: Remove broken duplicate from options mode (lines ~2224-2253)
    print("🔧 Fix #4: Removing broken duplicate from options mode...")
    
    # Pattern to match the broken code in options mode
    duplicate_options_pattern = r'    # --- Earnings fallback: try other yfinance endpoints if primary returns empty[\s\S]*?    # Make sure there is always a dict for template\s*if earnings_info is None:\s*earnings_info = \{"__note__": "earnings unavailable"\}'
    
    content = re.sub(duplicate_options_pattern, '    # earnings_info already initialized before mode branching', content, count=1)
    
    # Write fixed content
    with open(app_path, 'w') as f:
        f.write(content)
    
    fixed_lines = len(content.split('\n'))
    print(f"✅ Fixed {app_path}: {original_lines} → {fixed_lines} lines")
    
    return True

def fix_gemini_confidence():
    """Fix import in gemini_confidence.py"""
    
    conf_path = "data/gemini_confidence.py"
    print(f"\n📝 Fixing {conf_path}...")
    
    # Backup first
    backup_file(conf_path)
    
    with open(conf_path, 'r') as f:
        content = f.read()
    
    # Fix import statement
    print("🔧 Fixing import: gemini_analyst → gemini_analyst_v2...")
    content = content.replace(
        'from gemini_analyst import',
        'from gemini_analyst_v2 import'
    )
    
    with open(conf_path, 'w') as f:
        f.write(content)
    
    print(f"✅ Fixed {conf_path}")
    return True

def main():
    """Run all fixes"""
    
    print("="*70)
    print("🔧 AUTOMATED FIX SCRIPT - APPLYING ALL FIXES")
    print("="*70)
    
    try:
        # Check files exist
        if not Path("app.py").exists():
            print("❌ Error: app.py not found in current directory")
            print("Please run this script from your project root directory")
            return False
        
        if not Path("data/gemini_confidence.py").exists():
            print("❌ Error: data/gemini_confidence.py not found")
            return False
        
        # Apply fixes
        success = True
        
        # Fix app.py
        if not fix_app_py():
            success = False
        
        # Fix gemini_confidence.py
        if not fix_gemini_confidence():
            success = False
        
        if success:
            print("\n" + "="*70)
            print("✅ ALL FIXES APPLIED SUCCESSFULLY!")
            print("="*70)
            print("\n📋 Next steps:")
            print("1. Install new Gemini package:")
            print("   pip uninstall google-generativeai -y")
            print("   pip install google-genai --break-system-packages")
            print("\n2. Install gemini_analyst_v2.py:")
            print("   cp gemini_analyst_NEW.py data/gemini_analyst_v2.py")
            print("\n3. Restart server:")
            print("   pkill -f 'python.*run.py'")
            print("   python3 run.py")
            print("\n4. Test:")
            print("   - Try MU in OPTIONS mode")
            print("   - Try auto-select expiry")
            print("   - Check for AI confidence (not 48%)")
            print()
            return True
        else:
            print("\n❌ Some fixes failed - check errors above")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during fix: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

