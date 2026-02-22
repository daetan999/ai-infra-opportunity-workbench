"""
Volatility Surface Analyzer
============================
Interprets volatility skew and surface shape.

Analyzes:
- OTM put IV vs ATM (downside protection pricing)
- OTM call IV vs ATM (upside convexity pricing)
- Skew steepness
- Trading implications

Goldman Sachs volatility trading desk approach.
"""

from typing import Dict, List, Optional

class VolatilitySurfaceAnalyzer:
    """Analyze and interpret volatility surface shape."""
    
    def analyze_skew(
        self,
        # IV data by delta
        atm_iv: float,  # 50 delta
        otm_put_25d_iv: Optional[float] = None,  # 25 delta put
        otm_call_25d_iv: Optional[float] = None,  # 25 delta call
        otm_put_10d_iv: Optional[float] = None,  # 10 delta put (further OTM)
        
        # Or by strike
        strikes_and_ivs: Optional[List[Dict]] = None,  # [{'strike': X, 'iv': Y, 'type': 'call/put'}]
        spot: Optional[float] = None,
        
        # User stance
        user_stance: str = 'bullish',
        
    ) -> Dict:
        """
        Analyze volatility skew and provide interpretation.
        
        Returns dict with:
        - skew_shape: 'steep_put', 'flat', 'call_wing', etc.
        - put_premium: % premium of OTM puts vs ATM
        - call_premium: % premium of OTM calls vs ATM
        - interpretation: What market is pricing
        - trading_implications: How to trade it
        - favorability: For bullish/bearish stance
        """
        
        # Calculate skew metrics
        if otm_put_25d_iv and otm_call_25d_iv:
            put_premium_pct = ((otm_put_25d_iv - atm_iv) / atm_iv) * 100
            call_premium_pct = ((otm_call_25d_iv - atm_iv) / atm_iv) * 100
        elif strikes_and_ivs and spot:
            # Estimate from strikes
            put_premium_pct, call_premium_pct = self._estimate_from_strikes(
                strikes_and_ivs, atm_iv, spot
            )
        else:
            # No skew data
            return {
                'available': False,
                'message': 'Insufficient data for skew analysis',
            }
        
        # Classify skew shape
        skew_shape = self._classify_skew(put_premium_pct, call_premium_pct)
        
        # Interpret what market is pricing
        interpretation = self._interpret_skew(
            skew_shape, put_premium_pct, call_premium_pct
        )
        
        # Trading implications
        implications = self._get_trading_implications(
            skew_shape, user_stance, put_premium_pct, call_premium_pct
        )
        
        # Favorability for user stance
        favorability = self._assess_favorability(
            skew_shape, user_stance, put_premium_pct, call_premium_pct
        )
        
        return {
            'available': True,
            'skew_shape': skew_shape,
            'atm_iv_pct': round(atm_iv * 100, 1),
            'otm_put_iv_pct': round(otm_put_25d_iv * 100, 1) if otm_put_25d_iv else None,
            'otm_call_iv_pct': round(otm_call_25d_iv * 100, 1) if otm_call_25d_iv else None,
            'put_premium_pct': round(put_premium_pct, 1),
            'call_premium_pct': round(call_premium_pct, 1),
            'interpretation': interpretation,
            'trading_implications': implications,
            'favorability': favorability,
        }
    
    def _estimate_from_strikes(
        self, strikes_and_ivs: List[Dict], atm_iv: float, spot: float
    ) -> tuple:
        """Estimate put/call premium from strike data."""
        # Find OTM puts (strikes ~15-20% below spot)
        otm_put_target = spot * 0.80
        otm_puts = [
            s for s in strikes_and_ivs
            if s.get('type') == 'put' and abs(s['strike'] - otm_put_target) / spot < 0.10
        ]
        
        # Find OTM calls (strikes ~15-20% above spot)
        otm_call_target = spot * 1.20
        otm_calls = [
            s for s in strikes_and_ivs
            if s.get('type') == 'call' and abs(s['strike'] - otm_call_target) / spot < 0.10
        ]
        
        put_iv = otm_puts[0]['iv'] if otm_puts else atm_iv
        call_iv = otm_calls[0]['iv'] if otm_calls else atm_iv
        
        put_premium_pct = ((put_iv - atm_iv) / atm_iv) * 100
        call_premium_pct = ((call_iv - atm_iv) / atm_iv) * 100
        
        return put_premium_pct, call_premium_pct
    
    def _classify_skew(self, put_premium_pct: float, call_premium_pct: float) -> str:
        """Classify skew shape."""
        if put_premium_pct > 5 and call_premium_pct < 2:
            return 'steep_put_skew'  # Classic equity skew
        elif put_premium_pct > 3 and call_premium_pct > 3:
            return 'symmetric_smile'  # Both wings expensive
        elif call_premium_pct > 5 and put_premium_pct < 2:
            return 'call_wing_expensive'  # Unusual, buying upside convexity
        elif abs(put_premium_pct) < 2 and abs(call_premium_pct) < 2:
            return 'flat_skew'  # No skew
        else:
            return 'moderate_put_skew'  # Normal equity skew
    
    def _interpret_skew(
        self, shape: str, put_premium: float, call_premium: float
    ) -> str:
        """Interpret what the skew is telling us."""
        interpretations = {
            'steep_put_skew': f"Market pricing significant downside risk. OTM puts trading {abs(put_premium):.1f}% above ATM. Strong demand for downside protection.",
            'moderate_put_skew': f"Normal equity skew. OTM puts {abs(put_premium):.1f}% premium reflects standard tail risk.",
            'symmetric_smile': f"Both wings expensive (puts +{put_premium:.1f}%, calls +{call_premium:.1f}%). Market expecting large move in either direction.",
            'call_wing_expensive': f"Unusual pattern - OTM calls trading {abs(call_premium):.1f}% above ATM. Market pricing explosive upside potential.",
            'flat_skew': "Flat volatility surface. No premium for tail risk. Complacent market.",
        }
        return interpretations.get(shape, "Skew pattern unclear")
    
    def _get_trading_implications(
        self, shape: str, stance: str, put_premium: float, call_premium: float
    ) -> List[str]:
        """Get trading implications based on skew and stance."""
        implications = []
        
        if stance == 'bullish':
            if shape == 'steep_put_skew':
                implications.append("✅ Favorable for bullish: Cheap upside (flat call wing)")
                implications.append("Buy calls - upside convexity not expensive")
                implications.append("Avoid selling puts - expensive downside protection")
            elif shape == 'call_wing_expensive':
                implications.append("⚠️ Challenging: Market already pricing upside")
                implications.append("Consider spreads to offset expensive calls")
            elif shape == 'flat_skew':
                implications.append("✅ Neutral: No strong directional bias priced")
                implications.append("Good environment for outright calls")
        else:  # bearish
            if shape == 'steep_put_skew':
                implications.append("⚠️ Expensive: Downside protection priced in")
                implications.append("Consider put spreads to reduce cost")
            elif shape == 'call_wing_expensive':
                implications.append("✅ Favorable: Sell call spreads (expensive upside)")
            elif shape == 'flat_skew':
                implications.append("✅ Good: No downside premium")
                implications.append("Cheap puts available")
        
        return implications
    
    def _assess_favorability(
        self, shape: str, stance: str, put_premium: float, call_premium: float
    ) -> str:
        """Assess favorability for user's stance."""
        if stance == 'bullish':
            if shape in ['steep_put_skew', 'moderate_put_skew']:
                return "🟢 Favorable (cheap calls, expensive puts)"
            elif shape == 'call_wing_expensive':
                return "🔴 Unfavorable (expensive upside already priced)"
            else:
                return "🟡 Neutral"
        else:  # bearish
            if shape in ['steep_put_skew', 'moderate_put_skew']:
                return "🔴 Unfavorable (expensive puts)"
            elif shape == 'call_wing_expensive':
                return "🟢 Favorable (sell expensive calls)"
            else:
                return "🟡 Neutral"