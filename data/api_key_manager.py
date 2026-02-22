# data/api_key_manager.py
# API Key Rotation System - 5 Accounts = 125 calls/day
# Automatically rotates through 5 sets of API keys to expand capacity

import json
import os
from datetime import datetime, date
from typing import Dict, Optional, Tuple

# ========================================
# API KEY CONFIGURATION - 5 SETS
# ========================================

# ========================================
# SET 1 - daetan999@gmail.com
# ========================================
#ALPHA_VANTAGE_KEY = " S2P33SDFC20QS6KE"
#FMP_KEY = "1MiWM5ABxN3xsyshtu1gHZSZ4C6LU8uJ"
#NEWS_API_KEY = "b0f4169249e3414582069134a5e4a2a1"

# ========================================
# SET 2 - daetanlovesleep@gmail.com
# ========================================
#ALPHA_VANTAGE_KEY = “WZLS876HIRLAVE97”
#FMP_KEY = "AfY0JceMawOWCCIR7c9E4Y7y70R6hp5q"
#NEWS_API_KEY = "e9e57a1dfb00487c947d6faae8e5aeef"

# ========================================
# SET 3 - vanessalim420123@gmail.com
# ========================================
#ALPHA_VANTAGE_KEY = “G3SIPCVKZ8H5UMH0”
#FMP_KEY = "zPfXdy7ltfGH53MohtJ01OGXxuCl0Ukq”
#NEWS_API_KEY = “d36323e7d22040588fd781b47ff8d84c”

# ========================================
# SET 4 - tankirkjundae@gmail.com
# ========================================
#ALPHA_VANTAGE_KEY = “3FM2K9S4CL14UNW5”
#FMP_KEY = "TMHnjr2bW5yryaRC46SCNCfQdvCOOcgy”
#NEWS_API_KEY (using bobbybombastic34@gmail.com) = “4cf39d2d49554225be1fea35fcb630e4”

# ========================================
# SET 5 - dae26811@gmail.com
# ========================================
#ALPHA_VANTAGE_KEY = “AM19MKSBHLOHBDT4”
#FMP_KEY = "WVCDCcHfSUWfyutsKPVPOyn1TL6ZL5Nj”
#NEWS_API_KEY = “5d7bdd4d040442979c7f6bf0849a152a”

API_KEY_SETS = [
    {
        "name": "Set 1 (Primary)",
        "alpha_vantage": "32B2RBELB93I0I4H",                    #  Set 1 Alpha Vantage key
        "fmp": "1MiWM5ABxN3xsyshtu1gHZSZ4C6LU8uJ",               #   Set 1 FMP key
        "newsapi": "b0f4169249e3414582069134a5e4a2a",          #   Set 1 NewsAPI key
    },
    {
        "name": "Set 2 (Secondary)",
        "alpha_vantage": "WZLS876HIRLAVE97",                        #   Set 2 Alpha Vantage key
        "fmp": "AfY0JceMawOWCCIR7c9E4Y7y70R6hp5q",               #   Set 2 FMP key
        "newsapi": "e9e57a1dfb00487c947d6faae8e5aeef",          #   Set 2 NewsAPI key
    },
    {
        "name": "Set 3 (Tertiary)",
        "alpha_vantage": "G3SIPCVKZ8H5UMH0",                        #   Set 3 Alpha Vantage key
        "fmp": "zPfXdy7ltfGH53MohtJ01OGXxuCl0Ukq",               #   Set 3 FMP key
        "newsapi": "d36323e7d22040588fd781b47ff8d84c",          #   Set 3 NewsAPI key
    },
    {
        "name": "Set 4 (Backup 1)",
        "alpha_vantage": "3FM2K9S4CL14UNW5",                    #   Set 4 Alpha Vantage key
        "fmp": "TMHnjr2bW5yryaRC46SCNCfQdvCOOcgy",               #   Set 4 FMP key
        "newsapi": "4cf39d2d49554225be1fea35fcb630e4",          #   Set 4 NewsAPI key
    },
    {
        "name": "Set 5 (Backup 2)",
        "alpha_vantage": "AM19MKSBHLOHBDT4",                    #   Set 5 Alpha Vantage key
        "fmp": "WVCDCcHfSUWfyutsKPVPOyn1TL6ZL5Nj",               #   Set 5 FMP key
        "newsapi": "5d7bdd4d040442979c7f6bf0849a152a",          #   Set 5 NewsAPI key
    },
]

# Limit per set (Alpha Vantage's 25 calls/day is the bottleneck)
CALLS_PER_SET = 25

# File to track usage (persists across server restarts)
USAGE_TRACKER_FILE = "/tmp/api_usage_tracker.json"

# ========================================
# USAGE TRACKER & ROTATION MANAGER
# ========================================

class APIKeyManager:
    """
    Manages API key rotation across 5 sets.
    
    Automatically switches to next set when current set hits limit.
    Tracks usage persistently, resets daily.
    """
    
    def __init__(self):
        self.usage = self._load_usage()
        self.current_set_index = 0
        self._determine_current_set()
    
    def _load_usage(self) -> Dict:
        """Load usage tracker from file."""
        if os.path.exists(USAGE_TRACKER_FILE):
            try:
                with open(USAGE_TRACKER_FILE, 'r') as f:
                    data = json.load(f)
                
                # Check if data is from today
                if data.get('date') == str(date.today()):
                    return data
            except Exception as e:
                print(f"⚠️ Failed to load usage tracker: {e}")
        
        # Return fresh tracker for new day
        return {
            'date': str(date.today()),
            'sets': [
                {'name': s['name'], 'calls': 0}
                for s in API_KEY_SETS
            ],
            'current_set': 0,
            'total_calls_today': 0,
        }
    
    def _save_usage(self):
        """Save usage tracker to file."""
        try:
            with open(USAGE_TRACKER_FILE, 'w') as f:
                json.dump(self.usage, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save usage tracker: {e}")
    
    def _determine_current_set(self):
        """Determine which set to use based on current usage."""
        for i, set_usage in enumerate(self.usage['sets']):
            if set_usage['calls'] < CALLS_PER_SET:
                self.current_set_index = i
                self.usage['current_set'] = i
                return
        
        # All sets exhausted - use last set (will likely hit API limit)
        self.current_set_index = len(API_KEY_SETS) - 1
        self.usage['current_set'] = self.current_set_index
        print(f"⚠️ WARNING: All {len(API_KEY_SETS)} API key sets exhausted for today!")
    
    def get_current_keys(self) -> Tuple[str, str, str, str]:
        """
        Get current API keys to use.
        
        Returns:
            (set_name, alpha_key, fmp_key, news_key)
        """
        current_set = API_KEY_SETS[self.current_set_index]
        
        return (
            current_set['name'],
            current_set['alpha_vantage'],
            current_set['fmp'],
            current_set['newsapi'],
        )
    
    def record_call(self):
        """
        Record that an API call was made with current set.
        Automatically switches to next set if current hits limit.
        """
        self.usage['sets'][self.current_set_index]['calls'] += 1
        self.usage['total_calls_today'] += 1
        
        # Check if current set hit limit
        if self.usage['sets'][self.current_set_index]['calls'] >= CALLS_PER_SET:
            print(f"⚠️ {API_KEY_SETS[self.current_set_index]['name']} hit limit ({CALLS_PER_SET} calls)")
            
            # Switch to next set if available
            if self.current_set_index < len(API_KEY_SETS) - 1:
                self.current_set_index += 1
                self.usage['current_set'] = self.current_set_index
                print(f"✅ Auto-switched to {API_KEY_SETS[self.current_set_index]['name']}")
                print(f"📊 Total calls today: {self.usage['total_calls_today']}/{CALLS_PER_SET * len(API_KEY_SETS)}")
        
        self._save_usage()
    
    def get_status(self) -> Dict:
        """Get current usage status."""
        return {
            'current_set': self.current_set_index,
            'current_set_name': API_KEY_SETS[self.current_set_index]['name'],
            'current_set_calls': self.usage['sets'][self.current_set_index]['calls'],
            'current_set_remaining': CALLS_PER_SET - self.usage['sets'][self.current_set_index]['calls'],
            'total_calls_today': self.usage['total_calls_today'],
            'total_capacity': CALLS_PER_SET * len(API_KEY_SETS),
            'total_remaining': (CALLS_PER_SET * len(API_KEY_SETS)) - self.usage['total_calls_today'],
            'sets': [
                {
                    'name': API_KEY_SETS[i]['name'],
                    'calls': self.usage['sets'][i]['calls'],
                    'remaining': CALLS_PER_SET - self.usage['sets'][i]['calls'],
                    'percentage': round((self.usage['sets'][i]['calls'] / CALLS_PER_SET) * 100, 1),
                }
                for i in range(len(API_KEY_SETS))
            ],
        }
    
    def reset_usage(self):
        """Manually reset usage (useful for testing)."""
        self.usage = {
            'date': str(date.today()),
            'sets': [
                {'name': s['name'], 'calls': 0}
                for s in API_KEY_SETS
            ],
            'current_set': 0,
            'total_calls_today': 0,
        }
        self.current_set_index = 0
        self._save_usage()
        print(f"✅ API usage reset for {date.today()}")


# ========================================
# GLOBAL INSTANCE (Singleton Pattern)
# ========================================

_api_key_manager = None

def get_api_key_manager() -> APIKeyManager:
    """Get global API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager


# ========================================
# CONVENIENCE FUNCTIONS
# ========================================

def get_current_api_keys():
    """
    Get current API keys to use.
    
    Returns:
        {
            'alpha_vantage': 'ABC123...',
            'fmp': 'xyz789...',
            'newsapi': 'news111...',
            'set_name': 'Set 1 (Primary)'
        }
    """
    manager = get_api_key_manager()
    set_name, alpha, fmp, news = manager.get_current_keys()
    
    return {
        'alpha_vantage': alpha,
        'fmp': fmp,
        'newsapi': news,
        'set_name': set_name,
    }


def record_api_call():
    """
    Record that an API call was made.
    Automatically handles rotation when limit is hit.
    """
    manager = get_api_key_manager()
    manager.record_call()


def get_usage_status():
    """Get current API usage status."""
    manager = get_api_key_manager()
    return manager.get_status()


def print_usage_status():
    """Print current API usage status to console."""
    status = get_usage_status()
    
    print(f"\n{'='*70}")
    print(f"📊 API USAGE STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    print(f"🔑 Current Set: {status['current_set_name']}")
    print(f"   Used: {status['current_set_calls']}/{CALLS_PER_SET} ({status['current_set_calls']/CALLS_PER_SET*100:.0f}%)")
    print(f"   Remaining: {status['current_set_remaining']}")
    print(f"\n📈 Total Today: {status['total_calls_today']}/{status['total_capacity']} ({status['total_calls_today']/status['total_capacity']*100:.0f}%)")
    print(f"   Remaining: {status['total_remaining']} calls")
    print(f"\n📋 All Sets:")
    for i, set_info in enumerate(status['sets']):
        current = " ← CURRENT" if i == status['current_set'] else ""
        bar_length = int(set_info['percentage'] / 5)  # 20 chars max
        bar = "█" * bar_length + "░" * (20 - bar_length)
        print(f"   {set_info['name']:20s} [{bar}] {set_info['calls']:2d}/{CALLS_PER_SET} ({set_info['percentage']:5.1f}%){current}")
    print(f"{'='*70}\n")


def reset_usage():
    """Manually reset API usage (useful for testing)."""
    manager = get_api_key_manager()
    manager.reset_usage()


# ========================================
# EXAMPLE USAGE / TESTING
# ========================================

if __name__ == "__main__":
    print("🔧 API Key Manager - Testing Mode\n")
    
    # Get current keys
    keys = get_current_api_keys()
    print(f"✅ Using: {keys['set_name']}")
    print(f"   Alpha Vantage: {keys['alpha_vantage'][:15]}...")
    print(f"   FMP: {keys['fmp'][:15]}...")
    print(f"   NewsAPI: {keys['newsapi'][:15]}...\n")
    
    # Initial status
    print("📊 Initial Status:")
    print_usage_status()
    
    # Simulate 30 API calls to test rotation
    print("🔄 Simulating 30 API calls...\n")
    for i in range(30):
        record_api_call()
        
        # Print status every 10 calls
        if (i + 1) % 10 == 0:
            print(f"After {i + 1} calls:")
            print_usage_status()
    
    # Final status
    print("✅ Simulation complete!")
    print("\nFinal status:")
    print_usage_status()
    
    # Show reset option
    print("💡 To reset usage manually: reset_usage()")
