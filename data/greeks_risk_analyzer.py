"""
Greeks Risk Table Generator
===========================
Analyzes Greeks exposure and stress scenarios.

For recommended contracts, shows:
- Delta: Directional exposure
- Gamma: Delta sensitivity
- Theta: Time decay
- Vega: IV sensitivity
- IV Crush scenario (-10% IV impact)

JPMorgan risk management approach.
"""

from typing import Dict, List

class GreeksRiskAnalyzer:
    """Analyze Greeks risk and generate stress scenarios."""
    
    def analyze_greeks_risk(
        self,
        # Contract details
        strike: float,
        spot: float,
        option_price: float,
        option_type: str,  # 'call' or 'put'
        
        # Greeks
        delta: float,
        gamma: float,
        theta: float,
        vega: float,
        
        # Volatility context
        iv: float,
        iv_rank: float,
        
        # Position size
        contracts: int = 1,
        
    ) -> Dict:
        """
        Generate complete Greeks risk analysis.
        
        Returns dict with:
        - delta_exposure: $ per $1 move
        - gamma_risk: Delta change per $1 move
        - theta_decay: $ lost per day
        - vega_exposure: $ per 1% IV change
        - iv_crush_scenario: Impact of -10% IV
        - risk_levels: Color-coded risk (low/moderate/high)
        - mitigation: Suggested mitigations
        """
        
        position_multiplier = contracts * 100  # $ per point
        
        # Delta exposure
        delta_exp = {
            'value': delta,
            'dollar_exposure': abs(delta) * spot * contracts,
            'per_dollar_move': abs(delta) * position_multiplier,
            'description': f"${abs(delta) * position_multiplier:.0f} P&L per $1 move in stock",
            'risk_level': self._assess_delta_risk(abs(delta)),
        }
        
        # Gamma risk
        gamma_risk = {
            'value': gamma,
            'delta_change': gamma * contracts,
            'description': f"Delta changes by {abs(gamma * contracts):.3f} per $1 move",
            'risk_level': self._assess_gamma_risk(gamma, abs(delta)),
        }
        
        # Theta decay
        theta_daily = theta * position_multiplier
        theta_exp = {
            'value': theta,
            'daily_decay_dollars': theta_daily,
            'weekly_decay': theta_daily * 5,  # Trading days
            'description': f"Losing ${abs(theta_daily):.2f}/day to time decay",
            'risk_level': self._assess_theta_risk(abs(theta)),
        }
        
        # Vega exposure
        vega_dollar = vega * position_multiplier
        vega_exp = {
            'value': vega,
            'per_percent_iv': vega_dollar,
            'per_point_iv': vega_dollar / 100,  # Per IV point (0.01)
            'description': f"${abs(vega_dollar):.2f} P&L per 1% IV change",
            'risk_level': self._assess_vega_risk(abs(vega), iv_rank),
        }
        
        # IV crush scenario
        iv_crush = self._calculate_iv_crush_scenario(
            current_price=option_price,
            vega=vega,
            iv=iv,
            contracts=contracts,
        )
        
        # Overall risk assessment
        overall_risk = self._assess_overall_risk(
            delta_exp['risk_level'],
            gamma_risk['risk_level'],
            theta_exp['risk_level'],
            vega_exp['risk_level'],
        )
        
        # Mitigation strategies
        mitigations = self._generate_mitigations(
            delta_exp, theta_exp, vega_exp, iv_rank
        )
        
        return {
            'delta': delta_exp,
            'gamma': gamma_risk,
            'theta': theta_exp,
            'vega': vega_exp,
            'iv_crush_scenario': iv_crush,
            'overall_risk': overall_risk,
            'mitigations': mitigations,
        }
    
    def _assess_delta_risk(self, delta_abs: float) -> str:
        """Assess delta risk level."""
        if delta_abs > 0.70:
            return '🔴 High'  # Deep ITM, too much capital
        elif delta_abs > 0.45:
            return '🟡 Moderate'  # Good directional
        elif delta_abs > 0.25:
            return '🟢 Low'  # Reasonable
        else:
            return '🟢 Low'  # Far OTM, lottery ticket
    
    def _assess_gamma_risk(self, gamma: float, delta: float) -> str:
        """Assess gamma risk."""
        if gamma > 0.025:
            return '🟡 Moderate'  # High gamma, delta very sensitive
        elif gamma > 0.015:
            return '🟢 Low'  # Normal gamma
        else:
            return '🟢 Low'  # Low gamma
    
    def _assess_theta_risk(self, theta_abs: float) -> str:
        """Assess theta decay risk."""
        if theta_abs > 0.40:
            return '🔴 High'  # >$40/day decay per contract
        elif theta_abs > 0.25:
            return '🟡 Moderate'  # $25-40/day
        else:
            return '🟢 Low'  # <$25/day
    
    def _assess_vega_risk(self, vega_abs: float, iv_rank: float) -> str:
        """Assess vega risk based on IV environment."""
        if iv_rank > 70 and vega_abs > 0.15:
            return '🔴 High'  # High IV + high vega = crush risk
        elif iv_rank > 50 and vega_abs > 0.20:
            return '🟡 Moderate'  # Moderate risk
        elif iv_rank < 30 and vega_abs > 0.15:
            return '🟢 Low'  # Low IV + positive vega = opportunity
        else:
            return '🟢 Low'  # Normal
    
    def _calculate_iv_crush_scenario(
        self, current_price: float, vega: float, iv: float, contracts: int
    ) -> Dict:
        """Calculate impact of -10% IV crush."""
        # -10% IV means IV drops by 10% of current level
        # E.g., if IV = 0.60 (60%), -10% = 0.54 (54%)
        iv_drop = iv * 0.10  # 10% of current IV
        iv_drop_percentage_points = iv_drop * 100  # Convert to percentage points
        
        # Impact = vega * IV_change_in_percentage_points
        dollar_impact = vega * iv_drop_percentage_points * contracts * 100
        
        percent_impact = (dollar_impact / (current_price * contracts * 100)) * 100 if current_price > 0 else 0
        
        return {
            'scenario': '-10% IV Crush',
            'iv_before': round(iv * 100, 1),
            'iv_after': round((iv - iv_drop) * 100, 1),
            'iv_drop_pts': round(iv_drop_percentage_points, 1),
            'dollar_impact': round(dollar_impact, 2),
            'percent_impact': round(percent_impact, 1),
            'assessment': self._assess_crush_severity(abs(percent_impact)),
        }
    
    def _assess_crush_severity(self, percent_impact: float) -> str:
        """Assess severity of IV crush."""
        if percent_impact > 25:
            return '🔴 Severe - Position loses >25% on IV alone'
        elif percent_impact > 15:
            return '🟡 Moderate - 15-25% loss possible'
        elif percent_impact > 10:
            return '🟢 Manageable - 10-15% impact'
        else:
            return '🟢 Minimal - <10% impact'
    
    def _assess_overall_risk(
        self, delta_risk: str, gamma_risk: str, theta_risk: str, vega_risk: str
    ) -> str:
        """Assess overall risk level."""
        high_count = sum([
            '🔴' in r for r in [delta_risk, gamma_risk, theta_risk, vega_risk]
        ])
        moderate_count = sum([
            '🟡' in r for r in [delta_risk, gamma_risk, theta_risk, vega_risk]
        ])
        
        if high_count >= 2:
            return '🔴 High Risk'
        elif high_count == 1 or moderate_count >= 2:
            return '🟡 Moderate Risk'
        else:
            return '🟢 Low Risk'
    
    def _generate_mitigations(
        self, delta_exp: Dict, theta_exp: Dict, vega_exp: Dict, iv_rank: float
    ) -> List[str]:
        """Generate mitigation strategies."""
        mitigations = []
        
        # Theta mitigation
        if '🔴' in theta_exp['risk_level'] or '🟡' in theta_exp['risk_level']:
            mitigations.append("Consider longer DTE to reduce theta decay")
        
        # Vega mitigation
        if '🔴' in vega_exp['risk_level']:
            mitigations.append("High IV environment - consider spreads to reduce vega")
            mitigations.append("Avoid holding through earnings if IV crush expected")
        elif iv_rank < 30:
            mitigations.append("Low IV - good environment for buying (cheap protection)")
        
        # Delta mitigation
        if '🔴' in delta_exp['risk_level']:
            mitigations.append("Consider spreads to reduce capital requirement")
        
        if not mitigations:
            mitigations.append("Risk profile acceptable - no immediate mitigations needed")
        
        return mitigations