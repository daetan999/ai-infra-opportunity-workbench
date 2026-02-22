"""
Institutional Contract Recommendation System
============================================
Recommends Top 3 option contracts based on:
- Greeks analysis (Delta, Gamma, Theta, Vega)
- Strike positioning vs entry zones
- Risk/Reward optimization
- IV environment alignment
- Probability of profit

JPMorgan Equity Derivatives desk-level selection logic.
"""

from typing import Dict, List, Optional, Tuple
import math
from scipy.stats import norm
import numpy as np

class ContractRecommender:
    """
    Professional option contract selection system.
    
    Analyzes all available strikes and recommends Top 3 based on:
    1. Delta alignment with directional view (30%)
    2. Strike positioning vs entry zones (25%)
    3. Greeks efficiency (Gamma/Theta/Vega tradeoff) (25%)
    4. Risk/Reward profile (20%)
    """
    
    def __init__(self):
        self.weights = {
            'delta_alignment': 0.30,
            'strike_positioning': 0.25,
            'greeks_efficiency': 0.25,
            'risk_reward': 0.20,
        }
    
    def recommend_top3(
        self,
        # Market data
        spot: float,
        target_price: float,
        entry_zones: Dict,  # {'normal': {'low': X, 'high': Y}, 'conservative': {...}}
        
        # Options data
        option_chain: List[Dict],  # [{'strike': X, 'type': 'call', 'mid': Y, 'iv': Z, ...}]
        
        # User parameters
        user_stance: str,  # 'bullish' or 'bearish'
        expiry: str,
        dte: int,
        
        # Volatility context
        iv_rank: float,
        iv_hv_ratio: float,
        
        # Risk parameters
        max_budget: Optional[float] = None,
        max_loss: Optional[float] = None,
        
    ) -> List[Dict]:
        """
        Recommend Top 3 contracts with full analysis.
        
        Returns list of:
        {
            'rank': 1,
            'strike': 380,
            'type': 'call',
            'expiry': '2026-04-17',
            'dte': 45,
            'price': 8.50,
            'delta': 0.42,
            'gamma': 0.018,
            'theta': -0.28,
            'vega': 0.15,
            'breakeven': 388.50,
            'max_risk': 850,
            'prob_itm': 0.42,
            'prob_profit': 0.38,
            'score': 0.85,
            'reason': 'Optimal delta...',
            'contracts_budget': 2,
        }
        """
        
        # Filter by option type based on stance
        option_type = 'call' if user_stance == 'bullish' else 'put'
        candidates = [opt for opt in option_chain if opt.get('type') == option_type]
        
        if not candidates:
            return []
        
        # Score each contract
        scored = []
        for opt in candidates:
            strike = opt['strike']
            mid_price = opt.get('mid', opt.get('last', 0))
            iv = opt.get('iv', 0.5)
            
            # Calculate Greeks
            greeks = self._calculate_greeks(
                strike=strike,
                spot=spot,
                iv=iv,
                dte=dte,
                option_type=option_type,
                r=0.05  # Risk-free rate
            )
            
            # Score contract
            delta_score = self._score_delta_alignment(greeks['delta'], user_stance)
            position_score = self._score_strike_positioning(strike, spot, entry_zones)
            greeks_score = self._score_greeks_efficiency(
                greeks, iv_rank, dte
            )
            rr_score = self._score_risk_reward(
                strike, mid_price, spot, target_price, option_type
            )
            
            total_score = (
                delta_score * self.weights['delta_alignment'] +
                position_score * self.weights['strike_positioning'] +
                greeks_score * self.weights['greeks_efficiency'] +
                rr_score * self.weights['risk_reward']
            )
            
            # Calculate probabilities
            prob_itm = abs(greeks['delta'])  # Delta approximates ITM probability
            prob_profit = self._calculate_prob_profit(
                strike, mid_price, spot, iv, dte, option_type
            )
            
            # Calculate breakeven
            if option_type == 'call':
                breakeven = strike + mid_price
            else:
                breakeven = strike - mid_price
            
            # Budget analysis
            max_risk = mid_price * 100  # Per contract
            contracts_budget = int(max_budget / max_risk) if max_budget else None
            contracts_loss = int(max_loss / max_risk) if max_loss else None
            
            # Generate reason
            reason = self._generate_reason(
                strike, greeks, delta_score, position_score,
                greeks_score, rr_score, iv_rank, user_stance
            )
            
            scored.append({
                'rank': None,  # Will be set after sorting
                'strike': strike,
                'type': option_type,
                'expiry': expiry,
                'dte': dte,
                'price': round(mid_price, 2),
                'delta': round(greeks['delta'], 3),
                'gamma': round(greeks['gamma'], 4),
                'theta': round(greeks['theta'], 3),
                'vega': round(greeks['vega'], 3),
                'breakeven': round(breakeven, 2),
                'max_risk': round(max_risk, 2),
                'prob_itm': round(prob_itm, 3),
                'prob_profit': round(prob_profit, 3),
                'score': round(total_score, 3),
                'reason': reason,
                'contracts_budget': contracts_budget,
                'contracts_loss': contracts_loss,
                'spread': opt.get('spread_pct', 0),
                'iv': round(iv, 4),
            })
        
        # Sort by score and take top 3
        scored.sort(key=lambda x: x['score'], reverse=True)
        top3 = scored[:3]
        
        # Assign ranks
        for i, contract in enumerate(top3):
            contract['rank'] = i + 1
        
        return top3
    
    def _calculate_greeks(
        self,
        strike: float,
        spot: float,
        iv: float,
        dte: int,
        option_type: str,
        r: float = 0.05
    ) -> Dict[str, float]:
        """
        Calculate option Greeks using Black-Scholes.
        
        Returns: {'delta', 'gamma', 'theta', 'vega'}
        """
        # Convert to years
        T = dte / 365.0
        
        if T <= 0:
            # Expired or same day - intrinsic value only
            if option_type == 'call':
                delta = 1.0 if spot > strike else 0.0
            else:
                delta = -1.0 if spot < strike else 0.0
            return {'delta': delta, 'gamma': 0, 'theta': 0, 'vega': 0}
        
        # Black-Scholes components
        d1 = (math.log(spot / strike) + (r + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)
        
        # Standard normal PDF and CDF
        nd1 = norm.cdf(d1)
        nd2 = norm.cdf(d2)
        nprime_d1 = norm.pdf(d1)
        
        # Calculate Greeks
        if option_type == 'call':
            delta = nd1
            theta = (
                -spot * nprime_d1 * iv / (2 * math.sqrt(T))
                - r * strike * math.exp(-r * T) * nd2
            ) / 365.0  # Per day
        else:
            delta = nd1 - 1
            theta = (
                -spot * nprime_d1 * iv / (2 * math.sqrt(T))
                + r * strike * math.exp(-r * T) * (1 - nd2)
            ) / 365.0  # Per day
        
        gamma = nprime_d1 / (spot * iv * math.sqrt(T))
        vega = spot * nprime_d1 * math.sqrt(T) / 100  # Per 1% change in IV
        
        return {
            'delta': delta,
            'gamma': gamma,
            'theta': theta,
            'vega': vega,
        }
    
    def _score_delta_alignment(self, delta: float, stance: str) -> float:
        """
        Score delta alignment with directional view.
        
        For bullish: want 0.30-0.50 delta (directional but not too aggressive)
        For bearish: want -0.30 to -0.50 delta
        """
        delta_abs = abs(delta)
        
        # Optimal range: 0.30-0.50
        if 0.30 <= delta_abs <= 0.50:
            score = 1.0  # Perfect
        elif 0.25 <= delta_abs < 0.30 or 0.50 < delta_abs <= 0.55:
            score = 0.85  # Good
        elif 0.20 <= delta_abs < 0.25 or 0.55 < delta_abs <= 0.60:
            score = 0.7  # Acceptable
        elif delta_abs > 0.70:
            score = 0.4  # Too deep ITM (capital inefficient)
        else:
            score = 0.5  # Too far OTM (low probability)
        
        return score
    
    def _score_strike_positioning(
        self, strike: float, spot: float, entry_zones: Dict
    ) -> float:
        """
        Score strike positioning relative to entry zones.
        
        Best strikes are near conservative entry (good risk/reward at entry).
        """
        if not entry_zones or 'normal' not in entry_zones:
            return 0.5
        
        normal = entry_zones['normal']
        conservative = entry_zones.get('conservative', normal)
        
        normal_avg = (normal.get('low', spot) + normal.get('high', spot)) / 2
        cons_avg = (conservative.get('low', spot) + conservative.get('high', spot)) / 2
        
        # Calculate distance from strike to entry zones
        # For calls: want strike near or below entry zones (buy at entry = profitable)
        strike_pct_from_spot = (strike - spot) / spot
        entry_pct_from_spot = (cons_avg - spot) / spot
        
        # Score based on how well strike aligns with entry strategy
        distance = abs(strike_pct_from_spot - entry_pct_from_spot)
        
        if distance < 0.05:
            score = 1.0  # Perfect alignment
        elif distance < 0.10:
            score = 0.85
        elif distance < 0.15:
            score = 0.7
        elif distance < 0.20:
            score = 0.55
        else:
            score = 0.4
        
        return score
    
    def _score_greeks_efficiency(
        self, greeks: Dict, iv_rank: float, dte: int
    ) -> float:
        """
        Score Greeks efficiency based on Gamma/Theta/Vega tradeoff.
        
        Factors:
        - Gamma: Higher is better (price sensitivity)
        - Theta: Lower (less negative) is better
        - Vega: Depends on IV environment
        """
        gamma = greeks['gamma']
        theta = greeks['theta']
        vega = greeks['vega']
        
        # Gamma score (higher = better, but not too high means ATM)
        if gamma > 0.025:
            gamma_score = 0.9  # High gamma (good)
        elif gamma > 0.015:
            gamma_score = 1.0  # Optimal gamma
        elif gamma > 0.010:
            gamma_score = 0.8  # Moderate gamma
        else:
            gamma_score = 0.6  # Low gamma
        
        # Theta score (less negative = better)
        theta_abs = abs(theta)
        if dte > 45:
            # Longer DTE: theta less important
            if theta_abs < 0.15:
                theta_score = 0.9
            elif theta_abs < 0.25:
                theta_score = 0.8
            else:
                theta_score = 0.7
        else:
            # Shorter DTE: theta very important
            if theta_abs < 0.20:
                theta_score = 1.0
            elif theta_abs < 0.35:
                theta_score = 0.8
            else:
                theta_score = 0.5  # High theta decay
        
        # Vega score (depends on IV environment)
        if iv_rank < 30:
            # Low IV: want positive vega (benefit from IV expansion)
            vega_score = 1.0 if vega > 0.12 else 0.7
        elif iv_rank > 70:
            # High IV: want lower vega (avoid IV crush)
            vega_score = 1.0 if vega < 0.15 else 0.6
        else:
            # Moderate IV: vega neutral
            vega_score = 0.8
        
        # Combined score
        score = (gamma_score * 0.4 + theta_score * 0.4 + vega_score * 0.2)
        return score
    
    def _score_risk_reward(
        self,
        strike: float,
        price: float,
        spot: float,
        target: float,
        option_type: str
    ) -> float:
        """
        Score risk/reward profile.
        
        For calls:
        - Risk = premium paid
        - Reward = (target - strike) - premium
        - Want R/R > 2.0
        """
        if option_type == 'call':
            max_risk = price
            max_reward = max(target - strike - price, 0)
        else:
            max_risk = price
            max_reward = max(strike - target - price, 0)
        
        if max_risk == 0:
            return 0.5
        
        rr_ratio = max_reward / max_risk
        
        if rr_ratio > 3.0:
            score = 1.0  # Excellent R/R
        elif rr_ratio > 2.0:
            score = 0.9  # Good R/R
        elif rr_ratio > 1.5:
            score = 0.75  # Acceptable R/R
        elif rr_ratio > 1.0:
            score = 0.6  # Marginal R/R
        else:
            score = 0.3  # Poor R/R
        
        return score
    
    def _calculate_prob_profit(
        self,
        strike: float,
        premium: float,
        spot: float,
        iv: float,
        dte: int,
        option_type: str
    ) -> float:
        """
        Calculate probability of profit using Monte Carlo.
        
        P(Profit) = P(Spot > Breakeven) for calls
        """
        # Breakeven
        if option_type == 'call':
            breakeven = strike + premium
        else:
            breakeven = strike - premium
        
        # Monte Carlo simulation
        np.random.seed(42)
        n_sims = 10000
        
        # Convert to annual terms
        T = dte / 365.0
        
        # Simulate final prices using geometric Brownian motion
        drift = 0.0  # Risk-neutral
        z = np.random.standard_normal(n_sims)
        final_prices = spot * np.exp((drift - 0.5 * iv ** 2) * T + iv * np.sqrt(T) * z)
        
        # Count profitable outcomes
        if option_type == 'call':
            profitable = final_prices > breakeven
        else:
            profitable = final_prices < breakeven
        
        prob = np.mean(profitable)
        return prob
    
    def _generate_reason(
        self,
        strike: float,
        greeks: Dict,
        delta_score: float,
        position_score: float,
        greeks_score: float,
        rr_score: float,
        iv_rank: float,
        stance: str
    ) -> str:
        """Generate human-readable reason for recommendation."""
        reasons = []
        
        # Delta alignment
        if delta_score > 0.85:
            reasons.append(f"Optimal delta {greeks['delta']:.2f} for directional {stance} play")
        elif delta_score > 0.7:
            reasons.append(f"Good delta {greeks['delta']:.2f} balance")
        
        # Positioning
        if position_score > 0.85:
            reasons.append("Strike aligns perfectly with entry zones")
        elif position_score > 0.7:
            reasons.append("Well-positioned near entry levels")
        
        # Greeks
        if greeks_score > 0.85:
            reasons.append(f"Favorable Greeks (Gamma {greeks['gamma']:.3f}, Theta {greeks['theta']:.2f})")
        
        # R/R
        if rr_score > 0.85:
            reasons.append("Excellent risk/reward profile")
        elif rr_score > 0.7:
            reasons.append("Favorable risk/reward")
        
        # IV environment
        if iv_rank < 30:
            reasons.append(f"Low IV environment (rank {iv_rank:.0f}%) - good for buying")
        elif iv_rank > 70:
            reasons.append(f"High IV (rank {iv_rank:.0f}%) - consider spreads")
        
        return "; ".join(reasons) if reasons else "Balanced directional contract"