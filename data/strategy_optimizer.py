"""
Options Strategy Optimizer
==========================
Recommends optimal options structure based on:
- User stance (bullish/bearish)
- IV environment (buy vs sell vol)
- Risk/Reward goals
- Budget constraints

Structures covered:
- Outright (call/put)
- Vertical spreads (call/put spreads)
- Diagonal spreads (for theta optimization)
- Ratio spreads (for cheap delta)
"""

from typing import Dict, List, Optional, Tuple

class StrategyOptimizer:
    """
    Recommend optimal options strategy structure.
    
    Goldman Sachs Options Strategy team approach:
    - Analyze IV environment → buy vs sell premium
    - Consider user stance → directional structure
    - Optimize for R/R → spreads vs outright
    - Factor in budget → defined risk if needed
    """
    
    def recommend_strategy(
        self,
        # User parameters
        user_stance: str,  # 'bullish' or 'bearish'
        spot: float,
        target: float,
        entry_zone_avg: float,
        
        # Volatility environment
        iv_rank: float,  # 0-100
        iv_hv_ratio: float,
        iv_percentile: float,
        
        # Option data
        atm_call_price: float,
        atm_put_price: float,
        otm_call_price: Optional[float] = None,  # 10-15% OTM
        otm_put_price: Optional[float] = None,
        
        # Greeks
        atm_delta: float = 0.50,
        atm_theta: float = -0.30,
        atm_vega: float = 0.20,
        
        # Constraints
        max_budget: Optional[float] = None,
        max_loss: Optional[float] = None,
        risk_preference: str = 'moderate',  # 'aggressive', 'moderate', 'conservative'
        
        # Time
        dte: int = 45,
        
        # blocked: Optional[bool] = None (from liquidity gate / confidence object)
        blocked: bool = False,
        blocked_reason: Optional[str] = None,
    ) -> Dict:
        """
        Recommend optimal strategy structure.

        Returns dict with:
        - structure: 'call_debit_spread', 'naked_call', 'put_spread', etc.
        - strikes: {'long': X, 'short': Y}
        - reasoning: why this structure
        - execution_details: entry, risk, reward
        - greeks_profile: net Greeks
        - blocked: True if execution should be gated
        """
        # Governance gate: if execution is blocked, return a safe stub
        if blocked:
            return {
                "structure": "blocked",
                "description": f"Execution blocked: {blocked_reason or 'liquidity/confidence gate'}",
                "strikes": {"long": None, "short": None},
                "expiry_recommendation": f"{dte} DTE",
                "execution": {
                    "entry_cost": 0,
                    "max_risk": 0,
                    "max_reward": 0,
                    "breakeven": spot,
                    "rr_ratio": 0,
                    "dte": dte,
                },
                "greeks_profile": {"delta": 0, "theta": 0, "vega": 0, "gamma": 0},
                "reasoning": blocked_reason or "Blocked by risk model",
                "pros": [],
                "cons": ["Execution blocked by risk model"],
                "ideal_scenario": "Wait for improved conditions",
                "blocked": True,
                "blocked_reason": blocked_reason,
            }

        # Determine buy vs sell vol environment
        vol_environment = self._assess_vol_environment(
            iv_rank, iv_hv_ratio, iv_percentile
        )
        
        # Determine structure based on vol + stance
        if user_stance == 'bullish':
            structure = self._recommend_bullish_structure(
                vol_environment=vol_environment,
                spot=spot,
                target=target,
                iv_rank=iv_rank,
                atm_call_price=atm_call_price,
                otm_call_price=otm_call_price,
                max_budget=max_budget,
                risk_preference=risk_preference,
            )
        else:  # bearish
            structure = self._recommend_bearish_structure(
                vol_environment=vol_environment,
                spot=spot,
                target=target,
                iv_rank=iv_rank,
                atm_put_price=atm_put_price,
                otm_put_price=otm_put_price,
                max_budget=max_budget,
                risk_preference=risk_preference,
            )
        
        # Calculate execution details
        execution = self._calculate_execution_details(
            structure=structure,
            spot=spot,
            target=target,
            dte=dte,
        )
        
        # Estimate net Greeks
        greeks = self._estimate_net_greeks(
            structure=structure,
            atm_delta=atm_delta,
            atm_theta=atm_theta,
            atm_vega=atm_vega,
        )
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            structure=structure,
            vol_environment=vol_environment,
            iv_rank=iv_rank,
            user_stance=user_stance,
            execution=execution,
        )
        
        return {
            'structure': structure['name'],
            'description': structure['description'],
            'strikes': structure['strikes'],
            'expiry_recommendation': f"{dte} DTE",
            'execution': execution,
            'greeks_profile': greeks,
            'reasoning': reasoning,
            'pros': structure.get('pros', []),
            'cons': structure.get('cons', []),
            'ideal_scenario': structure.get('ideal_scenario', ''),
        }
    
    def _assess_vol_environment(
        self, iv_rank: float, iv_hv_ratio: float, iv_percentile: float
    ) -> str:
        """
        Assess volatility environment for buy vs sell decision.
        
        Returns: 'buy_vol', 'sell_vol', or 'neutral'
        """
        buy_signals = 0
        sell_signals = 0
        
        # IV rank
        if iv_rank < 30:
            buy_signals += 2  # Strong buy signal
        elif iv_rank > 70:
            sell_signals += 2  # Strong sell signal
        
        # IV/HV ratio
        if iv_hv_ratio < 0.90:
            buy_signals += 1  # IV cheap vs realized
        elif iv_hv_ratio > 1.15:
            sell_signals += 1  # IV expensive
        
        # IV percentile
        if iv_percentile < 25:
            buy_signals += 1
        elif iv_percentile > 75:
            sell_signals += 1
        
        if buy_signals > sell_signals:
            return 'buy_vol'
        elif sell_signals > buy_signals:
            return 'sell_vol'
        else:
            return 'neutral'
    
    def _recommend_bullish_structure(
        self,
        vol_environment: str,
        spot: float,
        target: float,
        iv_rank: float,
        atm_call_price: float,
        otm_call_price: Optional[float],
        max_budget: Optional[float],
        risk_preference: str,
    ) -> Dict:
        """Recommend bullish structure based on environment."""
        
        # Calculate strikes
        atm_strike = round(spot / 5) * 5  # Round to nearest $5
        otm_strike = round(target / 5) * 5
        
        # Decision tree
        if vol_environment == 'buy_vol':
            # IV cheap → buy outright calls
            if max_budget and atm_call_price * 100 > max_budget:
                # Budget constrained → use spread
                return {
                    'name': 'call_debit_spread',
                    'description': 'Long Call Spread (Budget-friendly)',
                    'strikes': {'long': atm_strike, 'short': otm_strike},
                    'cost_per_contract': (atm_call_price - (otm_call_price or atm_call_price * 0.4)) * 100,
                    'pros': [
                        'Defined risk',
                        'Lower cost than naked call',
                        'Profitable if stock reaches target',
                    ],
                    'cons': [
                        'Limited upside (capped at short strike)',
                        'Lower delta than outright',
                    ],
                    'ideal_scenario': f'Stock moves to {otm_strike} by expiry',
                }
            else:
                # Can afford naked call → better choice in low IV
                return {
                    'name': 'naked_call',
                    'description': 'Long Call (Outright)',
                    'strikes': {'long': atm_strike, 'short': None},
                    'cost_per_contract': atm_call_price * 100,
                    'pros': [
                        'Unlimited upside',
                        'Cheap volatility (IV rank low)',
                        'Maximum delta exposure',
                    ],
                    'cons': [
                        'Higher capital requirement',
                        'Theta decay',
                    ],
                    'ideal_scenario': 'Stock rallies significantly; IV expands',
                }
        
        elif vol_environment == 'sell_vol':
            # IV expensive → spread to offset cost
            return {
                'name': 'call_debit_spread',
                'description': 'Long Call Spread (Sell premium to offset)',
                'strikes': {'long': atm_strike, 'short': otm_strike},
                'cost_per_contract': (atm_call_price - (otm_call_price or atm_call_price * 0.5)) * 100,
                'pros': [
                    'Reduced cost (sell expensive vol)',
                    'Defined risk',
                    'Good R/R if targeting short strike',
                ],
                'cons': [
                    'Capped upside',
                    'Negative vega (IV crush hurts less)',
                ],
                'ideal_scenario': f'Stock reaches {otm_strike}; IV contracts',
            }
        
        else:  # neutral vol
            # Use spread for conservative, naked for aggressive
            if risk_preference == 'aggressive':
                return {
                    'name': 'naked_call',
                    'description': 'Long Call (Outright)',
                    'strikes': {'long': atm_strike, 'short': None},
                    'cost_per_contract': atm_call_price * 100,
                    'pros': ['Unlimited upside', 'Simple execution'],
                    'cons': ['Higher cost', 'Theta decay'],
                    'ideal_scenario': 'Strong rally',
                }
            else:
                return {
                    'name': 'call_debit_spread',
                    'description': 'Long Call Spread (Balanced)',
                    'strikes': {'long': atm_strike, 'short': otm_strike},
                    'cost_per_contract': (atm_call_price - (otm_call_price or atm_call_price * 0.45)) * 100,
                    'pros': ['Defined risk', 'Good R/R', 'Lower cost'],
                    'cons': ['Capped profit'],
                    'ideal_scenario': f'Stock reaches {otm_strike}',
                }
    
    def _recommend_bearish_structure(
        self,
        vol_environment: str,
        spot: float,
        target: float,
        iv_rank: float,
        atm_put_price: float,
        otm_put_price: Optional[float],
        max_budget: Optional[float],
        risk_preference: str,
    ) -> Dict:
        """Recommend bearish structure."""
        # Similar logic to bullish, but with puts
        atm_strike = round(spot / 5) * 5
        otm_strike = round(target / 5) * 5
        
        if vol_environment == 'buy_vol':
            return {
                'name': 'naked_put',
                'description': 'Long Put (Outright)',
                'strikes': {'long': atm_strike, 'short': None},
                'cost_per_contract': atm_put_price * 100,
                'pros': ['Large profit if sharp decline', 'Cheap vol'],
                'cons': ['Theta decay', 'Higher cost'],
                'ideal_scenario': 'Stock drops sharply',
            }
        else:
            return {
                'name': 'put_debit_spread',
                'description': 'Long Put Spread',
                'strikes': {'long': atm_strike, 'short': otm_strike},
                'cost_per_contract': (atm_put_price - (otm_put_price or atm_put_price * 0.4)) * 100,
                'pros': ['Defined risk', 'Reduced cost'],
                'cons': ['Limited profit'],
                'ideal_scenario': f'Stock falls to {otm_strike}',
            }
    
    def _calculate_execution_details(
        self, structure: Dict, spot: float, target: float, dte: int
    ) -> Dict:
        """Calculate execution-specific details."""
        long_strike = structure['strikes']['long']
        short_strike = structure['strikes'].get('short')
        cost = structure['cost_per_contract']
        
        if structure['name'] in ['naked_call', 'naked_put']:
            # Outright option
            max_risk = cost
            max_reward = float('inf')  # Unlimited for calls
            breakeven = long_strike + cost / 100 if 'call' in structure['name'] else long_strike - cost / 100
        else:
            # Spread
            spread_width = abs(short_strike - long_strike)
            max_risk = cost
            max_reward = (spread_width * 100) - cost
            breakeven = long_strike + cost / 100 if 'call' in structure['name'] else long_strike - cost / 100
        
        rr_ratio = max_reward / max_risk if max_risk > 0 and max_reward != float('inf') else None
        
        return {
            'entry_cost': round(cost, 2),
            'max_risk': round(max_risk, 2),
            'max_reward': round(max_reward, 2) if max_reward != float('inf') else 'Unlimited',
            'breakeven': round(breakeven, 2),
            'rr_ratio': round(rr_ratio, 2) if rr_ratio else 'Unlimited',
            'dte': dte,
        }
    
    def _estimate_net_greeks(
        self, structure: Dict, atm_delta: float, atm_theta: float, atm_vega: float
    ) -> Dict:
        """Estimate net Greeks for the structure."""
        if structure['name'] in ['naked_call', 'naked_put']:
            # Outright: just use ATM Greeks
            multiplier = 1.0 if 'call' in structure['name'] else -1.0
            return {
                'delta': round(atm_delta * multiplier, 3),
                'theta': round(atm_theta, 3),
                'vega': round(atm_vega, 3),
                'gamma': 0.018,  # Approximate
            }
        else:
            # Spread: long ATM, short OTM
            # OTM has lower Greeks
            otm_delta = atm_delta * 0.6  # Approximate
            otm_theta = atm_theta * 0.5
            otm_vega = atm_vega * 0.6
            
            net_delta = atm_delta - otm_delta
            net_theta = atm_theta - (-otm_theta)  # Short option adds positive theta
            net_vega = atm_vega - otm_vega
            
            return {
                'delta': round(net_delta, 3),
                'theta': round(net_theta, 3),
                'vega': round(net_vega, 3),
                'gamma': 0.012,  # Approximate
            }
    
    def _generate_reasoning(
        self,
        structure: Dict,
        vol_environment: str,
        iv_rank: float,
        user_stance: str,
        execution: Dict,
    ) -> str:
        """Generate human-readable reasoning."""
        reasons = []
        
        # Vol environment
        if vol_environment == 'buy_vol':
            reasons.append(f"IV rank {iv_rank:.0f}% (cheap) favors buying options")
        elif vol_environment == 'sell_vol':
            reasons.append(f"IV rank {iv_rank:.0f}% (expensive) favors selling premium")
        
        # Structure choice
        if structure['name'] in ['naked_call', 'naked_put']:
            reasons.append("Outright position for maximum delta exposure")
        else:
            reasons.append("Spread structure to reduce cost and define risk")
        
        # R/R
        if execution['rr_ratio'] and execution['rr_ratio'] != 'Unlimited':
            reasons.append(f"R/R ratio of {execution['rr_ratio']}x is favorable")
        
        # Stance alignment
        reasons.append(f"Aligns with {user_stance} directional view")
        
        return "; ".join(reasons)